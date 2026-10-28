import os
from rest_framework import serializers
from .models import PrintingOrder, OrderDocument, OrderStatusHistory
from apps.shops.serializers import PrintingShopListSerializer
from apps.accounts.serializers import UserSerializer


class OrderDocumentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    file_type = serializers.SerializerMethodField()
    is_previewable = serializers.SerializerMethodField()
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = OrderDocument
        fields = [
            'id', 'original_filename', 'file_size', 'page_count',
            'paper_size', 'color_mode', 'print_side', 'orientation',
            'page_range', 'effective_pages', 'paper_type', 'copies',
            'unit_price', 'calculated_total', 'file_url', 'file_type',
            'is_previewable', 'has_file', 'created_at'
        ]

    def get_file_url(self, obj):
        return f"/api/v1/orders/{obj.order.id}/documents/{obj.id}/download/"

    def get_file_type(self, obj):
        if not obj.original_filename:
            return 'document'
        _, ext = os.path.splitext(obj.original_filename)
        return ext.lower().replace('.', '') or 'document'

    def get_is_previewable(self, obj):
        if not obj.original_filename:
            return False
        _, ext = os.path.splitext(obj.original_filename)
        return ext.lower() in ['.pdf', '.png', '.jpg', '.jpeg', '.txt']

    def get_has_file(self, obj):
        return bool(obj.file and bool(obj.file.name))


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.ReadOnlyField(source='changed_by.full_name')

    class Meta:
        model = OrderStatusHistory
        fields = ['id', 'status', 'changed_by_name', 'notes', 'created_at']


def _extract_latest_refund(obj):
    if not hasattr(obj, '_cached_latest_refund'):
        if hasattr(obj, '_prefetched_objects_cache') and 'refund_requests' in obj._prefetched_objects_cache:
            refunds = list(obj.refund_requests.all())
            obj._cached_latest_refund = refunds[0] if refunds else None
        elif hasattr(obj, 'refund_requests'):
            obj._cached_latest_refund = obj.refund_requests.order_by('-created_at').first()
        else:
            obj._cached_latest_refund = None
    return obj._cached_latest_refund


class PrintingOrderDetailSerializer(serializers.ModelSerializer):
    documents = OrderDocumentSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    customer = UserSerializer(read_only=True)
    shop = PrintingShopListSerializer(read_only=True)
    is_reviewed = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    queue_info = serializers.SerializerMethodField()
    refund_status = serializers.SerializerMethodField()
    refund_status_display = serializers.SerializerMethodField()
    has_active_refund = serializers.SerializerMethodField()
    refund_request = serializers.SerializerMethodField()

    class Meta:
        model = PrintingOrder
        fields = [
            'id', 'order_number', 'customer', 'shop', 'status', 'payment_status',
            'payment_deadline',
            'rejection_reason', 'cancellation_reason',
            'subtotal_amount', 'service_fee', 'total_amount',
            'instructions', 'pickup_date', 'pickup_time_slot',
            'pickup_code', 'pickup_confirmed_at',
            'documents', 'status_history', 'queue_info', 'is_reviewed', 'review',
            'refund_status', 'refund_status_display', 'has_active_refund', 'refund_request',
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

    def get_queue_info(self, obj):
        from .models import get_order_queue_details
        return get_order_queue_details(obj)

    def get_refund_status(self, obj):
        ref = _extract_latest_refund(obj)
        return ref.status if ref else None

    def get_refund_status_display(self, obj):
        ref = _extract_latest_refund(obj)
        if not ref:
            return None
        if ref.status in ['pending', 'under_review']:
            return 'Requesting Refund'
        return ref.get_status_display()

    def get_has_active_refund(self, obj):
        ref = _extract_latest_refund(obj)
        if not ref:
            return False
        return ref.status in ['pending', 'under_review', 'processing']

    def get_refund_request(self, obj):
        ref = _extract_latest_refund(obj)
        if not ref:
            return None
        return {
            'id': ref.id,
            'refund_reference': ref.refund_reference,
            'status': ref.status,
            'status_display': 'Requesting Refund' if ref.status in ['pending', 'under_review'] else ref.get_status_display(),
            'amount_requested': str(ref.amount_requested),
            'amount_approved': str(ref.amount_approved),
            'reason': ref.reason,
            'reason_display': ref.get_reason_display() if hasattr(ref, 'get_reason_display') else ref.reason,
            'explanation': ref.explanation,
            'decision_reason': ref.decision_reason,
            'created_at': ref.created_at.isoformat() if ref.created_at else None,
        }


class PrintingOrderListSerializer(serializers.ModelSerializer):
    shop_name = serializers.ReadOnlyField(source='shop.name')
    customer_name = serializers.ReadOnlyField(source='customer.full_name')
    document_count = serializers.IntegerField(source='documents.count', read_only=True)
    documents = OrderDocumentSerializer(many=True, read_only=True)
    is_reviewed = serializers.SerializerMethodField()
    queue_info = serializers.SerializerMethodField()
    refund_status = serializers.SerializerMethodField()
    refund_status_display = serializers.SerializerMethodField()
    has_active_refund = serializers.SerializerMethodField()
    refund_request = serializers.SerializerMethodField()

    class Meta:
        model = PrintingOrder
        fields = [
            'id', 'order_number', 'shop_name', 'customer_name', 'status',
            'payment_status', 'payment_deadline', 'total_amount', 'pickup_date',
            'pickup_time_slot', 'pickup_code', 'document_count', 'documents',
            'queue_info', 'is_reviewed',
            'refund_status', 'refund_status_display', 'has_active_refund', 'refund_request',
            'created_at'
        ]

    def get_is_reviewed(self, obj):
        return hasattr(obj, 'review') and obj.review is not None

    def get_queue_info(self, obj):
        from .models import get_order_queue_details
        return get_order_queue_details(obj)

    def get_refund_status(self, obj):
        ref = _extract_latest_refund(obj)
        return ref.status if ref else None

    def get_refund_status_display(self, obj):
        ref = _extract_latest_refund(obj)
        if not ref:
            return None
        if ref.status in ['pending', 'under_review']:
            return 'Requesting Refund'
        return ref.get_status_display()

    def get_has_active_refund(self, obj):
        ref = _extract_latest_refund(obj)
        if not ref:
            return False
        return ref.status in ['pending', 'under_review', 'processing']

    def get_refund_request(self, obj):
        ref = _extract_latest_refund(obj)
        if not ref:
            return None
        return {
            'id': ref.id,
            'refund_reference': ref.refund_reference,
            'status': ref.status,
            'status_display': 'Requesting Refund' if ref.status in ['pending', 'under_review'] else ref.get_status_display(),
            'amount_requested': str(ref.amount_requested),
            'amount_approved': str(ref.amount_approved),
            'reason': ref.reason,
            'reason_display': ref.get_reason_display() if hasattr(ref, 'get_reason_display') else ref.reason,
            'explanation': ref.explanation,
            'decision_reason': ref.decision_reason,
            'created_at': ref.created_at.isoformat() if ref.created_at else None,
        }


