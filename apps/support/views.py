from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from .models import SupportQuestion
from .serializers import SupportQuestionSerializer, SupportAnswerSerializer
from apps.accounts.permissions import IsPlatformAdmin
from apps.notifications.models import Notification


class SupportQuestionListCreateView(generics.ListCreateAPIView):
    serializer_class = SupportQuestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.role == 'admin' or user.is_superuser:
            qs = SupportQuestion.objects.all()
        else:
            qs = SupportQuestion.objects.filter(user=user)
        
        status_filter = self.request.query_params.get('status')
        if status_filter and status_filter != 'all':
            qs = qs.filter(status=status_filter)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AdminSupportQuestionListView(generics.ListAPIView):
    serializer_class = SupportQuestionSerializer
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get_queryset(self):
        qs = SupportQuestion.objects.all()
        status_filter = self.request.query_params.get('status')
        if status_filter and status_filter != 'all':
            qs = qs.filter(status=status_filter)
        category_filter = self.request.query_params.get('category')
        if category_filter and category_filter != 'all':
            qs = qs.filter(category=category_filter)
        return qs.order_by('-created_at')


class AdminSupportQuestionDetailView(generics.RetrieveAPIView):
    serializer_class = SupportQuestionSerializer
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]
    queryset = SupportQuestion.objects.all()


class AdminSupportQuestionAnswerView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk):
        question = generics.get_object_or_404(SupportQuestion, pk=pk)
        serializer = SupportAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reply_text = serializer.validated_data['response'].strip()
        new_status = serializer.validated_data.get('status', SupportQuestion.STATUS_ANSWERED)

        if not reply_text:
            return Response({"error": "Answer response cannot be blank."}, status=status.HTTP_400_BAD_REQUEST)

        question.admin_response = reply_text
        question.answered_by = request.user
        question.answered_at = timezone.now()
        question.status = new_status
        question.save(update_fields=['admin_response', 'answered_by', 'answered_at', 'status', 'updated_at'])

        # Notify the question author
        Notification.send(
            recipient=question.user,
            title="Your Question Has Been Answered",
            message=f"Administrator {request.user.full_name} answered your support question: '{question.subject}'.",
            notification_type=Notification.TYPE_GENERAL,
            link="/customer/questions"
        )

        return Response(SupportQuestionSerializer(question).data, status=status.HTTP_200_OK)
