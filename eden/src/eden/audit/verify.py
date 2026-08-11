"""Audit-chain verification CLI.

Usage:
    python -m eden.audit.verify

Exit code 0 when the chain verifies end-to-end, 1 when a broken link is
found (first broken seq printed), 2 on operational failure. Run it from
cron / CI — tamper-evidence that is never checked is decoration.
"""

from __future__ import annotations

import asyncio
import sys

from eden.audit.logger import verify_chain
from eden.db.session import control_session


async def _main() -> int:
    async with control_session() as session:
        ok, first_broken_seq = await verify_chain(session)
    if ok:
        print("audit chain OK")
        return 0
    print(f"audit chain BROKEN at seq={first_broken_seq}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(_main()))
    except SystemExit:
        raise
    except Exception as exc:
        print(f"verification failed to run: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
