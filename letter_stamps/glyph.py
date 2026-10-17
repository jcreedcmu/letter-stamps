"""Read a glyph out of a font file as scaled, mirrored, centered contours.

The base rectangle around the glyph is as wide as the glyph plus a margin on
each side, and always as tall as the font's ascent to descent. Height is
therefore the same for every letter of a font at a given size. The rectangle
is centered on the origin.

Within it, every letter is dropped by half the descent from where the baseline
would otherwise put it. Fonts leave little room between their cap height and
their ascent, so a capital placed strictly by the baseline nearly touches the
top edge; splitting the descent's slack between the two edges leaves a capital
close to centered. Every letter moves by the same amount, so they keep a
common baseline. A full descender reaches further down than it used to and can
pass the bottom edge, which is reported.

A contour is a list of segments forming a closed loop. A segment is one of

    ("line", p0, p1)
    ("quad", p0, c, p1)
    ("cubic", p0, c1, c2, p1)

where each point is an ``(x, y)`` tuple.
"""

import math
from dataclasses import dataclass

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

SIZE_MODES = ("bbox", "cap", "em")

#: Default gap in mm between the letter and the left and right base edges.
DEFAULT_MARGIN = 1.5


@dataclass(frozen=True)
class Outline:
    """A placed, scaled glyph outline and the base rectangle around it.

    All lengths are mm. The rectangle spans ``±width / 2`` by ``±height / 2``.
    Its height is the font's ascent to descent, so every letter at a given
    size gets the same one; its width is the letter plus ``margin`` either
    side, so it is the letter that is centered horizontally. ``baseline`` is
    where the glyph's own y = 0 ended up, which is half the descent above the
    bottom edge.
    """

    char: str
    contours: list
    width: float
    height: float
    scale: float
    margin: float
    baseline: float

    @property
    def box(self):
        """``(xmin, ymin, xmax, ymax)`` of the base rectangle."""
        return (
            -0.5 * self.width,
            -0.5 * self.height,
            0.5 * self.width,
            0.5 * self.height,
        )


class ContourPen(BasePen):
    """Collects a glyph's outline as contours of line/quad/cubic segments.

    ``BasePen`` does the fiddly parts: it expands TrueType ``qCurveTo`` runs
    into individual quadratic segments with the implied on-curve midpoints
    inserted, and it recurses through the glyph set for composite glyphs.
    """

    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.contours = []
        self._segments = None
        self._start = None
        self._pt = None

    def _flush(self):
        if self._segments:
            self.contours.append(self._segments)
        self._segments = None

    def _moveTo(self, pt):
        self._flush()
        self._segments = []
        self._start = pt
        self._pt = pt

    def _lineTo(self, pt):
        self._segments.append(("line", self._pt, pt))
        self._pt = pt

    def _qCurveToOne(self, c, pt):
        self._segments.append(("quad", self._pt, c, pt))
        self._pt = pt

    def _curveToOne(self, c1, c2, pt):
        self._segments.append(("cubic", self._pt, c1, c2, pt))
        self._pt = pt

    def _closePath(self):
        if self._pt is not None and self._pt != self._start:
            self._segments.append(("line", self._pt, self._start))
        self._flush()

    def _endPath(self):
        self._closePath()


#: Subdivision bound, so a pathological segment cannot recurse forever.
MAX_SUBDIVISIONS = 16


def _mid(a, b):
    return (0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]))


def _chord_deviation(points):
    """How far the control points stray from the chord, which bounds how far
    the curve itself strays."""
    (x0, y0), (x1, y1) = points[0], points[-1]
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return max(math.hypot(p[0] - x0, p[1] - y0) for p in points[1:-1])
    return max(
        abs((p[0] - x0) * dy - (p[1] - y0) * dx) / length for p in points[1:-1]
    )


def _subdivide(points):
    """Split a quadratic or cubic in half, de Casteljau."""
    if len(points) == 3:
        p0, c, p1 = points
        m0, m1 = _mid(p0, c), _mid(c, p1)
        m = _mid(m0, m1)
        return (p0, m0, m), (m, m1, p1)
    p0, c1, c2, p1 = points
    a, b, c = _mid(p0, c1), _mid(c1, c2), _mid(c2, p1)
    d, e = _mid(a, b), _mid(b, c)
    f = _mid(d, e)
    return (p0, a, d, f), (f, e, c, p1)


def _emit_curve(points, tolerance, out, level=0):
    if level >= MAX_SUBDIVISIONS or _chord_deviation(points) <= tolerance:
        out.append(points[-1])
        return
    first, second = _subdivide(points)
    _emit_curve(first, tolerance, out, level + 1)
    _emit_curve(second, tolerance, out, level + 1)


def _auto_tolerance(contours):
    """A flattening tolerance fine enough to measure by, in whatever units the
    contours happen to be in."""
    points = [p for contour in contours for seg in contour for p in seg[1:]]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    diagonal = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    return 1e-4 * diagonal if diagonal > 0 else 1e-6


def flatten(contours, tolerance=None):
    """Polyline approximations of each contour, closed and without a repeated
    final point, subdivided until no curve strays further than ``tolerance``.

    These polylines are what the rest of the pipeline works from: they decide
    the bounding box, the winding, the nesting, and the wires themselves.
    """
    if tolerance is None:
        tolerance = _auto_tolerance(contours)
    weld = 1e-3 * tolerance

    out = []
    for contour in contours:
        points = [contour[0][1]]
        for seg in contour:
            if seg[0] == "line":
                points.append(seg[2])
            else:
                _emit_curve(seg[1:], tolerance, points)

        deduped = [points[0]]
        for p in points[1:]:
            if math.hypot(p[0] - deduped[-1][0], p[1] - deduped[-1][1]) > weld:
                deduped.append(p)
        first, last = deduped[0], deduped[-1]
        if len(deduped) > 1 and math.hypot(last[0] - first[0], last[1] - first[1]) <= weld:
            deduped.pop()
        out.append(deduped)
    return out


def bbox(contours, tolerance=None):
    """``(xmin, ymin, xmax, ymax)`` of the flattened outline."""
    points = [p for poly in flatten(contours, tolerance) for p in poly]
    if not points:
        raise ValueError("outline is empty")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def map_points(contours, fn):
    """Apply ``fn`` to every point of every segment."""
    return [
        [(seg[0], *[fn(p) for p in seg[1:]]) for seg in contour]
        for contour in contours
    ]


def glyph_name(font, char):
    """The font's name for ``char``'s glyph."""
    try:
        cmap = font.getBestCmap()
    except Exception as exc:  # no usable unicode cmap (symbol fonts)
        raise ValueError(f"font has no usable unicode cmap: {exc}") from exc
    name = cmap.get(ord(char))
    if name is None:
        raise ValueError(f"font has no glyph for {char!r} (U+{ord(char):04X})")
    return name


def raw_contours(font, name):
    """Contours of the glyph called ``name``, in font units."""
    glyph_set = font.getGlyphSet()
    pen = ContourPen(glyph_set)
    glyph_set[name].draw(pen)
    if not pen.contours:
        raise ValueError(f"glyph {name!r} is empty")
    return pen.contours


def vertical_metrics(font):
    """``(ascent, descent)`` in font units.

    These come from ``hhea``, the values a text engine lays lines out with.
    They are not a bound on the outlines: accents reach above the ascent in
    most fonts, and ``OS/2.usWinAscent`` is the field that covers those. Line
    metrics are the right choice here anyway, being what makes one letter's
    stamp the same height as the next one's.
    """
    ascent = descent = None
    hhea = font.get("hhea")
    if hhea is not None:
        ascent = getattr(hhea, "ascender", getattr(hhea, "ascent", None))
        descent = getattr(hhea, "descender", getattr(hhea, "descent", None))

    if not (ascent and descent is not None and descent < 0):
        os2 = font.get("OS/2")
        if os2 is not None:
            ascent, descent = os2.sTypoAscender, os2.sTypoDescender

    if not (ascent and descent is not None and descent < 0):
        upem = font["head"].unitsPerEm
        ascent, descent = round(0.8 * upem), -round(0.2 * upem)

    return ascent, descent


def _reference_height(font, glyph_box, size_mode):
    if size_mode == "em":
        return font["head"].unitsPerEm
    if size_mode == "cap":
        cap = getattr(font.get("OS/2"), "sCapHeight", 0) or 0
        if cap > 0:
            return cap
        # Not all fonts record a cap height; measure one instead.
        try:
            _, ymin, _, ymax = bbox(raw_contours(font, glyph_name(font, "H")))
            return ymax - ymin
        except (ValueError, KeyError):
            return 0.7 * font["head"].unitsPerEm
    return glyph_box[3] - glyph_box[1]


def load_outline(
    font_path,
    char,
    size,
    size_mode="cap",
    mirror=True,
    margin=DEFAULT_MARGIN,
):
    """An ``Outline`` for ``char``: contours in mm, mirrored in x, inside a base
    rectangle centered on the origin.

    The letter is centered horizontally, with ``margin`` mm of base either
    side of it. Vertically it sits on a baseline half the descent above the
    bottom edge, between an ascent and a descent that do not vary from letter
    to letter.

    The mirror is what makes the impression read the right way round. It also
    reverses every contour's winding, which ``geom`` reassigns from scratch.
    """
    if size_mode not in SIZE_MODES:
        raise ValueError(f"size_mode must be one of {SIZE_MODES}")
    if len(char) != 1:
        raise ValueError("char must be a single character")
    if margin < 0:
        raise ValueError("margin cannot be negative")

    font = TTFont(font_path)
    contours = raw_contours(font, glyph_name(font, char))
    glyph_box = bbox(contours)

    reference = _reference_height(font, glyph_box, size_mode)
    if reference <= 0:
        raise ValueError(f"cannot size {char!r}: reference height is zero")
    scale = size / reference

    ascent, descent = vertical_metrics(font)
    width = (glyph_box[2] - glyph_box[0]) * scale + 2 * margin
    height = (ascent - descent) * scale

    center = 0.5 * (glyph_box[0] + glyph_box[2])
    direction = -1 if mirror else 1

    # Placing the baseline a full descent above the bottom edge would leave a
    # capital almost touching the top one. Dropping everything by half the
    # descent splits that slack between the two edges.
    middle = 0.5 * (ascent + descent) * scale
    drop = -0.5 * descent * scale
    baseline = -(middle + drop)

    def place(p):
        return (
            direction * (p[0] - center) * scale,
            p[1] * scale + baseline,
        )

    return Outline(
        char,
        map_points(contours, place),
        width,
        height,
        scale,
        margin,
        baseline,
    )
