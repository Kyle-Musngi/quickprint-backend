from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q, Min, Avg, Count, F
from datetime import datetime, time, timedelta
from django.utils import timezone
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.http import FileResponse
import mimetypes
from .models import PrintingShop, ShopStaffMembership, ShopOperatingHours, ShopReview, ShopApplicationAuditLog
from .serializers import (
    PrintingShopListSerializer,
    PrintingShopDetailSerializer,
    ShopRegistrationSerializer,
    ShopOperatingHoursSerializer,
    ShopReviewSerializer,
    ShopApplicationAuditLogSerializer
)
from apps.accounts.permissions import IsPlatformAdmin, IsShopOwner
from apps.notifications.models import Notification


class ShopListView(generics.ListAPIView):
    serializer_class = PrintingShopListSerializer
    permission_classes = [permissions.AllowAny]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        try:
            user_lat = self.request.query_params.get('lat')
            user_lng = self.request.query_params.get('lng')
            if user_lat is not None and user_lng is not None:
                context['user_lat'] = float(user_lat)
                context['user_lng'] = float(user_lng)
        except (ValueError, TypeError):
            pass
        return context

    def get_queryset(self):
        queryset = PrintingShop.objects.filter(
            status=PrintingShop.STATUS_APPROVED,
            is_active=True
        ).prefetch_related('pricing_rules', 'services', 'operating_hours')
        search = self.request.query_params.get('search', '').strip()
        city = self.request.query_params.get('city', '').strip()
        sort = self.request.query_params.get('sort', '').strip()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(address__icontains=search) |
                Q(barangay__icontains=search) |
                Q(city__icontains=search) |
                Q(description__icontains=search)
            )

        if city and city.lower() != 'all':
            queryset = queryset.filter(city__iexact=city)

        if sort == 'name':
            queryset = queryset.order_by('name')
        elif sort == 'price':
            queryset = queryset.annotate(
                min_price=Min('pricing_rules__price_per_page')
            ).order_by('min_price')
        elif sort == 'rating':
            queryset = queryset.annotate(
                avg_rate=Avg('reviews__rating', filter=Q(reviews__is_moderated=False)),
                rev_count=Count('reviews', filter=Q(reviews__is_moderated=False))
            ).order_by(F('avg_rate').desc(nulls_last=True), F('rev_count').desc())
        else:
            queryset = queryset.order_by('-created_at')

        # If sorting by distance and coordinates provided:
        user_lat = self.request.query_params.get('lat')
        user_lng = self.request.query_params.get('lng')
        if sort == 'distance' and user_lat and user_lng:
            try:
                u_lat = float(user_lat)
                u_lng = float(user_lng)
                shops = list(queryset)
                shops.sort(key=lambda s: s.distance_from(u_lat, u_lng) if s.distance_from(u_lat, u_lng) is not None else 999999)
                return shops
            except ValueError:
                pass

        return queryset


class ShopDetailView(generics.RetrieveAPIView):
    serializer_class = PrintingShopDetailSerializer
    permission_classes = [permissions.AllowAny]
    queryset = PrintingShop.objects.all()

    def get_object(self):
        shop = super().get_object()
        # Non-staff/admins can only view approved active shops
        user = self.request.user
        if shop.status != PrintingShop.STATUS_APPROVED or not shop.is_active:
            if not user.is_authenticated or (user != shop.owner and user.role != 'admin' and not user.is_superuser):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("This printing shop is currently not active or awaiting approval.")
        return shop


class ShopRegisterView(generics.CreateAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = ShopRegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        # Any authenticated user (including Customer) can apply to become a Shop Owner.
        # Submitting an application keeps the user as a CUSTOMER until administrator approval.
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        shop = serializer.save()

        # Notify admins
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admins = User.objects.filter(Q(role='admin') | Q(is_superuser=True))
        for admin in admins:
            Notification.send(
                recipient=admin,
                title="New Shop Registration Awaiting Approval",
                message=f"'{shop.name}' was submitted by {request.user.full_name} and is awaiting review.",
                notification_type=Notification.TYPE_GENERAL,
                link="/admin/approvals"
            )

        return Response({
            "message": "Your printing shop application has been submitted and is awaiting administrator approval.",
            "shop": PrintingShopDetailSerializer(shop).data
        }, status=status.HTTP_201_CREATED)


class MyShopView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        shop = PrintingShop.objects.filter(owner=user).first()
        if not shop:
            membership = ShopStaffMembership.objects.filter(user=user, is_active=True).first()
            if membership:
                shop = membership.shop
        if not shop:
            return Response({"detail": "No registered shop found for this account."}, status=status.HTTP_404_NOT_FOUND)
        return Response(PrintingShopDetailSerializer(shop).data)

    def patch(self, request):
        user = request.user
        shop = PrintingShop.objects.filter(owner=user).first()
        if not shop:
            return Response({"detail": "Only shop owners can edit shop settings."}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = PrintingShopDetailSerializer(shop, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ShopOperatingHoursView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_shop(self, user):
        shop = PrintingShop.objects.filter(owner=user).first()
        if not shop:
            membership = ShopStaffMembership.objects.filter(user=user, is_active=True).first()
            if membership:
                shop = membership.shop
        return shop

    def get(self, request):
        shop = self.get_shop(request.user)
        if not shop:
            return Response({"detail": "No registered shop found for this account."}, status=status.HTTP_404_NOT_FOUND)

        # Ensure all 7 days exist
        existing = {h.day_of_week: h for h in shop.operating_hours.all()}
        for day_num in range(7):
            if day_num not in existing:
                is_open = day_num < 6  # Mon-Sat open by default
                ShopOperatingHours.objects.create(
                    shop=shop,
                    day_of_week=day_num,
                    is_open=is_open,
                    opening_time=shop.opening_time,
                    closing_time=shop.closing_time
                )
        
        hours = shop.operating_hours.all().order_by('day_of_week')
        serializer = ShopOperatingHoursSerializer(hours, many=True)
        return Response(serializer.data)

    def put(self, request):
        shop = self.get_shop(request.user)
        if not shop or shop.owner != request.user:
            return Response({"detail": "Only the shop owner can configure operating hours."}, status=status.HTTP_403_FORBIDDEN)

        schedules_data = request.data
        if not isinstance(schedules_data, list):
            return Response({"error": "Expected a list of day schedules."}, status=status.HTTP_400_BAD_REQUEST)

        day_names = dict(ShopOperatingHours.DAY_CHOICES)
        open_days = []

        with transaction.atomic():
            for item in schedules_data:
                day_num = item.get('day_of_week')
                if day_num not in day_names:
                    return Response({"error": f"Invalid day_of_week: {day_num}"}, status=status.HTTP_400_BAD_REQUEST)
                
                is_open = bool(item.get('is_open', False))
                opening_time_str = item.get('opening_time')
                closing_time_str = item.get('closing_time')

                if is_open:
                    if not opening_time_str or not closing_time_str:
                        return Response({
                            "error": f"Opening and closing times are required for {day_names[day_num]} when marked open."
                        }, status=status.HTTP_400_BAD_REQUEST)
                    if opening_time_str == closing_time_str:
                        return Response({
                            "error": f"Opening and closing times cannot be identical for {day_names[day_num]}."
                        }, status=status.HTTP_400_BAD_REQUEST)

                    open_days.append(day_names[day_num])

                ShopOperatingHours.objects.update_or_create(
                    shop=shop,
                    day_of_week=day_num,
                    defaults={
                        'is_open': is_open,
                        'opening_time': opening_time_str or shop.opening_time,
                        'closing_time': closing_time_str or shop.closing_time,
                    }
                )

            # Update shop.operating_days summary string
            if open_days:
                if len(open_days) == 7:
                    summary_str = "Monday - Sunday"
                elif open_days == ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']:
                    summary_str = "Monday - Saturday"
                elif open_days == ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
                    summary_str = "Monday - Friday"
                else:
                    summary_str = ", ".join(open_days)
            else:
                summary_str = "Temporarily Closed"

            shop.operating_days = summary_str
            shop.save(update_fields=['operating_days', 'updated_at'])

        hours = shop.operating_hours.all().order_by('day_of_week')
        return Response(ShopOperatingHoursSerializer(hours, many=True).data)


class ShopPickupSlotsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        shop = generics.get_object_or_404(PrintingShop, pk=pk)
        date_str = request.query_params.get('date')
        
        # Consistent shop timezone in Cebu, Philippines
        now_dt = timezone.localtime()
        today = now_dt.date()

        if not date_str:
            date_str = today.strftime('%Y-%m-%d')
        
        try:
            pickup_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if requested date is in the past
        if pickup_date < today:
            return Response({"error": "Cannot schedule pickups for past dates."}, status=status.HTTP_400_BAD_REQUEST)

        # Check day-specific operating hours
        weekday_num = pickup_date.weekday()
        day_schedule = shop.operating_hours.filter(day_of_week=weekday_num).first()
        
        if day_schedule is not None:
            if not day_schedule.is_open:
                return Response({
                    "shop_id": shop.id,
                    "shop_name": shop.name,
                    "date": str(pickup_date),
                    "slots": [],
                    "message": f"{shop.name} is closed on {pickup_date.strftime('%A')}s."
                })
            open_time = day_schedule.opening_time
            close_time = day_schedule.closing_time
        else:
            # Fallback to shop operating_days text inspection
            op_days = (shop.operating_days or '').strip().lower()
            if 'temporarily closed' in op_days:
                return Response({
                    "shop_id": shop.id,
                    "shop_name": shop.name,
                    "date": str(pickup_date),
                    "slots": [],
                    "message": f"{shop.name} is currently temporarily closed."
                })
            if 'monday - friday' in op_days and weekday_num in [5, 6]:
                return Response({
                    "shop_id": shop.id,
                    "shop_name": shop.name,
                    "date": str(pickup_date),
                    "slots": [],
                    "message": f"{shop.name} is closed on {pickup_date.strftime('%A')}s (Operating days: {shop.operating_days})."
                })
            if 'monday - saturday' in op_days and weekday_num == 6:
                return Response({
                    "shop_id": shop.id,
                    "shop_name": shop.name,
                    "date": str(pickup_date),
                    "slots": [],
                    "message": f"{shop.name} is closed on Sundays (Operating days: {shop.operating_days})."
                })
            open_time = shop.opening_time
            close_time = shop.closing_time

        # Generate time slots between open_time and close_time
        slots = []
        interval = timedelta(minutes=shop.pickup_slot_interval_minutes or 30)
        
        open_dt = datetime.combine(pickup_date, open_time)
        close_dt = datetime.combine(pickup_date, close_time)
        
        current_dt = open_dt
        now_time = now_dt.time()

        from apps.orders.models import PrintingOrder

        while current_dt + interval <= close_dt:
            slot_end = current_dt + interval
            slot_label = f"{current_dt.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
            
            # Check if slot is already in the past for today
            is_past = (pickup_date == today and slot_end.time() <= now_time)
            
            # Count booked orders for this slot on this date (excluding cancelled, rejected, expired)
            booked_count = PrintingOrder.objects.filter(
                shop=shop,
                pickup_date=pickup_date,
                pickup_time_slot=slot_label
            ).exclude(status__in=[
                PrintingOrder.STATUS_CANCELLED,
                PrintingOrder.STATUS_REJECTED,
                PrintingOrder.STATUS_EXPIRED,
            ]).count()

            capacity = shop.slot_capacity or 5
            is_available = (not is_past) and (booked_count < capacity)

            slots.append({
                "time_slot": slot_label,
                "is_available": is_available,
                "booked_count": booked_count,
                "capacity": capacity,
                "is_past": is_past
            })
            current_dt = slot_end

        return Response({
            "shop_id": shop.id,
            "shop_name": shop.name,
            "date": str(pickup_date),
            "slots": slots
        })


# --- Admin Shop Management ---
class AdminShopListView(generics.ListAPIView):
    serializer_class = PrintingShopDetailSerializer
    permission_classes = [IsPlatformAdmin]

    def get_queryset(self):
        status_filter = self.request.query_params.get('status')
        if status_filter:
            return PrintingShop.objects.filter(status=status_filter).order_by('-created_at')
        return PrintingShop.objects.all().order_by('-created_at')


class AdminShopApprovalActionView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        shop = generics.get_object_or_404(PrintingShop, pk=pk)
        action = request.data.get('action')  # approve, reject, more_info, under_review, suspend, reactivate
        reason = request.data.get('reason', '').strip()
        old_status = shop.status

        if action == 'approve':
            with transaction.atomic():
                # 1. Update shop status to approved & active
                shop.status = PrintingShop.STATUS_APPROVED
                shop.rejection_reason = ''
                shop.is_active = True
                shop.save(update_fields=['status', 'rejection_reason', 'is_active', 'updated_at'])

                # 2. Promote the customer account to SHOP_OWNER
                owner = shop.owner
                if owner.role != 'admin' and not owner.is_superuser:
                    owner.role = 'shop_owner'
                    owner.save(update_fields=['role', 'updated_at'])

                # 3. Create audit trail
                ShopApplicationAuditLog.objects.create(
                    shop=shop,
                    actor=request.user,
                    action='approve',
                    from_status=old_status,
                    to_status=PrintingShop.STATUS_APPROVED,
                    notes=f"Approved by Administrator {request.user.full_name}. Customer account elevated to Shop Owner."
                )

            # Notify owner
            Notification.send(
                recipient=shop.owner,
                title="Your Shop Has Been Approved! 🎉",
                message=f"Congratulations! '{shop.name}' is now approved and active on Univ Quick Print. Your account is now a verified Shop Owner.",
                notification_type=Notification.TYPE_GENERAL,
                link="/shop/dashboard"
            )
            return Response({
                "message": f"Shop '{shop.name}' has been approved. Owner {shop.owner.username} is now a Shop Owner.",
                "status": "approved",
                "owner_role": shop.owner.role
            })

        elif action == 'reject':
            if not reason:
                return Response({"error": "Rejection reason is required."}, status=status.HTTP_400_BAD_REQUEST)
            
            with transaction.atomic():
                shop.status = PrintingShop.STATUS_REJECTED
                shop.is_active = False
                shop.rejection_reason = reason
                shop.save(update_fields=['status', 'rejection_reason', 'is_active', 'updated_at'])

                ShopApplicationAuditLog.objects.create(
                    shop=shop,
                    actor=request.user,
                    action='reject',
                    from_status=old_status,
                    to_status=PrintingShop.STATUS_REJECTED,
                    notes=f"Application rejected by Admin {request.user.full_name}. Reason: {reason}"
                )

            # Notify owner
            Notification.send(
                recipient=shop.owner,
                title="Shop Application Update",
                message=f"Your application for '{shop.name}' was not approved: {reason}",
                notification_type=Notification.TYPE_GENERAL,
                link="/shop-registration"
            )
            return Response({"message": f"Shop '{shop.name}' was rejected.", "status": "rejected"})

        elif action in ['more_info', 'request_more_info']:
            if not reason:
                return Response({"error": "Please provide details on what additional information is required."}, status=status.HTTP_400_BAD_REQUEST)
            
            with transaction.atomic():
                shop.status = PrintingShop.STATUS_MORE_INFO
                shop.rejection_reason = reason
                shop.save(update_fields=['status', 'rejection_reason', 'updated_at'])

                ShopApplicationAuditLog.objects.create(
                    shop=shop,
                    actor=request.user,
                    action='more_info',
                    from_status=old_status,
                    to_status=PrintingShop.STATUS_MORE_INFO,
                    notes=f"Additional information requested by Admin {request.user.full_name}: {reason}"
                )

            Notification.send(
                recipient=shop.owner,
                title="More Information Needed for Shop Application",
                message=f"Administrator requires more details for '{shop.name}': {reason}",
                notification_type=Notification.TYPE_GENERAL,
                link="/shop-registration"
            )
            return Response({"message": "Requested more information from applicant.", "status": "more_information_required"})

        elif action in ['under_review']:
            with transaction.atomic():
                shop.status = PrintingShop.STATUS_UNDER_REVIEW
                shop.save(update_fields=['status', 'updated_at'])

                ShopApplicationAuditLog.objects.create(
                    shop=shop,
                    actor=request.user,
                    action='under_review',
                    from_status=old_status,
                    to_status=PrintingShop.STATUS_UNDER_REVIEW,
                    notes=f"Application placed under review by Admin {request.user.full_name}."
                )
            return Response({"message": f"Shop '{shop.name}' is now under review.", "status": "under_review"})

        elif action == 'suspend':
            with transaction.atomic():
                if reason:
                    shop.rejection_reason = reason
                shop.status = PrintingShop.STATUS_SUSPENDED
                shop.is_active = False
                shop.save(update_fields=['status', 'rejection_reason', 'is_active', 'updated_at'])

                ShopApplicationAuditLog.objects.create(
                    shop=shop,
                    actor=request.user,
                    action='suspend',
                    from_status=old_status,
                    to_status=PrintingShop.STATUS_SUSPENDED,
                    notes=f"Shop suspended by Admin {request.user.full_name}. Reason: {reason or 'Administrative review'}"
                )

            suspension_msg = f"Shop '{shop.name}' has been temporarily suspended by an administrator."
            if reason:
                suspension_msg += f" Reason: {reason}"
            Notification.send(
                recipient=shop.owner,
                title="Shop Suspended",
                message=suspension_msg,
                notification_type=Notification.TYPE_GENERAL
            )
            return Response({"message": f"Shop '{shop.name}' has been suspended.", "status": "suspended"})

        elif action == 'reactivate':
            with transaction.atomic():
                shop.status = PrintingShop.STATUS_APPROVED
                shop.is_active = True
                shop.rejection_reason = ''
                shop.save(update_fields=['status', 'rejection_reason', 'is_active', 'updated_at'])

                owner = shop.owner
                if owner.role != 'admin' and not owner.is_superuser:
                    owner.role = 'shop_owner'
                    owner.save(update_fields=['role', 'updated_at'])

                ShopApplicationAuditLog.objects.create(
                    shop=shop,
                    actor=request.user,
                    action='reactivate',
                    from_status=old_status,
                    to_status=PrintingShop.STATUS_APPROVED,
                    notes=f"Shop reactivated by Admin {request.user.full_name}."
                )

            Notification.send(
                recipient=shop.owner,
                title="Shop Reactivated",
                message=f"Shop '{shop.name}' has been reactivated by an administrator and is now active.",
                notification_type=Notification.TYPE_GENERAL,
                link="/shop/dashboard"
            )
            return Response({"message": f"Shop '{shop.name}' has been reactivated.", "status": "approved"})

        return Response({"error": "Invalid action. Use approve, reject, more_info, under_review, suspend, or reactivate."}, status=status.HTTP_400_BAD_REQUEST)


class ShopVerificationDocumentDownloadView(APIView):
    """
    Secure endpoint allowing administrators and the shop applicant to view or download
    private verification documents (government_id, business_permit, proof_of_ownership).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, doc_type):
        shop = generics.get_object_or_404(PrintingShop, pk=pk)
        user = request.user

        # Access check: Only platform admin or the applicant themselves
        if user != shop.owner and user.role != 'admin' and not user.is_superuser:
            return Response({"error": "You do not have permission to view verification documents for this shop."}, status=status.HTTP_403_FORBIDDEN)

        if doc_type not in ['government_id', 'business_permit', 'proof_of_ownership']:
            return Response({"error": "Invalid document type requested."}, status=status.HTTP_400_BAD_REQUEST)

        file_field = getattr(shop, doc_type, None)
        if not file_field or not file_field.name:
            return Response({"error": f"No {doc_type.replace('_', ' ')} has been uploaded for this shop."}, status=status.HTTP_404_NOT_FOUND)

        try:
            if not file_field.storage.exists(file_field.name):
                return Response({"error": f"The verification file '{file_field.name}' could not be located in server storage."}, status=status.HTTP_404_NOT_FOUND)
            handle = file_field.open('rb')
        except Exception as e:
            return Response({"error": f"Failed to retrieve verification file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        content_type, _ = mimetypes.guess_type(file_field.name)
        if not content_type:
            content_type = 'application/octet-stream'

        response = FileResponse(handle, content_type=content_type)
        filename = file_field.name.split('/')[-1]
        disposition = request.query_params.get('disposition', 'inline').lower()
        if disposition not in ['inline', 'attachment']:
            disposition = 'inline'

        response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition, Content-Type'
        return response


class ShopReviewListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get(self, request, pk):
        shop = generics.get_object_or_404(PrintingShop, pk=pk)
        sort = request.query_params.get('sort', 'newest')
        reviews = ShopReview.objects.filter(shop=shop, is_moderated=False)
        if sort == 'highest':
            reviews = reviews.order_by('-rating', '-created_at')
        elif sort == 'lowest':
            reviews = reviews.order_by('rating', '-created_at')
        else:
            reviews = reviews.order_by('-created_at')

        return Response({
            "shop_id": shop.id,
            "shop_name": shop.name,
            "average_rating": shop.average_rating,
            "review_count": shop.review_count,
            "reviews": ShopReviewSerializer(reviews, many=True).data
        })

    def post(self, request, pk):
        shop = generics.get_object_or_404(PrintingShop, pk=pk)
        order_id = request.data.get('order_id')
        if not order_id:
            return Response({"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        from apps.orders.models import PrintingOrder
        try:
            order = PrintingOrder.objects.get(pk=order_id)
        except PrintingOrder.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        if order.customer != request.user and request.user.role != 'admin':
            return Response({"error": "You can only review your own orders."}, status=status.HTTP_403_FORBIDDEN)

        if order.shop != shop:
            return Response({"error": "This order does not belong to the specified printing shop."}, status=status.HTTP_400_BAD_REQUEST)

        if order.status != PrintingOrder.STATUS_COMPLETED:
            return Response({
                "error": f"Reviews are only permitted for completed orders. Current order status: '{order.get_status_display()}'."
            }, status=status.HTTP_400_BAD_REQUEST)

        if hasattr(order, 'review') and order.review is not None:
            return Response({"error": "You have already reviewed this order."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rating = int(request.data.get('rating'))
            if not (1 <= rating <= 5):
                raise ValueError()
        except (ValueError, TypeError):
            return Response({"error": "Rating must be an integer between 1 and 5 stars."}, status=status.HTTP_400_BAD_REQUEST)

        review_text = request.data.get('review_text', '').strip()

        review = ShopReview.objects.create(
            shop=shop,
            customer=request.user,
            order=order,
            rating=rating,
            review_text=review_text
        )

        Notification.send(
            recipient=shop.owner,
            title=f"New {rating}★ Customer Review",
            message=f"{request.user.full_name} left a {rating}-star review for Order #{order.order_number}.",
            notification_type=Notification.TYPE_GENERAL,
            link="/shop/dashboard?tab=reviews"
        )

        return Response(ShopReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class MyShopReviewsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_shop(self, user):
        shop = PrintingShop.objects.filter(owner=user).first()
        if not shop:
            membership = ShopStaffMembership.objects.filter(user=user, is_active=True).first()
            if membership:
                shop = membership.shop
        return shop

    def get(self, request):
        shop = self.get_shop(request.user)
        if not shop and request.user.role != 'admin':
            return Response({"error": "No registered shop found for this account."}, status=status.HTTP_404_NOT_FOUND)

        sort = request.query_params.get('sort', 'newest')
        reviews = ShopReview.objects.filter(shop=shop)
        if sort == 'highest':
            reviews = reviews.order_by('-rating', '-created_at')
        elif sort == 'lowest':
            reviews = reviews.order_by('rating', '-created_at')
        else:
            reviews = reviews.order_by('-created_at')

        return Response({
            "shop_name": shop.name,
            "average_rating": shop.average_rating,
            "review_count": shop.review_count,
            "reviews": ShopReviewSerializer(reviews, many=True).data
        })


class AdminReviewModerationView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def post(self, request, review_id):
        review = generics.get_object_or_404(ShopReview, pk=review_id)
        action = request.data.get('action')  # 'hide' or 'restore'
        reason = request.data.get('reason', '').strip()

        if action not in ['hide', 'restore']:
            return Response({"error": "Invalid action. Use 'hide' or 'restore'."}, status=status.HTTP_400_BAD_REQUEST)

        if action == 'hide':
            if not reason:
                return Response({"error": "A moderation reason is required when hiding a review."}, status=status.HTTP_400_BAD_REQUEST)
            review.is_moderated = True
            review.moderation_reason = reason
            review.moderated_by = request.user
            from django.utils import timezone
            review.moderated_at = timezone.now()
            review.save(update_fields=['is_moderated', 'moderation_reason', 'moderated_by', 'moderated_at', 'updated_at'])
            return Response({"message": "Review hidden by administrator moderation.", "review": ShopReviewSerializer(review).data})
        else:
            review.is_moderated = False
            review.moderation_reason = f"Restored by admin: {reason}" if reason else "Restored by admin."
            review.save(update_fields=['is_moderated', 'moderation_reason', 'updated_at'])
            return Response({"message": "Review restored to public visibility.", "review": ShopReviewSerializer(review).data})

