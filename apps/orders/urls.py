from django.urls import path
from .views import (
    DetectPagesView,
    OrderCreateView,
    OrderListView,
    OrderDetailView,
    OrderCancelView,
    OrderAcceptView,
    OrderRejectView,
    OrderStartPrintingView,
    OrderReadyForPickupView,
    OrderConfirmPickupView,
    OrderDocumentDownloadView,
    OrderUpdatePickupSlotView,
    OrderQueueStatusView,
)

urlpatterns = [
    path('detect-pages/', DetectPagesView.as_view(), name='detect-pages'),
    path('', OrderListView.as_view(), name='order-list'),
    path('create/', OrderCreateView.as_view(), name='order-create'),
    path('<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('<int:pk>/queue-status/', OrderQueueStatusView.as_view(), name='order-queue-status'),
    path('<int:pk>/cancel/', OrderCancelView.as_view(), name='order-cancel'),
    path('<int:pk>/accept/', OrderAcceptView.as_view(), name='order-accept'),
    path('<int:pk>/reject/', OrderRejectView.as_view(), name='order-reject'),
    path('<int:pk>/pickup-slot/', OrderUpdatePickupSlotView.as_view(), name='order-update-pickup-slot'),
    path('<int:pk>/start-printing/', OrderStartPrintingView.as_view(), name='order-start-printing'),
    path('<int:pk>/ready-for-pickup/', OrderReadyForPickupView.as_view(), name='order-ready-for-pickup'),
    path('<int:pk>/confirm-pickup/', OrderConfirmPickupView.as_view(), name='order-confirm-pickup'),
    path('<int:order_id>/documents/<int:doc_id>/download/', OrderDocumentDownloadView.as_view(), name='order-document-download'),
]

