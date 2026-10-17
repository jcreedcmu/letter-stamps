"""Turn a TTF glyph into a stamp solid on a rectangular base."""

from .geom import contours_to_faces
from .glyph import Outline, load_outline
from .stamp import DraftDropped, Overhang, ThinFeature, build_stamp

__all__ = [
    "DraftDropped",
    "Outline",
    "Overhang",
    "ThinFeature",
    "build_stamp",
    "contours_to_faces",
    "load_outline",
]
