from rest_framework import serializers
from .models import PaymentTransaction, RefundRequest, RefundAuditLog
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


class RefundAuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.full_name', read_only=True)

    class Meta:
        model = RefundAuditLog
        fields = ['id', 'actor', 'actor_name', 'action', 'from_status', 'to_status', 'amount', 'notes', 'created_at']
        read_only_fields = ['id', 'created_at']


class RefundRequestSerializer(serializers.ModelSerializer):
    order_number = serializers.ReadOnlyField(source='order.order_number')
    shop_id = serializers.ReadOnlyField(source='order.shop.id')
    shop_name = serializers.ReadOnlyField(source='order.shop.name')
    customer_name = serializers.ReadOnlyField(source='customer.full_name')
    decided_by_name = serializers.ReadOnlyField(source='decided_by.full_name')
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    audit_logs = RefundAuditLogSerializer(many=True, read_only=True)

    class Meta:
        model = RefundRequest
        fields = [
            'id', 'refund_reference', 'order', 'order_number', 'shop_id', 'shop_name',
            'customer', 'customer_name', 'payment', 'amount_requested', 'amount_approved',
            'reason', 'reason_display', 'explanation', 'status', 'status_display',
            'decision_reason', 'decided_by', 'decided_by_name', 'decided_at',
            'simulated_mode', 'audit_logs', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'refund_reference', 'order', 'customer', 'payment',
            'amount_approved', 'status', 'decision_reason', 'decided_by',
            'decided_at', 'simulated_mode', 'created_at', 'updated_at'
        ]


class CreateRefundRequestSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=RefundRequest.REASON_CHOICES)
    explanation = serializers.CharField(required=False, allow_blank=True, default='')
    customer_explanation = serializers.CharField(required=False, allow_blank=True, default='')
    amount_requested = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)

    def validate(self, attrs):
        if not attrs.get('explanation') and attrs.get('customer_explanation'):
            attrs['explanation'] = attrs['customer_explanation']
        return attrs

