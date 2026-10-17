"""Lets the package be run as ``python -m letter_stamps``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
