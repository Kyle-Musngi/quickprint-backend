from django.contrib import admin
from .models import PrintingShop, ShopOperatingHours, ShopReview


@admin.register(PrintingShop)
class PrintingShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'city', 'phone_number', 'status', 'is_active', 'created_at')
    list_filter = ('status', 'is_active', 'city')
    search_fields = ('name', 'address', 'city', 'email', 'phone_number', 'owner__username')


@admin.register(ShopOperatingHours)
class ShopOperatingHoursAdmin(admin.ModelAdmin):
    list_display = ('shop', 'day_of_week', 'is_open', 'opening_time', 'closing_time')
    list_filter = ('day_of_week', 'is_open')
    search_fields = ('shop__name',)


@admin.register(ShopReview)
class ShopReviewAdmin(admin.ModelAdmin):
    list_display = ('shop', 'customer', 'rating', 'is_moderated', 'created_at')
    list_filter = ('rating', 'is_moderated')
    search_fields = ('shop__name', 'customer__username', 'review_text')

