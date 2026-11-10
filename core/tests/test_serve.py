"""起動スクリプト (scripts/serve.py) のテスト。実際の PostgreSQL・nginx は起動しない。"""

from __future__ import annotations

import importlib.util
import socket
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase


def load_serve():
    spec = importlib.util.spec_from_file_location("serve", settings.BASE_DIR / "scripts" / "serve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ServeScriptTests(TestCase):
    def setUp(self):
        self.serve = load_serve()

    def test_port_in_use(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            port = s.getsockname()[1]
            self.assertTrue(self.serve.port_in_use(port))
        self.assertFalse(self.serve.port_in_use(port))

    def test_no_pending_migrations_in_test_db(self):
        self.assertEqual(self.serve.pending_migrations(), [])

    def test_start_refuses_when_app_already_running(self):
        s = self.serve
        with mock.patch.object(s.localdb, "ENV_PATH", Path(__file__)), \
                mock.patch.object(s, "recorded_app_pid", return_value=1234), \
                mock.patch.object(s.localdb, "cmd_start") as db_start, \
                mock.patch.object(s.devproxy, "cmd_run") as run:
            with self.assertRaises(SystemExit) as cm:
                s.main(["start"])
        self.assertIn("すでに動いています", str(cm.exception))
        db_start.assert_not_called()
        run.assert_not_called()

    def test_start_requires_env_file(self):
        s = self.serve
        with mock.patch.object(s.localdb, "ENV_PATH", Path("does-not-exist.env")), \
                self.assertRaises(SystemExit) as cm:
            s.main(["start"])
        self.assertIn(".env がありません", str(cm.exception))

    def test_start_runs_db_then_migrate_then_proxy(self):
        s = self.serve
        calls = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(s, "APP_PID", Path(tmp) / "app.pid"), \
                mock.patch.object(s.localdb, "ENV_PATH", Path(__file__)), \
                mock.patch.object(s, "port_in_use", return_value=False), \
                mock.patch.object(s, "uses_postgres", return_value=True), \
                mock.patch.object(s.localdb, "cmd_start", side_effect=lambda: calls.append("db")), \
                mock.patch.object(s, "wait_for_db", side_effect=lambda: calls.append("wait")), \
                mock.patch.object(s, "pending_migrations", return_value=[]), \
                mock.patch.object(s.devproxy, "cmd_run", side_effect=lambda: calls.append("run")), \
                mock.patch("builtins.print"):
            s.main(["start"])
            self.assertFalse((Path(tmp) / "app.pid").exists())  # 止めたらプロセス番号の記録を消す
        self.assertEqual(calls, ["db", "wait", "run"])

    def test_stop_stops_app_and_nginx_and_optionally_db(self):
        s = self.serve
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(s, "APP_PID", Path(tmp) / "app.pid"), \
                mock.patch.object(s, "recorded_app_pid", return_value=4321), \
                mock.patch.object(s, "uses_postgres", return_value=True), \
                mock.patch.object(s.subprocess, "run") as run, \
                mock.patch.object(s.os, "name", "nt"), \
                mock.patch.object(s.devproxy, "cmd_stop") as nginx_stop, \
                mock.patch.object(s.localdb, "cmd_stop") as db_stop, \
                mock.patch("builtins.print"):
            s.main(["stop"])
            self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "4321", "/T", "/F"])
            nginx_stop.assert_called_once()
            db_stop.assert_not_called()
            s.main(["stop", "--with-db"])
            db_stop.assert_called_once()
