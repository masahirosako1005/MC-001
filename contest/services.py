"""コンテストのルール。

① エントリーする (アバターはエントリー時点の見た目を保存)
② エントリーしたら評価モードへ
③ ランダムに選んだ 3 体を 3 回表示し、1 回ごとに 1 体まで高評価を付けられる
④ 候補は「表示回数が少ないアバター」を優先し、同じ表示回数の中ではランダム
⑤ 実際の参加者が 10 人 (Contest.bot_cutoff) に達するまでは BOT も候補に入れる。
   達したら BOT は表示しない。BOT への高評価はランキングに反映しない
"""

from __future__ import annotations

import secrets
import unicodedata
from collections import defaultdict

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from wardrobe.avatar import CATEGORY_CHOICES, Part, render_svg
from wardrobe.models import AvatarConfig, Item

from .models import Contest, ContestEntry, EvaluationRound

_rng = secrets.SystemRandom()
CATEGORIES = [c for c, _ in CATEGORY_CHOICES]


class ContestError(Exception):
    pass


# ---------------------------------------------------------------- アバターのスナップショット

def avatar_snapshot(config: AvatarConfig) -> dict:
    parts = {}
    for cat in CATEGORIES:
        item = getattr(config, cat)
        if item is not None:
            parts[cat] = {"style": item.style, "color": item.color, "name": item.name}
    return {"body_type": config.body_type, "skin_tone": config.skin_tone, "eye_color": config.eye_color, "parts": parts}


def snapshot_svg(snap: dict, label: str = "コンテストのアバター") -> str:
    parts = {}
    for cat, p in (snap.get("parts") or {}).items():
        if cat in CATEGORIES and isinstance(p, dict):
            parts[cat] = Part(cat, str(p.get("style", "")), str(p.get("color", "")), str(p.get("name", "")))
    return render_svg(str(snap.get("skin_tone", "tone3")), parts, body_type=str(snap.get("body_type", "girl")),
                      eye_color=str(snap.get("eye_color", "brown")), label=label)


# ---------------------------------------------------------------- ① エントリー

def clean_display_name(name: str) -> str:
    name = unicodedata.normalize("NFC", name or "").strip()
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")  # 制御文字を除く
    if not name:
        name = f"旅人#{_rng.randrange(1000, 10000)}"
    if len(name) > 20:
        raise ContestError("表示名は 20 文字以内にしてください。")
    return name


def real_entry_count(contest: Contest) -> int:
    return ContestEntry.objects.filter(contest=contest, is_bot=False).count()


def bots_visible(contest: Contest) -> bool:
    return real_entry_count(contest) < contest.bot_cutoff


@transaction.atomic
def enter(contest: Contest, user, display_name: str = "", now=None) -> ContestEntry:
    if not contest.is_open(now):
        raise ContestError("このコンテストは現在エントリーを受け付けていません。")
    if ContestEntry.objects.filter(contest=contest, user=user).exists():
        raise ContestError("すでにエントリー済みです。")
    from wardrobe.services import get_config

    return ContestEntry.objects.create(
        contest=contest, user=user, is_bot=False, display_name=clean_display_name(display_name),
        avatar=avatar_snapshot(get_config(user)),
    )


def my_entry(contest: Contest, user) -> ContestEntry | None:
    return ContestEntry.objects.filter(contest=contest, user=user).first()


# ---------------------------------------------------------------- ③④⑤ 候補の選び方

def pick_candidates(contest: Contest, voter, k: int, exclude_ids: set | None = None) -> list[ContestEntry]:
    """表示回数が少ない順に「層」を作り、少ない層から順にランダムに k 体選ぶ。"""
    pool = ContestEntry.objects.filter(contest=contest).exclude(user=voter)
    if not bots_visible(contest):
        pool = pool.filter(is_bot=False)
    entries = list(pool)
    exclude_ids = exclude_ids or set()
    fresh = [e for e in entries if e.pk not in exclude_ids]
    # 同じ人の評価で何度も同じアバターが出ないよう、まだ見せていないものを優先する
    chosen = _tiered_sample(fresh, k)
    if len(chosen) < k:
        rest = [e for e in entries if e.pk in exclude_ids]
        chosen += _tiered_sample(rest, k - len(chosen))
    return chosen


def _tiered_sample(entries: list[ContestEntry], k: int) -> list[ContestEntry]:
    tiers: dict[int, list[ContestEntry]] = defaultdict(list)
    for e in entries:
        tiers[e.impressions].append(e)
    picked: list[ContestEntry] = []
    for imp in sorted(tiers):
        tier = tiers[imp]
        _rng.shuffle(tier)
        picked.extend(tier[: k - len(picked)])
        if len(picked) >= k:
            break
    return picked


def rounds_answered(contest: Contest, voter) -> int:
    return EvaluationRound.objects.filter(contest=contest, voter=voter, answered_at__isnull=False).count()


@transaction.atomic
def current_round(contest: Contest, voter, now=None) -> EvaluationRound | None:
    """未回答の評価があればそれを、なければ次の評価を作って返す。全回終わっていれば None。"""
    if my_entry(contest, voter) is None:
        raise ContestError("評価するには、先にエントリーしてください。")
    # 同じコンテストの候補選びを直列化し、表示回数の更新が競合しないようにする
    Contest.objects.select_for_update().get(pk=contest.pk)
    pending = EvaluationRound.objects.filter(contest=contest, voter=voter, answered_at__isnull=True).first()
    if pending:
        return pending
    done = rounds_answered(contest, voter)
    if done >= contest.rounds:
        return None
    if not contest.is_open(now):
        raise ContestError("このコンテストは現在評価を受け付けていません。")
    seen = set(EvaluationRound.candidates.through.objects.filter(
        evaluationround__contest=contest, evaluationround__voter=voter).values_list("contestentry_id", flat=True))
    picks = pick_candidates(contest, voter, contest.per_round, seen)
    if not picks:
        raise ContestError("評価できるアバターがまだいません。しばらくしてからお試しください。")
    rnd = EvaluationRound.objects.create(contest=contest, voter=voter, round_no=done + 1)
    rnd.candidates.set(picks)
    ContestEntry.objects.filter(pk__in=[p.pk for p in picks]).update(impressions=F("impressions") + 1)
    return rnd


@transaction.atomic
def vote(contest: Contest, voter, round_id: int, entry_id: str | None, now=None) -> EvaluationRound:
    """1 回の評価に回答する。entry_id が None なら「どれも選ばない」。同じ回への再送は最初の回答のまま (冪等)。"""
    rnd = (EvaluationRound.objects.select_for_update()
           .filter(pk=round_id, contest=contest, voter=voter).first())
    if rnd is None:
        raise ContestError("評価の情報が正しくありません。もう一度お試しください。")
    if rnd.answered_at is not None:
        return rnd
    chosen = None
    if entry_id:
        chosen = rnd.candidates.filter(pk=entry_id).first()
        if chosen is None:
            raise ContestError("表示されたアバターの中から選んでください。")
    rnd.chosen = chosen
    rnd.answered_at = now or timezone.now()
    rnd.save(update_fields=["chosen", "answered_at"])
    if chosen is not None and not chosen.is_bot:  # BOT への評価はランキングに反映しない
        ContestEntry.objects.filter(pk=chosen.pk).update(likes=F("likes") + 1)
    return rnd


# ---------------------------------------------------------------- ランキング

def ranking(contest: Contest, limit: int = 50) -> list[ContestEntry]:
    return list(ContestEntry.objects.filter(contest=contest, is_bot=False)
                .order_by("-likes", "created_at")[:limit])


def rank_of(contest: Contest, entry: ContestEntry) -> int:
    """ランキングでの順位 (高評価が多い順、同数なら先にエントリーした順)。"""
    ahead = Q(likes__gt=entry.likes) | Q(likes=entry.likes, created_at__lt=entry.created_at)
    return ContestEntry.objects.filter(contest=contest, is_bot=False).filter(ahead).count() + 1


# ---------------------------------------------------------------- BOT

BOT_NAMES = ["みっけBOT・さくら", "みっけBOT・そら", "みっけBOT・こはく", "みっけBOT・あおい", "みっけBOT・ひなた",
             "みっけBOT・なぎ", "みっけBOT・つむぎ", "みっけBOT・はると", "みっけBOT・りん", "みっけBOT・ゆう",
             "みっけBOT・かえで", "みっけBOT・みなと"]


def random_bot_avatar() -> dict:
    body = _rng.choice(["girl", "boy"])
    items = list(Item.objects.filter(is_active=True, body_type__in=[body, "any"]))
    by_cat: dict[str, list[Item]] = defaultdict(list)
    for i in items:
        by_cat[i.category].append(i)
    parts = {}
    for cat in CATEGORIES:
        optional = cat in ("accessory", "effect")
        if by_cat[cat] and not (optional and _rng.random() < 0.4):
            it = _rng.choice(by_cat[cat])
            parts[cat] = {"style": it.style, "color": it.color, "name": it.name}
    return {"body_type": body, "skin_tone": _rng.choice(["tone1", "tone2", "tone3", "tone4", "tone5", "tone6"]),
            "eye_color": _rng.choice(["brown", "pink", "violet", "blue", "green", "amber"]), "parts": parts}


@transaction.atomic
def create_bots(contest: Contest, n: int = 12) -> int:
    existing = ContestEntry.objects.filter(contest=contest, is_bot=True).count()
    for i in range(existing, n):
        ContestEntry.objects.create(contest=contest, is_bot=True, user=None,
                                    display_name=BOT_NAMES[i % len(BOT_NAMES)], avatar=random_bot_avatar())
    return max(n - existing, 0)
