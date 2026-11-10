from django.contrib import admin

from .models import Signage


@admin.register(Signage)
class SignageAdmin(admin.ModelAdmin):
    list_display = ("name", "headline", "is_active", "updated_at")
    readonly_fields = ("display_key", "updated_by", "created_at", "updated_at")
