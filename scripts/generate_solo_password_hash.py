#!/usr/bin/env python3
"""Interactively generate a Restock solo-owner scrypt hash."""

from getpass import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.password_auth import hash_password


def main() -> int:
    password = getpass("Password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("passwords do not match")
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
