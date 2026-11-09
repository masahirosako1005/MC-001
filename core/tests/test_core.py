from __future__ import annotations

import base64
import os

from django.core.exceptions import FieldError
from django.db import connection
from django.test import TestCase, override_settings

from accounts.models import User
from core import crypto
from core.models import AuditLog


class CryptoTests(TestCase):
    def test_roundtrip(self):
        ct = crypto.encrypt("みっけ@example.com", "ctx.a")
        self.assertTrue(ct.startswith("enc:1:"))
        self.assertNotIn("example", ct)
        self.assertEqual(crypto.decrypt(ct, "ctx.a"), "みっけ@example.com")

    def test_nondeterministic(self):
        self.assertNotEqual(crypto.encrypt("x", "c"), crypto.encrypt("x", "c"))

    def test_tamper_detected(self):
        ct = crypto.encrypt("secret", "ctx")
        prefix, kid, token = ct.split(":", 2)
        blob = bytearray(base64.urlsafe_b64decode(token))
        blob[-1] ^= 0x01
        tampered = f"{prefix}:{kid}:{base64.urlsafe_b64encode(bytes(blob)).decode()}"
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(tampered, "ctx")

    def test_context_binding(self):
        """別カラムへ暗号文を移し替えても復号できない (AAD)。"""
        ct = crypto.encrypt("secret", "accounts.user.email")
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(ct, "rewards.usercoupon.redeem_code")

    def test_key_rotation(self):
        from django.conf import settings

        old_spec = settings.MIKKE_FIELD_KEYS
        ct_old = crypto.encrypt("rotate-me", "ctx")
        new_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        with override_settings(MIKKE_FIELD_KEYS=f"2:{new_key},{old_spec}"):
            crypto.reset_key_cache()
            try:
                self.assertEqual(crypto.decrypt(ct_old, "ctx"), "rotate-me")  # 旧鍵で復号できる
                self.assertTrue(crypto.needs_rotation(ct_old))
                ct_new = crypto.encrypt("rotate-me", "ctx")
                self.assertTrue(ct_new.startswith("enc:2:"))  # 新鍵で暗号化される
            finally:
                crypto.reset_key_cache()
        crypto.reset_key_cache()

    def test_blind_index_is_deterministic_and_purpose_bound(self):
        a = crypto.blind_index("a@example.com", "user.email")
        self.assertEqual(a, crypto.blind_index("a@example.com", "user.email"))
        self.assertNotEqual(a, crypto.blind_index("a@example.com", "other"))


class EncryptedFieldDbTests(TestCase):
    def test_email_is_ciphertext_at_rest(self):
        """DB を直接見ても平文のメールアドレスは見えない。"""
        user = User.objects.create_user("Plain.Text@Example.com", "correct horse battery staple", "たろう")
        with connection.cursor() as cur:
            cur.execute("SELECT email, email_hash FROM accounts_user WHERE id = %s", [user.pk])
            raw_email, raw_hash = cur.fetchone()
        self.assertTrue(raw_email.startswith("enc:"))
        self.assertNotIn("example", raw_email.lower())
        self.assertEqual(len(raw_hash), 64)
        self.assertEqual(User.objects.get(pk=user.pk).email, "plain.text@example.com")

    def test_lookup_on_encrypted_field_is_blocked(self):
        with self.assertRaises(FieldError):
            list(User.objects.filter(email="a@example.com"))


class AuditLogTests(TestCase):
    def test_append_only(self):
        entry = AuditLog.objects.create(action="test")
        entry.action = "changed"
        with self.assertRaises(ValueError):
            entry.save()
        with self.assertRaises(ValueError):
            entry.delete()


class SecurityHeaderTests(TestCase):
    def test_headers_on_landing(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        csp = res.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertIn("camera=(self)", res.headers["Permissions-Policy"])
        self.assertEqual(res.headers["X-Frame-Options"], "DENY")
        self.assertEqual(res.headers["X-Content-Type-Options"], "nosniff")
