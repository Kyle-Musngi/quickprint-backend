from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.support.models import SupportQuestion

User = get_user_model()


class SupportQuestionAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            username='asker_juan', password='Pass123!', role=User.ROLE_CUSTOMER
        )

    def test_unauthenticated_user_cannot_submit_question(self):
        payload = {
            "subject": "How to pay via sandbox?",
            "category": "payment",
            "message": "Is real money required for GCash sandbox tests?"
        }
        res = self.client.post('/api/v1/support/questions/', payload)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_submit_and_retrieve_question(self):
        self.client.force_authenticate(user=self.student)
        payload = {
            "subject": "Pickup schedule question",
            "category": "order",
            "message": "Can I pick up after 6 PM?"
        }
        res = self.client.post('/api/v1/support/questions/', payload)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['subject'], "Pickup schedule question")
        self.assertEqual(res.data['status'], "open")
        self.assertEqual(res.data['category'], "order")

        # Verify retrieval
        get_res = self.client.get('/api/v1/support/questions/')
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        results = get_res.data.get('results', get_res.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['subject'], "Pickup schedule question")

    def test_blank_fields_rejected(self):
        self.client.force_authenticate(user=self.student)
        payload = {
            "subject": "",
            "category": "general",
            "message": "   "
        }
        res = self.client.post('/api/v1/support/questions/', payload)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_support_question_management(self):
        # Create an admin user and a shop owner
        admin = User.objects.create_user(username='admin_boss', password='Pass123!', role=User.ROLE_ADMIN)
        shop_owner = User.objects.create_user(username='owner_mike', password='Pass123!', role=User.ROLE_SHOP_OWNER)

        # Student creates question
        q = SupportQuestion.objects.create(
            user=self.student,
            subject="Binding options",
            category=SupportQuestion.CATEGORY_ORDER,
            message="Do shops support spiral binding?"
        )

        # Shop owner should be forbidden from admin support questions
        self.client.force_authenticate(user=shop_owner)
        res = self.client.get('/api/v1/support/admin/questions/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Student should be forbidden from admin support questions
        self.client.force_authenticate(user=self.student)
        res = self.client.get('/api/v1/support/admin/questions/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Admin can access admin support questions
        self.client.force_authenticate(user=admin)
        res = self.client.get('/api/v1/support/admin/questions/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get('results', res.data)
        self.assertEqual(len(results), 1)

        # Admin answers question
        ans_res = self.client.post(f'/api/v1/support/admin/questions/{q.id}/answer/', {
            "response": "Yes, spiral binding is available at select partner shops under Specialty Services.",
            "status": "answered"
        })
        self.assertEqual(ans_res.status_code, status.HTTP_200_OK)
        self.assertEqual(ans_res.data['status'], 'answered')
        self.assertEqual(ans_res.data['admin_response'], "Yes, spiral binding is available at select partner shops under Specialty Services.")
        self.assertIsNotNone(ans_res.data['answered_at'])

        # Customer views their own answered question
        self.client.force_authenticate(user=self.student)
        cust_res = self.client.get('/api/v1/support/questions/')
        self.assertEqual(cust_res.status_code, status.HTTP_200_OK)
        cust_results = cust_res.data.get('results', cust_res.data)
        self.assertEqual(cust_results[0]['status'], 'answered')
        self.assertIn("spiral binding is available", cust_results[0]['admin_response'])
