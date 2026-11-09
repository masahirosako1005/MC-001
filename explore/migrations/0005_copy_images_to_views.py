"""既存の画像シンボル (1 枚の写真) を「正面」の見え方として SymbolView に移す。"""

from django.db import migrations

EMPTY_MASK = bytes(128)  # 32x32 ビット = すべて判定対象


def forwards(apps, schema_editor):
    SymbolImage = apps.get_model("explore", "SymbolImage")
    SymbolView = apps.get_model("explore", "SymbolView")
    for img in SymbolImage.objects.all():
        SymbolView.objects.update_or_create(
            symbol_id=img.symbol_id, angle="front",
            defaults=dict(
                jpeg=img.jpeg, width=img.width, height=img.height, features=img.features,
                keypoint_count=img.keypoint_count, verify_patch=img.verify_patch, verify_mask=EMPTY_MASK,
                created_by_id=img.created_by_id, created_at=img.created_at,
            ),
        )


def backwards(apps, schema_editor):
    SymbolImage = apps.get_model("explore", "SymbolImage")
    SymbolView = apps.get_model("explore", "SymbolView")
    for v in SymbolView.objects.filter(angle="front"):
        SymbolImage.objects.update_or_create(
            symbol_id=v.symbol_id,
            defaults=dict(
                jpeg=v.jpeg, width=v.width, height=v.height, features=v.features,
                keypoint_count=max(v.keypoint_count, 40), verify_patch=v.verify_patch,
                created_by_id=v.created_by_id, created_at=v.created_at,
            ),
        )


class Migration(migrations.Migration):
    dependencies = [("explore", "0004_symbol_views")]

    operations = [migrations.RunPython(forwards, backwards)]
