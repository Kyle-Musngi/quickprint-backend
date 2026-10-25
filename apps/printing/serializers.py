from rest_framework import serializers
from .models import ShopPricingRule, PrintingService


class ShopPricingRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopPricingRule
        fields = ['id', 'shop', 'paper_size', 'color_mode', 'print_side', 'price_per_page', 'is_available', 'updated_at']
        read_only_fields = ['id', 'shop', 'updated_at']


class PrintingServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrintingService
        fields = ['id', 'shop', 'name', 'description', 'base_price', 'is_active', 'created_at']
        read_only_fields = ['id', 'shop', 'created_at']
