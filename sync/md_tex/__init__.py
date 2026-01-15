"""Public exports for md/tex sync utilities.
Import from here to access the main sync entry points.
This module re-exports config and sync functions for convenience.
"""

from .config import FigureMapping, SyncConfig, load_config
from .syncer import SyncResult, sync_project

__all__ = [
    "FigureMapping",
    "SyncConfig",
    "SyncResult",
    "load_config",
    "sync_project",
]
