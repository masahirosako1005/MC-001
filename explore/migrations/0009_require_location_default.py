# 2026-11-09 セキュリティレビュー: 現地確認を既定で必須にする (位置のあるスポットは既存データも ON にする)

from django.db import migrations, models


def enable_for_located_spots(apps, schema_editor):
    Spot = apps.get_model("explore", "Spot")
    Spot.objects.filter(latitude__isnull=False, longitude__isnull=False).update(require_location=True)


class Migration(migrations.Migration):

    dependencies = [
        ("explore", "0008_roles_managers_analytics"),
    ]

    operations = [
        migrations.AlterField(
            model_name="spot",
            name="require_location",
            field=models.BooleanField(
                default=True,
                help_text="ON のとき、受け取りの直前に「近くのシンボルを探す」で付近に来ていること、および受け取り時の位置情報が判定半径内であることを確認します。位置が未設定のスポットでは確認できないため自動的に OFF になります",
                verbose_name="現地確認を必須にする",
            ),
        ),
        migrations.RunPython(enable_for_located_spots, migrations.RunPython.noop),
    ]
