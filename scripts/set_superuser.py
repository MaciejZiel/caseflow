"""Promote or demote a user to platform superuser."""

from __future__ import annotations

import argparse
import json

from app.application.services.superusers import SuperuserService
from app.infrastructure.db.models import import_model_modules
from app.infrastructure.db.session import get_session_factory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="User email to update.")
    parser.add_argument(
        "--demote",
        action="store_true",
        help="Remove superuser privileges instead of granting them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import_model_modules()
    session = get_session_factory()()
    try:
        user = SuperuserService(session).set_superuser_status(
            email=args.email,
            is_superuser=not args.demote,
        )
    finally:
        session.close()

    print(
        json.dumps(
            {
                "email": user.email,
                "is_superuser": user.is_superuser,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
