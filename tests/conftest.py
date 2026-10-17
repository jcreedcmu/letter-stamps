"""Fonts to test against.

``font_path`` is a synthetic font built by ``fixtures/synthetic.py``, so the
exact assertions in the suite stay deterministic. ``real_font_path`` is an
actual typeface, taken from ``LETTER_STAMPS_TEST_FONT`` or from the usual
system font directories, and the tests that use it only check that the
pipeline survives real outlines.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fixtures.synthetic import build_font  # noqa: E402

PREFERRED = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
)

SEARCH_DIRS = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    str(Path.home() / ".fonts"),
    str(Path.home() / ".local/share/fonts"),
    "/Library/Fonts",
    "/System/Library/Fonts",
    "C:/Windows/Fonts",
)


def _find_real_font():
    explicit = os.environ.get("LETTER_STAMPS_TEST_FONT")
    if explicit:
        return Path(explicit)
    for candidate in PREFERRED:
        if Path(candidate).is_file():
            return Path(candidate)
    for directory in SEARCH_DIRS:
        root = Path(directory)
        if root.is_dir():
            for found in sorted(root.rglob("*.ttf")):
                return found
    return None


@pytest.fixture(scope="session")
def font_path(tmp_path_factory):
    return str(build_font(tmp_path_factory.mktemp("font") / "fixture.ttf"))


@pytest.fixture(scope="session")
def real_font_path():
    found = _find_real_font()
    if found is None or not found.is_file():
        pytest.skip(
            "no system .ttf found; set LETTER_STAMPS_TEST_FONT to point at one"
        )
    return str(found)
