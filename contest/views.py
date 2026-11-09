from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core import audit
from core.http import svg_response

from . import services
from .models import Contest, ContestEntry


def _contest(pk: int) -> Contest:
    return get_object_or_404(Contest, pk=pk, is_active=True)


@login_required
@require_GET
def contest_list(request):
    now = timezone.now()
    contests = list(Contest.objects.filter(is_active=True))
    mine = set(ContestEntry.objects.filter(user=request.user).values_list("contest_id", flat=True))
    rows = [{"c": c, "open": c.is_open(now), "entered": c.pk in mine} for c in contests]
    return render(request, "contest/list.html", {"rows": rows})


@login_required
@require_GET
def contest_detail(request, pk: int):
    contest = _contest(pk)
    entry = services.my_entry(contest, request.user)
    return render(request, "contest/detail.html", {
        "contest": contest,
        "entry": entry,
        "open": contest.is_open(),
        "answered": services.rounds_answered(contest, request.user),
        "real_count": services.real_entry_count(contest),
        "rank": services.rank_of(contest, entry) if entry else None,
    })


@login_required
@require_POST
def contest_enter(request, pk: int):
    contest = _contest(pk)
    try:
        entry = services.enter(contest, request.user, request.POST.get("display_name", ""))
    except services.ContestError as exc:
        messages.error(request, str(exc))
        return redirect("contest:detail", pk=contest.pk)
    audit.record("contest.enter", request=request, target=entry, contest=contest.pk)
    messages.success(request, "エントリーしました!つづけて、ほかの人のコーデを評価しましょう。")
    return redirect("contest:evaluate", pk=contest.pk)  # ② エントリー後は評価モードへ


@login_required
@require_http_methods(["GET", "POST"])
def contest_evaluate(request, pk: int):
    contest = _contest(pk)
    if request.method == "POST":
        choice = request.POST.get("choice", "skip")
        try:
            round_id = int(request.POST.get("round", "0"))
            services.vote(contest, request.user, round_id, None if choice == "skip" else choice)
        except (ValueError, services.ContestError) as exc:
            messages.error(request, str(exc) if isinstance(exc, services.ContestError) else "評価の情報が正しくありません。")
        return redirect("contest:evaluate", pk=contest.pk)
    try:
        rnd = services.current_round(contest, request.user)
    except services.ContestError as exc:
        messages.error(request, str(exc))
        return redirect("contest:detail", pk=contest.pk)
    if rnd is None:
        return render(request, "contest/evaluate_done.html", {"contest": contest})
    candidates = list(rnd.candidates.all())
    services._rng.shuffle(candidates)  # 並び順でも有利・不利が出ないように
    return render(request, "contest/evaluate.html", {"contest": contest, "round": rnd, "candidates": candidates})


@login_required
@require_GET
def contest_ranking(request, pk: int):
    contest = _contest(pk)
    entry = services.my_entry(contest, request.user)
    return render(request, "contest/ranking.html", {
        "contest": contest,
        "rows": services.ranking(contest),
        "entry": entry,
        "rank": services.rank_of(contest, entry) if entry else None,
    })


@login_required
@require_GET
def entry_svg(request, entry_id):
    entry = get_object_or_404(ContestEntry, pk=entry_id, contest__is_active=True)
    # スナップショットなので変わらない
    return svg_response(services.snapshot_svg(entry.avatar), cache="private, max-age=3600")
