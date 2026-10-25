from rest_framework import serializers
from .models import SupportQuestion
from apps.accounts.serializers import UserSerializer


class SupportQuestionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    answered_by = UserSerializer(read_only=True)

    class Meta:
        model = SupportQuestion
        fields = [
            'id', 'user', 'subject', 'category', 'category_display',
            'message', 'status', 'status_display', 'admin_response',
            'answered_by', 'answered_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'admin_response', 'answered_by', 'answered_at', 'created_at', 'updated_at']

    def validate_subject(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Subject cannot be blank.")
        return value.strip()

    def validate_message(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Question details cannot be blank.")
        return value.strip()


class SupportAnswerSerializer(serializers.Serializer):
    response = serializers.CharField(required=True, allow_blank=False)
    status = serializers.ChoiceField(
        choices=[
            SupportQuestion.STATUS_OPEN,
            SupportQuestion.STATUS_IN_PROGRESS,
            SupportQuestion.STATUS_ANSWERED,
            SupportQuestion.STATUS_RESOLVED,
        ],
        default=SupportQuestion.STATUS_ANSWERED,
        required=False
    )
