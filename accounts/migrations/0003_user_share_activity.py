from django.db import migrations, models


def keep_existing_private(apps, schema_editor):
    """これまでの登録画面では「ニックネームはほかの人には表示されません」と案内していたため、
    既存の利用者は「表示しない」から始める (本人がアカウント画面で ON にできる)。
    動作確認用のデモ利用者だけは表示する。"""
    User = apps.get_model("accounts", "User")
    User.objects.exclude(groups__name="デモ利用者").update(share_activity=False)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_roles_managers_analytics"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="share_activity",
            field=models.BooleanField(
                default=True,
                help_text="ON のとき、同じシンボルを 30 分以内にみっけした人に、ニックネームと今のコーデが表示されます",
                verbose_name="みっけ仲間に表示する",
            ),
        ),
        migrations.RunPython(keep_existing_private, migrations.RunPython.noop),
    ]
