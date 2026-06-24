"""H1 entrypoint: verify OAuth authentication without touching Calendar data."""

import logging
import sys

from dotenv import load_dotenv

from calendar_agent.auth import AuthError, get_calendar_service

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    load_dotenv()
    try:
        get_calendar_service()
    except AuthError as exc:
        print(f"Error de autenticación: {exc}", file=sys.stderr)
        return 1

    print("Autenticación exitosa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
