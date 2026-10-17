"""Turn glyph contours into cadquery faces on the XY plane.

The contours are flattened to polylines first. That costs a little exactness
on curves and buys a great deal of robustness: OpenCascade's 2D offset, which
`stamp` needs for the draft, mangles or refuses Bezier wires on real
letterforms, and handles polygons without complaint.
"""

import cadquery as cq

from .glyph import flatten

#: Flattening tolerance in mm. No point on a curve ends up further than this
#: from the polyline that stands in for it.
DEFAULT_TOLERANCE = 0.01


def signed_area(polygon):
    total = 0.0
    n = len(polygon)
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        total += x0 * y1 - x1 * y0
    return 0.5 * total


def _poly_bbox(polygon):
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            t = (y - y0) / (y1 - y0)
            if x < x0 + t * (x1 - x0):
                inside = not inside
    return inside


def _contains(outer, outer_box, inner, inner_box):
    oxmin, oymin, oxmax, oymax = outer_box
    ixmin, iymin, ixmax, iymax = inner_box
    if ixmin < oxmin or iymin < oymin or ixmax > oxmax or iymax > oymax:
        return False
    return point_in_polygon(inner[0], outer)


def reverse_contour(contour):
    """Reverse a contour's direction, segments and all."""
    return [(seg[0], *reversed(seg[1:])) for seg in reversed(contour)]


def polygon_to_wire(polygon):
    """One closed ``cq.Wire`` around a polyline."""
    if len(polygon) < 3:
        raise ValueError("contour collapsed to fewer than three points")
    return cq.Wire.makePolygon([cq.Vector(x, y, 0) for x, y in polygon], close=True)


def contours_to_faces(contours, tolerance=DEFAULT_TOLERANCE):
    """Faces for an outline, pairing each outer boundary with its holes.

    Nesting decides which contours are holes, rather than the winding the font
    happens to use. ``i`` and ``=`` give several disjoint faces; ``B`` and ``8``
    give one face with two holes.
    """
    polygons = flatten(contours, tolerance)
    boxes = [_poly_bbox(p) for p in polygons]

    depth = [
        sum(
            1
            for j in range(len(polygons))
            if j != i and _contains(polygons[j], boxes[j], polygons[i], boxes[i])
        )
        for i in range(len(polygons))
    ]

    def box_area(i):
        xmin, ymin, xmax, ymax = boxes[i]
        return (xmax - xmin) * (ymax - ymin)

    def parent(i):
        candidates = [
            j
            for j in range(len(polygons))
            if j != i
            and depth[j] == depth[i] - 1
            and _contains(polygons[j], boxes[j], polygons[i], boxes[i])
        ]
        return min(candidates, key=box_area) if candidates else None

    def oriented(i, counterclockwise):
        polygon = polygons[i]
        if (signed_area(polygon) < 0) == counterclockwise:
            return polygon[::-1]
        return polygon

    faces = []
    for i in range(len(polygons)):
        if depth[i] % 2:
            continue
        outer = polygon_to_wire(oriented(i, True))
        inners = [
            polygon_to_wire(oriented(j, False))
            for j in range(len(polygons))
            if depth[j] % 2 and parent(j) == i
        ]
        faces.append(cq.Face.makeFromWires(outer, inners))
    if not faces:
        raise ValueError("outline has no outer contour")
    return faces
