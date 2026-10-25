from django.db import models
from django.conf import settings


class SupportQuestion(models.Model):
    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_ANSWERED = 'answered'
    STATUS_RESOLVED = 'resolved'

    STATUS_CHOICES = (
        (STATUS_OPEN, 'Open'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_ANSWERED, 'Answered'),
        (STATUS_RESOLVED, 'Resolved'),
    )

    CATEGORY_GENERAL = 'general'
    CATEGORY_ORDER = 'order'
    CATEGORY_PAYMENT = 'payment'
    CATEGORY_SHOP = 'shop'
    CATEGORY_TECHNICAL = 'technical'

    CATEGORY_CHOICES = (
        (CATEGORY_GENERAL, 'General Inquiry'),
        (CATEGORY_ORDER, 'Order & Printing'),
        (CATEGORY_PAYMENT, 'Payments & Sandbox'),
        (CATEGORY_SHOP, 'Shop Registration'),
        (CATEGORY_TECHNICAL, 'Technical Issue'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_questions'
    )
    subject = models.CharField(max_length=255)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default=CATEGORY_GENERAL)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    admin_response = models.TextField(blank=True, default='')
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='answered_support_questions'
    )
    answered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_category_display()}] {self.subject} ({self.user.username})"
