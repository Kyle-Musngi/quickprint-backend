from rest_framework import serializers
from .models import PaymentTransaction
from apps.orders.serializers import PrintingOrderListSerializer


class PaymentTransactionSerializer(serializers.ModelSerializer):
    order_number = serializers.ReadOnlyField(source='order.order_number')
    shop_name = serializers.ReadOnlyField(source='order.shop.name')
    customer_name = serializers.ReadOnlyField(source='user.full_name')

    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'order', 'order_number', 'shop_name', 'customer_name',
            'payment_method', 'transaction_reference', 'amount', 'status',
            'simulated_mode', 'failure_reason', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'transaction_reference', 'created_at']
