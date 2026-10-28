from django.contrib import admin
from .models import PaymentTransaction, RefundRequest, RefundAuditLog


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_reference', 'order', 'user', 'payment_method', 'amount', 'status', 'created_at')
    list_filter = ('payment_method', 'status', 'simulated_mode', 'created_at')
    search_fields = ('transaction_reference', 'order__order_number', 'user__username')


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    list_display = ('refund_reference', 'order', 'customer', 'amount_requested', 'amount_approved', 'reason', 'status', 'created_at')
    list_filter = ('status', 'reason', 'simulated_mode', 'created_at')
    search_fields = ('refund_reference', 'order__order_number', 'customer__username', 'customer__email')
    readonly_fields = ('refund_reference', 'created_at', 'updated_at')


@admin.register(RefundAuditLog)
class RefundAuditLogAdmin(admin.ModelAdmin):
    list_display = ('refund', 'actor', 'action', 'from_status', 'to_status', 'amount', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('refund__refund_reference', 'actor__username')
    readonly_fields = ('created_at',)

