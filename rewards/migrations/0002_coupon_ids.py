import secrets

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import rewards.models
from core.crypto import blind_index

# データ移行で使う値の作り方は、このファイルの中に固定する
# (あとで rewards.models / rewards.services を変えても、このマイグレーションの動きが変わらないように)
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _coupon_id() -> str:
    return "CP-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def _redeem_code() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"MK-{body[:4]}-{body[4:]}"


def _redeem_hash(code: str) -> str:
    return blind_index(code.strip().upper(), "coupon.redeem")


def fill_ids(apps, schema_editor):
    """既存のクーポンにクーポン ID を、発行済みクーポンに引換コードの照合用ハッシュを付ける。"""
    CouponTemplate = apps.get_model("rewards", "CouponTemplate")
    UserCoupon = apps.get_model("rewards", "UserCoupon")
    used = set()
    for tpl in CouponTemplate.objects.all():
        cid = _coupon_id()
        while cid in used:
            cid = _coupon_id()
        used.add(cid)
        tpl.coupon_id = cid
        tpl.save(update_fields=["coupon_id"])
    seen = set()
    for uc in UserCoupon.objects.all():
        h = _redeem_hash(uc.redeem_code)
        while h in seen:  # 万一の重複は引換コードを作り直す
            uc.redeem_code = _redeem_code()
            h = _redeem_hash(uc.redeem_code)
        seen.add(h)
        uc.redeem_hash = h
        uc.save(update_fields=["redeem_code", "redeem_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("rewards", "0001_initial"),
        ("accounts", "0003_user_share_activity"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="coupontemplate",
            name="coupon_id",
            field=models.CharField(editable=False, max_length=12, null=True, verbose_name="クーポン ID"),
        ),
        migrations.AddField(
            model_name="usercoupon",
            name="redeem_hash",
            field=models.CharField(editable=False, max_length=64, null=True, verbose_name="引換コードの照合用ハッシュ"),
        ),
        migrations.RunPython(fill_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="coupontemplate",
            name="coupon_id",
            field=models.CharField(default=rewards.models.new_coupon_id, editable=False, max_length=12, unique=True,
                                   verbose_name="クーポン ID"),
        ),
        migrations.AlterField(
            model_name="usercoupon",
            name="redeem_hash",
            field=models.CharField(editable=False, max_length=64, unique=True, verbose_name="引換コードの照合用ハッシュ"),
        ),
        migrations.AddField(
            model_name="coupontemplate",
            name="available_until",
            field=models.DateTimeField(blank=True, null=True, verbose_name="有効期限",
                                       help_text="この日時を過ぎると配布を止め、受け取り済みのクーポンも使えなくなる。空欄なら無期限"),
        ),
        migrations.AddField(
            model_name="coupontemplate",
            name="owner",
            field=models.ForeignKey(blank=True, limit_choices_to={"role": "manager"}, null=True,
                                    on_delete=django.db.models.deletion.SET_NULL, related_name="owned_coupons",
                                    to=settings.AUTH_USER_MODEL, verbose_name="登録した管理者"),
        ),
        migrations.AddField(
            model_name="coupontemplate",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name="登録日時"),
        ),
        migrations.AlterField(
            model_name="coupontemplate",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="配布する"),
        ),
        migrations.AlterField(
            model_name="coupontemplate",
            name="valid_days",
            field=models.PositiveSmallIntegerField(default=30, help_text="受け取ってから使えるまでの日数", verbose_name="有効日数"),
        ),
    ]
