from __future__ import annotations

import logging

from . import net
from .crypto import blind_index
from .models import AuditLog

logger = logging.getLogger("mikke.audit")


def client_ip(request) -> str:
    # 信頼済みプロキシ経由のときだけ X-Forwarded-For を使う (core/net.py)
    return net.client_ip(request)


def record(action: str, *, request=None, actor=None, target=None, **detail) -> AuditLog:
    if actor is None and request is not None and getattr(request, "user", None) is not None:
        actor = request.user if request.user.is_authenticated else None
    ip = client_ip(request)
    entry = AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target._meta.label_lower if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        detail=detail,
        ip_hash=blind_index(ip, "audit.ip") if ip else "",
    )
    logger.info("audit action=%s actor=%s target=%s:%s", action, getattr(actor, "pk", None),
                entry.target_type, entry.target_id)
    return entry
