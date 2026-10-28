from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from datetime import time
from apps.shops.models import PrintingShop
from django.contrib.auth import get_user_model

User = get_user_model()


class ShopOperatingHoursAndStatusTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username='cebu_owner', password='OwnerPass123!', role=User.ROLE_SHOP_OWNER
        )
        self.other_owner = User.objects.create_user(
            username='other_owner', password='OwnerPass123!', role=User.ROLE_SHOP_OWNER
        )
        self.student = User.objects.create_user(
            username='student_juan', password='StudentPass123!', role=User.ROLE_CUSTOMER
        )

        self.shop = PrintingShop.objects.create(
            owner=self.owner,
            name='Cebu Test Printing',
            email='cebu@print.ph',
            phone_number='032 123 4567',
            address='Osmeña Boulevard',
            city='Cebu City',
            status=PrintingShop.STATUS_APPROVED,
            opening_time=time(7, 30),
            closing_time=time(19, 30),
            operating_days='Monday - Saturday'
        )

    def test_public_shop_listing_excludes_pending_and_suspended_shops(self):
        pending_shop = PrintingShop.objects.create(
            owner=self.other_owner,
            name='Pending Demo Shop',
            email='pending@test.ph',
            phone_number='032 999 8888',
            address='Mandaue',
            city='Cebu City',
            status=PrintingShop.STATUS_PENDING
        )
        suspended_shop = PrintingShop.objects.create(
            owner=self.other_owner,
            name='Suspended Demo Shop',
            email='suspended@test.ph',
            phone_number='032 777 6666',
            address='Banilad',
            city='Cebu City',
            status=PrintingShop.STATUS_SUSPENDED
        )

        res = self.client.get('/api/v1/shops/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        shop_names = [s['name'] for s in res.data['results']]
        self.assertIn('Cebu Test Printing', shop_names)
        self.assertNotIn('Pending Demo Shop', shop_names)
        self.assertNotIn('Suspended Demo Shop', shop_names)

    def test_get_shop_operating_hours_initializes_seven_days(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get('/api/v1/shops/my-shop/operating-hours/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 7)
        days = [item['day_of_week'] for item in res.data]
        self.assertEqual(days, [0, 1, 2, 3, 4, 5, 6])

    def test_update_shop_operating_hours_success(self):
        self.client.force_authenticate(user=self.owner)
        payload = [
            {"day_of_week": 0, "is_open": True, "opening_time": "08:00:00", "closing_time": "17:00:00"},
            {"day_of_week": 1, "is_open": False, "opening_time": "08:00:00", "closing_time": "17:00:00"},
            {"day_of_week": 2, "is_open": True, "opening_time": "08:00:00", "closing_time": "17:00:00"},
            {"day_of_week": 3, "is_open": False, "opening_time": "08:00:00", "closing_time": "17:00:00"},
            {"day_of_week": 4, "is_open": True, "opening_time": "08:00:00", "closing_time": "17:00:00"},
            {"day_of_week": 5, "is_open": False, "opening_time": "08:00:00", "closing_time": "17:00:00"},
            {"day_of_week": 6, "is_open": False, "opening_time": "08:00:00", "closing_time": "17:00:00"},
        ]
        res = self.client.put('/api/v1/shops/my-shop/operating-hours/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.shop.refresh_from_db()
        self.assertEqual(self.shop.operating_days, "Monday, Wednesday, Friday")

    def test_operating_hours_rejects_identical_open_and_close_time(self):
        self.client.force_authenticate(user=self.owner)
        payload = [
            {"day_of_week": 0, "is_open": True, "opening_time": "08:00:00", "closing_time": "08:00:00"}
        ]
        res = self.client.put('/api/v1/shops/my-shop/operating-hours/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_cannot_modify_shop_operating_hours(self):
        self.client.force_authenticate(user=self.student)
        payload = [
            {"day_of_week": 0, "is_open": True, "opening_time": "08:00:00", "closing_time": "17:00:00"}
        ]
        res = self.client.put('/api/v1/shops/my-shop/operating-hours/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class ShopRatingsAndReviewsTests(TestCase):
    def setUp(self):
        from decimal import Decimal
        from apps.orders.models import PrintingOrder
        from apps.shops.models import ShopReview

        self.client = APIClient()
        self.customer = User.objects.create_user(
            username='rating_student', password='PassWord123!', role=User.ROLE_CUSTOMER,
            first_name='Maria', last_name='Santos'
        )
        self.other_customer = User.objects.create_user(
            username='other_student_rating', password='PassWord123!', role=User.ROLE_CUSTOMER,
            first_name='Pedro', last_name='Penduko'
        )
        self.owner = User.objects.create_user(
            username='rating_owner', password='PassWord123!', role=User.ROLE_SHOP_OWNER
        )
        self.shop = PrintingShop.objects.create(
            owner=self.owner,
            name='Cebu Tech Printing',
            email='tech@cebu.ph',
            phone_number='032 444 8888',
            address='Lahug',
            city='Cebu City',
            status=PrintingShop.STATUS_APPROVED
        )

        self.order = PrintingOrder.objects.create(
            customer=self.customer,
            shop=self.shop,
            total_amount=Decimal('80.00'),
            status=PrintingOrder.STATUS_COMPLETED,
            payment_status='paid'
        )

    def test_unrated_shop_has_zero_reviews(self):
        self.assertEqual(self.shop.review_count, 0)
        self.assertIsNone(self.shop.average_rating)

        res = self.client.get(f"/api/v1/shops/{self.shop.id}/reviews/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['review_count'], 0)
        self.assertEqual(len(res.data['reviews']), 0)

    def test_customer_cannot_review_pending_or_uncompleted_order(self):
        from apps.orders.models import PrintingOrder
        self.order.status = PrintingOrder.STATUS_PENDING_ACCEPTANCE
        self.order.save()

        self.client.force_authenticate(user=self.customer)
        res = self.client.post(f"/api/v1/shops/{self.shop.id}/reviews/", {
            'order_id': self.order.id,
            'rating': 5,
            'review_text': 'Great service!'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("completed", res.data['error'])

    def test_customer_cannot_review_other_customers_order(self):
        self.client.force_authenticate(user=self.other_customer)
        res = self.client.post(f"/api/v1/shops/{self.shop.id}/reviews/", {
            'order_id': self.order.id,
            'rating': 5,
            'review_text': 'Trying to review another person order'
        })
        self.assertEqual(res.status_code, 403)

    def test_customer_submits_valid_review_and_average_updates(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.post(f"/api/v1/shops/{self.shop.id}/reviews/", {
            'order_id': self.order.id,
            'rating': 5,
            'review_text': 'Excellent fast thesis print!'
        })
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['rating'], 5)
        self.assertEqual(res.data['customer_name'], 'Maria Santos')

        self.shop.refresh_from_db()
        self.assertEqual(self.shop.review_count, 1)
        self.assertEqual(self.shop.average_rating, 5.0)

    def test_duplicate_review_for_same_order_is_blocked(self):
        from apps.shops.models import ShopReview
        ShopReview.objects.create(
            shop=self.shop,
            customer=self.customer,
            order=self.order,
            rating=4,
            review_text='First review'
        )

        self.client.force_authenticate(user=self.customer)
        res = self.client.post(f"/api/v1/shops/{self.shop.id}/reviews/", {
            'order_id': self.order.id,
            'rating': 5,
            'review_text': 'Second review attempt'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("already reviewed", res.data['error'])

    def test_invalid_star_ratings_are_rejected(self):
        self.client.force_authenticate(user=self.customer)
        # Rating 0 (below 1)
        res_zero = self.client.post(f"/api/v1/shops/{self.shop.id}/reviews/", {
            'order_id': self.order.id,
            'rating': 0
        })
        self.assertEqual(res_zero.status_code, 400)

        # Rating 6 (above 5)
        res_six = self.client.post(f"/api/v1/shops/{self.shop.id}/reviews/", {
            'order_id': self.order.id,
            'rating': 6
        })
        self.assertEqual(res_six.status_code, 400)

    def test_shop_owner_can_view_my_shop_reviews(self):
        from apps.shops.models import ShopReview
        ShopReview.objects.create(
            shop=self.shop,
            customer=self.customer,
            order=self.order,
            rating=5,
            review_text='Awesome print quality'
        )

        self.client.force_authenticate(user=self.owner)
        res = self.client.get('/api/v1/shops/my-shop/reviews/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['review_count'], 1)
        self.assertEqual(res.data['average_rating'], 5.0)
        self.assertEqual(len(res.data['reviews']), 1)
        self.assertEqual(res.data['reviews'][0]['review_text'], 'Awesome print quality')

    def test_admin_can_suspend_and_reactivate_shop(self):
        admin = User.objects.create_user(username='super_admin', password='AdminPass123!', role=User.ROLE_ADMIN)
        self.client.force_authenticate(user=admin)

        # Suspend shop with reason
        res = self.client.post(f'/api/v1/shops/admin/{self.shop.id}/action/', {
            'action': 'suspend',
            'reason': 'Violating student data privacy policy'
        })
        self.assertEqual(res.status_code, 200)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.status, PrintingShop.STATUS_SUSPENDED)
        self.assertFalse(self.shop.is_active)
        self.assertEqual(self.shop.rejection_reason, 'Violating student data privacy policy')

        # Reactivate shop
        res_reactivate = self.client.post(f'/api/v1/shops/admin/{self.shop.id}/action/', {
            'action': 'reactivate'
        })
        self.assertEqual(res_reactivate.status_code, 200)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.status, PrintingShop.STATUS_APPROVED)
        self.assertTrue(self.shop.is_active)

    def test_customer_shop_application_and_admin_approval(self):
        customer = User.objects.create_user(username='applicant_cust', password='CustPass123!', role=User.ROLE_CUSTOMER)
        self.client.force_authenticate(user=customer)
        payload = {
            'name': 'Campus Quick Print Hub',
            'email': 'hub@campusprint.ph',
            'phone_number': '032 555 1234',
            'address': 'Lahug Main Gate',
            'city': 'Cebu City'
        }
        # 1. Customer submits shop application -> 201 Created
        res = self.client.post('/api/v1/shops/register/', payload)
        self.assertEqual(res.status_code, 201)
        
        # 2. Customer remains a customer before approval
        customer.refresh_from_db()
        self.assertEqual(customer.role, User.ROLE_CUSTOMER)

        # 3. Admin reviews and approves application
        admin_user = User.objects.create_user(username='admin_reviewer', password='AdminPass123!', role=User.ROLE_ADMIN)
        self.client.force_authenticate(user=admin_user)
        shop_id = res.data['shop']['id']
        approve_res = self.client.post(f'/api/v1/shops/admin/{shop_id}/action/', {'action': 'approve'})
        self.assertEqual(approve_res.status_code, 200)

        # 4. Verified: Account is elevated to SHOP_OWNER
        customer.refresh_from_db()
        self.assertEqual(customer.role, User.ROLE_SHOP_OWNER)

