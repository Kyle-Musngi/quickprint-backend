from django.contrib import admin
from .models import ShopPricingRule, PrintingService


@admin.register(ShopPricingRule)
class ShopPricingRuleAdmin(admin.ModelAdmin):
    list_display = ('shop', 'paper_size', 'color_mode', 'print_side', 'price_per_page', 'is_available')
    list_filter = ('paper_size', 'color_mode', 'print_side', 'is_available')
    search_fields = ('shop__name',)


@admin.register(PrintingService)
class PrintingServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop', 'base_price', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'shop__name')

