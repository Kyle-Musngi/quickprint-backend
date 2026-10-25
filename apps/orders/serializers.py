from rest_framework import serializers
from .models import PrintingOrder, OrderDocument, OrderStatusHistory
from apps.shops.serializers import PrintingShopListSerializer
from apps.accounts.serializers import UserSerializer


class OrderDocumentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = OrderDocument
        fields = [
            'id', 'original_filename', 'file_size', 'page_count',
            'paper_size', 'color_mode', 'print_side', 'orientation',
            'page_range', 'effective_pages', 'paper_type', 'copies',
            'unit_price', 'calculated_total', 'file_url', 'created_at'
        ]

    def get_file_url(self, obj):
        return f"/api/v1/orders/{obj.order.id}/documents/{obj.id}/download/"


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.ReadOnlyField(source='changed_by.full_name')

    class Meta:
        model = OrderStatusHistory
        fields = ['id', 'status', 'changed_by_name', 'notes', 'created_at']


class PrintingOrderDetailSerializer(serializers.ModelSerializer):
    documents = OrderDocumentSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    customer = UserSerializer(read_only=True)
    shop = PrintingShopListSerializer(read_only=True)
    is_reviewed = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()

    class Meta:
        model = PrintingOrder
        fields = [
            'id', 'order_number', 'customer', 'shop', 'status', 'payment_status',
            'payment_deadline',
            'rejection_reason', 'cancellation_reason',
            'subtotal_amount', 'service_fee', 'total_amount',
            'instructions', 'pickup_date', 'pickup_time_slot',
            'pickup_code', 'pickup_confirmed_at',
            'documents', 'status_history', 'is_reviewed', 'review',
            'created_at', 'updated_at'
        ]

    def get_is_reviewed(self, obj):
        return hasattr(obj, 'review') and obj.review is not None

    def get_review(self, obj):
        if hasattr(obj, 'review') and obj.review is not None:
            r = obj.review
            return {
                'id': r.id,
                'rating': r.rating,
                'review_text': r.review_text,
                'created_at': r.created_at
            }
        return None


class PrintingOrderListSerializer(serializers.ModelSerializer):
    shop_name = serializers.ReadOnlyField(source='shop.name')
    customer_name = serializers.ReadOnlyField(source='customer.full_name')
    document_count = serializers.IntegerField(source='documents.count', read_only=True)
    is_reviewed = serializers.SerializerMethodField()

    class Meta:
        model = PrintingOrder
        fields = [
            'id', 'order_number', 'shop_name', 'customer_name', 'status',
            'payment_status', 'payment_deadline', 'total_amount', 'pickup_date',
            'pickup_time_slot', 'pickup_code', 'document_count', 'is_reviewed', 'created_at'
        ]

    def get_is_reviewed(self, obj):
        return hasattr(obj, 'review') and obj.review is not None
