from django.urls import path
from .views import (
    ShopListView,
    ShopDetailView,
    ShopRegisterView,
    MyShopView,
    ShopOperatingHoursView,
    ShopPickupSlotsView,
    AdminShopListView,
    AdminShopApprovalActionView,
    ShopReviewListCreateView,
    MyShopReviewsView,
    AdminReviewModerationView,
)

urlpatterns = [
    path('', ShopListView.as_view(), name='shop-list'),
    path('register/', ShopRegisterView.as_view(), name='shop-register'),
    path('my-shop/', MyShopView.as_view(), name='my-shop'),
    path('my-shop/operating-hours/', ShopOperatingHoursView.as_view(), name='shop-operating-hours'),
    path('my-shop/reviews/', MyShopReviewsView.as_view(), name='my-shop-reviews'),
    path('<int:pk>/', ShopDetailView.as_view(), name='shop-detail'),
    path('<int:pk>/pickup-slots/', ShopPickupSlotsView.as_view(), name='shop-pickup-slots'),
    path('<int:pk>/reviews/', ShopReviewListCreateView.as_view(), name='shop-reviews'),
    
    # Admin shop endpoints
    path('admin/all/', AdminShopListView.as_view(), name='admin-shop-list'),
    path('admin/<int:pk>/action/', AdminShopApprovalActionView.as_view(), name='admin-shop-action'),
    path('admin/reviews/<int:review_id>/moderate/', AdminReviewModerationView.as_view(), name='admin-review-moderate'),
]
