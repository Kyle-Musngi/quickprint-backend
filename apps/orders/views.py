import json
import mimetypes
import urllib.parse
from decimal import Decimal
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .models import (
    PrintingOrder,
    OrderDocument,
    OrderStatusHistory,
    GlobalPickupSequence,
    ShopDailyQueueSequence,
    ShopQueueEntry,
    get_order_queue_details,
)
from .serializers import (
    PrintingOrderDetailSerializer,
    PrintingOrderListSerializer,
    OrderDocumentSerializer,
)
from .pdf_utils import extract_pdf_page_count
from .document_inspector import validate_and_inspect_document, DocumentInspectionError
from apps.shops.models import PrintingShop, ShopStaffMembership
from apps.printing.pricing_calculator import calculate_document_cost
from apps.notifications.models import Notification


def user_can_access_order(user, order):
    if user.role == 'admin' or user.is_superuser:
        return True
    if order.customer == user:
        return True
    if order.shop.owner == user:
        return True
    if ShopStaffMembership.objects.filter(shop=order.shop, user=user, is_active=True).exists():
        return True
    return False


def user_is_shop_staff(user, shop):
    if user.role == 'admin' or user.is_superuser:
        return True
    if shop.owner == user:
        return True
    return ShopStaffMembership.objects.filter(shop=shop, user=user, is_active=True).exists()


def validate_pickup_slot_availability(shop, pickup_date_val, pickup_time_slot, exclude_order_pk=None):
    if not pickup_date_val:
        return None, None

    if isinstance(pickup_date_val, str):
        try:
            parsed_date = timezone.datetime.strptime(pickup_date_val, '%Y-%m-%d').date()
        except ValueError:
            return "Invalid pickup date format. Expected YYYY-MM-DD.", None
    else:
        parsed_date = pickup_date_val

    now_ph = timezone.localtime()
    today_ph = now_ph.date()
    if parsed_date < today_ph:
        return "Cannot schedule pickup for a past date.", None

    weekday = parsed_date.weekday()
    day_schedule = shop.operating_hours.filter(day_of_week=weekday).first()
    if day_schedule is not None:
        if not day_schedule.is_open:
            return f"{shop.name} is closed on {parsed_date.strftime('%A')}s. Please choose an open day.", None
    else:
        op_days = (shop.operating_days or '').strip().lower()
        if 'temporarily closed' in op_days:
            return f"{shop.name} is currently temporarily closed.", None
        if 'monday - friday' in op_days and weekday in [5, 6]:
            return f"{shop.name} is closed on weekends (Operating schedule: {shop.operating_days}).", None
        if 'monday - saturday' in op_days and weekday == 6:
            return f"{shop.name} is closed on Sundays (Operating schedule: {shop.operating_days}).", None

    if pickup_time_slot:
        capacity = shop.slot_capacity or 5
        qs = PrintingOrder.objects.filter(
            shop=shop,
            pickup_date=parsed_date,
            pickup_time_slot=pickup_time_slot
        ).exclude(status__in=[
            PrintingOrder.STATUS_CANCELLED,
            PrintingOrder.STATUS_REJECTED,
            PrintingOrder.STATUS_EXPIRED
        ])
        if exclude_order_pk:
            qs = qs.exclude(pk=exclude_order_pk)

        active_booked = qs.count()
        if active_booked >= capacity:
            return f"The selected pickup slot ({pickup_time_slot} on {parsed_date}) is at full capacity ({capacity} orders). Please choose another pickup time.", None

    return None, parsed_date


class DetectPagesView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({"error": "No document file was provided."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            inspection = validate_and_inspect_document(uploaded_file, uploaded_file.name)
            return Response(inspection)
        except DocumentInspectionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Failed to inspect document: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class OrderCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        shop_id = request.data.get('shop_id')
        if not shop_id:
            return Response({"error": "shop_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            shop = PrintingShop.objects.get(id=shop_id, status=PrintingShop.STATUS_APPROVED, is_active=True)
        except PrintingShop.DoesNotExist:
            return Response({"error": "Selected printing shop is not available or not approved."}, status=status.HTTP_400_BAD_REQUEST)

        instructions = request.data.get('instructions', '').strip()
        pickup_date = request.data.get('pickup_date') or None
        pickup_time_slot = request.data.get('pickup_time_slot', '').strip()

        if pickup_date or pickup_time_slot:
            slot_err, parsed_pickup_date = validate_pickup_slot_availability(shop, pickup_date, pickup_time_slot)
            if slot_err:
                return Response({"error": slot_err}, status=status.HTTP_400_BAD_REQUEST)
            pickup_date = parsed_pickup_date

        # Parse settings metadata for each uploaded file
        settings_raw = request.data.get('file_settings', '[]')
        try:
            file_settings = json.loads(settings_raw) if isinstance(settings_raw, str) else settings_raw
        except Exception:
            file_settings = []

        files = request.FILES.getlist('files')
        if not files:
            return Response({"error": "At least one document file must be uploaded."}, status=status.HTTP_400_BAD_REQUEST)

        # Pre-validate all files and independently verify page counts and pricing server-side
        validated_items = []
        subtotal = Decimal('0.00')

        for idx, f in enumerate(files):
            setting = file_settings[idx] if idx < len(file_settings) else {}
            paper_size = setting.get('paper_size', 'A4')
            color_mode = setting.get('color_mode', 'bw')
            print_side = setting.get('print_side', 'single')
            orientation = setting.get('orientation', 'portrait')
            page_range = str(setting.get('page_range', 'all') or 'all').strip()
            paper_type = setting.get('paper_type', 'standard')
            try:
                copies = max(1, int(setting.get('copies', 1)))
            except (ValueError, TypeError):
                copies = 1

            # Independent server-side file and page count validation
            try:
                inspection = validate_and_inspect_document(f, f.name)
            except DocumentInspectionError as e:
                return Response(
                    {"error": f"Document '{f.name}' validation failed: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Exception as e:
                return Response(
                    {"error": f"Document '{f.name}' processing error: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            verified_page_count = inspection['page_count']

            # Authoritative server-side price calculation
            cost_calc = calculate_document_cost(shop, paper_size, color_mode, print_side, verified_page_count, copies, page_range=page_range)
            if not cost_calc['success']:
                return Response(
                    {"error": f"Document '{f.name}': {cost_calc['error']}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            doc_total = cost_calc['calculated_total']
            subtotal += doc_total

            validated_items.append({
                'file': f,
                'original_filename': f.name,
                'file_size': f.size,
                'page_count': verified_page_count,
                'effective_pages': cost_calc.get('effective_pages', verified_page_count),
                'page_range': cost_calc.get('page_range', page_range),
                'orientation': orientation,
                'paper_type': paper_type,
                'paper_size': paper_size,
                'color_mode': color_mode,
                'print_side': print_side,
                'copies': copies,
                'unit_price': cost_calc['unit_price'],
                'calculated_total': doc_total
            })

        # Database creation in single atomic transaction after full verification
        with transaction.atomic():
            order = PrintingOrder.objects.create(
                customer=request.user,
                shop=shop,
                instructions=instructions,
                pickup_date=pickup_date,
                pickup_time_slot=pickup_time_slot,
                status=PrintingOrder.STATUS_SUBMITTED,
                payment_status=PrintingOrder.PAYMENT_STATUS_UNPAID,
                subtotal_amount=subtotal,
                service_fee=Decimal('0.00'),
                total_amount=subtotal
            )

            for item in validated_items:
                OrderDocument.objects.create(
                    order=order,
                    file=item['file'],
                    original_filename=item['original_filename'],
                    file_size=item['file_size'],
                    page_count=item['page_count'],
                    effective_pages=item.get('effective_pages', item['page_count']),
                    page_range=item.get('page_range', 'all'),
                    orientation=item.get('orientation', 'portrait'),
                    paper_type=item.get('paper_type', 'standard'),
                    paper_size=item['paper_size'],
                    color_mode=item['color_mode'],
                    print_side=item['print_side'],
                    copies=item['copies'],
                    unit_price=item['unit_price'],
                    calculated_total=item['calculated_total']
                )

            # Assign persistent queue entry for this shop
            ShopQueueEntry.assign_for_order(order)

        # Create history record
        OrderStatusHistory.objects.create(
            order=order,
            status=PrintingOrder.STATUS_SUBMITTED,
            changed_by=request.user,
            notes="Order submitted by customer."
        )

        # Notify shop owner
        Notification.send(
            recipient=shop.owner,
            title=f"New Order #{order.order_number}",
            message=f"{request.user.full_name} submitted a new printing order (₱{order.total_amount:.2f}).",
            notification_type=Notification.TYPE_ORDER_SUBMITTED,
            link=f"/shop/orders/{order.id}"
        )

        # Notify customer
        Notification.send(
            recipient=request.user,
            title="Order Submitted Successfully",
            message=f"Your order #{order.order_number} has been submitted to {shop.name}.",
            notification_type=Notification.TYPE_ORDER_SUBMITTED,
            link=f"/tracking/{order.id}"
        )

        return Response(PrintingOrderDetailSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderListView(generics.ListAPIView):
    serializer_class = PrintingOrderListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role_view = self.request.query_params.get('view')  # 'shop', 'customer', or 'admin'
        status_filter = self.request.query_params.get('status')

        if role_view == 'shop' and (user.role in ['shop_owner', 'shop_staff'] or user.role == 'admin'):
            shop = PrintingShop.objects.filter(owner=user).first()
            if not shop:
                membership = ShopStaffMembership.objects.filter(user=user, is_active=True).first()
                if membership:
                    shop = membership.shop
            if not shop:
                return PrintingOrder.objects.none()
            qs = PrintingOrder.objects.filter(shop=shop)
        elif role_view == 'admin' and (user.role == 'admin' or user.is_superuser):
            qs = PrintingOrder.objects.all()
        else:
            qs = PrintingOrder.objects.filter(customer=user)

        # Apply expiration checks for active awaiting-payment orders
        for o in qs.filter(status__in=[PrintingOrder.STATUS_AWAITING_PAYMENT, 'accepted']):
            o.check_and_apply_expiration()

        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs.prefetch_related('refund_requests', 'documents').order_by('-created_at')


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = PrintingOrderDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = PrintingOrder.objects.all()

    def get_object(self):
        order = super().get_object()
        order.check_and_apply_expiration()
        if not user_can_access_order(self.request.user, order):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have permission to view this order.")
        return order


class OrderCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(PrintingOrder, pk=pk)
        if order.customer != request.user and request.user.role != 'admin':
            return Response({"error": "Unauthorized."}, status=status.HTTP_403_FORBIDDEN)

        if order.status not in [PrintingOrder.STATUS_PENDING_ACCEPTANCE, 'submitted', PrintingOrder.STATUS_AWAITING_PAYMENT, 'accepted']:
            return Response({
                "error": f"Cannot cancel order with status '{order.get_status_display()}'. It may already be in production or completed."
            }, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get('reason', 'Cancelled by customer').strip()
        order.status = PrintingOrder.STATUS_CANCELLED
        order.cancellation_reason = reason
        order.save(update_fields=['status', 'cancellation_reason', 'updated_at'])

        OrderStatusHistory.objects.create(
            order=order,
            status=PrintingOrder.STATUS_CANCELLED,
            changed_by=request.user,
            notes=f"Order cancelled: {reason}"
        )

        Notification.send(
            recipient=order.shop.owner,
            title=f"Order #{order.order_number} Cancelled",
            message=f"Customer cancelled order #{order.order_number}. Reason: {reason}",
            notification_type=Notification.TYPE_ORDER_CANCELLED
        )

        return Response(PrintingOrderDetailSerializer(order).data)


class OrderAcceptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(PrintingOrder, pk=pk)
        if not user_is_shop_staff(request.user, order.shop):
            return Response({"error": "Only shop staff can accept orders."}, status=status.HTTP_403_FORBIDDEN)

        if order.shop.status != PrintingShop.STATUS_APPROVED or not order.shop.is_active:
            return Response({"error": "Cannot accept orders for a shop that is not approved or is currently inactive/suspended."}, status=status.HTTP_400_BAD_REQUEST)

        if order.status in [PrintingOrder.STATUS_CANCELLED, PrintingOrder.STATUS_REJECTED, PrintingOrder.STATUS_EXPIRED]:
            return Response({"error": f"Cannot accept order with status '{order.get_status_display()}'."}, status=status.HTTP_400_BAD_REQUEST)

        if order.status not in [PrintingOrder.STATUS_PENDING_ACCEPTANCE, 'submitted']:
            return Response({"error": f"Order has already been processed (current status: {order.get_status_display()})."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate that pickup slot is still available and shop is open before accepting
        if order.pickup_date and order.pickup_time_slot:
            slot_err, _ = validate_pickup_slot_availability(
                order.shop,
                order.pickup_date,
                order.pickup_time_slot,
                exclude_order_pk=order.pk
            )
            if slot_err:
                return Response({
                    "error": f"Cannot accept order: {slot_err} The customer must reschedule pickup before order acceptance."
                }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if not order.pickup_code:
                order.pickup_code = GlobalPickupSequence.get_next_pickup_code()

            ShopQueueEntry.assign_for_order(order)

            order.status = PrintingOrder.STATUS_AWAITING_PAYMENT
            # Configurable payment deadline (24 hours)
            order.payment_deadline = timezone.now() + timezone.timedelta(hours=24)
            order.save(update_fields=['status', 'pickup_code', 'payment_deadline', 'updated_at'])

            deadline_str = order.payment_deadline.strftime('%b %d, %Y %I:%M %p')
            OrderStatusHistory.objects.create(
                order=order,
                status=PrintingOrder.STATUS_AWAITING_PAYMENT,
                changed_by=request.user,
                notes=f"Order accepted by {request.user.full_name}. Awaiting customer payment (Deadline: {deadline_str})."
            )

        Notification.send(
            recipient=order.customer,
            title=f"Order #{order.order_number} Accepted! Payment Required",
            message=f"Your order was accepted by {order.shop.name}. Final total: ₱{order.total_amount:.2f}. Please complete payment by {deadline_str} to start printing.",
            notification_type=Notification.TYPE_ORDER_ACCEPTED,
            link=f"/payment/{order.id}"
        )

        return Response(PrintingOrderDetailSerializer(order).data)


class OrderRejectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(PrintingOrder, pk=pk)
        if not user_is_shop_staff(request.user, order.shop):
            return Response({"error": "Only shop staff can reject orders."}, status=status.HTTP_403_FORBIDDEN)

        reason = (request.data.get('reason') or request.data.get('rejection_reason') or '').strip()
        if not reason:
            return Response({"error": "Rejection reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        order.status = PrintingOrder.STATUS_REJECTED
        order.rejection_reason = reason
        order.save(update_fields=['status', 'rejection_reason', 'updated_at'])

        OrderStatusHistory.objects.create(
            order=order,
            status=PrintingOrder.STATUS_REJECTED,
            changed_by=request.user,
            notes=f"Order rejected: {reason}"
        )

        Notification.send(
            recipient=order.customer,
            title=f"Order #{order.order_number} Rejected",
            message=f"Your order was rejected by {order.shop.name}. Reason: {reason}. No payment was charged.",
            notification_type=Notification.TYPE_ORDER_REJECTED,
            link=f"/tracking/{order.id}"
        )

        return Response(PrintingOrderDetailSerializer(order).data)


class OrderStartPrintingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(PrintingOrder, pk=pk)
        if not user_is_shop_staff(request.user, order.shop):
            return Response({"error": "Only shop staff can update production status."}, status=status.HTTP_403_FORBIDDEN)

        # Enforce payment confirmation before production
        if order.payment_status != PrintingOrder.PAYMENT_STATUS_PAID:
            return Response({
                "error": "Cannot start production for an unpaid order. Payment must be confirmed before production begins."
            }, status=status.HTTP_400_BAD_REQUEST)

        order.status = PrintingOrder.STATUS_IN_PRODUCTION
        order.save(update_fields=['status', 'updated_at'])

        OrderStatusHistory.objects.create(
            order=order,
            status=PrintingOrder.STATUS_IN_PRODUCTION,
            changed_by=request.user,
            notes="Printing production started."
        )

        Notification.send(
            recipient=order.customer,
            title="Printing in Progress",
            message=f"The shop has started printing your documents for order #{order.order_number}.",
            notification_type=Notification.TYPE_PRINTING_STARTED,
            link=f"/tracking/{order.id}"
        )

        return Response(PrintingOrderDetailSerializer(order).data)


class OrderUpdatePickupSlotView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        order = get_object_or_404(PrintingOrder, pk=pk)
        if order.customer != request.user and request.user.role != 'admin':
            return Response({"error": "Unauthorized."}, status=status.HTTP_403_FORBIDDEN)

        if order.status in [PrintingOrder.STATUS_COMPLETED, PrintingOrder.STATUS_CANCELLED, PrintingOrder.STATUS_REJECTED, PrintingOrder.STATUS_EXPIRED]:
            return Response({"error": f"Cannot update pickup schedule for order with status '{order.get_status_display()}'."}, status=status.HTTP_400_BAD_REQUEST)

        pickup_date = request.data.get('pickup_date')
        pickup_time_slot = request.data.get('pickup_time_slot', '').strip()

        if not pickup_date or not pickup_time_slot:
            return Response({"error": "pickup_date and pickup_time_slot are required."}, status=status.HTTP_400_BAD_REQUEST)

        slot_err, parsed_date = validate_pickup_slot_availability(
            order.shop,
            pickup_date,
            pickup_time_slot,
            exclude_order_pk=order.pk
        )
        if slot_err:
            return Response({"error": slot_err}, status=status.HTTP_400_BAD_REQUEST)

        order.pickup_date = parsed_date
        order.pickup_time_slot = pickup_time_slot
        order.save(update_fields=['pickup_date', 'pickup_time_slot', 'updated_at'])

        OrderStatusHistory.objects.create(
            order=order,
            status=order.status,
            changed_by=request.user,
            notes=f"Pickup schedule updated to {pickup_date} ({pickup_time_slot})."
        )

        return Response(PrintingOrderDetailSerializer(order).data)


class OrderReadyForPickupView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(PrintingOrder, pk=pk)
        if not user_is_shop_staff(request.user, order.shop):
            return Response({"error": "Only shop staff can update production status."}, status=status.HTTP_403_FORBIDDEN)

        order.status = PrintingOrder.STATUS_READY_FOR_PICKUP
        order.save(update_fields=['status', 'updated_at'])

        OrderStatusHistory.objects.create(
            order=order,
            status=PrintingOrder.STATUS_READY_FOR_PICKUP,
            changed_by=request.user,
            notes="Documents printed and packaged. Ready for pickup."
        )

        Notification.send(
            recipient=order.customer,
            title="Ready for Pickup!",
            message=f"Your order #{order.order_number} is ready for pickup! Present your pickup code ({order.pickup_code}) at {order.shop.name}.",
            notification_type=Notification.TYPE_READY_FOR_PICKUP,
            link=f"/tracking/{order.id}"
        )

        return Response(PrintingOrderDetailSerializer(order).data)


class OrderConfirmPickupView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(PrintingOrder, pk=pk)
        if not user_is_shop_staff(request.user, order.shop):
            return Response({"error": "Only shop staff can confirm order pickup."}, status=status.HTTP_403_FORBIDDEN)

        if order.status == PrintingOrder.STATUS_COMPLETED:
            return Response({"error": "Order is already marked completed."}, status=status.HTTP_400_BAD_REQUEST)

        code_provided = request.data.get('pickup_code', '').strip().upper()
        if code_provided and order.pickup_code and code_provided != order.pickup_code.upper():
            return Response({"error": "Pickup code does not match this order."}, status=status.HTTP_400_BAD_REQUEST)

        order.status = PrintingOrder.STATUS_COMPLETED
        order.pickup_confirmed_at = timezone.now()
        order.pickup_confirmed_by = request.user
        order.save(update_fields=['status', 'pickup_confirmed_at', 'pickup_confirmed_by', 'updated_at'])

        OrderStatusHistory.objects.create(
            order=order,
            status=PrintingOrder.STATUS_COMPLETED,
            changed_by=request.user,
            notes=f"Pickup verified and completed by {request.user.full_name}."
        )

        Notification.send(
            recipient=order.customer,
            title="Order Completed",
            message=f"Your pickup for order #{order.order_number} has been confirmed. Thank you for using Univ Quick Print!",
            notification_type=Notification.TYPE_PICKUP_CONFIRMED,
            link=f"/tracking/{order.id}"
        )

        return Response(PrintingOrderDetailSerializer(order).data)


class OrderDocumentDownloadView(APIView):
    """
    Authenticated and authorized document viewing and download endpoint.
    Supports JWT authorization header or ?token=<jwt> parameter for direct browser preview.
    Prevents cross-shop and unauthorized customer document access.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, order_id, doc_id):
        # 1. Resolve user: check header auth first, then fallback to ?token= query parameter
        user = request.user
        if not user or not user.is_authenticated:
            token = request.query_params.get('token')
            if token:
                try:
                    jwt_auth = JWTAuthentication()
                    validated_token = jwt_auth.get_validated_token(token)
                    user = jwt_auth.get_user(validated_token)
                except (InvalidToken, TokenError):
                    return Response({"error": "Invalid or expired authorization token."}, status=status.HTTP_401_UNAUTHORIZED)

        if not user or not user.is_authenticated:
            return Response({"error": "Authentication required to access documents."}, status=status.HTTP_401_UNAUTHORIZED)

        # 2. Check order existence and access permissions
        order = get_object_or_404(PrintingOrder, pk=order_id)
        if not user_can_access_order(user, order):
            return Response({"error": "You do not have permission to access documents from this order."}, status=status.HTTP_403_FORBIDDEN)

        # 3. Check document belongs to this specific order
        try:
            document = order.documents.get(pk=doc_id)
        except OrderDocument.DoesNotExist:
            return Response({"error": "Document not found for this order."}, status=status.HTTP_404_NOT_FOUND)

        # 4. Check if file is stored and exists
        if not document.file or not document.file.name:
            return Response({"error": f"The document file '{document.original_filename}' is not stored on the server."}, status=status.HTTP_404_NOT_FOUND)

        try:
            if not document.file.storage.exists(document.file.name):
                return Response({"error": f"The document file '{document.original_filename}' could not be located in storage."}, status=status.HTTP_404_NOT_FOUND)
            file_handle = document.file.open('rb')
        except Exception as e:
            return Response({"error": f"Failed to retrieve file from storage: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 5. Content-Type and Disposition
        disposition = request.query_params.get('disposition', 'inline').lower()
        if disposition not in ['inline', 'attachment']:
            disposition = 'inline'

        content_type, _ = mimetypes.guess_type(document.original_filename)
        if not content_type:
            content_type = 'application/octet-stream'

        response = FileResponse(file_handle, content_type=content_type)
        safe_filename = document.original_filename.replace('"', '').replace('\n', '').replace('\r', '')
        encoded_filename = urllib.parse.quote(safe_filename)
        response['Content-Disposition'] = f'{disposition}; filename="{safe_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition, Content-Type, Content-Length'
        return response


class OrderQueueStatusView(APIView):
    """
    Returns real-time queue position, tickets ahead, and estimated wait for an order.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        order = get_object_or_404(PrintingOrder, pk=pk)
        if not user_can_access_order(request.user, order):
            return Response({"error": "Unauthorized access to order queue."}, status=status.HTTP_403_FORBIDDEN)
        return Response(get_order_queue_details(order))


