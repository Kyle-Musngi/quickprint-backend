from django.urls import path
from .views import ShopDashboardOverviewView, AdminDashboardOverviewView

urlpatterns = [
    path('shop-overview/', ShopDashboardOverviewView.as_view(), name='shop-dashboard-overview'),
    path('admin-overview/', AdminDashboardOverviewView.as_view(), name='admin-dashboard-overview'),
]
