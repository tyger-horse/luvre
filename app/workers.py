"""In-process workers (M2): TTL sweeper thread.

Started from the app lifespan unless LUVRE_RUN_WORKER=0 (tests set that).
Background removal was scratched — the founders cut their own plates —
so the only loop left is the unpaid-order sweep. Swap for RQ/Celery
later if ever needed.
"""

from __future__ import annotations

import os
import threading
import time


def worker_enabled() -> bool:
    return os.getenv("LUVRE_RUN_WORKER", "1") == "1"


def run_ttl_sweep_forever(poll_seconds: int = 600) -> None:
    from app.db import SessionLocal
    from app.models import Order, Piece
    from app.services.orders import sweep_expired

    while True:
        try:
            with SessionLocal() as db:
                orders = db.query(Order).filter(
                    Order.status.in_(["awaiting_payment", "reserved"])
                ).all()
                lookup = lambda o: db.get(Piece, o.piece_id)  # noqa: E731
                if sweep_expired(orders, lookup):
                    db.commit()
        except Exception:
            pass
        time.sleep(poll_seconds)


def start_workers() -> list[threading.Thread]:
    if not worker_enabled():
        return []
    t = threading.Thread(target=run_ttl_sweep_forever, kwargs={"poll_seconds": 600}, daemon=True)
    t.start()
    return [t]
