"""Integration fixtures: a REAL Postgres 16 on 127.0.0.1:5433.

Resolution order:
1. A server is already listening (CI's postgres service, or a dev's own) →
   use it, ensuring the eden_app role and eden database exist.
2. Local postgres binaries are available → spawn a throwaway cluster in the
   pytest tmp area (as a non-root user when running as root), tear it down
   at session end.
3. Neither → skip the whole integration package.

Either way, the Alembic control-plane migration is applied before tests run,
exactly as production would.
"""

from __future__ import annotations

import os
import pwd
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

PG_PORT = 5433
PG_HOST = "127.0.0.1"
OWNER = "eden_owner"
OWNER_PW = "eden_owner_pw"
APP = "eden_app"
APP_PW = "eden_app_pw"
DB = "eden"

_EDEN_ROOT = Path(__file__).resolve().parents[2]  # the eden/ package dir


def _pg_bindir() -> Path | None:
    candidates = sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True)
    return candidates[0] if candidates else None


def _try_connect_sync(dsn: str) -> bool:
    import asyncio

    import asyncpg

    async def _ping() -> bool:
        try:
            conn = await asyncpg.connect(dsn, timeout=3)
            await conn.close()
            return True
        except Exception:
            return False

    return asyncio.run(_ping())


def _run_as(user: str | None, cmd: list[str], **kw) -> subprocess.CompletedProcess:
    if user:
        cmd = ["runuser", "-u", user, "--", *cmd]
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _spawn_cluster() -> tuple[Path, str | None] | None:
    """initdb + start a cluster on PG_PORT. Returns (datadir, run_user)."""
    bindir = _pg_bindir()
    if bindir is None:
        return None

    run_user: str | None = None
    if os.geteuid() == 0:
        # postgres refuses to run as root; use (or create) an unprivileged user.
        for candidate in ("postgres", "nobody"):
            try:
                pwd.getpwnam(candidate)
                run_user = candidate
                break
            except KeyError:
                continue
        if run_user is None:
            subprocess.run(["useradd", "--system", "pgtest"], capture_output=True)
            run_user = "pgtest"

    base = Path(tempfile.mkdtemp(prefix="eden-pgtest-"))
    datadir = base / "data"
    sockdir = base / "sock"
    datadir.mkdir()
    sockdir.mkdir()
    if run_user:
        subprocess.run(["chown", "-R", run_user, str(base)], check=True)

    r = _run_as(run_user, [str(bindir / "initdb"), "-A", "trust", "-U", OWNER, "-D", str(datadir)])
    if r.returncode != 0:
        return None

    r = _run_as(
        run_user,
        [
            str(bindir / "pg_ctl"),
            "-D", str(datadir),
            "-l", str(base / "pg.log"),
            "-o", f"-p {PG_PORT} -c listen_addresses={PG_HOST} -c unix_socket_directories={sockdir}",
            "start",
        ],
    )
    if r.returncode != 0:
        return None

    deadline = time.monotonic() + 30
    probe = f"postgresql://{OWNER}@{PG_HOST}:{PG_PORT}/postgres"
    while time.monotonic() < deadline:
        if _try_connect_sync(probe):
            return datadir, run_user
        time.sleep(0.5)
    return None


def _bootstrap_roles_and_db() -> None:
    """Idempotently ensure the app role + database + baseline REVOKEs exist,
    mirroring scripts/initdb/01_roles.sql for non-compose environments."""
    import asyncio

    import asyncpg

    async def _go() -> None:
        conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=OWNER, password=OWNER_PW, database="postgres"
        )
        try:
            if not await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", APP):
                await conn.execute(f"CREATE ROLE {APP} LOGIN PASSWORD '{APP_PW}'")
            if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", DB):
                await conn.execute(f'CREATE DATABASE {DB} OWNER {OWNER}')
        finally:
            await conn.close()

        conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=OWNER, password=OWNER_PW, database=DB
        )
        try:
            await conn.execute(f"REVOKE CREATE ON DATABASE {DB} FROM PUBLIC")
            await conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            await conn.execute(f"GRANT CONNECT ON DATABASE {DB} TO {APP}")
        finally:
            await conn.close()

    asyncio.run(_go())


def _alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_EDEN_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_EDEN_ROOT / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def pg_server():
    admin_probe = f"postgresql://{OWNER}:{OWNER_PW}@{PG_HOST}:{PG_PORT}/postgres"
    spawned: tuple[Path, str | None] | None = None

    if not _try_connect_sync(admin_probe):
        spawned = _spawn_cluster()
        if spawned is None:
            pytest.skip(
                "no Postgres on 127.0.0.1:5433 and no local postgres binaries to spawn one"
            )

    _bootstrap_roles_and_db()
    _alembic_upgrade()
    yield

    if spawned is not None:
        datadir, run_user = spawned
        bindir = _pg_bindir()
        stopped = False
        if bindir is not None:
            r = _run_as(
                run_user,
                [str(bindir / "pg_ctl"), "-D", str(datadir), "-m", "immediate", "stop"],
            )
            stopped = r.returncode == 0
        if not stopped:
            # Belt and braces: a zombie server would make the NEXT run reuse
            # a stale cluster (old schema state) — kill it by datadir match.
            subprocess.run(["pkill", "-f", str(datadir)], capture_output=True)
            time.sleep(1)
        shutil.rmtree(datadir.parent, ignore_errors=True)
