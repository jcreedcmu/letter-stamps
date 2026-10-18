"""Measure the draft angle of every wall of a letter.

Every side face of a correctly drafted letter leans at exactly the requested
angle. This walks the faces and reports the ones that do not, which is how to
tell a real geometry fault from something that only looks wrong.

    python3 tools/check_draft.py --font "Some Font.otf" --chars RA
"""

import argparse
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from letter_stamps.geom import (  # noqa: E402
    DEFAULT_TOLERANCE,
    contours_to_faces,
)
from letter_stamps.glyph import SIZE_MODES, flatten, load_outline  # noqa: E402
from letter_stamps.stamp import _extrude  # noqa: E402

#: A wall this far off the requested angle is worth looking at, in degrees.
TOLERANCE_DEG = 0.05


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--font", required=True)
    p.add_argument("--chars", default="ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    p.add_argument("--size", type=float, default=15.0)
    p.add_argument("--size-mode", default="cap", choices=SIZE_MODES)
    p.add_argument("--depth", type=float, default=3.0)
    p.add_argument("--draft", type=float, default=5.0)
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    p.add_argument(
        "--worst", type=int, default=3, help="how many offending walls to name"
    )
    return p.parse_args(argv)


def wall_tilts(shape):
    """``(geometry type, lean from vertical in degrees, where)`` per side face.

    A cap is any face whose normal is along z. Everything else is a wall, and
    its lean is how far its normal sits from horizontal.
    """
    walls = []
    caps = Counter()
    for face in shape.Faces():
        normal = face.normalAt()
        if abs(normal.z) > 1.0 - 1e-6:
            caps[face.geomType()] += 1
            continue
        lean = 90.0 - math.degrees(
            math.acos(max(-1.0, min(1.0, abs(normal.z))))
        )
        centre = face.Center()
        walls.append(
            (face.geomType(), abs(lean), (centre.x, centre.y), face.Area())
        )
    return walls, caps


def main(argv=None):
    args = parse_args(argv)
    print(
        f"{args.font}\n"
        f"size {args.size:g} mm, depth {args.depth:g} mm, draft {args.draft:g} "
        f"deg, chord tolerance {args.tolerance:g} mm\n"
        f"every wall should lean {args.draft:g} deg, within "
        f"{TOLERANCE_DEG:g} deg\n"
    )
    print(
        f"{'char':<5}{'walls':>7}{'types':>22}{'min':>8}{'max':>8}{'off':>6}"
        f"{'off area':>10}"
    )

    offenders = []
    for char in args.chars:
        try:
            outline = load_outline(
                args.font, char, size=args.size, size_mode=args.size_mode
            )
            faces = contours_to_faces(outline.contours, args.tolerance)
            polygons = flatten(outline.contours, args.tolerance)
            # Before the flip and before the base, so only the draft is in view.
            shape = _extrude(faces, polygons, args.depth, args.draft).val()
        except Exception as exc:
            print(f"{char:<5}  {type(exc).__name__}: {exc}")
            continue

        walls, caps = wall_tilts(shape)
        if not walls:
            print(f"{char:<5}  no walls found")
            continue

        bad = [w for w in walls if abs(w[1] - args.draft) > TOLERANCE_DEG]
        bad_area = sum(w[3] for w in bad)
        kinds = ", ".join(
            f"{n}x{k.lower()}" for k, n in Counter(w[0] for w in walls).most_common()
        )
        leans = [w[1] for w in walls]
        print(
            f"{char:<5}{len(walls):>7}{kinds:>22}{min(leans):>8.2f}"
            f"{max(leans):>8.2f}{len(bad):>6}{bad_area:>10.3f}"
        )
        for kind, lean, (x, y), area in sorted(
            bad, key=lambda w: -w[3]
        )[: args.worst]:
            offenders.append(
                f"  {char}: {kind.lower()} wall leans {lean:.2f} deg, "
                f"{area:.3f} mm^2, at ({x:.2f}, {y:.2f})"
            )

    if offenders:
        print("\nworst offenders:")
        print("\n".join(offenders))
    else:
        print("\nevery wall is at the requested angle")
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
