from django.urls import path
from .views import (
    ProcessSandboxPaymentView,
    PaymentTransactionListView,
    PaymentTransactionDetailView,
    RefundEligibilityView,
    CreateRefundRequestView,
    RefundRequestListView,
    RefundRequestDetailView,
    CancelRefundRequestView,
    ProcessRefundActionView
)

urlpatterns = [
    path('process/', ProcessSandboxPaymentView.as_view(), name='payment-process'),
    path('', PaymentTransactionListView.as_view(), name='payment-list'),
    path('<int:pk>/', PaymentTransactionDetailView.as_view(), name='payment-detail'),
    
    # Refund management endpoints
    path('refunds/eligibility/', RefundEligibilityView.as_view(), name='refund-eligibility'),
    path('refunds/request/', CreateRefundRequestView.as_view(), name='refund-request-create'),
    path('refunds/', RefundRequestListView.as_view(), name='refund-list'),
    path('refunds/<int:pk>/', RefundRequestDetailView.as_view(), name='refund-detail'),
    path('refunds/<int:pk>/cancel/', CancelRefundRequestView.as_view(), name='refund-cancel'),
    path('refunds/<int:pk>/action/', ProcessRefundActionView.as_view(), name='refund-action'),
]
