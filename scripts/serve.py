"""みっけの Web サービスをまとめて起動・停止する (PostgreSQL → マイグレーション → nginx + アプリ)。

    start.bat                              # 起動 (= python scripts\\serve.py start)。Ctrl+C で止める
    stop.bat                               # 停止 (= python scripts\\serve.py stop)。別のウィンドウから止めるとき
    python scripts\\serve.py status         # 状態 (DB・nginx・アプリ・証明書)

start の流れ:
    1. .env があるか確かめる (なければ初期設定の手順を出して終わる)
    2. DB_ENGINE=postgresql なら PostgreSQL を起動し、接続できるまで待つ (最大 60 秒)
    3. まだ適用していないマイグレーションを適用する (--no-migrate で省略)
    4. scripts/devproxy.py run: 静的ファイルの収集 → nginx (https://localhost:8000) → アプリ (127.0.0.1:8080)

stop は、アプリ (start が記録したプロセス番号) と nginx を止める。--with-db を付けると PostgreSQL も止める。
PC を再起動したあとも start だけで動く (以前は PostgreSQL を先に手で起動する必要があった)。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
DB_WAIT_SECONDS = 60


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


devproxy = _load("devproxy")
localdb = _load("localdb")
APP_PID = devproxy.PROXY_DIR / "app.pid"


def say(msg: str) -> None:
    print(f"[mikke] {msg}", flush=True)


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def recorded_app_pid() -> int | None:
    try:
        pid = int(APP_PID.read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if pid_alive(pid) else None


def uses_postgres() -> bool:
    return localdb.read_env().get("DB_ENGINE", "postgresql").lower() in ("", "postgresql", "postgres")


def setup_django() -> None:
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def wait_for_db(seconds: int = DB_WAIT_SECONDS) -> None:
    from django.db import connection
    from django.db.utils import OperationalError

    deadline = time.monotonic() + seconds
    while True:
        try:
            connection.ensure_connection()
            return
        except OperationalError as exc:
            connection.close()
            if time.monotonic() > deadline:
                raise SystemExit(f"データベースに接続できません ({seconds} 秒待ちました): {exc}") from None
            time.sleep(2)


def pending_migrations() -> list[str]:
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{m.app_label}.{m.name}" for m, _ in plan]


def start_background() -> None:
    """自分自身 (serve.py start) を、見えない別のコンソールで起動して、すぐに戻る。

    起動したウィンドウ・ターミナルを閉じても止まらない。出力は .runtime\\proxy\\logs\\app.log。
    止めるときは stop.bat。
    """
    log = devproxy.PROXY_DIR / "logs" / "app.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    flags = 0
    info = None
    if os.name == "nt":
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0  # SW_HIDE
        flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    with open(log, "ab") as out:
        for extra in (getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0), 0):  # 親のジョブから外れられれば外す
            try:
                subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "start"], cwd=str(BASE_DIR),
                                 stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, env=env,
                                 creationflags=flags | extra, startupinfo=info, close_fds=True)
                break
            except OSError:
                if not extra:
                    raise
    say(f"バックグラウンドで起動しました: https://localhost:{devproxy.PROXY_PORT}/ (ログ: {log}、止めるときは stop.bat)")


def cmd_start(args) -> None:
    if getattr(args, "background", False):
        start_background()
        return
    if not localdb.ENV_PATH.exists():
        raise SystemExit("設定ファイル .env がありません。最初に README の「セットアップ」を行ってください "
                         "(python scripts\\localdb.py init → manage.py migrate → manage.py seed_mikke)。")
    pid = recorded_app_pid()
    if pid or port_in_use(devproxy.APP_PORT):
        raise SystemExit(f"アプリはすでに動いています (127.0.0.1:{devproxy.APP_PORT}"
                         f"{f'、プロセス {pid}' if pid else ''})。止めるときは stop.bat を実行してください。")
    if port_in_use(devproxy.PROXY_PORT) and not devproxy.is_running():
        raise SystemExit(f"ポート {devproxy.PROXY_PORT} を別のプログラムが使っています。そのプログラムを止めてください。")

    if uses_postgres():
        say("PostgreSQL を起動します")
        localdb.cmd_start()
    setup_django()
    say("データベースに接続しています")
    wait_for_db()
    if args.migrate:
        todo = pending_migrations()
        if todo:
            from django.core.management import call_command

            say(f"マイグレーションを適用します: {', '.join(todo)}")
            call_command("migrate", interactive=False, verbosity=0)
    APP_PID.parent.mkdir(parents=True, exist_ok=True)
    APP_PID.write_text(str(os.getpid()))
    say(f"起動します: https://localhost:{devproxy.PROXY_PORT}/ (止めるときは Ctrl+C か stop.bat)")
    try:
        devproxy.cmd_run()  # Ctrl+C / stop で戻ってくる。nginx は cmd_run が止める
    except KeyboardInterrupt:
        pass
    finally:
        APP_PID.unlink(missing_ok=True)
        say("停止しました")


def cmd_stop(args) -> None:
    # nginx はアプリのプロセスから起動しているので、アプリを止める (プロセスごと終了) 前に、きちんと止める
    devproxy.cmd_stop()
    pid = recorded_app_pid()
    if pid:
        say(f"アプリ (プロセス {pid}) を止めます")
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)  # noqa: S607
        else:
            os.kill(pid, 15)
        APP_PID.unlink(missing_ok=True)
    else:
        say("アプリは動いていません")
    if args.with_db and uses_postgres():
        say("PostgreSQL を止めます")
        localdb.cmd_stop()


def cmd_status(args) -> None:
    if uses_postgres():
        env = localdb.read_env()
        pgdata = env.get("PGDATA", str(localdb.DEFAULT_PGDATA))
        try:
            ok = subprocess.run([localdb.pg(env, "pg_ctl"), "status", "-D", pgdata],
                                capture_output=True).returncode == 0
        except (KeyError, OSError):
            ok = False
        say(f"PostgreSQL: {'起動中' if ok else '停止中'}")
    else:
        say("データベース: SQLite")
    pid = recorded_app_pid()
    app = port_in_use(devproxy.APP_PORT)
    say(f"アプリ: {'起動中' if app else '停止中'} (127.0.0.1:{devproxy.APP_PORT}{f'、プロセス {pid}' if pid else ''})")
    say(f"nginx: {'起動中' if devproxy.is_running() else '停止中'} (https://localhost:{devproxy.PROXY_PORT}/)")
    if devproxy.CERT.exists():
        say(devproxy._trust_line())


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="serve.py", description="みっけの Web サービスの起動・停止")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start", help="PostgreSQL・nginx・アプリを起動する (Ctrl+C で停止)")
    p.add_argument("--no-migrate", dest="migrate", action="store_false", help="マイグレーションを適用しない")
    p.add_argument("--background", action="store_true",
                   help="見えない別のコンソールで起動してすぐ戻る (ウィンドウを閉じても止まらない)")
    p.set_defaults(func=cmd_start)
    p = sub.add_parser("stop", help="アプリと nginx を止める")
    p.add_argument("--with-db", action="store_true", help="PostgreSQL も止める")
    p.set_defaults(func=cmd_stop)
    sub.add_parser("status", help="状態を表示する").set_defaults(func=cmd_status)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
