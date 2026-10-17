import math

import cadquery as cq
import pytest

from letter_stamps.geom import contours_to_faces, reverse_contour
from letter_stamps.glyph import bbox, load_outline
from letter_stamps.stamp import build_stamp

LETTERS = ["L", "O", "B", "8", "i", "é"]


@pytest.fixture
def outline(font_path):
    def make(char, size=10.0, **kw):
        return load_outline(font_path, char, size=size, **kw)

    return make


@pytest.mark.parametrize("char", LETTERS)
def test_solid_is_valid(outline, char):
    body = build_stamp(outline(char), depth=4, draft=7)
    shape = body.val()
    assert shape.isValid()
    assert shape.Volume() > 0


def test_face_count_matches_contour_nesting(outline):
    """'O' is one face with a hole; 'i' is two disjoint faces."""
    assert len(contours_to_faces(outline("O"))) == 1
    assert len(contours_to_faces(outline("i"))) == 2


def test_hole_is_subtracted_from_its_outer_boundary(outline):
    face = contours_to_faces(outline("O"))[0]
    assert len(face.innerWires()) == 1
    assert face.Area() < cq.Face.makeFromWires(face.outerWire()).Area()


def test_nesting_decides_holes_regardless_of_font_winding(outline):
    """Reversing every contour must not change which one is the hole."""
    contours = outline("O")
    flipped = [reverse_contour(c) for c in contours]
    assert len(contours_to_faces(flipped)) == 1
    assert contours_to_faces(flipped)[0].Area() == pytest.approx(
        contours_to_faces(contours)[0].Area(), rel=1e-9
    )


def test_draft_widens_the_body(outline):
    contours = outline("L")
    straight = build_stamp(contours, depth=4, draft=0).val()
    tapered = build_stamp(contours, depth=4, draft=7).val()
    assert tapered.Volume() > straight.Volume()

    straight_box = straight.BoundingBox()
    tapered_box = tapered.BoundingBox()
    assert tapered_box.xlen > straight_box.xlen
    assert tapered_box.ylen > straight_box.ylen


def test_depth_sets_the_z_extent(outline):
    box = build_stamp(outline("L"), depth=4, draft=7).val().BoundingBox()
    assert box.zlen == pytest.approx(4.0, abs=1e-6)
    assert box.zmin == pytest.approx(0.0, abs=1e-6)


def test_base_sits_under_the_letter(outline):
    """The model rests on z = 0 with the stamping face on top."""
    body = build_stamp(
        outline("B"), depth=4, draft=7, base="plate", base_thickness=2
    )
    box = body.val().BoundingBox()
    assert box.zmin == pytest.approx(0.0, abs=1e-6)
    assert box.zmax == pytest.approx(6.0, abs=1e-6)

    top = [f.BoundingBox() for f in body.faces(">Z").vals()]
    assert max(b.zmin for b in top) == pytest.approx(6.0, abs=1e-6)
    # The pad is wider than the letter, so the lowest face is the pad.
    bottom = body.faces("<Z").val().BoundingBox()
    assert bottom.xlen > max(b.xlen for b in top)


def test_stamping_face_is_the_top_and_matches_the_glyph(outline):
    """The face at z = depth is the letterform at its requested size."""
    contours = outline("L", size=10)
    xmin, ymin, xmax, ymax = bbox(contours)

    body = build_stamp(contours, depth=4, draft=7)
    top = [f.BoundingBox() for f in body.faces(">Z").vals()]
    assert top
    assert max(b.zmin for b in top) == pytest.approx(4.0, abs=1e-6)
    assert max(b.xlen for b in top) == pytest.approx(xmax - xmin, abs=1e-4)
    assert max(b.ylen for b in top) == pytest.approx(ymax - ymin, abs=1e-4)

    # The body flares out behind the stamping face, so the bottom is bigger.
    bottom = [f.BoundingBox() for f in body.faces("<Z").vals()]
    assert max(b.xlen for b in bottom) > max(b.xlen for b in top)
    assert max(b.ylen for b in bottom) > max(b.ylen for b in top)


def test_untapered_body_matches_the_glyph_footprint(outline):
    contours = outline("O", size=10)
    xmin, ymin, xmax, ymax = bbox(contours)
    box = build_stamp(contours, depth=4, draft=0).val().BoundingBox()
    assert box.xlen == pytest.approx(xmax - xmin, abs=1e-4)
    assert box.ylen == pytest.approx(ymax - ymin, abs=1e-4)


@pytest.mark.parametrize("kind", ["disc", "plate"])
def test_base_adds_thickness_and_covers_the_letter(outline, kind):
    contours = outline("B", size=10)
    plain = build_stamp(contours, depth=4, draft=7).val().BoundingBox()
    body = build_stamp(
        contours,
        depth=4,
        draft=7,
        base=kind,
        base_thickness=2,
        base_margin=1.5,
    )
    shape = body.val()
    assert shape.isValid()
    box = shape.BoundingBox()
    assert box.zlen == pytest.approx(6.0, abs=1e-6)
    assert box.xlen > plain.xlen
    assert box.ylen > plain.ylen
    if kind == "disc":
        expected = math.hypot(plain.xlen, plain.ylen) + 3.0
        assert box.xlen == pytest.approx(expected, abs=1e-6)


def test_base_is_fused_into_one_solid(outline):
    body = build_stamp(outline("i"), depth=4, draft=7, base="plate")
    assert len(body.val().Solids()) == 1


def test_step_round_trips(outline, tmp_path):
    path = tmp_path / "O.step"
    body = build_stamp(outline("O"), depth=4, draft=7)
    cq.exporters.export(body, str(path))
    assert path.stat().st_size > 0

    reimported = cq.importers.importStep(str(path))
    assert reimported.val().isValid()
    assert reimported.val().Volume() == pytest.approx(body.val().Volume(), rel=1e-6)


def test_stl_is_written(outline, tmp_path):
    path = tmp_path / "O.stl"
    cq.exporters.export(build_stamp(outline("O"), depth=4, draft=7), str(path))
    assert path.stat().st_size > 0


def test_bad_parameters_are_errors(outline):
    contours = outline("L")
    with pytest.raises(ValueError):
        build_stamp(contours, depth=0)
    with pytest.raises(ValueError):
        build_stamp(contours, draft=60)
    with pytest.raises(ValueError):
        build_stamp(contours, base="wedge")


def test_steep_draft_warns(outline):
    with pytest.warns(UserWarning):
        build_stamp(outline("i", size=6), depth=8, draft=30)
