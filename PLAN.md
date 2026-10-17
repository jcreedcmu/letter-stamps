# letter-stamps

Automation pipeline: a `.ttf` font file plus a choice of letter goes in,
a STEP (or STL) solid of a stamp for that letterform comes out. The
solid is a tapered extrusion of the glyph outline, mirrored so the
impression reads correctly, optionally sitting on a base pad.

Status: built. `README.md` covers usage; this file is the design.

## Dependencies

* `cadquery` (pulls in `OCP`, the OpenCascade binding) for geometry and export
* `fonttools` for reading the `.ttf`
* `pytest` for the checks below

`pip install cadquery fonttools pytest`

Tested against cadquery 2.7 and fonttools 4.29.

## Layout

```
pyproject.toml
letter_stamps/
  __init__.py
  glyph.py    # ttf -> contours of line/quadratic/cubic segments
  geom.py     # contours -> cadquery Face
  stamp.py    # Face -> tapered solid (+ base pad)
  cli.py      # argparse entry point
tests/
  conftest.py
  fixtures/synthetic.py   # builds a small TTF to test against
  test_glyph.py
  test_stamp.py           # covers geom.py too
  test_cli.py
  test_real_font.py
```

## Stage 1: glyph outline (`glyph.py`)

Load with `fontTools.ttLib.TTFont`, resolve the character through
`font.getBestCmap()[ord(ch)]` to a glyph name, and draw it into a pen.

Subclass `fontTools.pens.basePen.BasePen`, constructed with
`font.getGlyphSet()`, and implement `_moveTo`, `_lineTo`, `_qCurveToOne`,
`_curveToOne`, `_closePath`. Two things come free from `BasePen`: it
expands TrueType `qCurveTo` runs into individual quadratic segments with
the implied on-curve midpoints inserted, and `addComponent` recurses
through the glyph set, so composite glyphs like `é` decompose without
extra work. `_curveToOne` is implemented for completeness (`.ttf` outlines
are quadratic, but the same pen then works on a `.otf`).

Output is a list of contours; each contour is a list of segments, each
segment a tuple `("line", p0, p1)`, `("quad", p0, c, p1)`, or
`("cubic", p0, c1, c2, p1)`, in font units.

Then, in order:

1. **Scale.** `scale = size_mm / reference`, where `reference` depends on
   `--size-mode`:
   * `bbox` (default): the glyph's own outline height, so the letter comes
     out exactly `size_mm` tall
   * `cap`: `font['OS/2'].sCapHeight`, so sibling letters stay in
     proportion to one another
   * `em`: `font['head'].unitsPerEm`
2. **Mirror.** Negate x. This is what makes the impression read correctly.
3. **Center.** Translate so the outline bounding box is centered on the
   origin in xy, which keeps a base pad concentric with the letter.

Mirroring reverses every contour's winding; stage 2 reassigns winding from
scratch, so that needs no special handling here.

## Stage 2: outline to face (`geom.py`)

Build each contour as a `cadquery.Wire`:

* `("line", ...)` to `Edge.makeLine`
* `("quad", ...)` and `("cubic", ...)` to `Edge.makeBezier` with the
  control points as given, so curves stay exact rather than polylined
* drop any segment whose endpoints are within `1e-7 * size_mm` of each
  other before building; coincident points are the usual cause of an OCC
  edge failure
* `Wire.assembleEdges(edges)`, then close it

Classify outer boundaries against holes by nesting rather than by trusting
the font's winding:

1. Compute each contour's signed area (shoelace over segment endpoints is
   accurate enough for this) and its bounding box.
2. For each contour, count how many other contours contain it, testing
   bounding-box containment first and confirming with a point-in-polygon
   check of one vertex against the flattened candidate.
3. Even containment count means an outer boundary, odd means a hole.

Group each hole with its immediate container and emit one
`cadquery.Face.makeFromWires(outer, inners)` per outer boundary, forcing
outer wires counterclockwise and holes clockwise by reversing where the
signed area disagrees. `i`, `j`, `%`, and `=` give several disjoint faces;
`B` and `8` give one face with two holes.

## Stage 3: solid (`stamp.py`)

Convention: the letterform is the top face of the solid, at `z = depth`,
and the body widens on the way down to `z = 0`. Looking down at the model
from `+z` shows the stamping surface itself, reading mirrored, the way a
real stamp looks turned face up, and the impression it leaves reads
correctly. With a base the model rests on `z = 0`, flat side down and
letter up, which is also the right way round for a printer bed: every
layer is wider than the one above it.

Building it that way round directly is awkward, so the extrusion runs
letterform-down and widening upward, and the result is turned over with
`mirror("XY")` and a translate.

For a face with no inner wires, cadquery's taper extrusion does the job,
with a negative taper to expand the cross-section rather than shrink it:

```python
cq.Workplane("XY").add(faces).toPending().extrude(depth, taper=-draft)
```

That path rejects faces with inner wires outright ("Inner wires not
allowed with tapered extrusion"), so any glyph with a counter goes through
a loft instead: offset the outline by `depth * tan(draft)`, outward for the
outer boundary and inward for each hole, put the offset wires at the far
end, and `Solid.makeLoft` between them, cutting the hole lofts out of the
outer one. Use `offset2D(d, "intersection")` rather than the default
`"arc"`, so corners extend to meet instead of being rounded off; that
preserves the edge count, which keeps the loft from twisting, and it is
what a draft angle should do to a corner anyway. A glyph goes down one
path or the other as a whole, so every wall of a given letter is built the
same way.

The loft walls are ruled rather than true draft surfaces, which is exact
for straight outline segments and a close approximation on curves. On a
10 mm square at 4 mm depth and 7 degrees it matches the analytic
sharp-cornered volume to six figures.

Guard against draft collapsing a thin stem: warn if `depth * tan(draft)`
exceeds roughly a third of a feature width estimated as
`2 * area / perimeter`, which is about right for a long stroke of uniform
width.

The optional base is a `plate` (rectangle spanning the letter bounding box
plus `--base-margin`) or a `disc` (circle enclosing the same box), of
`--base-thickness`, fused under the letter from `z = 0` up. A chamfer on
its bottom edge is cosmetic and cheap to add.

## Stage 4: export (`cli.py`)

`cq.exporters.export(body, out_path)` dispatches on the extension. STEP
keeps the Bezier geometry as B-splines, so prefer it; STL tessellates and
takes `tolerance` / `angularTolerance`.

CLI:

```
letter-stamp --font Garamond.ttf --char A \
             --size 12 --size-mode bbox \
             --depth 4 --draft 7 \
             --base disc --base-thickness 2 --base-margin 1.5 \
             --out A.step
```

Defaults: `--size 10`, `--size-mode bbox`, `--depth 4`, `--draft 7`,
`--base none`.

## Checks

The exact assertions need a font whose geometry is known, and there is no
guarantee of finding one on the machine, so `tests/fixtures/synthetic.py`
builds one with `fontTools.fontBuilder`. Its letterforms are blocky
stand-ins on a 1000 unit em with a 700 cap height, covering the cases the
pipeline has to get right: one contour (`L`, `H`), one hole (`O`, `A`), two
holes (`B`, `8`), two disjoint contours (`i`), quadratic curves (`O`, `o`,
`8`), and a composite glyph (`é`).

`tests/test_glyph.py`:

* contour counts: 1 for `L`, 2 for `O` and `A`, 3 for `B`, 2 for `i`
* mirroring: the x coordinates of `L` are negated relative to the
  unmirrored outline, and y is untouched
* `bbox` mode makes the outline exactly `--size` tall; `cap` mode makes `H`
  exactly `--size` tall and `o` shorter
* flattening follows the curve: the raw control points of `O` reach outside
  the measured bounding box

`tests/test_stamp.py`:

* `isValid()` and positive volume for `L`, `O`, `B`, `8`, `i`, `é`
* nesting decides holes: `O` is one face with a hole, `i` is two faces, and
  reversing every contour changes neither
* draft widens the body relative to an untapered extrusion
* the bounding box z extent equals `depth` plus any base thickness, the
  model rests on `z = 0`, the top face matches the glyph size, and the
  bottom face is larger
* a base fuses the two disjoint pieces of `i` into one solid
* a STEP file is written and reimports with the same volume

`tests/test_cli.py` runs the entry point for a STEP and an STL output and
checks the error paths. `tests/test_real_font.py` pushes the whole alphabet
through an actual typeface, named by `LETTER_STAMPS_TEST_FONT` or found in
the system font directories, asserting only validity; it skips when there
is no font to find.


## Extensions, once the single letter works

* `--text ABC` to set a word, advancing by each glyph's `hmtx` advance
  width and kerning from `GPOS` if present, mirrored as a whole so the
  word reads correctly
* a handle: a cylinder or knob fused to the base
* `--relief` to invert, cutting the letter out of a plate instead
* a true draft surface for the lofted path, if the ruled approximation ever
  turns out to matter
