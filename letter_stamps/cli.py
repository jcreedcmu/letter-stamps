"""Command line entry point."""

import argparse
import sys

import cadquery as cq

from .geom import DEFAULT_TOLERANCE
from .glyph import DEFAULT_MARGIN, DEFAULT_MIN_WIDTH, SIZE_MODES, load_outline
from .stamp import build_stamp


def default_output(char):
    tag = char if char.isalnum() and char.isascii() else f"u{ord(char):04X}"
    return f"stamp_{tag}.step"


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="letter-stamp",
        description="Build a tapered stamp solid from one glyph of a TTF font.",
    )
    p.add_argument("--font", required=True, help="path to a .ttf or .otf file")
    p.add_argument("--char", required=True, help="the single character to stamp")
    p.add_argument("--out", help="output path; .step or .stl (default: stamp_<char>.step)")

    p.add_argument("--size", type=float, default=10.0, help="letter size in mm")
    p.add_argument(
        "--size-mode",
        choices=SIZE_MODES,
        default="cap",
        help="what --size measures: the font's cap height (cap), its em square "
        "(em), or the glyph's own height (bbox). Only cap and em scale every "
        "letter by the same factor, so only they give a set of stamps one "
        "common base height",
    )
    p.add_argument("--depth", type=float, default=4.0, help="extrusion depth in mm")
    p.add_argument("--draft", type=float, default=7.0, help="draft angle in degrees")
    p.add_argument(
        "--no-mirror",
        action="store_true",
        help="skip the x mirror (the model then reads correctly, the "
        "impression does not)",
    )

    p.add_argument(
        "--base-thickness",
        type=float,
        default=4.5,
        help="base thickness in mm, groove included",
    )
    p.add_argument(
        "--base-margin",
        type=float,
        default=DEFAULT_MARGIN,
        help="base to leave either side of the letter in mm. The base's height "
        "is not adjustable: it is the font's ascent to descent, so every letter "
        "comes out the same height",
    )
    p.add_argument(
        "--base-min-width",
        type=float,
        default=DEFAULT_MIN_WIDTH,
        help="narrowest base to produce in mm, whatever the margins work out "
        "to. A letter narrower than this gets a wider base rather than a "
        "narrower groove, so every stamp fits the same rail",
    )
    p.add_argument(
        "--base-chamfer",
        type=float,
        default=0.0,
        help="chamfer on the base's bottom edge in mm",
    )

    p.add_argument(
        "--chord-tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help="how far the polylines standing in for the glyph's curves may "
        "stray from them, in mm",
    )
    p.add_argument(
        "--stl-tolerance", type=float, default=0.01, help="STL linear tolerance in mm"
    )
    p.add_argument(
        "--stl-angular-tolerance",
        type=float,
        default=0.1,
        help="STL angular tolerance",
    )
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    out = args.out or default_output(args.char)

    try:
        outline = load_outline(
            args.font,
            args.char,
            size=args.size,
            size_mode=args.size_mode,
            mirror=not args.no_mirror,
            margin=args.base_margin,
            min_width=args.base_min_width,
        )
        body = build_stamp(
            outline,
            depth=args.depth,
            draft=args.draft,
            base_thickness=args.base_thickness,
            base_chamfer=args.base_chamfer,
            tolerance=args.chord_tolerance,
        )
    except (ValueError, KeyError, OSError) as exc:
        print(f"letter-stamp: {exc}", file=sys.stderr)
        return 1

    # Measure before exporting: writing STL attaches a triangulation to the
    # shape, which shifts what BoundingBox reports.
    box = body.val().BoundingBox()
    volume = body.val().Volume()

    cq.exporters.export(
        body,
        out,
        tolerance=args.stl_tolerance,
        angularTolerance=args.stl_angular_tolerance,
    )

    print(
        f"wrote {out}  "
        f"({box.xlen:.2f} x {box.ylen:.2f} x {box.zlen:.2f} mm overall, "
        f"base {outline.width:.2f} x {outline.height:.2f} mm, "
        f"volume {volume:.1f} mm^3)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
