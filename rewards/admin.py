from django.contrib import admin

from .models import Achievement, CouponTemplate, UserAchievement, UserCoupon


@admin.register(CouponTemplate)
class CouponTemplateAdmin(admin.ModelAdmin):
    list_display = ("coupon_id", "code", "shop_name", "title", "benefit", "spot", "owner", "valid_days",
                    "available_until", "is_active")
    list_filter = ("is_active", "spot")
    search_fields = ("coupon_id", "code", "title", "shop_name")


@admin.register(UserCoupon)
class UserCouponAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "template", "issued_at", "expires_at", "used_at")
    list_filter = ("template",)
    list_select_related = ("user", "template")
    raw_id_fields = ("user",)
    readonly_fields = ("redeem_code",)


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("sort_order", "code", "icon", "name", "kind", "threshold", "reward_item", "reward_coupon", "is_active")
    list_display_links = ("code",)
    list_filter = ("kind", "is_active")


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ("user", "achievement", "achieved_at")
    raw_id_fields = ("user",)
