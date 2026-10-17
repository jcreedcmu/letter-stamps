"""Build the stamp solid from glyph contours.

The letterform face is the top of the solid, at ``z = depth``, and the body
widens on the way down to ``z = 0``, so the walls flare back away from the
contact face. Looking down at the model from ``+z`` therefore shows the
stamping surface itself, reading mirrored, the way a real stamp looks when you
turn it face up. Underneath is a rectangular base, as wide as the letter plus
a margin and as tall as the font's ascent to descent, so every letter of a
font comes out the same height. The whole thing sits on ``z = 0``, flat side
down, ready to print.
"""

import math
import warnings
from functools import reduce

import cadquery as cq

from .geom import DEFAULT_TOLERANCE, contours_to_faces
from .glyph import bbox

class DraftDropped(UserWarning):
    """The requested draft could not be applied; the walls came out straight."""


class ThinFeature(UserWarning):
    """The draft is large next to the finest detail in the outline."""


class Overhang(UserWarning):
    """The letter reaches past the base rectangle around it."""


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


def _offset_wire(wire, delta, grow):
    """Offset ``wire`` by ``delta``, outward if ``grow`` else inward.

    Only the ``intersection`` join type is any use here: it extends offset
    edges to meet, which keeps the edge count and lets the walls correspond
    one for one. The ``arc`` join type offsets happily but rounds every corner
    into extra edges, and a loft between wires of unequal edge count always
    fails, so it is not worth trying.

    Hole wires can wind either way, so both signs are tried and the result is
    picked by whether it came out bigger or smaller than the original. Raises
    ``ValueError`` describing what went wrong if nothing usable comes back.
    """
    box = wire.BoundingBox()
    original = box.xlen * box.ylen
    problems = []

    for signed in (delta, -delta):
        try:
            candidates = wire.offset2D(signed, "intersection")
        except Exception as exc:
            problems.append(f"offsetting by {signed:+.3f} mm raised {type(exc).__name__}")
            continue
        if len(candidates) != 1:
            problems.append(
                f"offsetting by {signed:+.3f} mm broke the outline into "
                f"{len(candidates)} wires"
            )
            continue
        candidate = candidates[0]
        cbox = candidate.BoundingBox()
        if ((cbox.xlen * cbox.ylen) > original) != grow:
            continue
        return candidate

    raise ValueError("; ".join(problems) or "no offset came out the right size")


def _straight(face, depth):
    """Extrude with no draft at all. Inner wires are fine here."""
    return cq.Solid.extrudeLinear(face, cq.Vector(0, 0, depth), 0)


def _loft_pair(near, far, depth):
    return cq.Solid.makeLoft([near, far.translate((0, 0, depth))], True)


def _draft_one(face, depth, delta):
    """One drafted solid, or ``ValueError`` explaining why not."""
    outer = face.outerWire()
    wide = _offset_wire(outer, delta, grow=True)
    try:
        solid = _loft_pair(outer, wide, depth)
    except Exception as exc:
        raise ValueError(
            f"lofting {len(outer.Edges())} edges to {len(wide.Edges())} failed "
            f"({type(exc).__name__}), which usually means the offset outline "
            f"crossed itself"
        ) from exc

    for inner in face.innerWires():
        # A hole shrinks as the outline grows. One too tight to shrink by the
        # full offset keeps straight walls rather than sinking the whole glyph.
        try:
            hole = _loft_pair(inner, _offset_wire(inner, delta, grow=False), depth)
        except Exception:
            hole = _straight(cq.Face.makeFromWires(inner), depth)
        solid = solid.cut(hole)
    return solid


def _draft_solid(face, depth, draft):
    delta = depth * math.tan(math.radians(draft))
    try:
        solid = _draft_one(face, depth, delta)
        if not solid.isValid():
            raise ValueError("the drafted solid came out invalid")
        return solid
    except Exception as exc:
        warnings.warn(
            f"could not apply a {draft:g} degree draft: {exc}. Extruding with "
            f"straight walls instead. The draft has to move the walls "
            f"{delta:.2f} mm sideways, and an outline with detail finer than "
            f"that cannot absorb it; a smaller --depth or --draft asks for less "
            f"room",
            DraftDropped,
        )
        return _straight(face, depth)


def _extrude(faces, depth, draft):
    """Extrude the letterform, widening as it goes.

    Every wall comes from a loft between the outline and a 2D offset of it.
    cadquery's tapered extrusion would be the obvious tool, but the underlying
    ``LocOpe_DPrism`` refuses faces with inner wires and fails outright on many
    real letterforms, as does ``BRepOffsetAPI_DraftAngle``.
    """
    if abs(draft) < 1e-9:
        return cq.Workplane("XY").add(faces).toPending().extrude(depth)

    solids = [_draft_solid(f, depth, draft) for f in faces]
    shape = solids[0] if len(solids) == 1 else reduce(lambda a, b: a.fuse(b), solids)
    return cq.Workplane("XY").add(shape)


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


def _add_base(body, outline, thickness, chamfer):
    """Put the base rectangle under the letter."""
    _overhang_warning(body, outline)
    body = body.translate((0, 0, thickness))
    pad = cq.Workplane("XY").rect(outline.width, outline.height).extrude(thickness)
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
    base_thickness=2.0,
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
    _min_feature_warning(faces, depth, draft)

    # Built letterform-down and widening upward, then turned over so the
    # letterform is the top face.
    body = _extrude(faces, depth, draft).mirror("XY").translate((0, 0, depth))

    return _add_base(body, outline, base_thickness, base_chamfer)
