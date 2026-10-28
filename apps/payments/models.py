from django.db import models
from django.conf import settings
# pyrefly: ignore[missing-import]
from apps.orders.models import PrintingOrder
import uuid


class PaymentTransaction(models.Model):
    METHOD_GCASH = 'gcash'
    METHOD_MAYA = 'maya'
    METHOD_GOTYME = 'gotyme'

    METHOD_CHOICES = (
        (METHOD_GCASH, 'GCash (Sandbox)'),
        (METHOD_MAYA, 'Maya (Sandbox)'),
        (METHOD_GOTYME, 'GoTyme (Sandbox)'),
    )

    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Successful'),
        (STATUS_FAILED, 'Failed'),
    )

    order = models.ForeignKey(PrintingOrder, on_delete=models.CASCADE, related_name='payments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payment_transactions')
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    transaction_reference = models.CharField(max_length=100, unique=True, editable=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    simulated_mode = models.BooleanField(default=True)
    failure_reason = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_reference} - {self.payment_method} ({self.status}) - ₱{self.amount}"

    def save(self, *args, **kwargs):
        if not self.transaction_reference:
            prefix = self.payment_method.upper()
            self.transaction_reference = f"TXN-{prefix}-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


class RefundRequest(models.Model):
    REASON_SHOP_REJECTED = 'shop_rejected'
    REASON_SHOP_CANNOT_FULFILL = 'shop_cannot_fulfill'
    REASON_CUSTOMER_CANCELLED = 'customer_cancelled'
    REASON_DUPLICATE_PAYMENT = 'duplicate_payment'
    REASON_DEFECTIVE_PRINTING = 'defective_printing'
    REASON_PAYMENT_UNCONFIRMED = 'payment_unconfirmed'
    REASON_OTHER = 'other'

    REASON_CHOICES = (
        (REASON_SHOP_REJECTED, 'Shop Rejected Paid Order'),
        (REASON_SHOP_CANNOT_FULFILL, 'Shop Cannot Complete Order'),
        (REASON_CUSTOMER_CANCELLED, 'Cancelled Before Printing Started'),
        (REASON_DUPLICATE_PAYMENT, 'Duplicate Payment Detected'),
        (REASON_DEFECTIVE_PRINTING, 'Incorrect or Defective Printing Quality'),
        (REASON_PAYMENT_UNCONFIRMED, 'Payment Deducted But Order Unconfirmed'),
        (REASON_OTHER, 'Other / Special Request'),
    )

    STATUS_PENDING = 'pending'
    STATUS_UNDER_REVIEW = 'under_review'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_UNDER_REVIEW, 'Under Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed (Sandbox)'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled by Customer'),
    )

    order = models.ForeignKey(PrintingOrder, on_delete=models.CASCADE, related_name='refund_requests')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='refund_requests')
    payment = models.ForeignKey(PaymentTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='refunds')
    
    refund_reference = models.CharField(max_length=100, unique=True, editable=False)
    amount_requested = models.DecimalField(max_digits=10, decimal_places=2)
    amount_approved = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    reason = models.CharField(max_length=50, choices=REASON_CHOICES)
    explanation = models.TextField(blank=True, default='')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING)
    decision_reason = models.TextField(blank=True, default='')
    
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='decided_refunds')
    decided_at = models.DateTimeField(null=True, blank=True)
    
    simulated_mode = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.refund_reference} ({self.status}) - ₱{self.amount_requested} for Order #{self.order.order_number}"

    def save(self, *args, **kwargs):
        if not self.refund_reference:
            self.refund_reference = f"REF-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


class RefundAuditLog(models.Model):
    """
    Maintains complete audit history of all refund decisions, amounts, actors, and state transitions.
    """
    refund = models.ForeignKey(RefundRequest, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50)  # submitted, under_review, approved, rejected, cancelled, completed
    from_status = models.CharField(max_length=30, blank=True, default='')
    to_status = models.CharField(max_length=30)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        actor_name = self.actor.username if self.actor else 'System'
        return f"{self.refund.refund_reference}: {self.from_status} -> {self.to_status} by {actor_name} (₱{self.amount})"

