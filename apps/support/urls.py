from django.urls import path
from .views import (
    SupportQuestionListCreateView,
    AdminSupportQuestionListView,
    AdminSupportQuestionDetailView,
    AdminSupportQuestionAnswerView,
)

urlpatterns = [
    path('questions/', SupportQuestionListCreateView.as_view(), name='support-questions'),
    path('admin/questions/', AdminSupportQuestionListView.as_view(), name='admin-support-questions'),
    path('admin/questions/<int:pk>/', AdminSupportQuestionDetailView.as_view(), name='admin-support-question-detail'),
    path('admin/questions/<int:pk>/answer/', AdminSupportQuestionAnswerView.as_view(), name='admin-support-question-answer'),
]
