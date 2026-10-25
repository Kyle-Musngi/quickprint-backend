from django.contrib import admin
from .models import PaymentTransaction


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_reference', 'order', 'user', 'payment_method', 'amount', 'status', 'created_at')
    list_filter = ('payment_method', 'status', 'simulated_mode', 'created_at')
    search_fields = ('transaction_reference', 'order__order_number', 'user__username')

