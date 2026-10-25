from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.shops.models import PrintingShop
from apps.orders.models import PrintingOrder
from apps.payments.models import PaymentTransaction
from decimal import Decimal

User = get_user_model()


class ShopDashboardOverviewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username='eduardo_owner', password='Password123!', role=User.ROLE_SHOP_OWNER,
            first_name='Eduardo', last_name='Reyes'
        )
        self.pending_owner = User.objects.create_user(
            username='pending_owner', password='Password123!', role=User.ROLE_SHOP_OWNER,
            first_name='Pending', last_name='Owner'
        )
        self.suspended_owner = User.objects.create_user(
            username='suspended_owner', password='Password123!', role=User.ROLE_SHOP_OWNER,
            first_name='Suspended', last_name='Owner'
        )
        self.customer = User.objects.create_user(
            username='regular_customer', password='Password123!', role=User.ROLE_CUSTOMER
        )

        self.shop_approved = PrintingShop.objects.create(
            owner=self.owner,
            name='Cebu Campus Print Hub',
            email='campus@cebu.ph',
            phone_number='032 111 2222',
            address='Taft Avenue',
            city='Cebu City',
            status=PrintingShop.STATUS_APPROVED,
            is_active=True
        )

        self.shop_pending = PrintingShop.objects.create(
            owner=self.pending_owner,
            name='Sugbo Student Center',
            email='sugbo@cebu.ph',
            phone_number='032 333 4444',
            address='Banilad',
            city='Cebu City',
            status=PrintingShop.STATUS_PENDING,
            is_active=True
        )

        self.shop_suspended = PrintingShop.objects.create(
            owner=self.suspended_owner,
            name='University Print Corner',
            email='corner@cebu.ph',
            phone_number='032 555 6666',
            address='Lahug',
            city='Cebu City',
            status=PrintingShop.STATUS_SUSPENDED,
            is_active=True
        )

        self.order = PrintingOrder.objects.create(
            customer=self.customer,
            shop=self.shop_approved,
            total_amount=Decimal('60.00'),
            status=PrintingOrder.STATUS_PENDING_ACCEPTANCE
        )

    def test_eduardo_can_access_his_shop_overview(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get('/api/v1/analytics/shop-overview/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['shop']['name'], 'Cebu Campus Print Hub')
        self.assertEqual(res.data['shop']['status'], 'approved')
        self.assertIn('status_counts', res.data)
        self.assertEqual(res.data['status_counts']['submitted'], 1)

    def test_pending_shop_owner_can_access_shop_overview(self):
        self.client.force_authenticate(user=self.pending_owner)
        res = self.client.get('/api/v1/analytics/shop-overview/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['shop']['name'], 'Sugbo Student Center')
        self.assertEqual(res.data['shop']['status'], 'pending')

    def test_suspended_shop_owner_can_access_shop_overview(self):
        self.client.force_authenticate(user=self.suspended_owner)
        res = self.client.get('/api/v1/analytics/shop-overview/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['shop']['name'], 'University Print Corner')
        self.assertEqual(res.data['shop']['status'], 'suspended')

    def test_user_without_shop_returns_404(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.get('/api/v1/analytics/shop-overview/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res.data['code'], 'NO_SHOP')

    def test_unauthenticated_user_cannot_access_shop_overview(self):
        res = self.client.get('/api/v1/analytics/shop-overview/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class AdminDashboardOverviewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='platform_admin', password='Password123!', role=User.ROLE_ADMIN,
            is_staff=True
        )
        self.owner = User.objects.create_user(
            username='shop_owner_demo', password='Password123!', role=User.ROLE_SHOP_OWNER
        )
        self.customer = User.objects.create_user(
            username='customer_demo', password='Password123!', role=User.ROLE_CUSTOMER
        )

    def test_admin_can_access_platform_overview(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/v1/analytics/admin-overview/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('users', res.data)
        self.assertIn('shops', res.data)
        self.assertIn('orders', res.data)
        self.assertIn('payments', res.data)
        self.assertEqual(res.data['users']['administrators'], 1)
        self.assertEqual(res.data['users']['shop_owners'], 1)
        self.assertEqual(res.data['users']['customers'], 1)

    def test_customer_cannot_access_admin_overview(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.get('/api/v1/analytics/admin-overview/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_shop_owner_cannot_access_admin_overview(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get('/api/v1/analytics/admin-overview/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_access_admin_overview(self):
        res = self.client.get('/api/v1/analytics/admin-overview/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
