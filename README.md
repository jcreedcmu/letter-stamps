# letter-stamps

Generate some letter stamps. For example:

```shell
python3 tools/sweep.py --font "Arial Rounded MT Std Extra Bold.otf" --depth 3 --draft 5 --out-dir /tmp/letters --size 15
```

## Orientation

The letterform is the **top** face of the solid. Looking down at the model
from `+z` shows the stamping surface itself, reading mirrored, the way a real
stamp looks when you turn it face up. The impression it leaves reads
correctly.

The body widens on the way down from that face, by `--draft` degrees, so the
relief has some meat behind it and releases cleanly. The base is underneath,
and the model rests on `z = 0`, letter up: every layer is wider than the one
above it, so there is nothing for a printer to overhang.

`--no-mirror` skips the mirror. The model then reads correctly when viewed
from above and the impression comes out backwards, which is useful for
checking a glyph against the font but not for stamping.

## The base

The base rectangle is as wide as the letter plus `--base-margin` either side,
or `--base-min-width`, whichever is greater; the letter is centered on it
either way, so a narrow letter like `I` just gets more margin than it asked
for. The minimum exists so that every base can take the same groove with wall
left either side. Its height is not adjustable: it is the font's ascent to
descent, which is the same measurement for every letter, so a set of stamps
cut from one font at one size all come out the same height and the letters sit
on a common baseline.

Every letter is then dropped by half the descent. Arial Black in
particular looks like it leaves very little room between cap height
and ascent, so a capital placed strictly on the baseline nearly
touches the top edge; moving everything down splits the descent's
slack between the two edges.

The cost is that a full descender now hangs past the bottom edge, by 1.3 mm for
a `j` in that font. For a set of capitals that does not arise.

Three things get flagged rather than fixed:

* A letter whose draft reaches past the side of its base. Widen
  `--base-margin` past `depth × tan(draft)`, or ask for less draft.
* A glyph reaching past the font's ascent, as accents do.
* A descender reaching past the bottom edge, per the drop above.

Nothing is trimmed in any of these cases: widening the base would cost the one
dimension meant to be identical across a set.

## The groove

A dovetail groove runs the full height of the back of every base, open at both
ends, to slide onto a rail. Its profile is sketched in the `xz` plane and
extruded along `y`:

```
   z=2.5  /------------- 10 mm -------------\     deeper into the base
         /                                   \   45 degrees
   z=0   \--------  5 mm  --------/              the back face, open
```

The mouth at the open face is the narrow edge. Both widths and the 45 degree
sides are fixed, not options: every stamp carries the same groove so that any
of them fits the same rail. Together they fix the depth at 2.5 mm, which with
the default 4.5 mm base leaves 2 mm of material between the groove and the
underside of the letter.

Two refusals rather than warnings here, since either would produce a piece
that is not a stamp. A base narrower than the groove plus 1 mm of wall either
side cannot be cut at all; raise `--base-min-width`. A base thinner than the
groove plus 1 mm of material over it would be cut through; raise
`--base-thickness`.

`--base-chamfer` is best left off: after the groove is cut, the bottom edge it
chamfers includes the groove's mouth.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--font` | required | path to a `.ttf` or `.otf` |
| `--char` | required | the single character to stamp |
| `--out` | `stamp_<char>.step` | output path; `.step` or `.stl` |
| `--size` | `10` | letter size in mm, measured per `--size-mode` |
| `--size-mode` | `cap` | `cap` for the font's cap height, `em` for its em square, `bbox` for the glyph's own height |
| `--depth` | `4` | height of the relief above the base, in mm |
| `--draft` | `7` | draft angle in degrees |
| `--base-thickness` | `4.5` | base thickness in mm, groove included |
| `--base-margin` | `1.5` | base to leave either side of the letter, in mm |
| `--base-min-width` | `15` | narrowest base to produce, whatever the margins work out to |
| `--base-chamfer` | `0` | chamfer on the base's bottom edge |
| `--no-mirror` | off | skip the mirror |
| `--chord-tolerance` | `0.01` | how far the polylines standing in for the glyph's curves may stray from them, in mm |
| `--stl-tolerance` | `0.01` | STL linear tolerance |
| `--stl-angular-tolerance` | `0.1` | STL angular tolerance |

`--size-mode cap` scales every glyph by the same factor, so `--size 12` means
"capitals 12 mm tall" and an `o` comes out shorter than an `H`. That shared
factor is what gives a set of letters one base height, which is why it is the
default. `bbox` instead makes each glyph exactly `--size` tall, scaling each
one differently, so use it for a single stamp rather than a matching set.
