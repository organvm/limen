"""Canonical whole-estate agent review.

The package owns the reusable review pipeline. Dated review directories are
frozen outputs and compatibility entrypoints only.
"""

from .config import ReviewConfig, derive_windows
from .model import OUTCOMES, Window

__all__ = ["OUTCOMES", "ReviewConfig", "Window", "derive_windows"]
