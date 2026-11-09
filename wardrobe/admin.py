from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .avatar import STYLES
from .models import AvatarConfig, Item, UserItem

ALL_STYLE_CHOICES = sorted({(k, f"{v['label']} ({k})") for d in STYLES.values() for k, v in d.items()})


class ItemForm(forms.ModelForm):
    style = forms.ChoiceField(choices=ALL_STYLE_CHOICES, label="形")
    color = forms.CharField(widget=forms.TextInput(attrs={"type": "color"}), label="色")

    class Meta:
        model = Item
        fields = ["code", "name", "description", "body_type", "category", "style", "color", "rarity", "is_starter", "is_active"]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    form = ItemForm
    list_display = ("code", "name", "body_type", "category", "style", "swatch", "rarity", "is_starter", "is_active")
    list_filter = ("body_type", "category", "rarity", "is_starter", "is_active")
    search_fields = ("code", "name")

    @admin.display(description="色")
    def swatch(self, obj):
        return format_html('<code>{}</code>', obj.color)


@admin.register(UserItem)
class UserItemAdmin(admin.ModelAdmin):
    list_display = ("user", "item", "obtained_count", "first_obtained_at")
    list_select_related = ("user", "item")
    raw_id_fields = ("user",)


@admin.register(AvatarConfig)
class AvatarConfigAdmin(admin.ModelAdmin):
    list_display = ("user", "body_type", "skin_tone", "eye_color", "version", "updated_at")
    raw_id_fields = ("user",)
