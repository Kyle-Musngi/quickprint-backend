import io
import json
import zipfile
import pypdf
from decimal import Decimal
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from apps.shops.models import PrintingShop
from apps.orders.models import PrintingOrder, OrderDocument, GlobalPickupSequence
from apps.printing.models import ShopPricingRule
from apps.orders.document_inspector import MAX_UPLOAD_SIZE

User = get_user_model()


def make_pdf_bytes(num_pages=1):
    writer = pypdf.PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_docx_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>'
        )
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'
        )
        doc = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Hello QuickPrint Document</w:t></w:r></w:p></w:body>'
            '</w:document>'
        )
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', doc)
    return buf.getvalue()


class OrderAndPickupSequenceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(username='customer1', password='passWord123!', role=User.ROLE_CUSTOMER)
        self.other_customer = User.objects.create_user(username='customer2', password='passWord123!', role=User.ROLE_CUSTOMER)
        self.shop_owner = User.objects.create_user(username='shopowner1', password='passWord123!', role=User.ROLE_SHOP_OWNER)
        
        self.shop = PrintingShop.objects.create(
            owner=self.shop_owner,
            name='Alpha Prints',
            email='alpha@print.ph',
            phone_number='09123334444',
            address='Taft Avenue',
            status=PrintingShop.STATUS_APPROVED
        )

        self.order = PrintingOrder.objects.create(
            customer=self.customer,
            shop=self.shop,
            total_amount=Decimal('50.00'),
            status=PrintingOrder.STATUS_SUBMITTED
        )

    def test_global_pickup_sequence_format_and_continuity(self):
        GlobalPickupSequence.objects.all().delete()
        code1 = GlobalPickupSequence.get_next_pickup_code()
        code2 = GlobalPickupSequence.get_next_pickup_code()
        code3 = GlobalPickupSequence.get_next_pickup_code()

        self.assertEqual(code1, 'UQP01')
        self.assertEqual(code2, 'UQP02')
        self.assertEqual(code3, 'UQP03')

    def test_customer_cannot_accept_order(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(f"/api/v1/orders/{self.order.id}/accept/")
        self.assertEqual(response.status_code, 403)

    def test_shop_owner_accepts_order_assigns_pickup_code(self):
        self.client.force_authenticate(user=self.shop_owner)
        response = self.client.post(f"/api/v1/orders/{self.order.id}/accept/")
        self.assertEqual(response.status_code, 200)
        
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PrintingOrder.STATUS_ACCEPTED)
        self.assertTrue(self.order.pickup_code.startswith('UQP'))

    def test_customer_cannot_view_unrelated_order(self):
        self.client.force_authenticate(user=self.other_customer)
        response = self.client.get(f"/api/v1/orders/{self.order.id}/")
        self.assertEqual(response.status_code, 403)

    def test_cannot_accept_order_if_shop_suspended(self):
        self.shop.status = PrintingShop.STATUS_SUSPENDED
        self.shop.save()
        self.client.force_authenticate(user=self.shop_owner)
        response = self.client.post(f"/api/v1/orders/{self.order.id}/accept/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("inactive/suspended", response.data['error'])


class AutomaticDocumentPageCountAndPricingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(username='student_user', password='passWord123!', role=User.ROLE_CUSTOMER)
        self.shop_owner_a = User.objects.create_user(username='owner_a', password='passWord123!', role=User.ROLE_SHOP_OWNER)
        self.shop_owner_b = User.objects.create_user(username='owner_b', password='passWord123!', role=User.ROLE_SHOP_OWNER)

        # Shop A: Taft Prints
        self.shop_a = PrintingShop.objects.create(
            owner=self.shop_owner_a,
            name='Taft Campus Prints',
            email='taft@quickprint.ph',
            phone_number='09111111111',
            address='Taft Avenue',
            status=PrintingShop.STATUS_APPROVED
        )

        # Shop B: Katipunan Express
        self.shop_b = PrintingShop.objects.create(
            owner=self.shop_owner_b,
            name='Katipunan Express',
            email='katipunan@quickprint.ph',
            phone_number='09222222222',
            address='Katipunan Avenue',
            status=PrintingShop.STATUS_APPROVED
        )

        # Shop A Pricing Rules
        # A4 B&W Single: 1.50
        ShopPricingRule.objects.create(shop=self.shop_a, paper_size='A4', color_mode='bw', print_side='single', price_per_page=Decimal('1.50'))
        # A4 B&W Double: 2.50 (per sheet)
        ShopPricingRule.objects.create(shop=self.shop_a, paper_size='A4', color_mode='bw', print_side='double', price_per_page=Decimal('2.50'))
        # A4 Color Single: 5.00
        ShopPricingRule.objects.create(shop=self.shop_a, paper_size='A4', color_mode='color', print_side='single', price_per_page=Decimal('5.00'))

        # Shop B Pricing Rules (Different rates)
        # A4 B&W Single: 2.00
        ShopPricingRule.objects.create(shop=self.shop_b, paper_size='A4', color_mode='bw', print_side='single', price_per_page=Decimal('2.00'))
        # A4 Color Single: 7.50
        ShopPricingRule.objects.create(shop=self.shop_b, paper_size='A4', color_mode='color', print_side='single', price_per_page=Decimal('7.50'))

    def test_one_page_pdf_detection(self):
        pdf_content = make_pdf_bytes(1)
        pdf_file = SimpleUploadedFile("single_page.pdf", pdf_content, content_type="application/pdf")

        response = self.client.post("/api/v1/orders/detect-pages/", {"file": pdf_file}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["page_count"], 1)
        self.assertEqual(response.data["doc_type"], "PDF")
        self.assertEqual(response.data["status"], "Ready to print")

    def test_multipage_pdf_detection(self):
        pdf_content = make_pdf_bytes(6)
        pdf_file = SimpleUploadedFile("research_paper.pdf", pdf_content, content_type="application/pdf")

        response = self.client.post("/api/v1/orders/detect-pages/", {"file": pdf_file}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["page_count"], 6)
        self.assertEqual(response.data["doc_type"], "PDF")
        self.assertEqual(response.data["status"], "Ready to print")

    def test_empty_file_rejected(self):
        empty_file = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")

        response = self.client.post("/api/v1/orders/detect-pages/", {"file": empty_file}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("empty (0 bytes)", response.data["error"])

    def test_corrupt_file_rejected(self):
        corrupt_file = SimpleUploadedFile("broken.pdf", b"NOT_A_REAL_PDF_DATA", content_type="application/pdf")

        response = self.client.post("/api/v1/orders/detect-pages/", {"file": corrupt_file}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not match its '.pdf' extension", response.data["error"])

    def test_unsupported_format_rejected(self):
        unsupported_file = SimpleUploadedFile("program.exe", b"MZ\x90\x00\x03\x00\x00\x00", content_type="application/octet-stream")

        response = self.client.post("/api/v1/orders/detect-pages/", {"file": unsupported_file}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported document format", response.data["error"])

    def test_file_exceeding_upload_limit_rejected(self):
        # 25MB + 512 bytes payload
        huge_bytes = b"%PDF-1.4\n" + (b"0" * (MAX_UPLOAD_SIZE + 512))
        huge_file = SimpleUploadedFile("huge.pdf", huge_bytes, content_type="application/pdf")

        response = self.client.post("/api/v1/orders/detect-pages/", {"file": huge_file}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds the maximum allowed upload limit", response.data["error"])

    def test_docx_document_detection_and_limitation_handling(self):
        docx_content = make_docx_bytes()
        docx_file = SimpleUploadedFile("thesis.docx", docx_content, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

        response = self.client.post("/api/v1/orders/detect-pages/", {"file": docx_file}, format="multipart")
        # In test environment without LibreOffice headless binary, server returns clear explanation
        # rather than guessing an inaccurate page count
        if response.status_code == 200:
            self.assertIn("Word", response.data["doc_type"])
            self.assertGreaterEqual(response.data["page_count"], 1)
        else:
            self.assertEqual(response.status_code, 400)
            self.assertIn("Word documents", response.data["error"])
            self.assertIn("PDF", response.data["error"])

    def test_image_document_detection(self):
        # Create a small valid PNG in-memory
        from PIL import Image
        img_buf = io.BytesIO()
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(img_buf, format='PNG')
        img_file = SimpleUploadedFile("photo.png", img_buf.getvalue(), content_type="image/png")

        response = self.client.post("/api/v1/orders/detect-pages/", {"file": img_file}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["page_count"], 1)
        self.assertIn("Image", response.data["doc_type"])

    def test_order_creation_verifies_page_count_ignoring_client_tampering(self):
        self.client.force_authenticate(user=self.customer)

        # Upload 4-page PDF, but client sends manual_page_count: 1
        pdf_content = make_pdf_bytes(4)
        pdf_file = SimpleUploadedFile("actual_4_pages.pdf", pdf_content, content_type="application/pdf")

        tampered_settings = [
            {
                "paper_size": "A4",
                "color_mode": "bw",
                "print_side": "single",
                "copies": 1,
                "manual_page_count": 1,  # Client tries to pay for only 1 page
            }
        ]

        data = {
            "shop_id": self.shop_a.id,
            "instructions": "Leave at front desk",
            "file_settings": json.dumps(tampered_settings),
            "files": [pdf_file]
        }

        response = self.client.post("/api/v1/orders/create/", data, format="multipart")
        self.assertEqual(response.status_code, 201)

        created_order = PrintingOrder.objects.get(id=response.data["id"])
        doc = created_order.documents.first()

        # Backend MUST have independently verified 4 pages and billed accordingly (4 * 1.50 = 6.00)
        self.assertEqual(doc.page_count, 4)
        self.assertEqual(doc.calculated_total, Decimal("6.00"))
        self.assertEqual(created_order.total_amount, Decimal("6.00"))

    def test_single_sided_vs_double_sided_pricing_calculation(self):
        # 5 pages:
        # Single-sided: 5 sheets * 1.50 = 7.50
        # Double-sided: ceil(5/2) = 3 sheets * 2.50 = 7.50 (for rate 2.50/sheet)
        items_single = [
            {"paper_size": "A4", "color_mode": "bw", "print_side": "single", "page_count": 5, "copies": 1}
        ]
        res_single = self.client.post("/api/v1/printing/estimate/", {"shop_id": self.shop_a.id, "items": items_single}, format="json")
        self.assertEqual(res_single.status_code, 200)
        self.assertEqual(res_single.data["breakdown"][0]["physical_sheets"], 5)
        self.assertEqual(res_single.data["breakdown"][0]["document_pages"], 5)
        self.assertEqual(Decimal(res_single.data["total"]), Decimal("7.50"))

        items_double = [
            {"paper_size": "A4", "color_mode": "bw", "print_side": "double", "page_count": 5, "copies": 1}
        ]
        res_double = self.client.post("/api/v1/printing/estimate/", {"shop_id": self.shop_a.id, "items": items_double}, format="json")
        self.assertEqual(res_double.status_code, 200)
        # ceil(5/2) = 3 physical sheets back-to-back
        self.assertEqual(res_double.data["breakdown"][0]["physical_sheets"], 3)
        self.assertEqual(res_double.data["breakdown"][0]["document_pages"], 5)
        # 3 sheets * 2.50 = 7.50
        self.assertEqual(Decimal(res_double.data["total"]), Decimal("7.50"))

    def test_multiple_copies_calculation(self):
        # 5 pages, 3 copies single-sided: 5 pages * 1.50 * 3 copies = 22.50
        items = [
            {"paper_size": "A4", "color_mode": "bw", "print_side": "single", "page_count": 5, "copies": 3}
        ]
        res = self.client.post("/api/v1/printing/estimate/", {"shop_id": self.shop_a.id, "items": items}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Decimal(res.data["total"]), Decimal("22.50"))

    def test_color_and_black_and_white_pricing(self):
        # 4 pages A4:
        # B&W Single: 4 * 1.50 = 6.00
        # Color Single: 4 * 5.00 = 20.00
        items_bw = [{"paper_size": "A4", "color_mode": "bw", "print_side": "single", "page_count": 4, "copies": 1}]
        res_bw = self.client.post("/api/v1/printing/estimate/", {"shop_id": self.shop_a.id, "items": items_bw}, format="json")
        self.assertEqual(Decimal(res_bw.data["total"]), Decimal("6.00"))

        items_color = [{"paper_size": "A4", "color_mode": "color", "print_side": "single", "page_count": 4, "copies": 1}]
        res_color = self.client.post("/api/v1/printing/estimate/", {"shop_id": self.shop_a.id, "items": items_color}, format="json")
        self.assertEqual(Decimal(res_color.data["total"]), Decimal("20.00"))

    def test_recalculation_when_changing_shop(self):
        # 10 pages A4 B&W Single:
        # Shop A: 10 * 1.50 = 15.00
        # Shop B: 10 * 2.00 = 20.00
        items = [{"paper_size": "A4", "color_mode": "bw", "print_side": "single", "page_count": 10, "copies": 1}]

        res_a = self.client.post("/api/v1/printing/estimate/", {"shop_id": self.shop_a.id, "items": items}, format="json")
        self.assertEqual(Decimal(res_a.data["total"]), Decimal("15.00"))

        res_b = self.client.post("/api/v1/printing/estimate/", {"shop_id": self.shop_b.id, "items": items}, format="json")
        self.assertEqual(Decimal(res_b.data["total"]), Decimal("20.00"))


class PaymentAfterAcceptanceWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            username='student_workflow', password='passWord123!', role=User.ROLE_CUSTOMER,
            first_name='Juan', last_name='Dela Cruz'
        )
        self.other_customer = User.objects.create_user(
            username='other_student', password='passWord123!', role=User.ROLE_CUSTOMER
        )
        self.owner = User.objects.create_user(
            username='shop_owner_wf', password='passWord123!', role=User.ROLE_SHOP_OWNER
        )
        self.shop = PrintingShop.objects.create(
            owner=self.owner,
            name='Cebu Workflow Hub',
            email='hub@cebu.ph',
            phone_number='032 555 1234',
            address='Jones Ave',
            city='Cebu City',
            status=PrintingShop.STATUS_APPROVED
        )
        self.order = PrintingOrder.objects.create(
            customer=self.customer,
            shop=self.shop,
            total_amount=Decimal('45.00'),
            status=PrintingOrder.STATUS_PENDING_ACCEPTANCE,
            payment_status='unpaid'
        )

    def test_new_order_starts_as_pending_acceptance_unpaid(self):
        self.assertEqual(self.order.status, PrintingOrder.STATUS_PENDING_ACCEPTANCE)
        self.assertEqual(self.order.payment_status, 'unpaid')
        self.assertIsNone(self.order.payment_deadline)

    def test_payment_blocked_while_pending_acceptance(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post('/api/v1/payments/process/', {
            'order_id': self.order.id,
            'payment_method': 'gcash',
            'simulated_outcome': 'success'
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("pending shop review", response.data['error'])

    def test_shop_rejects_order_no_payment_possible(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(f"/api/v1/orders/{self.order.id}/reject/", {
            'rejection_reason': 'Out of 80gsm paper stocks'
        })
        self.assertEqual(res.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PrintingOrder.STATUS_REJECTED)
        self.assertEqual(self.order.rejection_reason, 'Out of 80gsm paper stocks')
        self.assertEqual(self.order.payment_status, 'unpaid')

        # Customer attempts to pay rejected order
        self.client.force_authenticate(user=self.customer)
        pay_res = self.client.post('/api/v1/payments/process/', {
            'order_id': self.order.id,
            'payment_method': 'gcash',
            'simulated_outcome': 'success'
        })
        self.assertEqual(pay_res.status_code, 400)

    def test_shop_accepts_order_transitions_to_awaiting_payment_with_deadline(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(f"/api/v1/orders/{self.order.id}/accept/")
        self.assertEqual(res.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PrintingOrder.STATUS_AWAITING_PAYMENT)
        self.assertIsNotNone(self.order.payment_deadline)
        self.assertTrue(self.order.pickup_code.startswith('UQP'))

    def test_shop_cannot_start_production_before_payment(self):
        # Accept order
        self.order.status = PrintingOrder.STATUS_AWAITING_PAYMENT
        self.order.save()

        self.client.force_authenticate(user=self.owner)
        res = self.client.post(f"/api/v1/orders/{self.order.id}/start-printing/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("unpaid", res.data['error'].lower())

    def test_successful_sandbox_payment_transitions_order_to_in_production(self):
        # Move order to awaiting payment
        self.client.force_authenticate(user=self.owner)
        self.client.post(f"/api/v1/orders/{self.order.id}/accept/")

        # Customer pays successfully
        self.client.force_authenticate(user=self.customer)
        pay_res = self.client.post('/api/v1/payments/process/', {
            'order_id': self.order.id,
            'payment_method': 'gcash',
            'simulated_outcome': 'success'
        })
        self.assertEqual(pay_res.status_code, 201)
        self.assertEqual(pay_res.data['payment_status'], 'paid')
        self.assertEqual(pay_res.data['order_status'], PrintingOrder.STATUS_IN_PRODUCTION)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertEqual(self.order.status, PrintingOrder.STATUS_IN_PRODUCTION)

    def test_failed_sandbox_payment_keeps_order_awaiting_payment(self):
        self.client.force_authenticate(user=self.owner)
        self.client.post(f"/api/v1/orders/{self.order.id}/accept/")

        # Customer attempts payment with failure simulation
        self.client.force_authenticate(user=self.customer)
        pay_res = self.client.post('/api/v1/payments/process/', {
            'order_id': self.order.id,
            'payment_method': 'maya',
            'simulated_outcome': 'failure'
        })
        self.assertEqual(pay_res.status_code, 201)
        self.assertEqual(pay_res.data['payment_status'], 'failed')
        self.assertEqual(pay_res.data['order_status'], PrintingOrder.STATUS_AWAITING_PAYMENT)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'failed')
        self.assertEqual(self.order.status, PrintingOrder.STATUS_AWAITING_PAYMENT)

    def test_duplicate_payment_blocked_for_already_paid_order(self):
        self.order.status = PrintingOrder.STATUS_IN_PRODUCTION
        self.order.payment_status = 'paid'
        self.order.save()

        self.client.force_authenticate(user=self.customer)
        pay_res = self.client.post('/api/v1/payments/process/', {
            'order_id': self.order.id,
            'payment_method': 'gcash',
            'simulated_outcome': 'success'
        })
        self.assertEqual(pay_res.status_code, 400)
        self.assertIn("already paid", pay_res.data['error'])

    def test_expired_payment_deadline_blocks_payment(self):
        from django.utils import timezone
        self.order.status = PrintingOrder.STATUS_AWAITING_PAYMENT
        self.order.payment_deadline = timezone.now() - timezone.timedelta(hours=1)
        self.order.save()

        self.client.force_authenticate(user=self.customer)
        pay_res = self.client.post('/api/v1/payments/process/', {
            'order_id': self.order.id,
            'payment_method': 'gcash',
            'simulated_outcome': 'success'
        })
        self.assertEqual(pay_res.status_code, 400)
        self.assertIn("expired", pay_res.data['error'])

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PrintingOrder.STATUS_EXPIRED)

    def test_full_production_and_pickup_completion(self):
        self.order.status = PrintingOrder.STATUS_IN_PRODUCTION
        self.order.payment_status = 'paid'
        self.order.pickup_code = 'UQP99'
        self.order.save()

        self.client.force_authenticate(user=self.owner)
        ready_res = self.client.post(f"/api/v1/orders/{self.order.id}/ready-for-pickup/")
        self.assertEqual(ready_res.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PrintingOrder.STATUS_READY_FOR_PICKUP)

        # Confirm pickup
        confirm_res = self.client.post(f"/api/v1/orders/{self.order.id}/confirm-pickup/", {
            'pickup_code': 'UQP99'
        })
        self.assertEqual(confirm_res.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PrintingOrder.STATUS_COMPLETED)

