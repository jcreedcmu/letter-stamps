"""Read a glyph out of a font file as scaled, mirrored, centered contours.

A contour is a list of segments forming a closed loop. A segment is one of

    ("line", p0, p1)
    ("quad", p0, c, p1)
    ("cubic", p0, c1, c2, p1)

where each point is an ``(x, y)`` tuple.
"""

import math

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

SIZE_MODES = ("bbox", "cap", "em")


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


def raw_contours(font, char):
    """Contours of ``char`` in font units."""
    try:
        cmap = font.getBestCmap()
    except Exception as exc:  # no usable unicode cmap (symbol fonts)
        raise ValueError(f"font has no usable unicode cmap: {exc}") from exc
    name = cmap.get(ord(char))
    if name is None:
        raise ValueError(f"font has no glyph for {char!r} (U+{ord(char):04X})")
    glyph_set = font.getGlyphSet()
    pen = ContourPen(glyph_set)
    glyph_set[name].draw(pen)
    if not pen.contours:
        raise ValueError(f"glyph for {char!r} is empty")
    return pen.contours


def _reference_height(font, contours, size_mode):
    if size_mode == "em":
        return font["head"].unitsPerEm
    if size_mode == "cap":
        cap = getattr(font.get("OS/2"), "sCapHeight", 0) or 0
        if cap > 0:
            return cap
        # Not all fonts record a cap height; measure one instead.
        try:
            _, ymin, _, ymax = bbox(raw_contours(font, "H"))
            return ymax - ymin
        except ValueError:
            return 0.7 * font["head"].unitsPerEm
    _, ymin, _, ymax = bbox(contours)
    return ymax - ymin


def load_outline(font_path, char, size, size_mode="bbox", mirror=True):
    """Contours for ``char``, in mm, mirrored in x and centered on the origin.

    The mirror is what makes the impression read the right way round. It also
    reverses every contour's winding, which ``geom`` reassigns from scratch.
    """
    if size_mode not in SIZE_MODES:
        raise ValueError(f"size_mode must be one of {SIZE_MODES}")
    if len(char) != 1:
        raise ValueError("char must be a single character")

    font = TTFont(font_path)
    contours = raw_contours(font, char)

    reference = _reference_height(font, contours, size_mode)
    if reference <= 0:
        raise ValueError(f"cannot size {char!r}: reference height is zero")
    scale = size / reference
    sx = -scale if mirror else scale
    contours = map_points(contours, lambda p: (p[0] * sx, p[1] * scale))

    xmin, ymin, xmax, ymax = bbox(contours)
    cx, cy = 0.5 * (xmin + xmax), 0.5 * (ymin + ymax)
    return map_points(contours, lambda p: (p[0] - cx, p[1] - cy))
