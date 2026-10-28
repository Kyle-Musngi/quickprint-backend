from django.test import TestCase
from rest_framework.test import APIClient
from decimal import Decimal
from django.contrib.auth import get_user_model
from apps.shops.models import PrintingShop
from apps.orders.models import PrintingOrder
from apps.payments.models import PaymentTransaction, RefundRequest, RefundAuditLog

User = get_user_model()


class PaymentAndRefundWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(username='shopowner_pay', password='OwnerPass123!', role=User.ROLE_SHOP_OWNER)
        self.customer = User.objects.create_user(username='cust_pay', password='CustPass123!', role=User.ROLE_CUSTOMER)
        self.admin = User.objects.create_user(username='admin_pay', password='AdminPass123!', role=User.ROLE_ADMIN)

        self.shop = PrintingShop.objects.create(
            owner=self.owner,
            name='Test Payment Print Shop',
            email='pay@testshop.ph',
            phone_number='09170000000',
            address='Taft Ave',
            city='Manila',
            status=PrintingShop.STATUS_APPROVED,
            is_active=True
        )

        self.order = PrintingOrder.objects.create(
            customer=self.customer,
            shop=self.shop,
            order_number='UQP-TEST001',
            status=PrintingOrder.STATUS_AWAITING_PAYMENT,
            payment_status=PrintingOrder.PAYMENT_STATUS_UNPAID,
            subtotal_amount=Decimal('150.00'),
            total_amount=Decimal('150.00')
        )

    def test_payment_and_refund_lifecycle(self):
        # 1. Customer executes sandbox payment
        self.client.force_authenticate(user=self.customer)
        pay_res = self.client.post('/api/v1/payments/process/', {
            'order_id': self.order.id,
            'payment_method': 'gcash',
            'simulated_outcome': 'success'
        })
        self.assertEqual(pay_res.status_code, 201)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PrintingOrder.PAYMENT_STATUS_PAID)

        # 2. Check refund eligibility
        elig_res = self.client.get(f'/api/v1/payments/refunds/eligibility/?order_id={self.order.id}')
        self.assertEqual(elig_res.status_code, 200)
        self.assertTrue(elig_res.data['is_eligible'])
        self.assertEqual(Decimal(str(elig_res.data['remaining_refundable'])), Decimal('150.00'))

        # 3. Customer submits refund request
        req_res = self.client.post('/api/v1/payments/refunds/request/', {
            'order_id': self.order.id,
            'reason': 'shop_cannot_fulfill',
            'explanation': 'Shop ran out of specialized paper.',
            'amount_requested': '150.00'
        })
        self.assertEqual(req_res.status_code, 201)
        refund_id = req_res.data['refund']['id']
        self.assertEqual(req_res.data['refund']['status'], 'pending')

        # 4. Duplicate request rejected
        dup_res = self.client.post('/api/v1/payments/refunds/request/', {
            'order_id': self.order.id,
            'reason': 'duplicate_payment',
            'amount_requested': '150.00'
        })
        self.assertEqual(dup_res.status_code, 400)

        # 5. Shop owner reviews and approves the refund
        self.client.force_authenticate(user=self.owner)
        approve_res = self.client.post(f'/api/v1/payments/refunds/{refund_id}/action/', {
            'action': 'approve',
            'decision_reason': 'Verified inventory shortage. Full refund approved.'
        })
        self.assertEqual(approve_res.status_code, 200)
        self.assertEqual(approve_res.data['refund']['status'], 'completed')

        # 6. Check order status updated to refunded
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'refunded')

        # 7. Audit log verified
        refund = RefundRequest.objects.get(pk=refund_id)
        self.assertTrue(refund.audit_logs.filter(action='approved_and_completed').exists())
