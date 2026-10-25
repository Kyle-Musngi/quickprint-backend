from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.utils import timezone
from django.db.models import Count, Sum, Q
from datetime import datetime, timedelta

from apps.orders.models import PrintingOrder
from apps.shops.models import PrintingShop, ShopStaffMembership
from apps.payments.models import PaymentTransaction
from apps.accounts.permissions import IsPlatformAdmin, IsShopOwner
from django.contrib.auth import get_user_model

User = get_user_model()


class ShopDashboardOverviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        shop = PrintingShop.objects.filter(owner=user).first()
        if not shop:
            membership = ShopStaffMembership.objects.filter(user=user, is_active=True).first()
            if membership:
                shop = membership.shop
        if not shop:
            return Response({
                "error": "No shop found for user.",
                "code": "NO_SHOP"
            }, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        orders_qs = PrintingOrder.objects.filter(shop=shop)

        status_counts = orders_qs.aggregate(
            total=Count('id'),
            submitted=Count('id', filter=Q(status__in=[
                PrintingOrder.STATUS_PENDING_ACCEPTANCE,
                'submitted',
                'received'
            ])),
            awaiting_payment=Count('id', filter=Q(status__in=[
                PrintingOrder.STATUS_AWAITING_PAYMENT,
                'accepted'
            ])),
            accepted=Count('id', filter=Q(status__in=[
                PrintingOrder.STATUS_AWAITING_PAYMENT,
                'accepted'
            ])),
            in_production=Count('id', filter=Q(status__in=[
                PrintingOrder.STATUS_IN_PRODUCTION,
                'printing'
            ])),
            printing=Count('id', filter=Q(status__in=[
                PrintingOrder.STATUS_IN_PRODUCTION,
                'printing'
            ])),
            ready_for_pickup=Count('id', filter=Q(status=PrintingOrder.STATUS_READY_FOR_PICKUP)),
            completed=Count('id', filter=Q(status=PrintingOrder.STATUS_COMPLETED)),
            cancelled=Count('id', filter=Q(status=PrintingOrder.STATUS_CANCELLED)),
            rejected=Count('id', filter=Q(status=PrintingOrder.STATUS_REJECTED)),
            expired=Count('id', filter=Q(status=PrintingOrder.STATUS_EXPIRED)),
        )

        today_orders = orders_qs.filter(created_at__gte=today_start).count()
        monthly_orders = orders_qs.filter(created_at__gte=month_start).count()

        recorded_payments = PaymentTransaction.objects.filter(
            order__shop=shop,
            status=PaymentTransaction.STATUS_SUCCESS
        ).aggregate(total_amount=Sum('amount'))['total_amount'] or 0.00

        recent_orders = orders_qs.order_by('-created_at')[:8].values(
            'id', 'order_number', 'customer__first_name', 'customer__last_name',
            'status', 'payment_status', 'total_amount', 'pickup_code',
            'pickup_date', 'pickup_time_slot', 'created_at'
        )

        return Response({
            "shop": {
                "id": shop.id,
                "name": shop.name,
                "status": shop.status,
                "rejection_reason": getattr(shop, 'rejection_reason', '') or '',
                "is_active": shop.is_active,
                "is_open": shop.is_currently_open,
                "opening_time": str(shop.opening_time),
                "closing_time": str(shop.closing_time),
            },
            "status_counts": {
                "total": status_counts['total'] or 0,
                "submitted": status_counts['submitted'] or 0,
                "awaiting_payment": status_counts['awaiting_payment'] or 0,
                "accepted": status_counts['accepted'] or 0,
                "in_production": status_counts['in_production'] or 0,
                "printing": status_counts['printing'] or 0,
                "ready_for_pickup": status_counts['ready_for_pickup'] or 0,
                "completed": status_counts['completed'] or 0,
                "cancelled": status_counts['cancelled'] or 0,
                "rejected": status_counts['rejected'] or 0,
                "expired": status_counts['expired'] or 0,
            },
            "today_orders": today_orders,
            "monthly_orders": monthly_orders,
            "recorded_payments_total": str(recorded_payments),
            "is_sandbox_notice": "Amounts reflect simulated sandbox transactions.",
            "recent_orders": list(recent_orders)
        })


class AdminDashboardOverviewView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        total_customers = User.objects.filter(role=User.ROLE_CUSTOMER).count()
        total_shop_owners = User.objects.filter(role=User.ROLE_SHOP_OWNER).count()
        total_admins = User.objects.filter(Q(role=User.ROLE_ADMIN) | Q(is_superuser=True)).count()

        shops_stats = PrintingShop.objects.aggregate(
            total=Count('id'),
            approved=Count('id', filter=Q(status=PrintingShop.STATUS_APPROVED)),
            pending=Count('id', filter=Q(status=PrintingShop.STATUS_PENDING)),
            rejected=Count('id', filter=Q(status=PrintingShop.STATUS_REJECTED)),
            suspended=Count('id', filter=Q(status=PrintingShop.STATUS_SUSPENDED)),
        )

        orders_stats = PrintingOrder.objects.aggregate(
            total=Count('id'),
            pending_acceptance=Count('id', filter=Q(status__in=[
                PrintingOrder.STATUS_PENDING_ACCEPTANCE,
                'submitted',
                'received'
            ])),
            awaiting_payment=Count('id', filter=Q(status__in=[
                PrintingOrder.STATUS_AWAITING_PAYMENT,
                'accepted'
            ])),
            in_production=Count('id', filter=Q(status__in=[
                PrintingOrder.STATUS_IN_PRODUCTION,
                'printing'
            ])),
            ready_for_pickup=Count('id', filter=Q(status=PrintingOrder.STATUS_READY_FOR_PICKUP)),
            completed=Count('id', filter=Q(status=PrintingOrder.STATUS_COMPLETED)),
            cancelled=Count('id', filter=Q(status=PrintingOrder.STATUS_CANCELLED)),
            rejected=Count('id', filter=Q(status=PrintingOrder.STATUS_REJECTED)),
            expired=Count('id', filter=Q(status=PrintingOrder.STATUS_EXPIRED)),
            active=Count('id', filter=Q(status__in=[
                PrintingOrder.STATUS_PENDING_ACCEPTANCE,
                'submitted',
                'received',
                PrintingOrder.STATUS_AWAITING_PAYMENT,
                'accepted',
                PrintingOrder.STATUS_IN_PRODUCTION,
                'printing',
                PrintingOrder.STATUS_READY_FOR_PICKUP
            ])),
        )

        payments_stats = PaymentTransaction.objects.aggregate(
            total_count=Count('id'),
            successful_count=Count('id', filter=Q(status=PaymentTransaction.STATUS_SUCCESS)),
            pending_count=Count('id', filter=Q(status=PaymentTransaction.STATUS_PENDING)),
            failed_count=Count('id', filter=Q(status=PaymentTransaction.STATUS_FAILED)),
            total_volume=Sum('amount', filter=Q(status=PaymentTransaction.STATUS_SUCCESS))
        )

        recent_shops = PrintingShop.objects.order_by('-created_at')[:6].values(
            'id', 'name', 'city', 'status', 'owner__first_name', 'owner__last_name', 'created_at'
        )

        recent_orders = PrintingOrder.objects.order_by('-created_at')[:6].values(
            'id', 'order_number', 'shop__name', 'customer__first_name', 'customer__last_name',
            'status', 'payment_status', 'total_amount', 'created_at'
        )

        return Response({
            "users": {
                "customers": total_customers,
                "shop_owners": total_shop_owners,
                "administrators": total_admins,
                "total": total_customers + total_shop_owners + total_admins
            },
            "shops": {
                "total": shops_stats['total'] or 0,
                "approved": shops_stats['approved'] or 0,
                "pending": shops_stats['pending'] or 0,
                "rejected": shops_stats['rejected'] or 0,
                "suspended": shops_stats['suspended'] or 0,
            },
            "orders": {
                "total": orders_stats['total'] or 0,
                "pending_acceptance": orders_stats['pending_acceptance'] or 0,
                "awaiting_payment": orders_stats['awaiting_payment'] or 0,
                "in_production": orders_stats['in_production'] or 0,
                "ready_for_pickup": orders_stats['ready_for_pickup'] or 0,
                "completed": orders_stats['completed'] or 0,
                "cancelled": orders_stats['cancelled'] or 0,
                "rejected": orders_stats['rejected'] or 0,
                "expired": orders_stats['expired'] or 0,
                "active": orders_stats['active'] or 0,
            },
            "payments": {
                "total_count": payments_stats['total_count'] or 0,
                "successful_count": payments_stats['successful_count'] or 0,
                "pending_count": payments_stats['pending_count'] or 0,
                "failed_count": payments_stats['failed_count'] or 0,
                "total_volume": str(payments_stats['total_volume'] or 0.00),
                "is_sandbox_notice": "Sandbox simulated test transactions."
            },
            "recent_shops": list(recent_shops),
            "recent_orders": list(recent_orders)
        })
