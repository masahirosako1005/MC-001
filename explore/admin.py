from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Discovery, DropEntry, Spot, SpotVisit, Symbol


class SymbolInline(admin.TabularInline):
    model = Symbol
    extra = 0
    fields = ("name", "hint", "cooldown_hours", "is_active")


@admin.register(Spot)
class SpotAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "require_location", "radius_m", "is_active")
    list_filter = ("is_active", "require_location")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [SymbolInline]


class DropInline(admin.TabularInline):
    model = DropEntry
    extra = 1
    autocomplete_fields = ("item",)


@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ("name", "spot", "cooldown_hours", "is_active", "symbol_image")
    list_filter = ("spot", "is_active")
    inlines = [DropInline]

    @admin.display(description="シンボル画像")
    def symbol_image(self, obj):
        if obj.pk is None:
            return "-"
        url = reverse("explore:symbol_svg", args=[obj.pk])
        return format_html('<a href="{}" target="_blank" rel="noopener">表示</a> / <a href="{}?download=1">保存</a>', url, url)


@admin.register(SpotVisit)
class SpotVisitAdmin(admin.ModelAdmin):
    list_display = ("user", "spot", "visit_date", "season")
    list_filter = ("spot", "season")
    raw_id_fields = ("user",)


@admin.register(Discovery)
class DiscoveryAdmin(admin.ModelAdmin):
    list_display = ("found_at", "user", "symbol", "reward_kind", "reward_label", "is_new")
    list_filter = ("reward_kind", "symbol__spot")
    raw_id_fields = ("user",)
    readonly_fields = [f.name for f in Discovery._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False
