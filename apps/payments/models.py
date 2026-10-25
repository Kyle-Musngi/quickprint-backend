from django.db import models
from django.conf import settings
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
