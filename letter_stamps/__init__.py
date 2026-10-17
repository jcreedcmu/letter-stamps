"""Turn a TTF glyph into a tapered stamp solid."""

from .glyph import load_outline
from .geom import contours_to_faces
from .stamp import build_stamp

__all__ = ["load_outline", "contours_to_faces", "build_stamp"]
