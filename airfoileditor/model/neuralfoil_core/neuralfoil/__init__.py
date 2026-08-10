from .core_api import (
    available_model_sizes,
    bl_x_points,
    get_aero_from_kulfan_parameters,
)

__all__ = [
    "available_model_sizes",
    "get_aero_from_kulfan_parameters",
    "bl_x_points",
]

try:
    from importlib.metadata import version

    __version__ = version("neuralfoil-core")
except Exception:
    __version__ = "unknown"
