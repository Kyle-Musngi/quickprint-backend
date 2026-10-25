from django.db import models
from django.conf import settings


class Notification(models.Model):
    TYPE_ORDER_SUBMITTED = 'order_submitted'
    TYPE_ORDER_ACCEPTED = 'order_accepted'
    TYPE_ORDER_REJECTED = 'order_rejected'
    TYPE_PAYMENT_STATUS = 'payment_status'
    TYPE_PRINTING_STARTED = 'printing_started'
    TYPE_READY_FOR_PICKUP = 'ready_for_pickup'
    TYPE_PICKUP_CONFIRMED = 'pickup_confirmed'
    TYPE_ORDER_CANCELLED = 'order_cancelled'
    TYPE_GENERAL = 'general'

    TYPE_CHOICES = (
        (TYPE_ORDER_SUBMITTED, 'Order Submitted'),
        (TYPE_ORDER_ACCEPTED, 'Order Accepted'),
        (TYPE_ORDER_REJECTED, 'Order Rejected'),
        (TYPE_PAYMENT_STATUS, 'Payment Status Updated'),
        (TYPE_PRINTING_STARTED, 'Printing Started'),
        (TYPE_READY_FOR_PICKUP, 'Ready for Pickup'),
        (TYPE_PICKUP_CONFIRMED, 'Pickup Confirmed'),
        (TYPE_ORDER_CANCELLED, 'Order Cancelled'),
        (TYPE_GENERAL, 'General Notification'),
    )

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_GENERAL)
    link = models.CharField(max_length=255, blank=True, default='')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"To {self.recipient.username}: {self.title}"

    @classmethod
    def send(cls, recipient, title, message, notification_type=TYPE_GENERAL, link=''):
        return cls.objects.create(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link
        )
