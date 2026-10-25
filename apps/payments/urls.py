from django.urls import path
from .views import (
    ProcessSandboxPaymentView,
    PaymentTransactionListView,
    PaymentTransactionDetailView
)

urlpatterns = [
    path('process/', ProcessSandboxPaymentView.as_view(), name='payment-process'),
    path('', PaymentTransactionListView.as_view(), name='payment-list'),
    path('<int:pk>/', PaymentTransactionDetailView.as_view(), name='payment-detail'),
]
