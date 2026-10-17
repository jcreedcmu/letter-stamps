"""Build a small synthetic TTF to test against.

The letterforms are blocky stand-ins, not a real typeface. What matters is
that they cover the cases the pipeline has to get right: one contour, a
contour with one hole, a contour with two holes, two disjoint contours,
quadratic curves, and a composite glyph.

Geometry is on a 1000 unit em with a cap height of 700 and an x-height
of 500.
"""

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

UNITS_PER_EM = 1000
CAP_HEIGHT = 700
X_HEIGHT = 500


def _rect(pen, x0, y0, x1, y1, clockwise=False):
    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if clockwise:
        points.reverse()
    pen.moveTo(points[0])
    for p in points[1:]:
        pen.lineTo(p)
    pen.closePath()


def _ring(pen, cx, cy, rx, ry, clockwise=False):
    """A closed quadratic approximation of an ellipse."""
    on = [(cx + rx, cy), (cx, cy + ry), (cx - rx, cy), (cx, cy - ry)]
    control = [(cx + rx, cy + ry), (cx - rx, cy + ry), (cx - rx, cy - ry), (cx + rx, cy - ry)]
    if clockwise:
        on = [on[0]] + on[:0:-1]
        control = control[::-1]
    pen.moveTo(on[0])
    for i in range(4):
        pen.qCurveTo(control[i], on[(i + 1) % 4])
    pen.closePath()


def _draw_L(pen):
    pen.moveTo((100, 0))
    for p in [(600, 0), (600, 150), (250, 150), (250, CAP_HEIGHT), (100, CAP_HEIGHT)]:
        pen.lineTo(p)
    pen.closePath()


def _draw_H(pen):
    pen.moveTo((100, 0))
    for p in [
        (250, 0), (250, 280), (450, 280), (450, 0), (600, 0),
        (600, CAP_HEIGHT), (450, CAP_HEIGHT), (450, 430), (250, 430),
        (250, CAP_HEIGHT), (100, CAP_HEIGHT),
    ]:
        pen.lineTo(p)
    pen.closePath()


def _draw_O(pen):
    _ring(pen, 350, 350, 250, 350)
    _ring(pen, 350, 350, 130, 230, clockwise=True)


def _draw_o(pen):
    _ring(pen, 330, 250, 230, 250)
    _ring(pen, 330, 250, 110, 130, clockwise=True)


def _draw_A(pen):
    """An outer boundary with one counter, clear of the boundary on all sides."""
    _rect(pen, 60, 0, 540, CAP_HEIGHT)
    pen.moveTo((180, 120))
    for p in [(420, 120), (300, 580)]:
        pen.lineTo(p)
    pen.closePath()


def _draw_B(pen):
    """One outer contour with two holes."""
    _rect(pen, 100, 0, 600, CAP_HEIGHT)
    _rect(pen, 220, 380, 480, 600, clockwise=True)
    _rect(pen, 220, 100, 480, 320, clockwise=True)


def _draw_eight(pen):
    _rect(pen, 100, 0, 600, CAP_HEIGHT)
    _ring(pen, 350, 520, 120, 120, clockwise=True)
    _ring(pen, 350, 190, 150, 150, clockwise=True)


def _draw_i(pen):
    """Two disjoint contours."""
    _rect(pen, 150, 0, 300, X_HEIGHT)
    _rect(pen, 150, 600, 300, CAP_HEIGHT)


def _draw_x(pen):
    _rect(pen, 100, 0, 500, X_HEIGHT)


def _draw_e(pen):
    _ring(pen, 330, 250, 230, 250)
    _ring(pen, 330, 300, 120, 120, clockwise=True)


def _draw_acute(pen):
    pen.moveTo((200, 560))
    for p in [(340, 560), (420, 740), (280, 740)]:
        pen.lineTo(p)
    pen.closePath()


OUTLINES = {
    "L": _draw_L,
    "H": _draw_H,
    "O": _draw_O,
    "o": _draw_o,
    "A": _draw_A,
    "B": _draw_B,
    "eight": _draw_eight,
    "i": _draw_i,
    "x": _draw_x,
    "e": _draw_e,
    "acute": _draw_acute,
}

#: ``eacute`` is a composite, which exercises ``BasePen.addComponent``.
COMPONENTS = {"eacute": [("e", (1, 0, 0, 1, 0, 0)), ("acute", (1, 0, 0, 1, 20, 0))]}

CHARACTER_MAP = {
    ord("L"): "L",
    ord("H"): "H",
    ord("O"): "O",
    ord("o"): "o",
    ord("A"): "A",
    ord("B"): "B",
    ord("8"): "eight",
    ord("i"): "i",
    ord("x"): "x",
    ord("e"): "e",
    ord("é"): "eacute",
}


def build_font(path):
    """Write the synthetic font to ``path`` and return ``path``."""
    glyph_order = [".notdef", *OUTLINES, *COMPONENTS]

    glyphs = {}
    pen = TTGlyphPen(None)
    glyphs[".notdef"] = pen.glyph()
    for name, draw in OUTLINES.items():
        pen = TTGlyphPen(None)
        draw(pen)
        glyphs[name] = pen.glyph()
    for name, components in COMPONENTS.items():
        pen = TTGlyphPen(glyphs)
        for base, transform in components:
            pen.addComponent(base, transform)
        glyphs[name] = pen.glyph()

    fb = FontBuilder(unitsPerEm=UNITS_PER_EM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(CHARACTER_MAP)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (700, 50) for name in glyph_order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "LetterStampsFixture", "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, sCapHeight=CAP_HEIGHT)
    fb.setupPost()
    fb.save(str(path))
    return path


if __name__ == "__main__":
    import sys

    print(build_font(sys.argv[1] if len(sys.argv) > 1 else "fixture.ttf"))
