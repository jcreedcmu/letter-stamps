# letter-stamps

Turn one glyph of a TTF font into a stamp solid: a tapered extrusion of the
letterform, exported as STEP or STL.

Run it from the repo without installing anything:

```
python3 -m letter_stamps --font DejaVuSans.ttf --char A --size 12 --depth 4 \
                         --draft 7 --base disc --out A.step
```

Or install it and get the `letter-stamp` command:

```
pip install -e .
letter-stamp --font DejaVuSans.ttf --char A --size 12 --base disc --out A.step
```

## Orientation

The letterform is the **top** face of the solid, at `z = depth`. Looking down
at the model from `+z` shows the stamping surface itself, reading mirrored, the
way a real stamp looks when you turn it face up. The impression it leaves
reads correctly.

The body widens on the way down from that face, by `--draft` degrees, so the
relief has some meat behind it and releases cleanly. With a base the model
rests on `z = 0`, flat side down and letter up, which is also how you want it
on a printer bed: every layer is wider than the one above it, so there is
nothing to overhang.

`--no-mirror` skips the mirror. The model then reads correctly when viewed
from above and the impression comes out backwards, which is useful for
checking a glyph against the font but not for stamping.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--font` | required | path to a `.ttf` or `.otf` |
| `--char` | required | the single character to stamp |
| `--out` | `stamp_<char>.step` | output path; `.step` or `.stl` |
| `--size` | `10` | letter size in mm, measured per `--size-mode` |
| `--size-mode` | `bbox` | `bbox` for the glyph's own height, `cap` for the font's cap height, `em` for its em square |
| `--depth` | `4` | extrusion depth in mm |
| `--draft` | `7` | draft angle in degrees |
| `--base` | `none` | `none`, `disc`, or `plate` |
| `--base-thickness` | `2` | pad thickness in mm |
| `--base-margin` | `1.5` | how far the pad extends past the letter |
| `--base-chamfer` | `0` | chamfer on the pad's bottom edge |
| `--no-mirror` | off | skip the mirror |

`--size-mode cap` is the one to use when cutting a set of letters that have to
look like each other: every glyph is scaled by the same factor, so an `o` comes
out shorter than an `H`. `bbox` makes each glyph exactly `--size` tall, which
is what you want for a single stamp.

## As a library

```python
from letter_stamps import load_outline, build_stamp
import cadquery as cq

contours = load_outline("DejaVuSans.ttf", "A", size=12, size_mode="cap")
body = build_stamp(contours, depth=4, draft=7, base="disc")
cq.exporters.export(body, "A.step")
```

`load_outline` returns contours of `("line", p0, p1)`, `("quad", p0, c, p1)`,
and `("cubic", p0, c1, c2, p1)` segments in mm, already mirrored and centered
on the origin.

## How it works

1. `glyph.py` draws the glyph through a `fontTools` pen that collects line and
   Bezier segments. `BasePen` expands TrueType `qCurveTo` runs into individual
   quadratics with the implied on-curve midpoints inserted, and recurses into
   composite glyphs, so `é` works like any other character. The outline is then
   scaled, mirrored in x, and centered.
2. `geom.py` builds each contour as a wire of exact Bezier edges, and decides
   which contours are holes by counting how deeply each one is nested rather
   than by trusting the winding the font happens to use. `i` comes out as two
   disjoint faces; `B` as one face with two holes.
3. `stamp.py` extrudes. cadquery's tapered extrusion rejects faces with inner
   wires, so a glyph with a counter is instead lofted between its outline and
   a 2D offset of it, which gives the same draft with straight walls. Then the
   solid is turned over so the letterform is on top, and the base is fused on.

## Tests

```
pip install pytest
pytest
```

The suite builds its own synthetic font (`tests/fixtures/synthetic.py`), so the
exact assertions have something deterministic to measure. `tests/test_real_font.py`
additionally runs the whole alphabet through a real typeface, found in the
system font directories or named by `LETTER_STAMPS_TEST_FONT`; it skips if
there is no font to be found.
