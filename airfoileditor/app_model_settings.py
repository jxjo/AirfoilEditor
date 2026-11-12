#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""

Persisted settings of the app model

- where they live: the app settings file or the individual settings file of an airfoil
- what is stored: paneling, reference airfoils, polar definitions
- how it is read from and written to a settings dict

The functions are stateless and know nothing about the App_Model: they take and return
plain data or model objects. Applying the values to the model stays with the App_Model.

"""

import os
from typing                  import NamedTuple, Iterable

from .base.common_utils      import Parameters
from .base.app_utils         import Settings

from .model.airfoil          import Airfoil
from .model.geometry_spline  import Paneling_Spline
from .model.geometry_bezier  import Paneling_Bezier
from .model.geometry_bspline import Paneling_BSpline
from .model.geometry_cst     import Paneling_CST
from .model.polar_set        import Polar_Definition

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# -----------------------------------------------------------------------------


class Airfoil_Settings (Parameters):
    """
    Settings for an airfoil which are stored with the airfoil
    in an individual settings file with airfoil fileName + '.ae'
    """

    FILE_EXTENSION = ".ae"

    @classmethod
    def settings_pathFileName (cls, airfoil : Airfoil) -> str:
        """ get settings file pathFileName for airfoil """
        return os.path.join (airfoil.pathName_abs, airfoil.fileName_stem + cls.FILE_EXTENSION)


    @classmethod
    def exists_for (cls, airfoil : Airfoil) -> bool:
        """ check if settings file exists for airfoil """

        if isinstance (airfoil, Airfoil):
            return os.path.isfile (cls.settings_pathFileName(airfoil))
        return False


    def __init__ (self, airfoil : Airfoil):

        if not isinstance (airfoil, Airfoil):
            raise ValueError (f"Airfoil_Settings: airfoil must be of type Airfoil")

        self._airfoil = airfoil

        super().__init__(self.settings_pathFileName (airfoil))


    def __repr__ (self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__} for Airfoil '{self._airfoil}'>"



# -----------------------------------------------------------------------------


class Reference_Entry (NamedTuple):
    """ a reference airfoil as stored in the settings """

    path  : str                                 # pathFileName of the airfoil
    show  : bool = True                         # airfoil is visible
    scale : float | None = None                 # optional Reynolds scale factor



# -----------------------------------------------------------------------------


def settings_for (airfoil : Airfoil | None) -> Parameters:
    """
    The individual settings of airfoil if there are any - otherwise the app settings.
    The settings are read freshly from file.
    """

    if Airfoil_Settings.exists_for (airfoil):
        return Airfoil_Settings (airfoil)
    return Settings()


def read_paneling (s : dict):
    """ set the paneling parameters, which are class variables, from settings s """

    Paneling_Spline.from_dict(s)
    Paneling_Bezier.from_dict(s)
    Paneling_BSpline.from_dict(s)
    Paneling_CST.from_dict(s)


def write_paneling (s : dict):
    """ write the paneling parameters into settings s - values equal to default are removed from s """

    Paneling_Spline.to_dict(s)
    Paneling_Bezier.to_dict(s)
    Paneling_BSpline.to_dict(s)
    Paneling_CST.to_dict(s)


def read_polar_definitions (s : dict) -> list[Polar_Definition]:
    """ polar definitions stored in settings s, sorted by Reynolds number """

    polar_defs = [Polar_Definition(dataDict=def_dict) for def_dict in s.get('polar_definitions', [])]
    polar_defs.sort (key=lambda aDef : aDef.re)
    return polar_defs


def write_polar_definitions (s : Parameters, polar_defs : Iterable[Polar_Definition]):
    """ write polar_defs into settings s """

    s.set ('polar_definitions', [polar_def._as_dict() for polar_def in polar_defs])


def read_reference_entries (s : dict) -> list[Reference_Entry]:
    """
    The reference airfoils stored in settings s - entries without a path are skipped.
    An entry is either a pathFileName (older versions) or a dict with path, show and scale.
    """

    entries = []

    for ref_entry in s.get('reference_airfoils', []):

        if isinstance (ref_entry, str):                                 # compatible with older version
            entry = Reference_Entry (ref_entry)
        elif isinstance (ref_entry, dict) and ref_entry.get ("path", None) is not None:
            entry = Reference_Entry (ref_entry["path"], ref_entry.get ("show", True), ref_entry.get ("scale", None))
        else:
            continue

        entries.append (entry)

    return entries


def load_reference_airfoil (entry : Reference_Entry) -> Airfoil:
    """ load the reference airfoil of entry with its show and scale properties - raises an exception if that fails """

    airfoil = Airfoil.onFileType (pathFileName=entry.path)
    airfoil.load ()
    airfoil.set_property ("show", entry.show)
    airfoil.set_scale_factor (entry.scale)

    return airfoil


def write_reference_airfoils (s : Parameters, airfoils : Iterable[Airfoil]):
    """ write the reference airfoils into settings s - default values of show and scale are not stored """

    ref_list = []

    for airfoil in airfoils:
        ref_entry = {}
        ref_entry ["path"]  = airfoil.pathFileName_abs
        if not airfoil.get_property ("show", True):             # avoid default True
            ref_entry ["show"]  = airfoil.get_property ("show", True)
        if airfoil.isScaled:                                    # avoid default 1.0
            ref_entry ["scale"] = airfoil.scale_factor
        ref_list.append (ref_entry)

    s.set ('reference_airfoils', ref_list)
