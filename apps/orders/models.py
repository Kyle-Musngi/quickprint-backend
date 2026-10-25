from django.db import models, transaction
from django.conf import settings
from apps.shops.models import PrintingShop
import uuid


class GlobalPickupSequence(models.Model):
    """
    Database-safe singleton model for generating globally sequential,
    unique pickup codes across all printing shops (UQP01, UQP02, etc.).
    """
    last_number = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_next_pickup_code(cls):
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(id=1)
            seq.last_number += 1
            seq.save(update_fields=['last_number', 'updated_at'])
            return f"UQP{seq.last_number:02d}"

    def __str__(self):
        return f"Global Sequence: UQP{self.last_number:02d}"


class PrintingOrder(models.Model):
    STATUS_PENDING_ACCEPTANCE = 'pending_acceptance'
    STATUS_SUBMITTED = 'pending_acceptance'
    STATUS_RECEIVED = 'received'
    STATUS_AWAITING_PAYMENT = 'awaiting_payment'
    STATUS_ACCEPTED = 'awaiting_payment'
    STATUS_IN_PRODUCTION = 'in_production'
    STATUS_PRINTING = 'in_production'
    STATUS_READY_FOR_PICKUP = 'ready_for_pickup'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_REJECTED = 'rejected'
    STATUS_EXPIRED = 'expired'

    STATUS_CHOICES = (
        (STATUS_PENDING_ACCEPTANCE, 'Pending Acceptance'),
        ('submitted', 'Pending Acceptance'),
        (STATUS_AWAITING_PAYMENT, 'Awaiting Payment'),
        ('accepted', 'Awaiting Payment'),
        (STATUS_IN_PRODUCTION, 'In Production'),
        ('printing', 'In Production'),
        (STATUS_READY_FOR_PICKUP, 'Ready for Pickup'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_EXPIRED, 'Expired'),
    )

    PAYMENT_STATUS_UNPAID = 'unpaid'
    PAYMENT_STATUS_PENDING = 'pending'
    PAYMENT_STATUS_PAID = 'paid'
    PAYMENT_STATUS_FAILED = 'failed'

    PAYMENT_STATUS_CHOICES = (
        (PAYMENT_STATUS_UNPAID, 'Unpaid'),
        (PAYMENT_STATUS_PENDING, 'Payment Pending'),
        (PAYMENT_STATUS_PAID, 'Paid'),
        (PAYMENT_STATUS_FAILED, 'Payment Failed'),
    )

    order_number = models.CharField(max_length=64, unique=True, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    shop = models.ForeignKey(PrintingShop, on_delete=models.CASCADE, related_name='orders')
    
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING_ACCEPTANCE)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_STATUS_UNPAID)
    payment_deadline = models.DateTimeField(null=True, blank=True)
    
    rejection_reason = models.TextField(blank=True, default='')
    cancellation_reason = models.TextField(blank=True, default='')
    
    subtotal_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    service_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    instructions = models.TextField(blank=True, default='')
    pickup_date = models.DateField(null=True, blank=True)
    pickup_time_slot = models.CharField(max_length=60, blank=True, default='')
    
    pickup_code = models.CharField(max_length=20, blank=True, null=True, unique=True)
    pickup_confirmed_at = models.DateTimeField(null=True, blank=True)
    pickup_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_pickups'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def check_and_apply_expiration(self):
        """
        If order is awaiting payment and deadline has passed (with no pending payment transaction),
        mark order as EXPIRED and notify customer and shop.
        """
        from django.utils import timezone
        if self.status in [self.STATUS_AWAITING_PAYMENT, 'accepted'] and self.payment_deadline:
            if timezone.now() > self.payment_deadline:
                has_pending = self.payments.filter(status='pending').exists()
                if not has_pending:
                    self.status = self.STATUS_EXPIRED
                    self.save(update_fields=['status', 'updated_at'])
                    OrderStatusHistory.objects.create(
                        order=self,
                        status=self.STATUS_EXPIRED,
                        notes="Payment deadline expired. Order cancelled and pickup slot released."
                    )
                    from apps.notifications.models import Notification
                    Notification.send(
                        recipient=self.customer,
                        title=f"Order #{self.order_number} Expired",
                        message=f"The payment deadline for order #{self.order_number} has expired. Please submit a new order if still needed.",
                        notification_type=Notification.TYPE_GENERAL,
                        link=f"/tracking/{self.id}"
                    )
                    Notification.send(
                        recipient=self.shop.owner,
                        title=f"Order #{self.order_number} Payment Expired",
                        message=f"Payment was not completed for order #{self.order_number} within deadline. Capacity has been released.",
                        notification_type=Notification.TYPE_GENERAL,
                        link=f"/shop/orders/{self.id}"
                    )
                    return True
        return False

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_number} ({self.status}) - {self.shop.name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"UQP-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class OrderDocument(models.Model):
    order = models.ForeignKey(PrintingOrder, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='order_documents/%Y/%m/%d/')
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)  # in bytes
    page_count = models.PositiveIntegerField(default=1)
    
    paper_size = models.CharField(max_length=20, default='A4')
    color_mode = models.CharField(max_length=10, default='bw')
    print_side = models.CharField(max_length=10, default='single')
    orientation = models.CharField(max_length=20, default='portrait', blank=True)
    page_range = models.CharField(max_length=100, default='all', blank=True)
    effective_pages = models.PositiveIntegerField(default=1)
    paper_type = models.CharField(max_length=50, default='standard', blank=True)
    copies = models.PositiveIntegerField(default=1)
    
    unit_price = models.DecimalField(max_digits=7, decimal_places=2, default=0.00)
    calculated_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.original_filename} ({self.page_count} pgs, {self.copies} copies)"


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(PrintingOrder, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.order.order_number} -> {self.status} at {self.created_at}"
