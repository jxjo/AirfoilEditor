#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Reusable DXF artist and CAD entity helpers."""

from abc            import ABC, abstractmethod
from typing         import Callable, override

import ezdxf
from ezdxf          import enums, units
from ezdxf.layouts  import Modelspace
from ezdxf.document import Drawing

from .spline        import Bezier, BSpline

import logging

TextAlign = enums.TextEntityAlignment


ezdxf_logger = logging.getLogger("ezdxf")
ezdxf_logger.setLevel(logging.WARNING)

# ------------------------------------------------------------------------------

class Cad_Entity(ABC):
    """Abstract base for CAD helper entities."""

    @abstractmethod
    def add_to(self, msp: Modelspace):
        """Add self to the DXF modelspace."""


class Cad_Line(Cad_Entity):
    """CAD line segment in planform coordinates."""

    def __init__(self, points: list[tuple[float, float]]):
        if len(points) != 2:
            raise ValueError("A CAD line must have exactly two points.")
        self.points = points


    @classmethod
    def from_x_y(cls, x: list[float], y: list[float]) -> "Cad_Line":
        """Build a CAD line from x and y coordinates."""
        points = [(round(float(xi), 10), round(float(yi), 10)) for xi, yi in zip(x, y)]
        return cls(points)


    @override
    def add_to(self, msp: Modelspace):
        """Add the CAD line to the modelspace."""
        msp.add_line(self.points[0], self.points[1])



class Cad_PolyLine(Cad_Entity):
    """CAD polyline segment in planform coordinates."""

    def __init__(self, points: list[tuple[float, float]]):
        if len(points) < 2:
            raise ValueError("A CAD polyline must have at least two points.")
        self.points = points


    @classmethod
    def from_x_y(cls, x: list[float], y: list[float]) -> "Cad_PolyLine":
        """Build a CAD polyline from x and y coordinates."""
        points = [(round(float(xi), 10), round(float(yi), 10)) for xi, yi in zip(x, y)]
        return cls(points)


    @override
    def add_to(self, msp: Modelspace):
        """Add the CAD polyline to the modelspace."""
        msp.add_lwpolyline(self.points, close=False)



class Cad_FitSpline (Cad_Entity):
    """CAD fit-point spline segment in planform coordinates."""

    def __init__(self, fit_points: list[tuple[float, float]]):

        if len(fit_points) < 2:
            raise ValueError("A CAD fit spline must have at least two points.")

        self.fit_points = fit_points


    @staticmethod
    def _build_points (x: list[float], y: list[float],
                       point_transform: Callable[[float, float], tuple[float, float]] | None = None,
                       ) -> list[tuple[float, float]]:
        """Build rounded 2D fit points with an optional XY transform."""

        points: list[tuple[float, float]] = []
        for xi, yi in zip(x, y):
            x_val = float(xi)
            y_val = float(yi)
            if point_transform is not None:
                x_val, y_val = point_transform(x_val, y_val)
            points.append((round(x_val, 10), round(y_val, 10)))

        return points


    @classmethod
    def from_x_y (cls, x: list[float], y: list[float], 
                  point_transform: Callable[[float, float], tuple[float, float]] | None = None,
                  ) -> "Cad_FitSpline":
        """Build a CAD fit-point spline from x and y coordinates."""

        points = cls._build_points(x, y, point_transform=point_transform)
        return cls(points)


    @override
    def add_to(self, msp: Modelspace):
        """Add the CAD fit-point spline to the modelspace."""

        msp.add_cad_spline_control_frame(fit_points=self.fit_points)



class Cad_Spline(Cad_Entity):
    """CAD spline segment in planform coordinates."""

    def __init__ (self,
                  control_points: list[tuple[float, float]],
                  degree: int,
                  knots: list[float] | None = None,
                  weights: list[float] | None = None ):
        
        self.control_points = control_points
        self.degree = degree
        self._knots = knots
        self.weights = weights


    @staticmethod
    def _build_points (control_points: list[tuple[float, float]],
                       point_transform: Callable[[float, float], tuple[float, float]] | None = None,
                      ) -> list[tuple[float, float]]:
        """Build rounded 2D points with an optional XY transform."""

        points: list[tuple[float, float]] = []
        for x, y in control_points:
            x_val = float(x)
            y_val = float(y)
            if point_transform is not None:
                x_val, y_val = point_transform(x_val, y_val)
            points.append((round(x_val, 10), round(y_val, 10)))

        return points


    @classmethod
    def from_bezier (cls, bezier: Bezier,
                     point_transform: Callable[[float, float], tuple[float, float]] | None = None,
                    ) -> "Cad_Spline":
        """Build a CAD spline from a Bezier curve control polygon."""

        points = cls._build_points(bezier.cpoints, point_transform=point_transform)
        return cls(points, degree=bezier.ncp - 1)


    @classmethod
    def from_bspline (cls, bspline: BSpline,
                      point_transform: Callable[[float, float], tuple[float, float]] | None = None,
                      ) -> "Cad_Spline":
        """Build a CAD spline from a B-spline curve control polygon."""

        points = cls._build_points(bspline.cpoints, point_transform=point_transform)
        return cls(points, degree=bspline.degree, knots=list(bspline.knots()))


    @property
    def knots(self) -> list[float]:
        """Clamped Bezier knot vector for this single-span spline."""
        if self._knots is not None:
            return self._knots
        return [0.0] * (self.degree + 1) + [1.0] * (self.degree + 1)


    @property
    def is_rational(self) -> bool:
        return self.weights is not None


    @override
    def add_to(self, msp: Modelspace):
        """Add the CAD spline to the modelspace."""

        control_points = [(x, y, 0.0) for x, y in self.control_points]

        if self.is_rational:
            msp.add_rational_spline(
                control_points=control_points,
                degree=self.degree,
                weights=self.weights,
                knots=self.knots,
            )
        else:
            msp.add_open_spline(
                control_points=self.control_points,
                degree=self.degree,
                knots=self.knots,
            )



class Cad_Text(Cad_Entity):
    """CAD text entity in planform coordinates."""

    def __init__(self,
                text: str,
                insert: tuple[float, float],
                height: float,
                align=TextAlign.LEFT,
                rotation: float | None = None):
        
        self.text   = text
        self.insert = insert
        self.height = height
        self.align  = align
        self.rotation = rotation


    @override
    def add_to(self, msp: Modelspace):
        """Add the CAD text to the modelspace."""
        text_entity = msp.add_text(self.text, height=self.height, rotation=self.rotation)
        text_entity.set_placement(self.insert, align=self.align)



class Dxf_Artist(ABC):
    """Abstract, model-agnostic DXF artist."""

    def __init__(self, drawing : Drawing|None = None):

        if isinstance(drawing, Drawing):
            self.drawing = drawing
        else:
            self.drawing = ezdxf.new("R2000", units=units.MM)   #R2010
        self.msp = self.drawing.modelspace()


    @abstractmethod
    def plot(self):
        """main entry point for plotting the model into the DXF document."""
        pass


    def _plot(self, entity: Cad_Entity):
        """Plot a CAD entity into the current modelspace."""
        entity.add_to(self.msp)


    def save(self, pathFileName):
        """Save the current DXF document to pathFileName."""

        self.drawing.saveas(pathFileName)
