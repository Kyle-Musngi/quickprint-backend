from django.test import TestCase
from decimal import Decimal
from apps.shops.models import PrintingShop
from apps.printing.models import ShopPricingRule
from apps.printing.pricing_calculator import calculate_document_cost
from django.contrib.auth import get_user_model

User = get_user_model()


class PricingCalculatorTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='testowner', password='password123', role=User.ROLE_SHOP_OWNER)
        self.shop = PrintingShop.objects.create(
            owner=self.owner,
            name='Test Shop',
            email='test@shop.com',
            phone_number='09123456789',
            address='Taft Ave',
            status=PrintingShop.STATUS_APPROVED
        )
        # Pricing rules
        ShopPricingRule.objects.create(
            shop=self.shop, paper_size='A4', color_mode='bw', print_side='single', price_per_page=Decimal('1.50')
        )
        ShopPricingRule.objects.create(
            shop=self.shop, paper_size='A4', color_mode='bw', print_side='double', price_per_page=Decimal('2.50')
        )
        ShopPricingRule.objects.create(
            shop=self.shop, paper_size='A4', color_mode='color', print_side='single', price_per_page=Decimal('5.00')
        )

    def test_single_sided_bw_calculation(self):
        # 10 pages, 1 copy = 10 * 1.50 = 15.00
        res = calculate_document_cost(self.shop, 'A4', 'bw', 'single', page_count=10, copies=1)
        self.assertTrue(res['success'])
        self.assertEqual(res['calculated_total'], Decimal('15.00'))

    def test_single_sided_multiple_copies(self):
        # 10 pages, 3 copies = 30 * 1.50 = 45.00
        res = calculate_document_cost(self.shop, 'A4', 'bw', 'single', page_count=10, copies=3)
        self.assertTrue(res['success'])
        self.assertEqual(res['calculated_total'], Decimal('45.00'))

    def test_double_sided_calculation(self):
        # 10 pages double-sided = 5 sheets * 2.50 = 12.50
        res = calculate_document_cost(self.shop, 'A4', 'bw', 'double', page_count=10, copies=1)
        self.assertTrue(res['success'])
        self.assertEqual(res['billable_units'], 5)
        self.assertEqual(res['calculated_total'], Decimal('12.50'))

    def test_double_sided_odd_pages(self):
        # 9 pages double-sided = 5 sheets (ceil(9/2)) * 2.50 = 12.50
        res = calculate_document_cost(self.shop, 'A4', 'bw', 'double', page_count=9, copies=1)
        self.assertTrue(res['success'])
        self.assertEqual(res['billable_units'], 5)
        self.assertEqual(res['calculated_total'], Decimal('12.50'))

    def test_unsupported_pricing_rule_fails_gracefully(self):
        # Legal is not configured
        res = calculate_document_cost(self.shop, 'Legal', 'bw', 'single', page_count=5, copies=1)
        self.assertFalse(res['success'])
        self.assertIn("does not support", res['error'])

    def test_page_range_subset_pricing(self):
        # 10 page document, print only pages 1-4 (4 pages) -> 4 * 1.50 = 6.00
        res = calculate_document_cost(self.shop, 'A4', 'bw', 'single', page_count=10, copies=1, page_range='1-4')
        self.assertTrue(res['success'])
        self.assertEqual(res['effective_pages'], 4)
        self.assertEqual(res['physical_sheets'], 4)
        self.assertEqual(res['calculated_total'], Decimal('6.00'))

    def test_page_range_double_sided_odd(self):
        # 10 page document, print pages 1-3 (3 pages) double-sided -> ceil(3/2) = 2 sheets * 2.50 = 5.00
        res = calculate_document_cost(self.shop, 'A4', 'bw', 'double', page_count=10, copies=1, page_range='1-3')
        self.assertTrue(res['success'])
        self.assertEqual(res['effective_pages'], 3)
        self.assertEqual(res['physical_sheets'], 2)
        self.assertEqual(res['calculated_total'], Decimal('5.00'))

    def test_invalid_page_range_fails_gracefully(self):
        # Range exceeds page count
        res = calculate_document_cost(self.shop, 'A4', 'bw', 'single', page_count=10, copies=1, page_range='1-20')
        self.assertFalse(res['success'])
        self.assertIn("out of document bounds", res['error'])
