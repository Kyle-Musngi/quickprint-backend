from django.contrib import admin
from .models import SupportQuestion


@admin.register(SupportQuestion)
class SupportQuestionAdmin(admin.ModelAdmin):
    list_display = ('subject', 'category', 'user', 'status', 'answered_by', 'created_at')
    list_filter = ('category', 'status', 'created_at')
    search_fields = ('subject', 'message', 'user__username', 'admin_response')
