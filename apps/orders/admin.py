from django.contrib import admin
from .models import PrintingOrder, OrderDocument, OrderStatusHistory, GlobalPickupSequence


class OrderDocumentInline(admin.TabularInline):
    model = OrderDocument
    extra = 0
    readonly_fields = ('created_at',)


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(PrintingOrder)
class PrintingOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'pickup_code', 'customer', 'shop', 'status', 'payment_status', 'total_amount', 'created_at')
    list_filter = ('status', 'payment_status', 'created_at')
    search_fields = ('order_number', 'pickup_code', 'customer__username', 'shop__name')
    inlines = [OrderDocumentInline, OrderStatusHistoryInline]


@admin.register(OrderDocument)
class OrderDocumentAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'order', 'page_count', 'copies', 'calculated_total', 'created_at')
    search_fields = ('original_filename', 'order__order_number')


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('order', 'status', 'changed_by', 'created_at')
    search_fields = ('order__order_number', 'status')


@admin.register(GlobalPickupSequence)
class GlobalPickupSequenceAdmin(admin.ModelAdmin):
    list_display = ('last_number', 'updated_at')

