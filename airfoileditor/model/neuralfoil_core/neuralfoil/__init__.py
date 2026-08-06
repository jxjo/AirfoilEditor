from .core_api import get_aero_from_kulfan_parameters, bl_x_points

__all__ = [
    "get_aero_from_kulfan_parameters",
    "bl_x_points",
]

try:
    from importlib.metadata import version

    __version__ = version("neuralfoil-core")
except Exception:
    __version__ = "unknown"
