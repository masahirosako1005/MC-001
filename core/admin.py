from django import forms
from django.contrib import admin
from django.utils.html import format_html, format_html_join

from . import audit
from .models import AuditLog, SiteSetting
from .themes import THEMES


class SiteSettingForm(forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = ["ui_theme"]
        widgets = {"ui_theme": forms.RadioSelect}


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    """UI テーマの切り替え。1 行だけの設定なので追加・削除はできない。"""

    form = SiteSettingForm
    list_display = ("__str__", "ui_theme", "updated_by", "updated_at")
    readonly_fields = ("theme_guide", "updated_by", "updated_at")
    fields = ("ui_theme", "theme_guide", "updated_by", "updated_at")

    @admin.display(description="各テーマの説明と試し見")
    def theme_guide(self, obj):
        rows = format_html_join(
            "", '<li><strong>{}</strong> — {} '
                '(<a href="/?ui={}" target="_blank" rel="noopener">自分だけ試す</a>)</li>',
            ((t.label, t.description, t.key) for t in THEMES.values()),
        )
        return format_html('<ul>{}</ul>'
                           '<p>試し見を終えるときは <a href="/?ui=reset" target="_blank" rel="noopener">こちら</a></p>', rows)

    def has_add_permission(self, request):
        return not SiteSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # 一覧を経由せず、設定画面を直接開く
        from django.shortcuts import redirect
        from django.urls import reverse

        obj = SiteSetting.current()
        return redirect(reverse("admin:core_sitesetting_change", args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        audit.record("site.ui_theme", request=request, target=obj, theme=obj.ui_theme)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "target_type", "target_id")
    list_filter = ("action",)
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
