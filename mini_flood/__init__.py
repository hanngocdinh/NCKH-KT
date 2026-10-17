"""Pipeline dự báo ngập 15/30 phút cho mô hình vật lý thu nhỏ."""

from .config import MiniFloodSettings
from .service import MiniFloodService

__all__ = ["MiniFloodService", "MiniFloodSettings"]
