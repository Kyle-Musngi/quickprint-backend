from django.urls import path
from .views import (
    ShopPricingListView,
    MyShopPricingManageView,
    ShopServicesListView,
    MyShopServicesManageView,
    EstimateCostView,
)

urlpatterns = [
    path('estimate/', EstimateCostView.as_view(), name='printing-estimate'),
    path('shops/<int:shop_id>/prices/', ShopPricingListView.as_view(), name='shop-prices'),
    path('shops/<int:shop_id>/services/', ShopServicesListView.as_view(), name='shop-services'),
    path('my-shop/prices/', MyShopPricingManageView.as_view(), name='my-shop-prices'),
    path('my-shop/services/', MyShopServicesManageView.as_view(), name='my-shop-services'),
]
