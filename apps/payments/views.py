from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction

from .models import PaymentTransaction
from .serializers import PaymentTransactionSerializer
from apps.orders.models import PrintingOrder
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
