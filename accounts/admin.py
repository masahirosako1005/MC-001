from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "nickname", "is_staff", "is_active", "date_joined")
    list_filter = ("is_staff", "is_active")
    search_fields = ("nickname",)  # email は暗号化されているため検索対象外
    readonly_fields = ("email_hash", "date_joined", "last_login", "password")
    fields = ("nickname", "email", "email_hash", "is_active", "is_staff", "is_superuser",
              "groups", "user_permissions", "date_joined", "last_login", "password")
    filter_horizontal = ("groups", "user_permissions")
