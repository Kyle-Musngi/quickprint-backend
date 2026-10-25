from django.db import models
from django.conf import settings
from django.utils import timezone
import math


class PrintingShop(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_SUSPENDED = 'suspended'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_SUSPENDED, 'Suspended'),
    )

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_shops')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    email = models.EmailField()
    phone_number = models.CharField(max_length=50)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=100, default='Manila')
    barangay = models.CharField(max_length=100, blank=True, default='')
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    image = models.ImageField(upload_to='shop_images/', blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    rejection_reason = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    
    opening_time = models.TimeField(default='08:00:00')
    closing_time = models.TimeField(default='18:00:00')
    operating_days = models.CharField(max_length=100, default='Monday - Saturday')
    pickup_slot_interval_minutes = models.PositiveIntegerField(default=30)
    slot_capacity = models.PositiveIntegerField(default=5)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def is_currently_open(self):
        if not self.is_active or self.status != self.STATUS_APPROVED:
            return False
        now = timezone.localtime()
        current_day = now.weekday()
        now_time = now.time()

        # Check per-day schedule if configured
        day_schedule = self.operating_hours.filter(day_of_week=current_day).first()
        if day_schedule is not None:
            if not day_schedule.is_open:
                return False
            if day_schedule.closing_time < day_schedule.opening_time:
                return now_time >= day_schedule.opening_time or now_time <= day_schedule.closing_time
            return day_schedule.opening_time <= now_time <= day_schedule.closing_time

        # Fallback to legacy string operating_days if no per-day schedule exists
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        configured_days = self.operating_days.replace(' ', '').split(',')
        current_day_name = day_names[current_day]
        day_is_configured = any(
            current_day_name == day or (
                '-' in day and
                day_names.index(day.split('-')[0]) <= current_day <= day_names.index(day.split('-')[1])
            )
            for day in configured_days
            if day and ('-' not in day or all(part in day_names for part in day.split('-')))
        )
        if not day_is_configured:
            return False

        if self.closing_time < self.opening_time:
            return now_time >= self.opening_time or now_time <= self.closing_time
        return self.opening_time <= now_time <= self.closing_time

    @property
    def average_rating(self):
        valid_reviews = self.reviews.filter(is_moderated=False)
        if not valid_reviews.exists():
            return None
        avg = valid_reviews.aggregate(models.Avg('rating'))['rating__avg']
        return round(float(avg), 1) if avg is not None else None

    @property
    def review_count(self):
        return self.reviews.filter(is_moderated=False).count()

    def distance_from(self, lat, lng):
        """Calculates distance in kilometers using Haversine formula."""
        if self.latitude is None or self.longitude is None:
            return None
        try:
            lat1, lon1 = float(lat), float(lng)
            lat2, lon2 = float(self.latitude), float(self.longitude)
        except (ValueError, TypeError):
            return None

        # Earth radius in kilometers
        r = 6371.0
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(d_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(r * c, 2)


class ShopStaffMembership(models.Model):
    shop = models.ForeignKey(PrintingShop, on_delete=models.CASCADE, related_name='staff_members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_assignments')
    role = models.CharField(max_length=20, default='staff')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('shop', 'user')

    def __str__(self):
        return f"{self.user.username} @ {self.shop.name}"


class ShopOperatingHours(models.Model):
    DAY_CHOICES = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    )

    shop = models.ForeignKey(PrintingShop, on_delete=models.CASCADE, related_name='operating_hours')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    is_open = models.BooleanField(default=True)
    opening_time = models.TimeField(default='08:00:00')
    closing_time = models.TimeField(default='18:00:00')

    class Meta:
        ordering = ['day_of_week']
        unique_together = ('shop', 'day_of_week')

    def __str__(self):
        day_name = dict(self.DAY_CHOICES).get(self.day_of_week, f"Day {self.day_of_week}")
        status_str = f"{self.opening_time} - {self.closing_time}" if self.is_open else "Closed"
        return f"{self.shop.name} - {day_name}: {status_str}"


class ShopReview(models.Model):
    RATING_CHOICES = (
        (1, '1 Star - Poor'),
        (2, '2 Stars - Fair'),
        (3, '3 Stars - Good'),
        (4, '4 Stars - Very Good'),
        (5, '5 Stars - Excellent'),
    )

    shop = models.ForeignKey(PrintingShop, on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shop_reviews')
    order = models.OneToOneField('orders.PrintingOrder', on_delete=models.CASCADE, related_name='review')
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    review_text = models.TextField(blank=True, default='')

    # Moderation controls
    is_moderated = models.BooleanField(default=False)
    moderation_reason = models.TextField(blank=True, default='')
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderated_reviews'
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer.username} -> {self.shop.name} ({self.rating}★)"

