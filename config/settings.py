"""みっけ (Mikke) Django 設定。

設定値はすべて環境変数 (.env) から読み込む (The Twelve-Factor App)。
秘密情報はこのファイルに書かない。
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"環境変数 {name} が設定されていません (.env を確認してください)")
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
ADMIN_URL = env("DJANGO_ADMIN_URL", "admin/")
# サイト運営者の画面 (ログイン・利用者管理・分析) の場所。推測されにくい値を .env で設定する
OPS_URL = env("MIKKE_OPS_URL", "ops/")
# サイト運営者のログインは短めに切れるようにする (秒)
OPS_SESSION_SECONDS = int(env("MIKKE_OPS_SESSION_SECONDS", str(60 * 60 * 4)))

# ---- フィールド暗号化鍵 (core/crypto.py) ----
MIKKE_FIELD_KEYS = env("MIKKE_FIELD_KEYS", required=True)
MIKKE_BLIND_INDEX_KEY = env("MIKKE_BLIND_INDEX_KEY", required=True)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "accounts",
    "wardrobe",
    "rewards",
    "explore",
    "maps",
    "contest",
    "ops",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # 画面は日本語のみのため LocaleMiddleware は使わない (多言語化するときに戻す)
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "core.middleware.ForcePasswordChangeMiddleware",
    "core.middleware.UiThemeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csp",
                "core.context_processors.mikke",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---- データベース ----
# 既定は PostgreSQL (TLS 必須)。環境制約で使えない場合は DB_ENGINE=sqlite で切り替え可能。
DB_ENGINE = env("DB_ENGINE", "postgresql").lower()
if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / env("SQLITE_NAME", "mikke.sqlite3"),
        }
    }
elif DB_ENGINE == "postgresql":
    pg_bin = env("PG_BIN", "")
    if os.name == "nt" and pg_bin and Path(pg_bin).is_dir():
        # psycopg 同梱 DLL がアプリ制御ポリシーで拒否される環境向けに、
        # PostgreSQL 付属の libpq.dll を使う pure-python 実装を選ぶ。
        os.environ["PATH"] = pg_bin + os.pathsep + os.environ.get("PATH", "")
        os.environ.setdefault("PSYCOPG_IMPL", "python")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "mikke"),
            "USER": env("DB_USER", required=True),
            "PASSWORD": env("DB_PASSWORD", required=True),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {"sslmode": env("DB_SSLMODE", "require")},
        }
    }
else:
    raise ImproperlyConfigured("DB_ENGINE は postgresql か sqlite を指定してください")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"

# ---- 認証 (NIST SP 800-63B / OWASP Password Storage Cheat Sheet) ----
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 15}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
MIKKE_LOGIN_MAX_FAILURES = 5  # アカウント単位のロック
# IP 単位のロックはアカウント単位より緩くする (同じ回線・施設の Wi-Fi の人をまとめてロックしないため)
MIKKE_LOGIN_MAX_FAILURES_PER_IP = int(env("MIKKE_LOGIN_MAX_FAILURES_PER_IP", "20"))
MIKKE_LOGIN_LOCK_SECONDS = 15 * 60
# 信頼済みリバースプロキシの IP / CIDR (カンマ区切り)。このときだけ X-Forwarded-For を使う (core/net.py)
MIKKE_TRUSTED_PROXIES = [ipaddress.ip_network(p.strip(), strict=False)
                         for p in env("MIKKE_TRUSTED_PROXIES", "").split(",") if p.strip()]

# ---- 国際化 ----
LANGUAGE_CODE = "ja"
LANGUAGES = [("ja", "日本語")]
TIME_ZONE = "Asia/Tokyo"  # 表示・季節判定用。DB 保存は UTC (USE_TZ)
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# キャッシュ (レート制限・ログインロック・みっけ仲間の表示 ID に使う)。
# 既定のメモリキャッシュは 1 プロセス内だけで有効。複数プロセス / 複数台で動かすときは
# MIKKE_CACHE=db (createcachetable が必要) か MIKKE_CACHE=redis://… を設定すること。
_CACHE = env("MIKKE_CACHE", "locmem")
if _CACHE == "db":
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "mikke_cache"}}
elif _CACHE.startswith(("redis://", "rediss://")):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _CACHE}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "mikke"}}
    if not DEBUG and not env_bool("MIKKE_ALLOW_LOCMEM_CACHE"):
        # 本番 (DEBUG=False) でプロセス内キャッシュを使うと、ログインロックやレート制限がワーカーごとに
        # 別々に数えられて実質的に無効になる。明示的に許可しない限り起動を止める。
        raise ImproperlyConfigured(
            "DEBUG=False では MIKKE_CACHE=db または MIKKE_CACHE=redis://… を設定してください "
            "(単一プロセスで動かすことを理解したうえで許可する場合は MIKKE_ALLOW_LOCMEM_CACHE=1)"
        )

# ---- セキュリティ (OWASP ASVS L2 / Top 10:2025) ----
SECURE_COOKIES = env_bool("DJANGO_SECURE_COOKIES", not DEBUG)
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True  # JS は <meta name="csrf-token"> から読む
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    # HSTS はホスト名単位 (ポートは区別しない)。localhost で有効にすると、同じブラウザで開く
    # ほかの http://localhost:XXXX の開発サーバーまで https に強制されるため、ローカルでは 0 にする
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", str(60 * 60 * 24 * 365)))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
# リバースプロキシ (nginx) で TLS を終端するとき: nginx が付ける X-Forwarded-Proto: https を信用して
# 「https のリクエスト」として扱う。アプリ本体が 127.0.0.1 だけで待ち受け、nginx を通らないと
# 届かない構成 (scripts/devproxy.py) のときだけ有効にすること (直接つながると偽装できるため)
if env_bool("DJANGO_BEHIND_TLS_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# テストは .env の本番相当の設定 (HTTPS への転送) に左右されないようにする
TEST_RUNNER = "config.test_runner.MikkeTestRunner"

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:", "blob:"],
    "media-src": [CSP.SELF, "blob:"],
    "connect-src": [CSP.SELF],
    "font-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.NONE],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024

# ---- ログ (個人情報・秘密情報は出力しない) ----
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "mikke": {"handlers": ["console"], "level": "INFO"},
        "django.security": {"handlers": ["console"], "level": "WARNING"},
    },
}

# ---- ゲームバランス ----
MIKKE_SCAN_TICKET_MAX_AGE = 300  # 秒: スキャンから受け取りまでの有効時間
# 現地確認 (require_location のスポット): 受け取りの何分前までに「近くのシンボルを探す」で付近に来ている必要があるか
MIKKE_PRESENCE_WINDOW_MINUTES = int(env("MIKKE_PRESENCE_WINDOW_MINUTES", "30"))
# 直前のみっけ地点からの移動速度 (km/h) がこれを超える受け取りは、位置偽装とみなして拒否する (0 で無効)
MIKKE_MAX_TRAVEL_SPEED_KMH = float(env("MIKKE_MAX_TRAVEL_SPEED_KMH", "200"))
# 画像シンボル: 映像から切り出した画像と登録画像の類似度 (0〜1) がこの値以上なら「写っている」と判定
MIKKE_IMAGE_SIMILARITY_THRESHOLD = float(env("MIKKE_IMAGE_SIMILARITY_THRESHOLD", "0.65"))

# ---- 地図 (Protomaps / PMTiles をローカル配信。外部 API は使わない) ----
MIKKE_TILES_DIR = BASE_DIR / "maps" / "tiles"
# パスワードを忘れた方の問い合わせ先 (画面に表示する。メールアドレスや窓口名など)
MIKKE_SUPPORT_CONTACT = env("MIKKE_SUPPORT_CONTACT", "みっけ運営事務局(サイト内のお問い合わせ窓口)")
# 「こんな人が獲得しているよ」に出す期間 (分)。文言もこの値から作る
MIKKE_FINDER_WINDOW_MINUTES = 30

def _floats(name: str, default: str) -> list[float]:
    return [float(v) for v in env(name, default).split(",")]


# 地図 (タイルを別の地域で作り直したときは .env で変える)。既定は大阪府 京橋付近 (scripts/extract_tiles.py の範囲)
_b = _floats("MIKKE_MAP_BOUNDS", "34.6800,135.5150,34.7080,135.5500")  # 南,西,北,東
_c = _floats("MIKKE_MAP_CENTER", "34.6950,135.5330")
MIKKE_MAP = {
    "tiles": env("MIKKE_MAP_TILES", "kyobashi"),
    "bounds": [[_b[0], _b[1]], [_b[2], _b[3]]],
    "center": [_c[0], _c[1]],
    "zoom": int(env("MIKKE_MAP_ZOOM", "15")),
    "max_data_zoom": int(env("MIKKE_MAP_MAX_DATA_ZOOM", "15")),
}
# 「みっけ」画面の下にスポットとシンボルのカード一覧を出すか (いまは非表示)
MIKKE_SHOW_SPOT_CARDS = env_bool("MIKKE_SHOW_SPOT_CARDS", False)
