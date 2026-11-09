from django.contrib import admin, messages

from . import services
from .models import Contest, ContestEntry, EvaluationRound


@admin.register(Contest)
class ContestAdmin(admin.ModelAdmin):
    list_display = ("title", "starts_at", "ends_at", "is_active", "real_entries", "bot_entries", "bot_cutoff")
    list_filter = ("is_active",)
    actions = ["make_bots"]

    @admin.display(description="参加者")
    def real_entries(self, obj):
        return obj.entries.filter(is_bot=False).count()

    @admin.display(description="BOT")
    def bot_entries(self, obj):
        return obj.entries.filter(is_bot=True).count()

    @admin.action(description="BOT を 12 体まで作成する (参加者が少ないうちの評価用)")
    def make_bots(self, request, queryset):
        made = sum(services.create_bots(c) for c in queryset)
        self.message_user(request, f"BOT を {made} 体作成しました。", messages.SUCCESS)


@admin.register(ContestEntry)
class ContestEntryAdmin(admin.ModelAdmin):
    list_display = ("display_name", "contest", "is_bot", "likes", "impressions", "created_at")
    list_filter = ("contest", "is_bot")
    readonly_fields = ("id", "contest", "user", "is_bot", "avatar", "impressions", "likes", "created_at")
    raw_id_fields = ("user",)


@admin.register(EvaluationRound)
class EvaluationRoundAdmin(admin.ModelAdmin):
    list_display = ("contest", "voter", "round_no", "chosen", "answered_at")
    list_filter = ("contest",)
    raw_id_fields = ("voter",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
