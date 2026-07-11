#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""

Handle export of a single airfoil to external file formats.

"""

import logging
import os
import shutil

from typing import override

from airfoileditor.base.dxf_artist          import *
from airfoileditor.base.common_utils        import PathHandler, fromDict, toDict
from airfoileditor.model.airfoil            import Airfoil, Flap_Definition
from airfoileditor.model.geometry_curve     import Geometry_Curve

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class Dxf_Airfoil_Artist(Dxf_Artist):
    """DXF artist for a single airfoil."""

    def __init__(self, airfoil: Airfoil, 
                 nick_name: str|None = None,
                 drawing = None,
                 chord_mm: float = 1.0, 
                 te_gap_mm: float|None = None,
                 xy_pos_mm: tuple[float, float] = (0.0, 0.0),
                 always_as_cubic_fit: bool = False):
        
        super().__init__(drawing=drawing)

        self._airfoil       = airfoil.asCopy()
        self._nick_name     = nick_name
        self._chord_mm      = chord_mm
        self._te_gap_mm     = te_gap_mm
        self._xy_pos_mm     = xy_pos_mm
        self._always_as_cubic_fit = always_as_cubic_fit
        if te_gap_mm is not None:
            self._airfoil.geo.set_te_gap(te_gap_mm / chord_mm)

    @property
    def airfoil(self) -> Airfoil:
        return self._airfoil

    def set_airfoil(self, airfoil: Airfoil):
        self._airfoil = airfoil


    @property
    def chord_mm(self) -> float:
        return self._chord_mm

    def set_chord_mm(self, chord_mm: float):
        self._chord_mm = chord_mm


    @property
    def xy_pos_mm(self) -> tuple[float, float]:
        return self._xy_pos_mm

    def set_xy_pos_mm(self, xy_pos_mm: tuple[float, float]):
        self._xy_pos_mm = xy_pos_mm


    def _point_transform(self):
        x0, y0 = self.xy_pos_mm
        chord_mm = self.chord_mm

        def transform(x: float, y: float) -> tuple[float, float]:
            return x0 + x * chord_mm, y0 + y * chord_mm

        return transform


    def _plot_dat_airfoil(self):
        """ plot .dat as cubic fit-point spline"""
        transform = self._point_transform()
        self._plot(Cad_FitSpline.from_x_y(self.airfoil.x, self.airfoil.y, point_transform=transform))


    def _plot_curve_airfoil(self):
        """ plot Bezier or B-spline airfoil as uniform B-spline curves"""
        transform = self._point_transform()
        geo : Geometry_Curve = self.airfoil.geo
        upper = geo.upper.curve
        lower = geo.lower.curve

        if self.airfoil.isBezierBased:
            self._plot(Cad_Spline.from_bezier(upper, point_transform=transform))
            self._plot(Cad_Spline.from_bezier(lower, point_transform=transform))
        else:
            self._plot(Cad_Spline.from_bspline(upper, point_transform=transform))
            self._plot(Cad_Spline.from_bspline(lower, point_transform=transform))

    @property
    def is_bspline_plot(self) -> bool:
        """Return True if the airfoil was plotted as uniform B-spline curves."""
        return not self._always_as_cubic_fit and  (self.airfoil.isBezierBased or self.airfoil.isBSplineBased)


    def _plot_title (self):
        """Add a title text to the DXF drawing."""

        xt, yt = self.xy_pos_mm

        # title right above LE
        if self._nick_name:
            title = f"'{self._nick_name}'"
        else:
            title = f"{self.airfoil.fileName}"

        if self.chord_mm <= 1.0:
            height = 0.04
        elif self.chord_mm <= 20.0:
            height = 0.4
        else:
            height = 4.0

        yt   += 0.1 * self.chord_mm + height

        self._plot (Cad_Text(title, (xt, yt), height=height, align=TextAlign.LEFT))

        # subtitle with chord and te_gap info
        subtitles = []
        if self.chord_mm > 1.0:
            subtitles.append(f"Chord: {self.chord_mm:.1f} mm")
            if self._te_gap_mm is not None:
                subtitles.append(f"TE gap: {self._te_gap_mm:.1f} mm")

        if self.is_bspline_plot:
            subtitles.append("uniform B-Spline")
        else:
            subtitles.append("cubic fit-point spline")

        subtitle = ", ".join(subtitles)
        yt    -= height
        height = height * 0.6
        self._plot (Cad_Text(subtitle, (xt, yt), height=height, align=TextAlign.LEFT))    


    @override
    def plot(self):

        if self.is_bspline_plot:
            self._plot_curve_airfoil()
        else:
            self._plot_dat_airfoil()

        self._plot_title()



class Export_Abstract:
    """Abstract base class for airfoil export classes."""

    EXPORT_DIR_SUFFIX = "_exported"

    def __init__(self, airfoil: Airfoil, dataDict: dict = None):

        self._airfoil       = airfoil
        self._working_dir   = airfoil.pathName_abs if airfoil else None
        self._export_dir    = fromDict(dataDict, "export_dir", None)
        self._clear_export_dir = False


    @property
    def airfoil(self) -> Airfoil:
        return self._airfoil


    def set_airfoil(self, airfoil: Airfoil):
        self._airfoil = airfoil
        self._working_dir = airfoil.pathName_abs if airfoil else None


    @property
    def issues (self) -> list[str]:
        """ list of issues of current airfoil geometry"""
        if self.airfoil:
            return self.airfoil.geo.assess_quality()
        else:
            return None
    
    @property
    def is_quality_good (self) -> bool:
        """ True if geometry has no issues"""
        return not self.issues
    

    @property
    def export_dir_default(self) -> str:
        return self.airfoil.fileName_stem + self.EXPORT_DIR_SUFFIX


    @property
    def export_dir(self) -> str:
        if self._export_dir is None or self._export_dir.strip() == "":
            return self.export_dir_default
        return self._export_dir


    def set_export_dir(self, newStr: str):
        export_dir = PathHandler(workingDir=self._working_dir).relFilePath(newStr)
        if export_dir != self.export_dir_default:
            self._export_dir = export_dir
        else:
            self._export_dir = None


    @property
    def export_dir_abs(self) -> str:
        return PathHandler(workingDir=self._working_dir).fullFilePath(self.export_dir)


    @property
    def clear_export_dir(self) -> bool:
        return self._clear_export_dir


    def set_clear_export_dir(self, aBool: bool):
        self._clear_export_dir = aBool


    def _as_dict(self) -> dict:
        d = {}
        export_dir = self._export_dir.replace(os.sep, "/") if self._export_dir else None
        toDict(d, "export_dir", export_dir)
        return d


    def _ensure_export_dir(self):
        if self.clear_export_dir and os.path.isdir(self.export_dir_abs):
            shutil.rmtree(self.export_dir_abs, ignore_errors=True)

        if not os.path.exists(self.export_dir_abs):
            os.makedirs(self.export_dir_abs)



class Export_Airfoil_Dxf (Export_Abstract):
    """Handle export of a single airfoil to DXF."""

    EXPORT_DIR_SUFFIX = "_dxf"

    def __init__(self, airfoil: Airfoil, dataDict: dict = None):
        super().__init__(airfoil, dataDict=dataDict)

        self._chord_mm      = fromDict(dataDict, "chord_mm", 1.0)
        self._te_gap_mm     = fromDict(dataDict, "te_gap_mm", None)
        self._xy_pos_mm     = (0.0, 0.0)

        self._always_as_cubic_fit = fromDict(dataDict, "always_as_cubic_fit", False)


    def _as_dict(self) -> dict:
        d = {}
        if self.adapt_te_gap:
            toDict(d, "te_gap_mm", self.te_gap_mm)
        if self.adapt_chord:
            toDict(d, "chord_mm", self.chord_mm)
        if self.always_as_cubic_fit:
            toDict(d, "always_as_cubic_fit", self.always_as_cubic_fit)
        return d


    @property
    def adapt_te_gap(self) -> bool:
        return self._te_gap_mm is not None 

    def set_adapt_te_gap(self, aBool: bool):
        if aBool:
            if self._te_gap_mm is None:
                self._te_gap_mm = self.airfoil.geo.te_gap * self.chord_mm
        else:
            self._te_gap_mm = None


    @property
    def te_gap_mm(self) -> float:
        if self._te_gap_mm is None:
            return self.airfoil.geo.te_gap * self.chord_mm
        else:
            return self._te_gap_mm

    def set_te_gap_mm(self, aVal: float):
        self._te_gap_mm = aVal


    @property
    def adapt_chord(self) -> bool:
        return self.chord_mm is not None and self.chord_mm != 1.0

    def set_adapt_chord(self, aBool: bool):
        if aBool:
            if self.chord_mm is None or self.chord_mm == 1.0:
                self._chord_mm = 100.0
        else:
            self._chord_mm = None

    @property
    def chord_mm(self) -> float:
        return self._chord_mm if self._chord_mm is not None else 1.0

    def set_chord_mm(self, aVal: float):
        self._chord_mm = aVal


    @property
    def xy_pos_mm(self) -> tuple[float, float]:
        return self._xy_pos_mm

    def set_xy_pos_mm(self, aVal: tuple[float, float]):
        self._xy_pos_mm = aVal

    @property
    def always_as_cubic_fit(self) -> bool:
        return self._always_as_cubic_fit

    def set_always_as_cubic_fit(self, aBool: bool):
        self._always_as_cubic_fit = aBool

    @property
    def export_fileName(self) -> str:
        return self.airfoil.fileName_stem + ".dxf"


    @property
    def export_pathFileName_abs(self) -> str:
        return os.path.join(self.export_dir_abs, self.export_fileName)


    def do_it(self, drawing = None) -> str:
        """ Export the airfoil to a DXF file and return the path to the exported file.
        If a drawing is provided, it will be used; otherwise, a new drawing will be created. """

        artist = Dxf_Airfoil_Artist(self._airfoil, 
                                    drawing=drawing,
                                    chord_mm=self.chord_mm, 
                                    te_gap_mm=self._te_gap_mm,
                                    xy_pos_mm=self.xy_pos_mm,
                                    always_as_cubic_fit=self.always_as_cubic_fit)
        artist.plot()

        if not drawing:
            # Ensure the export directory exists and is cleared if needed
            self._ensure_export_dir()
            artist.save(self.export_pathFileName_abs)
            logger.info(f"Airfoil exported to '{self.export_pathFileName_abs}'")
            return self.export_pathFileName_abs
        else:
            logger.info("Airfoil plotted to provided drawing.")
            return None
