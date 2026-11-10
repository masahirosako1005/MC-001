"""ローカル HTTPS リバースプロキシ (scripts/devproxy.py と deploy/nginx/nginx.conf.template) のテスト。"""

import importlib.util
import ipaddress
import os
import re
import runpy
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)


def load_devproxy():
    spec = importlib.util.spec_from_file_location("devproxy", ROOT / "scripts" / "devproxy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NginxConfigTests(SimpleTestCase):
    def setUp(self):
        self.dp = load_devproxy()
        # 桁そろえの空白を 1 個にまとめて比べる
        self.conf = re.sub(r"[ 	]+", " ", self.dp.render_config())

    def test_all_placeholders_are_filled(self):
        self.assertNotIn("{{", self.conf)
        self.assertIn(f"listen 127.0.0.1:{self.dp.PROXY_PORT} ssl;", self.conf)
        self.assertIn(f"server 127.0.0.1:{self.dp.APP_PORT};", self.conf)

    def test_listens_only_on_loopback_with_modern_tls(self):
        for line in self.conf.splitlines():
            if line.strip().startswith("listen "):
                self.assertIn("127.0.0.1:", line)
        self.assertIn("ssl_protocols TLSv1.2 TLSv1.3;", self.conf)
        self.assertIn("server_tokens off;", self.conf)

    def test_forwarded_headers_are_overwritten_not_appended(self):
        # クライアントが送った X-Forwarded-For を引き継ぐと接続元 IP を偽装できる
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", self.conf)
        self.assertNotIn("$proxy_add_x_forwarded_for", self.conf)
        self.assertIn("proxy_set_header X-Forwarded-Proto https;", self.conf)

    def test_plain_http_is_redirected_to_https(self):
        self.assertIn("error_page 497 =301 https://", self.conf)

    def test_unknown_placeholder_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.dp.render_config("listen {{UNKNOWN}};")


class CertificateTests(SimpleTestCase):
    def test_self_signed_cert_is_limited_to_localhost_server_auth(self):
        from cryptography import x509
        from cryptography.x509.oid import ExtendedKeyUsageOID

        dp = load_devproxy()
        with tempfile.TemporaryDirectory() as tmp:
            dp.CERT = Path(tmp) / "certs" / "localhost.crt"
            dp.KEY = Path(tmp) / "certs" / "localhost.key"
            with mock.patch("builtins.print"):
                dp.write_cert()
            cert = x509.load_pem_x509_certificate(dp.CERT.read_bytes())

        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        self.assertEqual(san.get_values_for_type(x509.DNSName), ["localhost"])
        self.assertEqual(set(san.get_values_for_type(x509.IPAddress)),
                         {ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")})
        # 信頼済みに登録しても、ほかのサイトの証明書を発行する認証局としては使えない
        self.assertFalse(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        self.assertFalse(cert.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign)
        self.assertEqual(list(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value),
                         [ExtendedKeyUsageOID.SERVER_AUTH])


class ProxySettingTests(SimpleTestCase):
    """SECURE_PROXY_SSL_HEADER は TLS 終端プロキシの内側で動かすと明示したときだけ有効にする。"""

    def load_settings(self, **env):
        base = {"DJANGO_DEBUG": "1"}
        with mock.patch.dict(os.environ, {**base, **env}):
            return runpy.run_path(str(ROOT / "config" / "settings.py"))

    def test_proxy_header_is_off_by_default(self):
        ns = self.load_settings(DJANGO_BEHIND_TLS_PROXY="0")
        self.assertNotIn("SECURE_PROXY_SSL_HEADER", ns)

    def test_proxy_header_is_on_when_behind_tls_proxy(self):
        ns = self.load_settings(DJANGO_BEHIND_TLS_PROXY="1")
        self.assertEqual(ns["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_hsts_can_be_disabled_for_localhost(self):
        ns = self.load_settings(DJANGO_DEBUG="0", DJANGO_HSTS_SECONDS="0", MIKKE_CACHE="db")
        self.assertEqual(ns["SECURE_HSTS_SECONDS"], 0)
        self.assertFalse(ns["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
