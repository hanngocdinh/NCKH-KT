"""Model-only water-level forecasting with configurable time windows and horizons."""

from .config import MiniFloodSettings
from .service import MiniFloodService

__all__ = ["MiniFloodService", "MiniFloodSettings"]
