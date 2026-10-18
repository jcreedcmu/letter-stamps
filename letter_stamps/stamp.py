"""Build the stamp solid from glyph contours.

The letterform face is the top of the solid, at ``z = depth``, and the body
widens on the way down to ``z = 0``, so the walls flare back away from the
contact face. Looking down at the model from ``+z`` therefore shows the
stamping surface itself, reading mirrored, the way a real stamp looks when you
turn it face up. Underneath is a rectangular base, as wide as the letter plus
a margin and as tall as the font's ascent to descent, so every letter of a
font comes out the same height. A dovetail groove runs the height of its back
face, to slide onto a rail. The whole thing sits on ``z = 0``, flat side down,
ready to print.
"""

import math
import warnings
from functools import reduce

import cadquery as cq

from .geom import DEFAULT_TOLERANCE, contours_to_faces
from .glyph import bbox, flatten

class DraftDropped(UserWarning):
    """The requested draft could not be applied; the walls came out straight."""


class ThinFeature(UserWarning):
    """The draft is large next to the finest detail in the outline."""


class Overhang(UserWarning):
    """The letter reaches past the base rectangle around it."""


#: The groove is a dovetail in the back of the base: a narrow mouth at the
#: open face widening to a broader inner edge, the two joined at 45 degrees.
#: Every base carries the same one, so stamps are interchangeable on a rail,
#: which is why these are constants and not options.
GROOVE_MOUTH = 5.0
GROOVE_INNER = 10.0

#: 45 degrees means each side steps out by half the difference in width, and
#: rises by as much again.
GROOVE_DEPTH = 0.5 * (GROOVE_INNER - GROOVE_MOUTH)

#: Least base left either side of the groove, and least left above it.
GROOVE_WALL = 1.0
GROOVE_WEB = 1.0


def _min_feature_warning(faces, depth, draft):
    """Flag a draft angle steep enough to eat a thin stem.

    For a long stem of width w, area / perimeter is about w / 2, which is a
    cheap enough estimate to be worth making.
    """
    delta = depth * math.tan(math.radians(draft))
    if delta <= 0:
        return
    for face in faces:
        perimeter = face.outerWire().Length() + sum(
            w.Length() for w in face.innerWires()
        )
        if perimeter <= 0:
            continue
        width = 2 * face.Area() / perimeter
        if delta > width / 3:
            warnings.warn(
                f"draft of {draft:g} deg over {depth:g} mm grows the outline by "
                f"{delta:.2f} mm, which is large next to a feature width of "
                f"about {width:.2f} mm; thin strokes may merge",
                ThinFeature,
            )
            return


#: Boundary edges shorter than this are skipped as degenerate, in mm.
EPS = 1e-9


def _straight(face, depth):
    """Extrude with no draft at all. Inner wires are fine here."""
    return cq.Solid.extrudeLinear(face, cq.Vector(0, 0, depth), 0)


def _wedge(a, b, depth, delta):
    """A triangular prism along one boundary edge, leaning out by ``delta``.

    It leans the same amount to either side of the edge. The inward half lands
    inside the letter, where the union swallows it, and not having to work out
    which side is outward means the winding of a contour never matters here.
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    nx, ny = dy / length * delta, -dx / length * delta
    triangle = [
        (a[0], a[1], 0.0),
        (a[0] + nx, a[1] + ny, depth),
        (a[0] - nx, a[1] - ny, depth),
    ]
    section = cq.Face.makeFromWires(
        cq.Wire.makePolygon([cq.Vector(*p) for p in triangle], close=True)
    )
    return cq.Solid.extrudeLinear(section, cq.Vector(dx, dy, 0), 0)


def _draft_parts(polygons, depth, delta):
    """The pieces that, unioned with the straight prism, make the draft.

    This is the letterform swept by a disk growing from nothing at the
    stamping face to ``delta`` at the far end: a Minkowski sum with a cone. A
    wedge along every boundary edge covers the edge sweeps and a cone at every
    vertex covers the vertex sweeps, which is the whole boundary, and the
    boundary is all that needs covering since the interior only grows.

    Every vertex needs its cone, however straight the boundary runs through
    it. A wedge stops at the ends of its own edge, so the triangular cap on
    each end is left bare unless something covers it, and only the cone at
    that vertex does: the neighbouring wedge does not reach past the shared
    point, no matter how nearly collinear the two edges are. Skipping cones at
    near-straight vertices leaves a vertical wall the full height of the
    relief at each one, which is a visible fault and not a small one.
    """
    for polygon in polygons:
        count = len(polygon)
        for i in range(count):
            here, following = polygon[i], polygon[(i + 1) % count]
            if math.hypot(following[0] - here[0], following[1] - here[1]) > EPS:
                yield _wedge(here, following, depth, delta)
            yield cq.Solid.makeCone(
                0,
                delta,
                depth,
                cq.Vector(here[0], here[1], 0),
                cq.Vector(0, 0, 1),
            )


def _extrude(faces, polygons, depth, draft):
    """Extrude the letterform, widening as it goes.

    Every wall is a plane leaning at exactly the draft angle, or a cone of
    exactly that half-angle, because that is what the pieces are made of.
    There is no profile to offset and no correspondence for a loft to infer,
    which is what the previous offset-and-loft arrangement kept getting wrong:
    an outline whose offset collapsed an edge left the loft pairing walls off
    by one, and the draft came out skewed from that point around.

    The cost is a boolean over a few hundred simple solids, so the part count,
    and with it the time, follows the chord tolerance of stage two.
    """
    prisms = [_straight(face, depth) for face in faces]
    plain = (
        prisms[0]
        if len(prisms) == 1
        else reduce(lambda a, b: a.fuse(b), prisms)
    )
    if abs(draft) < 1e-9:
        return cq.Workplane("XY").add(plain)

    delta = depth * math.tan(math.radians(draft))
    try:
        drafted = plain.fuse(*_draft_parts(polygons, depth, delta)).clean()
        if not drafted.isValid():
            raise ValueError("the union came out invalid")
    except Exception as exc:
        warnings.warn(
            f"could not apply a {draft:g} degree draft: {exc}. Extruding with "
            f"straight walls instead",
            DraftDropped,
        )
        return cq.Workplane("XY").add(plain)

    return cq.Workplane("XY").add(drafted)



def _overhang_warning(body, outline):
    """Say so when the letter reaches past its base, in either direction.

    The two directions mean different things and have different remedies, so
    they are reported apart. Sideways, the draft has pushed the widest
    cross-section out further than the margin allows, which a wider margin or
    a shallower draft would fix. Vertically, the glyph itself reaches past the
    font's own ascent or descent, as accents usually do; the base height is
    fixed on purpose, so there is nothing to adjust. The draft is left out of
    the vertical test, since a capital reaching the ascent would otherwise
    report an overhang that no setting can remove.

    Nothing is trimmed either way.
    """
    box = body.val().BoundingBox()
    bx0, by0, bx1, by1 = outline.box

    sideways = max(bx0 - box.xmin, box.xmax - bx1)
    if sideways > 1e-6:
        warnings.warn(
            f"{outline.char!r} and its draft reach {sideways:.2f} mm past the "
            f"side of its {outline.width:.2f} mm wide base; a larger "
            f"--base-margin, or less draft, would contain it",
            Overhang,
        )

    _, gy0, _, gy1 = bbox(outline.contours)
    vertical = max(by0 - gy0, gy1 - by1)
    if vertical > 1e-6:
        warnings.warn(
            f"{outline.char!r} reaches {vertical:.2f} mm past the font's ascent "
            f"or descent, so it hangs over the edge of a base whose height is "
            f"fixed at {outline.height:.2f} mm",
            Overhang,
        )


def _groove(length):
    """The dovetail, as a solid to cut away.

    The profile is drawn in the xz plane and extruded along y, so the groove
    runs the height of the base and is open at both ends. ``cq``'s ``XZ``
    plane has its normal along -y, hence the symmetric extrude: it reaches the
    same distance either way regardless.
    """
    mouth, inner = 0.5 * GROOVE_MOUTH, 0.5 * GROOVE_INNER
    return (
        cq.Workplane("XZ")
        .moveTo(-mouth, 0)
        .lineTo(mouth, 0)
        .lineTo(inner, GROOVE_DEPTH)
        .lineTo(-inner, GROOVE_DEPTH)
        .close()
        .extrude(0.5 * length, both=True)
    )


def _add_base(body, outline, thickness, chamfer):
    """Put the grooved base rectangle under the letter."""
    if outline.width < GROOVE_INNER + 2 * GROOVE_WALL:
        raise ValueError(
            f"a {outline.width:.2f} mm base cannot take the "
            f"{GROOVE_INNER:g} mm groove and leave {GROOVE_WALL:g} mm of wall "
            f"either side; raise --base-min-width"
        )
    if thickness < GROOVE_DEPTH + GROOVE_WEB:
        raise ValueError(
            f"a {thickness:.2f} mm base is too thin for a {GROOVE_DEPTH:g} mm "
            f"groove with {GROOVE_WEB:g} mm of material over it; raise "
            f"--base-thickness"
        )

    _overhang_warning(body, outline)
    body = body.translate((0, 0, thickness))

    pad = cq.Workplane("XY").rect(outline.width, outline.height).extrude(thickness)
    # Overshoot the ends of the base so the cut leaves no sliver behind.
    pad = pad.cut(_groove(outline.height + 2.0))

    result = body.union(pad)

    if chamfer > 0:
        try:
            result = result.faces("<Z").edges().chamfer(chamfer)
        except Exception as exc:
            warnings.warn(f"skipping base chamfer: {exc}")
    return result


def build_stamp(
    outline,
    depth=4.0,
    draft=7.0,
    base_thickness=4.5,
    base_chamfer=0.0,
    tolerance=DEFAULT_TOLERANCE,
):
    """Stamp solid for an ``Outline``, as a ``cq.Workplane``."""
    if depth <= 0:
        raise ValueError("depth must be positive")
    if base_thickness <= 0:
        raise ValueError("base_thickness must be positive")
    if not -45 < draft < 45:
        raise ValueError("draft must be between -45 and 45 degrees")

    faces = contours_to_faces(outline.contours, tolerance)
    polygons = flatten(outline.contours, tolerance)
    _min_feature_warning(faces, depth, draft)

    # Built letterform-down and widening upward, then turned over so the
    # letterform is the top face.
    body = (
        _extrude(faces, polygons, depth, draft)
        .mirror("XY")
        .translate((0, 0, depth))
    )

    return _add_base(body, outline, base_thickness, base_chamfer)
