"""みっけ (Mikke) Django 設定。

設定値はすべて環境変数 (.env) から読み込む (The Twelve-Factor App)。
秘密情報はこのファイルに書かない。
"""

from __future__ import annotations

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
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
MIKKE_LOGIN_MAX_FAILURES = 5
MIKKE_LOGIN_LOCK_SECONDS = 15 * 60

# ---- 国際化 ----
LANGUAGE_CODE = "ja"
LANGUAGES = [("ja", "日本語")]
TIME_ZONE = "Asia/Tokyo"  # 表示・季節判定用。DB 保存は UTC (USE_TZ)
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "mikke"}}

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
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

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
