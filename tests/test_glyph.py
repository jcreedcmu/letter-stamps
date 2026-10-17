import pytest

from letter_stamps.glyph import bbox, flatten, load_outline

# Contour counts for the synthetic fixture font.
EXPECTED_CONTOURS = {"L": 1, "O": 2, "A": 2, "B": 3, "i": 2, "8": 3}


@pytest.mark.parametrize("char,count", sorted(EXPECTED_CONTOURS.items()))
def test_contour_counts(font_path, char, count):
    contours = load_outline(font_path, char, size=10)
    assert len(contours) == count


def test_every_contour_is_closed(font_path):
    for contour in load_outline(font_path, "B", size=10):
        assert contour[0][1] == contour[-1][-1]


def test_mirror_flips_x(font_path):
    mirrored = load_outline(font_path, "L", size=10)
    plain = load_outline(font_path, "L", size=10, mirror=False)

    mx = sorted(p[0] for p in flatten(mirrored)[0])
    px = sorted(-p[0] for p in flatten(plain)[0])
    assert mx == pytest.approx(px, abs=1e-9)

    # y is untouched by the mirror.
    assert bbox(mirrored)[1] == pytest.approx(bbox(plain)[1])
    assert bbox(mirrored)[3] == pytest.approx(bbox(plain)[3])


def test_bbox_mode_sizes_the_glyph_exactly(font_path):
    xmin, ymin, xmax, ymax = bbox(load_outline(font_path, "A", size=12, size_mode="bbox"))
    assert ymax - ymin == pytest.approx(12.0, abs=1e-6)


def test_outline_is_centered(font_path):
    xmin, ymin, xmax, ymax = bbox(load_outline(font_path, "A", size=12))
    assert xmin + xmax == pytest.approx(0.0, abs=1e-9)
    assert ymin + ymax == pytest.approx(0.0, abs=1e-9)


def test_cap_mode_keeps_letters_in_proportion(font_path):
    cap_h = bbox(load_outline(font_path, "H", size=10, size_mode="cap"))
    cap_o = bbox(load_outline(font_path, "o", size=10, size_mode="cap"))
    h_height = cap_h[3] - cap_h[1]
    o_height = cap_o[3] - cap_o[1]
    assert h_height == pytest.approx(10.0, abs=1e-6)
    assert o_height < h_height


def test_em_mode_is_smaller_than_the_em(font_path):
    xmin, ymin, xmax, ymax = bbox(load_outline(font_path, "x", size=10, size_mode="em"))
    assert 0 < ymax - ymin < 10


def test_missing_glyph_is_an_error(font_path):
    with pytest.raises(ValueError):
        load_outline(font_path, "\uE000", size=10)


def test_multi_character_is_an_error(font_path):
    with pytest.raises(ValueError):
        load_outline(font_path, "AB", size=10)


def test_bad_size_mode_is_an_error(font_path):
    with pytest.raises(ValueError):
        load_outline(font_path, "A", size=10, size_mode="nonsense")


def test_bbox_measures_the_curve_not_the_control_points(font_path):
    """Off-curve control points of an 'O' lie outside the glyph itself."""
    contours = load_outline(font_path, "O", size=10)
    raw = [p for contour in contours for seg in contour for p in seg[1:]]
    raw_height = max(p[1] for p in raw) - min(p[1] for p in raw)
    xmin, ymin, xmax, ymax = bbox(contours)
    assert ymax - ymin == pytest.approx(10.0, abs=1e-6)
    assert raw_height > 10.0 + 1e-3
