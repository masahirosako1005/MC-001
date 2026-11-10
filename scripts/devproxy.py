"""ローカルの HTTPS リバースプロキシ (nginx) とアプリ本体 (waitress) の起動・停止。

    python scripts\\devproxy.py run       # nginx を起動し、アプリを 127.0.0.1:8080 で動かす (Ctrl+C で両方止める)
    python scripts\\devproxy.py start     # nginx だけ起動
    python scripts\\devproxy.py stop      # nginx を止める
    python scripts\\devproxy.py status
    python scripts\\devproxy.py cert      # 自己署名証明書を作り直す

構成:
    ブラウザ ──https://localhost:8000── nginx ──http://127.0.0.1:8080── waitress + Django

- 証明書・鍵・nginx の設定・ログは %LOCALAPPDATA%\\mikke\\proxy に置く (リポジトリには入れない)
- 証明書は localhost / 127.0.0.1 / ::1 だけに使える自己署名。ブラウザの警告を消すには、利用者が
  証明書を「信頼されたルート証明機関」に登録する (README 参照。システムの設定変更なので本人が行う)
- アプリ本体は 127.0.0.1 だけで待ち受ける (nginx を通らないと外からは届かない)

環境変数: NGINX_HOME (既定 %LOCALAPPDATA%\\nginx-1.28.0)、MIKKE_PROXY_DIR、MIKKE_PROXY_PORT (8000)、MIKKE_APP_PORT (8080)
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = BASE_DIR / "deploy" / "nginx" / "nginx.conf.template"
LOCAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
NGINX_HOME = Path(os.environ.get("NGINX_HOME", str(LOCAL / "nginx-1.28.0")))
PROXY_DIR = Path(os.environ.get("MIKKE_PROXY_DIR", str(LOCAL / "mikke" / "proxy")))
PROXY_PORT = int(os.environ.get("MIKKE_PROXY_PORT", "8000"))
APP_PORT = int(os.environ.get("MIKKE_APP_PORT", "8080"))
CERT = PROXY_DIR / "certs" / "localhost.crt"
KEY = PROXY_DIR / "certs" / "localhost.key"
CONF = PROXY_DIR / "conf" / "nginx.conf"


def _posix(p: Path) -> str:
    return str(p).replace("\\", "/")


def write_cert() -> None:
    """localhost 専用の自己署名証明書 (ECDSA P-256、1 年)。鍵はほかの用途に使えないよう用途を限定する。"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    CERT.parent.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Mikke local development")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.IPAddress(ipaddress.ip_address("::1")),
        ]), critical=False)
        # 認証局としては使えない (この証明書を信頼しても、ほかのサイトの証明書を作れない)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, content_commitment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                     crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    KEY.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"証明書を作りました: {CERT}")


def render_config(template: str | None = None) -> str:
    text = template if template is not None else TEMPLATE.read_text(encoding="utf-8")
    values = {
        "PROXY_PORT": str(PROXY_PORT), "APP_PORT": str(APP_PORT),
        "CERT": _posix(CERT), "KEY": _posix(KEY),
        "MIME_TYPES": _posix(NGINX_HOME / "conf" / "mime.types"),
        "STATIC_ROOT": _posix(BASE_DIR / "staticfiles"),
    }
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    if "{{" in text:
        raise SystemExit("nginx.conf.template に未設定の項目があります。")
    return text


def write_config() -> None:
    for d in ("conf", "logs", "temp"):
        (PROXY_DIR / d).mkdir(parents=True, exist_ok=True)
    CONF.write_text(render_config(), encoding="utf-8")


def _nginx(*args: str, wait: bool = True):
    exe = NGINX_HOME / "nginx.exe"
    if not exe.exists():
        raise SystemExit(f"nginx が見つかりません: {exe} (NGINX_HOME で場所を指定できます)")
    cmd = [str(exe), "-p", _posix(PROXY_DIR) + "/", "-c", _posix(CONF), *args]
    kw = {"stdin": subprocess.DEVNULL, "cwd": str(PROXY_DIR)}
    if wait:
        return subprocess.run(cmd, capture_output=True, text=True, **{k: v for k, v in kw.items() if k != "stdin"})
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, **kw)


def is_running() -> bool:
    pid = PROXY_DIR / "logs" / "nginx.pid"
    if not pid.exists():
        return False
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid.read_text().strip()}", "/NH"],
                         capture_output=True, text=True).stdout
    return "nginx" in out.lower()


def cmd_start() -> None:
    if not CERT.exists() or not KEY.exists():
        write_cert()
    write_config()
    test = _nginx("-t")
    if test.returncode != 0:
        raise SystemExit(f"nginx の設定に誤りがあります:\n{test.stderr}")
    if is_running():
        _nginx("-s", "reload")
        print("nginx の設定を読み込み直しました。")
    else:
        _nginx(wait=False)
        print(f"nginx を起動しました: https://localhost:{PROXY_PORT}/ → http://127.0.0.1:{APP_PORT}/")


def cmd_stop() -> None:
    if is_running():
        _nginx("-s", "quit")
        print("nginx を止めました。")
    else:
        print("nginx は動いていません。")


def cmd_status() -> None:
    print(f"nginx: {'起動中' if is_running() else '停止中'} (https://localhost:{PROXY_PORT}/)")
    print(f"証明書: {CERT} {'あり' if CERT.exists() else 'なし'}")


def cmd_run() -> None:
    """静的ファイルを集め、nginx を起動し、アプリを 127.0.0.1 で動かす。終了すると nginx も止める。"""
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    from django.core.management import call_command

    django.setup()
    call_command("collectstatic", interactive=False, verbosity=0)
    call_command("createcachetable", verbosity=0)
    cmd_start()
    from waitress import serve

    from config.wsgi import application

    try:
        print(f"アプリを起動します: http://127.0.0.1:{APP_PORT}/ (nginx 経由で https://localhost:{PROXY_PORT}/ を開いてください)")
        # ident=None: Server ヘッダーに版番号を出さない
        # clear_untrusted_proxy_headers=False: nginx が付けた X-Forwarded-Proto / For を Django まで渡す。
        #   信頼するかどうかは Django 側 (SECURE_PROXY_SSL_HEADER と MIKKE_TRUSTED_PROXIES) の 1 か所で決める。
        #   アプリは 127.0.0.1 だけで待ち受け、nginx は X-Forwarded-For を上書きするので外から偽装できない
        serve(application, host="127.0.0.1", port=APP_PORT, threads=8, ident=None,
              clear_untrusted_proxy_headers=False)
    finally:
        cmd_stop()


COMMANDS = {"run": cmd_run, "start": cmd_start, "stop": cmd_stop, "status": cmd_status, "cert": write_cert}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit("使い方: python scripts\\devproxy.py run|start|stop|status|cert")
    COMMANDS[sys.argv[1]]()
