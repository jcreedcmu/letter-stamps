"""Build a run of characters and report what happened to each one.

It tabulates whether the draft survived, which is the part that depends on the
font, the depth, and the draft angle all at once. Pass ``--out-dir`` to keep
the solids as well.

    python3 tools/sweep.py --font "Some Font.otf"
    python3 tools/sweep.py --font "Some Font.otf" --depth 3 --chars ABCDEFG
    python3 tools/sweep.py --font "Some Font.otf" --out-dir build
"""

import argparse
import math
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cadquery as cq  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

from letter_stamps.cli import default_output  # noqa: E402
from letter_stamps.geom import DEFAULT_TOLERANCE, contours_to_faces  # noqa: E402
from letter_stamps.glyph import (  # noqa: E402
    DEFAULT_MARGIN,
    DEFAULT_MIN_WIDTH,
    SIZE_MODES,
    load_outline,
)
from letter_stamps.stamp import (  # noqa: E402
    DraftDropped,
    Overhang,
    ThinFeature,
    build_stamp,
)

UPPERCASE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

HEADER = (
    f"{'char':<5}{'cont':>5}{'faces':>6}{'holes':>6}{'edges':>7}"
    f"{'base w x h':>14}{'draft':>7}{'thin':>6}{'over':>6}"
    f"{'valid':>7}{'volume':>10}{'time':>7}"
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--font", required=True)
    p.add_argument("--chars", default=UPPERCASE, help=f"default: {UPPERCASE}")
    p.add_argument("--size", type=float, default=10.0)
    p.add_argument("--size-mode", default="cap", choices=SIZE_MODES)
    p.add_argument("--depth", type=float, default=4.0)
    p.add_argument("--draft", type=float, default=7.0)
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    p.add_argument("--base-thickness", type=float, default=4.5)
    p.add_argument("--base-margin", type=float, default=DEFAULT_MARGIN)
    p.add_argument("--base-min-width", type=float, default=DEFAULT_MIN_WIDTH)
    p.add_argument(
        "--out-dir",
        help="write each solid here as stamp_<char>.<ext>; nothing is written "
        "without this",
    )
    p.add_argument("--ext", default="step", choices=("step", "stl"))
    p.add_argument(
        "--verbose",
        action="store_true",
        help="print every warning in full as it happens, rather than "
        "summarising the fallbacks at the end",
    )
    return p.parse_args(argv)


def describe(args, char, out_dir):
    """Build one character; return a row of findings and any warnings."""
    row = {"char": char}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        start = time.time()
        try:
            outline = load_outline(
                args.font,
                char,
                size=args.size,
                size_mode=args.size_mode,
                margin=args.base_margin,
                min_width=args.base_min_width,
            )
            contours = outline.contours
            faces = contours_to_faces(contours, args.tolerance)
            body = build_stamp(
                outline,
                depth=args.depth,
                draft=args.draft,
                base_thickness=args.base_thickness,
                tolerance=args.tolerance,
            )
            shape = body.val()
            # Measured before any export, since writing STL attaches a
            # triangulation that shifts what BoundingBox reports.
            row.update(
                contours=len(contours),
                faces=len(faces),
                holes=sum(len(f.innerWires()) for f in faces),
                edges=max(len(f.outerWire().Edges()) for f in faces),
                valid=shape.isValid(),
                volume=shape.Volume(),
                base=f"{outline.width:.2f} x {outline.height:.2f}",
            )
            if out_dir is not None:
                path = out_dir / Path(default_output(char)).with_suffix(
                    "." + args.ext
                )
                cq.exporters.export(body, str(path))
                row["path"] = path
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["seconds"] = time.time() - start

    row["dropped"] = [w for w in caught if issubclass(w.category, DraftDropped)]
    row["thin"] = any(issubclass(w.category, ThinFeature) for w in caught)
    row["over"] = [w for w in caught if issubclass(w.category, Overhang)]
    row["other"] = [
        w
        for w in caught
        if not issubclass(w.category, (DraftDropped, ThinFeature, Overhang))
    ]
    return row


def format_row(row):
    if "error" in row:
        return f"{row['char']:<5}{'-':>5}{'-':>6}{'-':>6}{'-':>7}  {row['error']}"
    return (
        f"{row['char']:<5}{row['contours']:>5}{row['faces']:>6}{row['holes']:>6}"
        f"{row['edges']:>7}{row['base']:>14}"
        f"{('no' if row['dropped'] else 'yes'):>7}"
        f"{('yes' if row['thin'] else ''):>6}"
        f"{('yes' if row['over'] else ''):>6}"
        f"{('yes' if row['valid'] else 'NO'):>7}"
        f"{row['volume']:>10.1f}{row['seconds']:>6.1f}s"
    )


def main(argv=None):
    args = parse_args(argv)
    if args.verbose:
        warnings.simplefilter("always")

    try:
        cmap = TTFont(args.font).getBestCmap()
    except Exception as exc:
        print(f"sweep: cannot read {args.font}: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    delta = args.depth * math.tan(math.radians(args.draft))
    print(
        f"{args.font}\n"
        f"size {args.size:g} mm, depth {args.depth:g} mm, draft {args.draft:g} deg, "
        f"chord tolerance {args.tolerance:g} mm\n"
        f"the draft moves the walls {delta:.3f} mm sideways\n"
    )
    print(HEADER)

    rows = []
    skipped = []
    for char in args.chars:
        if ord(char) not in cmap:
            skipped.append(char)
            continue
        row = describe(args, char, out_dir)
        rows.append(row)
        print(format_row(row), flush=True)

    built = [r for r in rows if "error" not in r]
    drafted = [r for r in built if not r["dropped"]]
    overhanging = [r for r in built if r["over"]]
    invalid = [r for r in built if not r["valid"]]
    errored = [r for r in rows if "error" in r]

    print(
        f"\n{len(rows)} characters: {len(drafted)} drafted, "
        f"{len(built) - len(drafted)} fell back to straight walls, "
        f"{len(invalid)} invalid, {len(errored)} failed outright, "
        f"{len(overhanging)} overhanging their base, "
        f"{sum(r['seconds'] for r in rows):.1f}s total"
    )
    if out_dir is not None:
        written = [r for r in rows if "path" in r]
        print(f"wrote {len(written)} .{args.ext} files to {out_dir}/")
    if skipped:
        print(f"not in this font: {''.join(skipped)}")

    if not args.verbose:
        for row in built:
            for w in row["dropped"] + row["over"] + row["other"]:
                print(f"\n{row['char']}: {w.message}")

    return 0 if not errored and not invalid else 1


if __name__ == "__main__":
    sys.exit(main())
