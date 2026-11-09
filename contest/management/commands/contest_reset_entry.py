"""指定した利用者のエントリーと評価の記録をコンテストから外し、もう一度エントリーできるようにする。

    python manage.py contest_reset_entry --email test@test.com --contest 1

- 外したエントリーへの高評価、その人が付けた高評価 (BOT 以外) は集計から差し引く
- 操作は監査ログに残す
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F

from accounts.models import User, email_hash_of
from contest.models import Contest, ContestEntry, EvaluationRound
from core import audit


class Command(BaseCommand):
    help = "利用者のコンテストエントリーと評価の記録を取り消す"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--contest", type=int, required=True)

    @transaction.atomic
    def handle(self, *args, **opts):
        user = User.objects.filter(email_hash=email_hash_of(opts["email"])).first()
        contest = Contest.objects.filter(pk=opts["contest"]).first()
        if user is None or contest is None:
            raise CommandError("利用者またはコンテストが見つかりません。")
        rounds = EvaluationRound.objects.filter(contest=contest, voter=user)
        # この人が付けた高評価を取り消す (BOT への評価は元々加算していない)
        for r in rounds.select_related("chosen"):
            if r.chosen and not r.chosen.is_bot:
                ContestEntry.objects.filter(pk=r.chosen.pk, likes__gt=0).update(likes=F("likes") - 1)
        n_rounds = rounds.count()
        rounds.delete()
        entry = ContestEntry.objects.filter(contest=contest, user=user).first()
        likes = entry.likes if entry else 0
        if entry:
            # このエントリーに付いた評価の記録は残すが、選択先は空にする (SET_NULL)
            entry.delete()
        audit.record("contest.reset_entry", actor=user, target=contest, rounds=n_rounds, removed_likes=likes)
        self.stdout.write(self.style.SUCCESS(
            f"{user.nickname} のエントリー{'を削除' if entry else 'はありません'}・評価 {n_rounds} 回分を取り消しました"))
