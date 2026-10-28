from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction

from decimal import Decimal
from django.utils import timezone
from .models import PaymentTransaction, RefundRequest, RefundAuditLog
from .serializers import (
    PaymentTransactionSerializer,
    RefundRequestSerializer,
    CreateRefundRequestSerializer,
    RefundAuditLogSerializer
)
from apps.orders.models import PrintingOrder, OrderStatusHistory
from apps.notifications.models import Notification


class ProcessSandboxPaymentView(APIView):
    """
    Simulates GCash / Maya / GoTyme sandbox payments with selectable simulation outcomes:
    'success', 'pending', or 'failed'.
    """
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        order_id = request.data.get('order_id')
        payment_method = request.data.get('payment_method', 'gcash').lower()
        simulated_outcome = request.data.get('simulated_outcome', 'success').lower()

        if payment_method not in ['gcash', 'maya', 'gotyme']:
            return Response({"error": "Invalid payment method. Choose GCash, Maya, or GoTyme."}, status=status.HTTP_400_BAD_REQUEST)

        order = get_object_or_404(PrintingOrder, pk=order_id)
        if order.customer != request.user and request.user.role != 'admin':
            return Response({"error": "Unauthorized."}, status=status.HTTP_403_FORBIDDEN)

        # 1. Enforce order acceptance before payment
        if order.status in [PrintingOrder.STATUS_PENDING_ACCEPTANCE, 'submitted']:
            return Response({
                "error": "This order is pending shop review and acceptance. Payment can only be made after the printing shop accepts your order."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Check rejected or cancelled orders
        if order.status in [PrintingOrder.STATUS_REJECTED, PrintingOrder.STATUS_CANCELLED]:
            return Response({
                "error": f"Cannot pay for an order with status '{order.get_status_display()}'."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 3. Check payment deadline expiration
        if order.check_and_apply_expiration() or order.status == PrintingOrder.STATUS_EXPIRED:
            return Response({
                "error": "The payment deadline for this order has expired. Order has been cancelled."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 4. Prevent duplicate payments
        if order.payment_status == PrintingOrder.PAYMENT_STATUS_PAID or PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.STATUS_SUCCESS).exists():
            return Response({"error": "This order is already paid."}, status=status.HTTP_400_BAD_REQUEST)

        # Determine transaction status based on simulation outcome
        if simulated_outcome == 'pending':
            txn_status = PaymentTransaction.STATUS_PENDING
            order_pay_status = PrintingOrder.PAYMENT_STATUS_PENDING
            notes = f"Simulated pending sandbox payment via {payment_method.upper()}."
            fail_reason = ""
        elif simulated_outcome in ['failed', 'failure']:
            txn_status = PaymentTransaction.STATUS_FAILED
            order_pay_status = PrintingOrder.PAYMENT_STATUS_FAILED
            notes = f"Simulated payment failure via {payment_method.upper()}."
            fail_reason = request.data.get('failure_reason', 'Insufficient sandbox balance or simulation failure.')
        else:
            txn_status = PaymentTransaction.STATUS_SUCCESS
            order_pay_status = PrintingOrder.PAYMENT_STATUS_PAID
            notes = f"Simulated sandbox payment processed successfully via {payment_method.upper()}."
            fail_reason = ""

        # Create backend transaction record
        payment = PaymentTransaction.objects.create(
            order=order,
            user=request.user,
            payment_method=payment_method,
            amount=order.total_amount,
            status=txn_status,
            simulated_mode=True,
            failure_reason=fail_reason,
            notes=notes
        )

        # Update order payment status and move to IN_PRODUCTION if payment succeeded
        order.payment_status = order_pay_status
        from apps.orders.models import OrderStatusHistory
        if txn_status == PaymentTransaction.STATUS_SUCCESS:
            order.status = PrintingOrder.STATUS_IN_PRODUCTION
            order.save(update_fields=['payment_status', 'status', 'updated_at'])
            OrderStatusHistory.objects.create(
                order=order,
                status=PrintingOrder.STATUS_IN_PRODUCTION,
                changed_by=request.user,
                notes=f"Payment verified via {payment_method.upper()} (Ref: {payment.transaction_reference}). Production started."
            )
        else:
            order.save(update_fields=['payment_status', 'updated_at'])
            OrderStatusHistory.objects.create(
                order=order,
                status=order.status,
                changed_by=request.user,
                notes=f"Payment attempt {txn_status} via {payment_method.upper()}."
            )

        # Send notifications
        if txn_status == PaymentTransaction.STATUS_SUCCESS:
            Notification.send(
                recipient=request.user,
                title="Payment Successful (Sandbox)",
                message=f"Sandbox payment of ₱{order.total_amount:.2f} for Order #{order.order_number} was successful (Ref: {payment.transaction_reference}).",
                notification_type=Notification.TYPE_PAYMENT_STATUS,
                link=f"/tracking/{order.id}"
            )
            Notification.send(
                recipient=order.shop.owner,
                title=f"Payment Received for Order #{order.order_number}",
                message=f"Order #{order.order_number} has been marked paid via {payment_method.upper()} (Sandbox Ref: {payment.transaction_reference}).",
                notification_type=Notification.TYPE_PAYMENT_STATUS,
                link=f"/shop/orders/{order.id}"
            )
        elif txn_status == PaymentTransaction.STATUS_FAILED:
            Notification.send(
                recipient=request.user,
                title="Payment Failed (Sandbox)",
                message=f"Payment attempt for Order #{order.order_number} failed: {fail_reason}. You can retry anytime.",
                notification_type=Notification.TYPE_PAYMENT_STATUS,
                link=f"/payment/{order.id}"
            )

        return Response({
            "message": f"Sandbox payment transaction completed with status: {txn_status}.",
            "transaction": PaymentTransactionSerializer(payment).data,
            "order_id": order.id,
            "order_number": order.order_number,
            "order_status": order.status,
            "payment_status": order.payment_status
        }, status=status.HTTP_201_CREATED)


class PaymentTransactionListView(generics.ListAPIView):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role_view = self.request.query_params.get('view')

        if role_view == 'shop' and (user.role in ['shop_owner', 'shop_staff'] or user.role == 'admin'):
            from apps.shops.models import PrintingShop
            shop = PrintingShop.objects.filter(owner=user).first()
            if shop:
                return PaymentTransaction.objects.filter(order__shop=shop).order_by('-created_at')
            return PaymentTransaction.objects.none()
        elif role_view == 'admin' and (user.role == 'admin' or user.is_superuser):
            return PaymentTransaction.objects.all().order_by('-created_at')
        
        # Customer view
        return PaymentTransaction.objects.filter(user=user).order_by('-created_at')


class PaymentTransactionDetailView(generics.RetrieveAPIView):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = PaymentTransaction.objects.all()

    def get_object(self):
        txn = super().get_object()
        user = self.request.user
        if txn.user != user and txn.order.shop.owner != user and user.role != 'admin' and not user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have access to this payment transaction.")
        return txn


# --- Refund Management Logic ---

def get_order_refund_balance(order):
    """
    Calculates verified total successful payments, non-rejected refund claims,
    and remaining refundable balance for an order.
    """
    successful_payments = PaymentTransaction.objects.filter(
        order=order,
        status=PaymentTransaction.STATUS_SUCCESS
    )
    total_paid = sum((p.amount for p in successful_payments), Decimal('0.00'))

    active_or_settled_refunds = RefundRequest.objects.filter(
        order=order,
        status__in=[
            RefundRequest.STATUS_PENDING,
            RefundRequest.STATUS_UNDER_REVIEW,
            RefundRequest.STATUS_APPROVED,
            RefundRequest.STATUS_PROCESSING,
            RefundRequest.STATUS_COMPLETED
        ]
    )
    refunded_sum = sum(
        (r.amount_approved if r.status in [RefundRequest.STATUS_APPROVED, RefundRequest.STATUS_COMPLETED]
         else r.amount_requested for r in active_or_settled_refunds),
        Decimal('0.00')
    )
    remaining = max(Decimal('0.00'), total_paid - refunded_sum)
    return total_paid, refunded_sum, remaining


class RefundEligibilityView(APIView):
    """
    Checks refund eligibility and calculates remaining refundable balance for an order.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        order_id = request.query_params.get('order_id')
        if not order_id:
            return Response({"error": "order_id query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        order = get_object_or_404(PrintingOrder, pk=order_id)
        user = request.user
        is_admin = user.role == 'admin' or user.is_superuser
        is_shop_staff = order.shop.owner == user or order.shop.staff_members.filter(user=user, is_active=True).exists()

        if order.customer != user and not is_shop_staff and not is_admin:
            return Response({"error": "Unauthorized access to order refund details."}, status=status.HTTP_403_FORBIDDEN)

        total_paid, refunded_sum, remaining = get_order_refund_balance(order)
        has_pending = RefundRequest.objects.filter(
            order=order,
            status__in=[RefundRequest.STATUS_PENDING, RefundRequest.STATUS_UNDER_REVIEW, RefundRequest.STATUS_PROCESSING]
        ).exists()

        is_eligible = total_paid > 0 and remaining > Decimal('0.00') and not has_pending
        ineligibility_reason = ""

        if total_paid <= 0:
            ineligibility_reason = "This order has no verified paid transactions."
        elif has_pending:
            ineligibility_reason = "This order already has a pending refund request under review."
        elif remaining <= 0:
            ineligibility_reason = "This order has already been fully refunded."

        # Suggested reason based on order status
        suggested_reason = RefundRequest.REASON_OTHER
        if order.status == PrintingOrder.STATUS_REJECTED:
            suggested_reason = RefundRequest.REASON_SHOP_REJECTED
        elif order.status == PrintingOrder.STATUS_CANCELLED:
            suggested_reason = RefundRequest.REASON_CUSTOMER_CANCELLED

        return Response({
            "order_id": order.id,
            "order_number": order.order_number,
            "order_status": order.status,
            "payment_status": order.payment_status,
            "is_eligible": is_eligible,
            "ineligibility_reason": ineligibility_reason,
            "has_pending_request": has_pending,
            "total_paid": float(total_paid),
            "refunded_total": float(refunded_sum),
            "remaining_refundable": float(remaining),
            "suggested_reason": suggested_reason,
            "available_reasons": [
                {"code": code, "label": label} for code, label in RefundRequest.REASON_CHOICES
            ]
        })


class CreateRefundRequestView(APIView):
    """
    Submits a refund request for an eligible paid order.
    Enforces server-side eligibility, locks row against race conditions, and prevents duplicate requests.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreateRefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order_id = serializer.validated_data['order_id']
        reason = serializer.validated_data['reason']
        explanation = serializer.validated_data.get('explanation', '').strip()
        user = request.user

        with transaction.atomic():
            # Concurrency-safe lock on the order
            try:
                order = PrintingOrder.objects.select_for_update().get(pk=order_id)
            except PrintingOrder.DoesNotExist:
                return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

            if order.customer != user and user.role != 'admin' and not user.is_superuser:
                return Response({"error": "You can only request refunds for your own orders."}, status=status.HTTP_403_FORBIDDEN)

            total_paid, _, remaining = get_order_refund_balance(order)
            if total_paid <= 0:
                return Response({"error": "Cannot request refund for an unpaid order."}, status=status.HTTP_400_BAD_REQUEST)

            if remaining <= Decimal('0.00'):
                return Response({"error": "This order has already been fully refunded or has active requests pending."}, status=status.HTTP_400_BAD_REQUEST)

            # Prevent duplicate simultaneous pending requests
            if RefundRequest.objects.filter(
                order=order,
                status__in=[RefundRequest.STATUS_PENDING, RefundRequest.STATUS_UNDER_REVIEW, RefundRequest.STATUS_PROCESSING]
            ).exists():
                return Response({"error": "A refund request for this order is already pending review."}, status=status.HTTP_400_BAD_REQUEST)

            amount_requested = serializer.validated_data.get('amount_requested')
            if not amount_requested or amount_requested <= 0 or amount_requested > remaining:
                amount_requested = remaining

            # Associate with the most recent successful payment transaction
            last_payment = PaymentTransaction.objects.filter(
                order=order,
                status=PaymentTransaction.STATUS_SUCCESS
            ).order_by('-created_at').first()

            refund = RefundRequest.objects.create(
                order=order,
                customer=order.customer,
                payment=last_payment,
                amount_requested=amount_requested,
                reason=reason,
                explanation=explanation,
                status=RefundRequest.STATUS_PENDING,
                simulated_mode=True
            )

            RefundAuditLog.objects.create(
                refund=refund,
                actor=user,
                action='submitted',
                from_status='',
                to_status=RefundRequest.STATUS_PENDING,
                amount=amount_requested,
                notes=f"Refund requested by customer. Reason: {refund.get_reason_display()}"
            )

        # Notify Shop Owner and Customer
        Notification.send(
            recipient=order.customer,
            title=f"Refund Request Submitted ({refund.refund_reference})",
            message=f"Your refund request of ₱{amount_requested:.2f} for Order #{order.order_number} has been submitted and is under review.",
            notification_type=Notification.TYPE_GENERAL,
            link=f"/tracking/{order.id}"
        )
        Notification.send(
            recipient=order.shop.owner,
            title=f"New Refund Request: Order #{order.order_number}",
            message=f"Customer {order.customer.full_name} submitted a refund request of ₱{amount_requested:.2f} for '{order.shop.name}'.",
            notification_type=Notification.TYPE_GENERAL,
            link=f"/shop/dashboard?tab=refunds"
        )

        return Response({
            "message": "Refund request submitted successfully and is awaiting review.",
            "refund": RefundRequestSerializer(refund).data
        }, status=status.HTTP_201_CREATED)


class RefundRequestListView(generics.ListAPIView):
    """
    Lists refund requests scoped to Customer, Shop Owner, or Platform Administrator.
    """
    serializer_class = RefundRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role_view = self.request.query_params.get('view')
        status_filter = self.request.query_params.get('status')

        qs = RefundRequest.objects.all().select_related('order', 'order__shop', 'customer', 'payment', 'decided_by').prefetch_related('audit_logs')

        if role_view == 'shop' and (user.role in ['shop_owner', 'shop_staff'] or user.role == 'admin'):
            from apps.shops.models import PrintingShop
            shop = PrintingShop.objects.filter(owner=user).first()
            if shop:
                qs = qs.filter(order__shop=shop)
            else:
                qs = qs.none()
        elif role_view == 'admin' and (user.role == 'admin' or user.is_superuser):
            pass  # Admins can view all
        else:
            # Customer view
            qs = qs.filter(customer=user)

        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs.order_by('-created_at')


class RefundRequestDetailView(generics.RetrieveAPIView):
    """
    Retrieves full details and audit history for a specific refund request.
    """
    serializer_class = RefundRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = RefundRequest.objects.all().select_related('order', 'order__shop', 'customer', 'payment', 'decided_by').prefetch_related('audit_logs')

    def get_object(self):
        refund = super().get_object()
        user = self.request.user
        is_admin = user.role == 'admin' or user.is_superuser
        is_shop_owner = refund.order.shop.owner == user

        if refund.customer != user and not is_shop_owner and not is_admin:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have access to this refund record.")
        return refund


class CancelRefundRequestView(APIView):
    """
    Allows a customer to cancel their own pending refund request.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        refund = get_object_or_404(RefundRequest, pk=pk)
        user = request.user

        if refund.customer != user and user.role != 'admin' and not user.is_superuser:
            return Response({"error": "Unauthorized to cancel this refund request."}, status=status.HTTP_403_FORBIDDEN)

        if refund.status not in [RefundRequest.STATUS_PENDING, RefundRequest.STATUS_UNDER_REVIEW]:
            return Response({"error": f"Cannot cancel a refund request with status '{refund.get_status_display()}'."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            old_status = refund.status
            refund.status = RefundRequest.STATUS_CANCELLED
            refund.decision_reason = "Cancelled by customer."
            refund.decided_by = user
            refund.decided_at = timezone.now()
            refund.save(update_fields=['status', 'decision_reason', 'decided_by', 'decided_at', 'updated_at'])

            RefundAuditLog.objects.create(
                refund=refund,
                actor=user,
                action='cancelled',
                from_status=old_status,
                to_status=RefundRequest.STATUS_CANCELLED,
                notes="Customer cancelled pending refund request."
            )

        Notification.send(
            recipient=refund.order.shop.owner,
            title=f"Refund Request Cancelled ({refund.refund_reference})",
            message=f"Customer cancelled the refund request for Order #{refund.order.order_number}.",
            notification_type=Notification.TYPE_GENERAL,
            link="/shop/dashboard?tab=refunds"
        )

        return Response({
            "message": "Refund request cancelled.",
            "refund": RefundRequestSerializer(refund).data
        })


class ProcessRefundActionView(APIView):
    """
    Processes Shop Owner or Administrator refund actions:
    'approve', 'reject', 'more_info', 'under_review'.
    In simulated sandbox mode, approved refunds immediately simulate completion
    with full financial safeguards, row locking, and audit logs.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        refund = get_object_or_404(RefundRequest, pk=pk)
        user = request.user
        action = (request.data.get('action') or '').strip().lower()
        decision_reason = (request.data.get('decision_reason') or request.data.get('reason') or '').strip()

        is_admin = user.role == 'admin' or user.is_superuser
        is_shop_owner = refund.order.shop.owner == user

        if not is_shop_owner and not is_admin:
            return Response({"error": "Only authorized shop owners or administrators can process refund actions."}, status=status.HTTP_403_FORBIDDEN)

        if refund.status in [RefundRequest.STATUS_COMPLETED, RefundRequest.STATUS_REJECTED, RefundRequest.STATUS_CANCELLED]:
            return Response({"error": f"This refund request has already been finalized ({refund.get_status_display()})."}, status=status.HTTP_400_BAD_REQUEST)

        old_status = refund.status

        if action == 'approve':
            with transaction.atomic():
                # Concurrency lock on order
                order = PrintingOrder.objects.select_for_update().get(pk=refund.order_id)
                total_paid, _, remaining = get_order_refund_balance(order)

                # Add back this refund's requested amount to remaining headroom
                available_to_refund = remaining + refund.amount_requested
                
                approved_amt_raw = request.data.get('amount_approved')
                if approved_amt_raw:
                    try:
                        approved_amount = Decimal(str(approved_amt_raw))
                    except Exception:
                        approved_amount = refund.amount_requested
                else:
                    approved_amount = refund.amount_requested

                if approved_amount <= 0 or approved_amount > available_to_refund:
                    approved_amount = min(refund.amount_requested, available_to_refund)

                # Simulated mode: set directly to completed with clear simulation tag
                refund.amount_approved = approved_amount
                refund.status = RefundRequest.STATUS_COMPLETED
                refund.decision_reason = decision_reason or "Approved by administrator/shop owner."
                refund.decided_by = user
                refund.decided_at = timezone.now()
                refund.simulated_mode = True
                refund.save(update_fields=['amount_approved', 'status', 'decision_reason', 'decided_by', 'decided_at', 'simulated_mode', 'updated_at'])

                # Update order payment status
                _, _, updated_remaining = get_order_refund_balance(order)
                if updated_remaining <= Decimal('0.00'):
                    order.payment_status = 'refunded'
                else:
                    order.payment_status = 'partially_refunded'
                order.save(update_fields=['payment_status', 'updated_at'])

                # Audit log
                RefundAuditLog.objects.create(
                    refund=refund,
                    actor=user,
                    action='approved_and_completed',
                    from_status=old_status,
                    to_status=RefundRequest.STATUS_COMPLETED,
                    amount=approved_amount,
                    notes=f"Approved & simulated completion by {user.full_name}. Amount: ₱{approved_amount:.2f}. Notes: {decision_reason or 'No additional notes'}"
                )

                OrderStatusHistory.objects.create(
                    order=order,
                    status=order.status,
                    changed_by=user,
                    notes=f"Sandbox refund of ₱{approved_amount:.2f} processed ({refund.refund_reference})."
                )

            # Notifications
            Notification.send(
                recipient=refund.customer,
                title=f"Refund Approved (₱{approved_amount:.2f})",
                message=f"Your refund of ₱{approved_amount:.2f} for Order #{order.order_number} has been approved and simulated successfully ({refund.refund_reference}).",
                notification_type=Notification.TYPE_GENERAL,
                link=f"/tracking/{order.id}"
            )
            return Response({
                "message": f"Refund of ₱{approved_amount:.2f} approved and completed in sandbox simulation.",
                "refund": RefundRequestSerializer(refund).data
            })

        elif action == 'reject':
            if not decision_reason:
                return Response({"error": "Please provide an explanation/reason for declining this refund request."}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                refund.status = RefundRequest.STATUS_REJECTED
                refund.decision_reason = decision_reason
                refund.decided_by = user
                refund.decided_at = timezone.now()
                refund.save(update_fields=['status', 'decision_reason', 'decided_by', 'decided_at', 'updated_at'])

                RefundAuditLog.objects.create(
                    refund=refund,
                    actor=user,
                    action='rejected',
                    from_status=old_status,
                    to_status=RefundRequest.STATUS_REJECTED,
                    amount=Decimal('0.00'),
                    notes=f"Declined by {user.full_name}. Reason: {decision_reason}"
                )

            Notification.send(
                recipient=refund.customer,
                title=f"Refund Request Declined ({refund.refund_reference})",
                message=f"Your refund request for Order #{refund.order.order_number} was not approved. Reason: {decision_reason}",
                notification_type=Notification.TYPE_GENERAL,
                link=f"/tracking/{refund.order.id}"
            )
            return Response({
                "message": "Refund request has been rejected.",
                "refund": RefundRequestSerializer(refund).data
            })

        elif action in ['under_review']:
            with transaction.atomic():
                refund.status = RefundRequest.STATUS_UNDER_REVIEW
                if decision_reason:
                    refund.decision_reason = decision_reason
                refund.save(update_fields=['status', 'decision_reason', 'updated_at'])

                RefundAuditLog.objects.create(
                    refund=refund,
                    actor=user,
                    action='under_review',
                    from_status=old_status,
                    to_status=RefundRequest.STATUS_UNDER_REVIEW,
                    notes=f"Placed under review by {user.full_name}."
                )
            return Response({
                "message": "Refund request placed under review.",
                "refund": RefundRequestSerializer(refund).data
            })

        return Response({"error": "Invalid action. Supported actions: 'approve', 'reject', 'under_review'."}, status=status.HTTP_400_BAD_REQUEST)
