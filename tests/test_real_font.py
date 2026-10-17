"""Smoke tests over a real typeface, which has messier outlines than the
synthetic fixture: many more curve segments, tight joins, and counters of
awkward shapes. These assert only that the pipeline produces valid solids.
"""

import pytest
from fontTools.ttLib import TTFont

from letter_stamps.glyph import bbox, load_outline
from letter_stamps.stamp import build_stamp

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789&?!"


@pytest.fixture(scope="module")
def cmap(real_font_path):
    return TTFont(real_font_path).getBestCmap()


@pytest.mark.parametrize("char", list(ALPHABET))
def test_every_letter_builds(real_font_path, cmap, char):
    if ord(char) not in cmap:
        pytest.skip(f"font has no {char!r}")
    contours = load_outline(real_font_path, char, size=10)
    xmin, ymin, xmax, ymax = bbox(contours)
    assert ymax - ymin == pytest.approx(10.0, abs=1e-6)

    shape = build_stamp(contours, depth=4, draft=7).val()
    assert shape.isValid()
    assert shape.Volume() > 0
    assert shape.BoundingBox().zlen == pytest.approx(4.0, abs=1e-6)


def test_a_letter_with_a_base_builds(real_font_path, cmap):
    char = next((c for c in "RB@g" if ord(c) in cmap), None)
    if char is None:
        pytest.skip("font has none of R, B, @, g")
    body = build_stamp(
        load_outline(real_font_path, char, size=12),
        depth=5,
        draft=6,
        base="plate",
        base_thickness=2,
    )
    assert body.val().isValid()
    assert len(body.val().Solids()) == 1
