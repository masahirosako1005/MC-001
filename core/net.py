"""接続元 IP アドレスの取得。

リバースプロキシ (ロードバランサーなど) の内側では REMOTE_ADDR が全員プロキシの IP になり、
IP 単位のログインロックが「全員まとめてロック」(DoS) になってしまう。
そこで、REMOTE_ADDR が信頼済みプロキシ (環境変数 MIKKE_TRUSTED_PROXIES) のときだけ
X-Forwarded-For を見て、信頼済みでない一番右の IP を本当の接続元とみなす。
信頼済みプロキシを設定していなければ X-Forwarded-For は使わない (偽装できるため)。
"""

from __future__ import annotations

import ipaddress

from django.conf import settings


def _trusted(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in settings.MIKKE_TRUSTED_PROXIES)


def client_ip(request) -> str:
    if request is None:
        return ""
    remote = request.META.get("REMOTE_ADDR", "")
    if not settings.MIKKE_TRUSTED_PROXIES or not _trusted(remote):
        return remote
    forwarded = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    for ip in reversed(forwarded):
        if not _trusted(ip):
            return ip
    return remote
