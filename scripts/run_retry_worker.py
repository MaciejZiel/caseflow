"""Run the CaseFlow retry worker."""

from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.workers.retries import run_retry_cycle, run_retry_worker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help="Run continuously instead of once.")
    parser.add_argument("--limit-per-queue", type=int, default=50)
    parser.add_argument("--poll-interval-seconds", type=int, default=None)
    args = parser.parse_args()

    if args.loop:
        run_retry_worker(
            limit_per_queue=args.limit_per_queue,
            poll_interval_seconds=args.poll_interval_seconds,
        )
        return 0

    result = run_retry_cycle(limit_per_queue=args.limit_per_queue)
    print(
        json.dumps(
            {
                "processed_document_jobs": result.processed_document_jobs,
                "processed_webhook_deliveries": result.processed_webhook_deliveries,
                "processed_admin_notification_digests": (
                    result.processed_admin_notification_digests
                ),
                "processed_emails": result.processed_emails,
                "worker_poll_interval_seconds": (
                    args.poll_interval_seconds or get_settings().worker_poll_interval_seconds
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
