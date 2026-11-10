"""ローカル開発用 PostgreSQL の初期化・起動・停止スクリプト。

使い方:
    python scripts/localdb.py init     # .env 生成 + initdb + TLS 証明書 + ロール/DB 作成
    python scripts/localdb.py start    # サーバー起動
    python scripts/localdb.py stop     # サーバー停止
    python scripts/localdb.py status   # 状態確認

セキュリティ方針 (docs/adr/0002-db-encryption.md 参照):
    - 認証は SCRAM-SHA-256 のみ。パスワードはランダム生成し .env (gitignore 済) に保存
    - 接続は TLS 必須 (pg_hba は hostssl のみ / TLSv1.3 以上)
    - localhost 以外からの接続を受け付けない
    - データチェックサム有効 (破損検知)
    - アプリ用ロールはスーパーユーザーではない
"""

from __future__ import annotations

import base64
import datetime as dt
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home()))
# 実行環境はプロジェクトの .runtime に置く (%LOCALAPPDATA% は、パッケージ化されたアプリから書くと
# そのアプリ専用の場所に振り替えられ、ほかのコンソールから見えなくなることがあるため)
RUNTIME_DIR = BASE_DIR / ".runtime"
DEFAULT_PG_BIN = RUNTIME_DIR / "pg17" / "pgsql" / "bin"
DEFAULT_PGDATA = RUNTIME_DIR / "pgdata"


def _b64key(n: int = 32) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(n)).decode()


def read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def ensure_env() -> dict[str, str]:
    """.env が無ければ秘密値をランダム生成して作る。既存値は上書きしない。"""
    env = read_env()
    defaults = {
        "DJANGO_DEBUG": "True",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
        "DJANGO_ADMIN_URL": f"ops-{secrets.token_hex(4)}/",
        "DJANGO_SECURE_COOKIES": "False",
        # フィールド暗号鍵: "鍵ID:base64鍵" をカンマ区切り。先頭が暗号化に使う現行鍵
        "MIKKE_FIELD_KEYS": f"1:{_b64key()}",
        "MIKKE_BLIND_INDEX_KEY": _b64key(),
        "DB_NAME": "mikke",
        "DB_USER": "mikke_app",
        "DB_PASSWORD": secrets.token_urlsafe(24),
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_SSLMODE": "require",
        "PG_BIN": str(DEFAULT_PG_BIN),
        "PGDATA": str(DEFAULT_PGDATA),
        "PG_SUPERUSER_PASSWORD": secrets.token_urlsafe(24),
    }
    changed = False
    for k, v in defaults.items():
        if k not in env:
            env[k] = v
            changed = True
    if changed:
        lines = ["# みっけ ローカル環境設定 (自動生成)。このファイルは絶対にコミットしないこと。"]
        lines += [f"{k}={v}" for k, v in env.items()]
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[env] {ENV_PATH} を作成/更新しました (秘密値は表示しません)")
    return env


def pg(env: dict[str, str], tool: str) -> str:
    exe = Path(env["PG_BIN"]) / f"{tool}.exe"
    if not exe.exists():
        exe = Path(env["PG_BIN"]) / tool
    return str(exe)


def write_tls_cert(pgdata: Path) -> None:
    """自己署名のサーバー証明書を生成 (localhost 用)。"""
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    x509.IPAddress(ipaddress.ip_address("::1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    (pgdata / "server.key").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (pgdata / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def cmd_init() -> None:
    env = ensure_env()
    pgdata = Path(env["PGDATA"])
    if (pgdata / "PG_VERSION").exists():
        print(f"[init] 既に初期化済み: {pgdata}")
    else:
        pgdata.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pw", encoding="utf-8") as f:
            f.write(env["PG_SUPERUSER_PASSWORD"])
            pwfile = f.name
        try:
            subprocess.run(
                [
                    pg(env, "initdb"),
                    "-D", str(pgdata),
                    "-U", "postgres",
                    "--pwfile", pwfile,
                    "--auth=scram-sha-256",
                    "--encoding=UTF8",
                    "--locale=C",
                    "--data-checksums",
                ],
                check=True,
            )
        finally:
            os.remove(pwfile)
        write_tls_cert(pgdata)
        with (pgdata / "postgresql.conf").open("a", encoding="utf-8") as f:
            f.write(
                "\n# ---- みっけ セキュリティ設定 ----\n"
                "listen_addresses = 'localhost'\n"
                f"port = {int(env['DB_PORT'])}\n"
                "password_encryption = 'scram-sha-256'\n"
                "ssl = on\n"
                "ssl_cert_file = 'server.crt'\n"
                "ssl_key_file = 'server.key'\n"
                "ssl_min_protocol_version = 'TLSv1.3'\n"
                "log_connections = on\n"
                "log_disconnections = on\n"
                "timezone = 'UTC'\n"
            )
        (pgdata / "pg_hba.conf").write_text(
            "# TYPE   DATABASE USER ADDRESS       METHOD\n"
            "# TLS 接続かつ SCRAM 認証のみ許可。平文 TCP 接続は拒否する。\n"
            "hostssl  all      all  127.0.0.1/32  scram-sha-256\n"
            "hostssl  all      all  ::1/128       scram-sha-256\n",
            encoding="utf-8",
        )
        print(f"[init] initdb 完了: {pgdata}")
    cmd_start()
    create_role_and_db(env)


def create_role_and_db(env: dict[str, str]) -> None:
    import psycopg
    from psycopg import sql

    conninfo = dict(
        host=env["DB_HOST"],
        port=env["DB_PORT"],
        user="postgres",
        password=env["PG_SUPERUSER_PASSWORD"],
        dbname="postgres",
        sslmode="require",
    )
    with psycopg.connect(**conninfo, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (env["DB_USER"],)).fetchone()
        if not exists:
            # CREATEDB はテスト用 DB 作成 (manage.py test) のため。本番では付与しない。
            conn.execute(
                sql.SQL("CREATE ROLE {} LOGIN CREATEDB PASSWORD {}").format(
                    sql.Identifier(env["DB_USER"]), sql.Literal(env["DB_PASSWORD"])
                )
            )
            print(f"[db] ロール {env['DB_USER']} を作成")
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (env["DB_NAME"],)).fetchone():
            conn.execute(
                sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
                    sql.Identifier(env["DB_NAME"]), sql.Identifier(env["DB_USER"])
                )
            )
            conn.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(env["DB_NAME"]))
            )
            print(f"[db] データベース {env['DB_NAME']} を作成")
        ssl = conn.execute("SELECT ssl, version FROM pg_stat_ssl WHERE pid = pg_backend_pid()").fetchone()
        print(f"[db] 接続の TLS 状態: ssl={ssl[0]} version={ssl[1]}")


def cmd_start() -> None:
    env = ensure_env()
    pgdata = env["PGDATA"]
    st = subprocess.run([pg(env, "pg_ctl"), "status", "-D", pgdata], capture_output=True, text=True)
    if st.returncode == 0:
        print("[start] 既に起動中")
        return
    log = Path(pgdata).parent / "postgres.log"
    # 子プロセス (postgres) が標準出力ハンドルを継承すると呼び出し側のパイプが閉じないため DEVNULL にする
    subprocess.run(
        [pg(env, "pg_ctl"), "start", "-D", pgdata, "-l", str(log), "-w"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **detached_console_kwargs(),
    )
    print(f"[start] 起動しました (ログ: {log})")


def detached_console_kwargs() -> dict:
    """Windows で、起動した側のコンソールから切り離して PostgreSQL を動かすための subprocess の引数。

    起動した側 (コマンドプロンプトのウィンドウ・エディタのターミナルなど) のコンソールを postgres が使い続けると、
    そのウィンドウを閉じたあとに新しい接続用のプロセスが作れなくなり (例外 0xC0000142)、サーバーが止まってしまう。
    専用の見えないコンソールで起動して、起動した側を閉じても動き続けるようにする。
    """
    if os.name != "nt":
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0  # SW_HIDE
    return {"creationflags": subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP, "startupinfo": info}


def cmd_stop() -> None:
    env = ensure_env()
    subprocess.run([pg(env, "pg_ctl"), "stop", "-D", env["PGDATA"], "-m", "fast", "-w"], check=False)


def cmd_status() -> None:
    env = ensure_env()
    subprocess.run([pg(env, "pg_ctl"), "status", "-D", env["PGDATA"]], check=False)


if __name__ == "__main__":
    commands = {"init": cmd_init, "start": cmd_start, "stop": cmd_stop, "status": cmd_status}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(__doc__)
        sys.exit(2)
    commands[sys.argv[1]]()
