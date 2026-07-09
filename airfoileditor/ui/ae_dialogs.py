#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

Extra functions (dialogs) to modify airfoil  

"""

import numpy as np

from PyQt6.QtCore               import Qt, QCoreApplication
from PyQt6.QtWidgets            import QWidget, QLayout, QDialogButtonBox, QPushButton, QDialogButtonBox, QFileDialog

from ..base.widgets             import * 
from ..base.panels              import Dialog_Modal, Dialog_Modeless, MessageBox

from ..model.airfoil            import Airfoil, Flap_Setter
from ..model.airfoil_exports    import Export_Airfoil_Dxf
from ..model.geometry           import Geometry
from ..model.geometry_spline    import Geometry_Splined, Panelling_Spline
from ..model.case               import Match_Targets
from ..match_runner             import Match_Result, Matcher

from .ae_widgets                import Airfoil_Select_Open_Widget

from ..app_model                import App_Model

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class Airfoil_Export_DXF_Dialog (Dialog_Modal):
    """Dialog to export the current airfoil to a DXF file."""

    _width = 450

    name = "Export Airfoil as DXF"

    def __init__(self, parent: QWidget, app_model: App_Model, **kwargs):

        self._app_model = app_model
        self._export_btn: QPushButton = None
        self._cancel_btn: QPushButton = None
        super().__init__(parent=parent, **kwargs)

        self._cancel_btn.clicked.connect(self.close)
        self._export_btn.clicked.connect(self._export_dxf)


    @property
    def app_model(self) -> App_Model:
        return self._app_model


    @property
    def airfoil(self) -> Airfoil:
        return self.app_model.airfoil


    @property
    def exporter_airfoil(self) -> Export_Airfoil_Dxf:
        return self.app_model.exporter_airfoil


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0
        SpaceR   (l, r, stretch=0, height=5)
        r += 1
        Field    (l, r, 0, lab="File Name", width=250, get=lambda: self.exporter_airfoil.export_fileName)
        r += 1
        Field    (l, r, 0, width=250, lab="To Directory", get=lambda: self.exporter_airfoil.export_dir)
        ToolButton(l, r,2, icon=Icon.OPEN, set=self._select_directory)
        r += 1
        SpaceR   (l, r, stretch=0, height=15)

        r += 1
        CheckBox (l, r, 0, text="Set chord length",
                  obj=self.exporter_airfoil, prop=Export_Airfoil_Dxf.adapt_chord)
        FieldF   (l, r, 1, width=90, unit="mm", dec=1, lim=(0.1, 10000), step=1.0,
                  obj=self.exporter_airfoil, prop=Export_Airfoil_Dxf.chord_mm,
                  disable=lambda: not self.exporter_airfoil.adapt_chord)
        r += 1
        CheckBox (l, r, 0, text="Set TE gap",
                  obj=self.exporter_airfoil, prop=Export_Airfoil_Dxf.adapt_te_gap)
        FieldF   (l, r, 1, width=90,  unit="mm", dec=1, lim=(0.0, 10), step=0.1,
                  obj=self.exporter_airfoil, prop=Export_Airfoil_Dxf.te_gap_mm,
                  disable=lambda: not self.exporter_airfoil.adapt_te_gap)
        r += 1
        SpaceR(l, r, stretch=1, height=15)
        r += 1
        CheckBox (l, r, 0, colSpan=4, text=self._just_as_cubic_message(),
                  obj=self.exporter_airfoil, prop=Export_Airfoil_Dxf.always_as_cubic_fit,
                  hide=lambda: not self._just_as_cubic_message(),
                  toolTip="Export as cubic spline fit if your CAD software" +
                          " does not support to import uniform B-Splines")

        l.setColumnMinimumWidth(0, 95)
        l.setColumnStretch(4, 5)
        return l


    def _select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, caption="Select Export Directory",
                                                     directory=self.exporter_airfoil.export_dir_abs)
        if directory:
            self.exporter_airfoil.set_export_dir(directory)
            self.refresh()


    def _just_as_cubic_message (self) -> str:
        if self.exporter_airfoil.airfoil.isBezierBased or self.exporter_airfoil.airfoil.isBSplineBased:
            curve = "Bezier" if self.exporter_airfoil.airfoil.isBezierBased else "B-Spline"
            return f"Export {curve} based airfoil as cubic spline fit not as uniform B-Spline"
        else:
            return None


    def _export_dxf(self, *_):
        try:
            pathFileName = self.exporter_airfoil.do_it()
        except Exception as e:
            MessageBox.error(self, "Export Airfoil as DXF", f"DXF export failed.\n\n{e}", min_height=80)
            return

        self.close()
        self._toast_message(f"Airfoil exported to {pathFileName}")


    @override
    def _on_widget_changed(self):
        self.refresh()


    @override
    def _button_box(self):
        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)

        self._cancel_btn = buttonBox.button(QDialogButtonBox.StandardButton.Cancel)
        self._export_btn = QPushButton("&Export", parent=self)
        self._export_btn.setFixedWidth(80)
        buttonBox.addButton(self._export_btn, QDialogButtonBox.ButtonRole.ActionRole)

        return buttonBox


class Blend_Airfoil_Dialog (Dialog_Modeless):
    """ Dialog to blend two airfoils into a new one"""

    _width  = 560

    name = "Blend Airfoil with ..."


    def __init__ (self, parent : QWidget, 
                  app_model : App_Model,
                  **kwargs): 

        self._app_model = app_model

        self._airfoil2    = None
        self._airfoil2_copy = None
        
        self._blendBy  = 0.5                            # initial blend value 

        # init layout etc 
        super().__init__ (parent=parent, **kwargs)


    @property
    def app_model (self) -> App_Model:
        return self._app_model
    
    @property
    def airfoil (self) -> Airfoil:
        return self.app_model.airfoil
    
    @property
    def airfoil_seed (self) -> Airfoil:
        """ original airfoil seed for blending """
        return self.app_model.airfoil_seed

    @property
    def blendBy (self) -> float:
        """ blend value"""
        return self._blendBy
    
    def set_blendBy (self, aVal : float):
        """ set new value - do Blend - signal change"""
        self._blendBy = aVal
        self.refresh()

        # Blend with new blend value - use copy as airfoil2 could be normalized
        if self._airfoil2_copy is not None: 
            self.airfoil.geo.blend(self.airfoil_seed.geo, self._airfoil2_copy.geo, 
                                     self._blendBy, moving=True)
            self.app_model.notify_airfoil_geo_changed()


    @property
    def airfoil_2 (self) -> Airfoil:
        """ airfoil to blend with """
        return self.app_model.airfoil_2

    def set_airfoil_2 (self, aAirfoil : Airfoil = None):
        """ set new 2nd airfoil - do blend - signal change"""

        self.app_model.set_airfoil_2 (aAirfoil)
        self.refresh()

        # first blend with new airfoil - use copy as airfoil2 could be normalized

        self._airfoil2_copy = aAirfoil.asCopy() if aAirfoil is not None else None

        if aAirfoil is not None: 
            self.airfoil.geo.blend(self.airfoil_seed.geo, self._airfoil2_copy.geo, 
                                     self._blendBy, moving=True)
            self.app_model.notify_airfoil_geo_changed()


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0 
        Label  (l,r,1, colSpan=5, get="Select airfoil to blend with and adjust blending value")
        r += 1
        SpaceR (l, r, stretch=0, height=5) 
        r += 1 
        Label  (l,r,1, get="Airfoil")
        Label  (l,r,3, get="Blended with")
        Label  (l,r,6, get="Airfoil 2")
        r += 1 
        Field  (l,r,1, get=self.airfoil_seed.fileName, width = 130)
        SpaceC (l,2, width=10, stretch=0)
        Slider (l,r,3, width=110, lim=(0,1), get=lambda: self.blendBy,
                       set=self.set_blendBy, hide=lambda: self.airfoil_2 is None)
        FieldF (l,r,4, width=60,  lim=(0, 100),get=lambda: self.blendBy, step=1, unit="%", dec=0,
                       set=self.set_blendBy, hide=lambda: self.airfoil_2 is None)
        SpaceC (l,5, width=10, stretch=0)
        Airfoil_Select_Open_Widget (l,r,6, withOpen=True, signal=True, width=180, widthOpen=80,
                                    get=lambda: self.airfoil_2, set=self.set_airfoil_2,
                                    addEmpty=True,                                  # do not show first airfoil in directory
                                    initialDir=self.airfoil_seed)
        SpaceC (l,7, width=5)
        r += 1
        SpaceR (l, r) 

        return l


    def done(self, result: int) -> None:
        """ close or x-Button pressed"""

        if self._changes:
            # do final blend with high quality (splined) 
            self.airfoil.geo.blend (self.airfoil_seed.geo, self.airfoil_2.geo, self.blendBy) 
            self.app_model.notify_airfoil_changed()

        self.app_model.set_airfoil_2 (None)

        return super().done(result)




class Repanel_Airfoil_Dialog (Dialog_Modeless):
    """ Dialog to repanel an airfoil"""

    _width  = 440

    name = "Repanel Airfoil"


    def __init__ (self, parent : QWidget, app_model : App_Model, **kwargs): 


        self._app_model = app_model

        # init layout etc 
        super().__init__ (parent, **kwargs)

        # do a first repanel with the actual parameters 
        self.geo._repanel (based_on_org=True)              # repanel based on original x,y

        # switch on show panels mode in diagram
        self._app_model.notify_airfoil_geo_paneling (True)


    @property
    def geo (self) -> Geometry_Splined:
        return self._app_model.airfoil.geo
    

    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0 
        Label  (l,r,0, colSpan=5, style=style.COMMENT,
            get="Adjust number of panels and density near the leading and trailing edges")
        r += 1
        SpaceR (l, r, stretch=0, height=5) 
        r += 1 
        Label  (l,r,1, get="Panels", align=Qt.AlignmentFlag.AlignRight)
        FieldI (l,r,2, width=60, step=10, lim=(40, 400),
                        obj=self.geo.panelling, prop=Panelling_Spline.nPanels,
                        style=self._le_bunch_style)
        r += 1 
        Slider (l,r,1, colSpan=3, width=150, align=Qt.AlignmentFlag.AlignHCenter,
                        lim=(40, 400), dec=0, # step=10,
                        obj=self.geo.panelling, prop=Panelling_Spline.nPanels)
        Label  (l,r,0, get="LE bunch")
        Label  (l,r,4, get="TE bunch")

        r += 1
        FieldF (l,r,0, width=60, step=0.02, lim=(0, 1),
                        obj=self.geo.panelling, prop=Panelling_Spline.le_bunch,
                        style=self._le_bunch_style)
        Slider (l,r,1, width=100, lim=(0, 1),
                        obj=self.geo.panelling, prop=Panelling_Spline.le_bunch)

        Slider (l,r,3, width=100, lim=(0, 1),
                        obj=self.geo.panelling, prop=Panelling_Spline.te_bunch)
        FieldF (l,r,4, width=60, step=0.02, lim=(0, 1),
                        obj=self.geo.panelling, prop=Panelling_Spline.te_bunch)
        r += 1
        Label  (l,r,0, colSpan=5, get=self._le_bunch_message, style=style.COMMENT)        
        SpaceC (l,5, width=5)

        return l


    def _le_bunch_message (self): 
        angle = self.geo.panelAngle_le
        if angle > Geometry.LE_PANEL_ANGLE_TOO_BLUNT: 
            text = f"Panel angle at LE of {angle:.1f}° is too blunt. Decrease panels or LE bunch" 
        elif angle < Geometry.PANEL_ANGLE_TOO_SHARP: 
            text = f"Panel angle at LE of {angle:.1f}° is too sharp. Increase panels or LE bunch"
        else:
            text = ""
        return text 
    

    def _le_bunch_style (self): 
        angle = self.geo.panelAngle_le
        if angle > Geometry.LE_PANEL_ANGLE_TOO_BLUNT or angle < Geometry.PANEL_ANGLE_TOO_SHARP: 
            return style.WARNING
        else: 
            return style.NORMAL


    @override
    def _on_widget_changed (self, widget):
        """ slot a input field changed - repanel and refresh"""

        super()._on_widget_changed (widget)

        self.geo._repanel (based_on_org=True)              # repanel based on original x,y 
        self.refresh()
        self._app_model.notify_airfoil_geo_paneling (True)


    def done(self, result: int) -> None:
        """ close or x-Button pressed"""

        if self._changes:
            # finalize modifications
            self.geo.repanel (just_finalize=True)
            self._app_model.notify_airfoil_changed ()

        self._app_model.notify_airfoil_geo_paneling (False)     # switch off panel mode in diagram

        return super().done(result)




class Flap_Airfoil_Dialog (Dialog_Modeless):
    """ Dialog to set flap of airfoil"""

    _width  = 320

    name = "Set Flap"

    sig_new_flap_settings    = pyqtSignal (bool)


    def __init__ (self, parent : QWidget, app_model : App_Model, **kwargs): 

        self._app_model = app_model

        super().__init__ (parent, **kwargs)

        # switch on TE gap mode in diagram
        self.app_model.notify_airfoil_flap_set (True)


    @property
    def app_model (self) -> App_Model:
        return self._app_model
    
    @property
    def airfoil (self) -> Airfoil:
        return self.app_model.airfoil

    @property
    def flap_setter (self) -> Flap_Setter:
        return self.airfoil.flap_setter

    @property
    def has_been_flapped (self) -> bool:
        """ True if flap was set in this dialog """
        return self._changes and self.flap_setter.flap_angle != 0.0  


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r,c = 0,0 
        SpaceR (l, r, stretch=0, height=5) 
        r += 1
        FieldF  (l,r,c, lab="Hinge x", width=60, step=1, lim=(1, 98), dec=1, unit="%",
                        obj=self.flap_setter, prop=Flap_Setter.x_flap)
        Slider  (l,r,c+3, colSpan=2, width=120,  
                        lim=(0.0, 1), dec=2,  
                        obj=self.flap_setter, prop=Flap_Setter.x_flap)
        r += 1
        FieldF  (l,r,c, lab="Hinge y", width=60, step=1, lim=(0, 100), dec=0, unit='%',
                        obj=self.flap_setter, prop=Flap_Setter.y_flap)
        Label   (l,r,c+3, get="of thickness", style=style.COMMENT)
        r += 1
        SpaceR  (l, r, stretch=1, height=10) 
        r += 1
        FieldF  (l,r,c, lab="Angle", width=60, step=0.1, lim=(-20,20), dec=1, unit='°', 
                        obj=self.flap_setter, prop=Flap_Setter.flap_angle)
        Slider  (l,r,c+3, colSpan=2, width=120,  
                        lim=(-20,20), dec=2,  
                        obj=self.flap_setter, prop=Flap_Setter.flap_angle)
        r += 1
        SpaceR  (l, r, stretch=3) 

        l.setColumnMinimumWidth (0,70)
        l.setColumnMinimumWidth (2,10)
        l.setColumnMinimumWidth (3,50)
        l.setColumnStretch (5,2)   
        return l


    @override
    def _on_widget_changed (self, widget):
        """ slot a input field changed - repanel and refresh"""

        super()._on_widget_changed (widget)

        self.refresh()
        self.flap_setter.set_flap()

        self.app_model.notify_airfoil_flap_set (True)


    def done(self, result: int) -> None:
        """ close or x-Button pressed"""

        if self.has_been_flapped:
            # finalize modifications
            self.airfoil.do_flap ()                             # modify airfoil geometry
            self.app_model.notify_airfoil_changed()

        self.app_model.notify_airfoil_flap_set (False)      # switch off flap mode in diagram

        return super().done(result)



class TE_Gap_Dialog (Dialog_Modeless):
    """ Dialog to set TE gap of airfoil"""

    _width  = 320
    
    name = "Set Trailing Edge Gap"

    def __init__ (self, parent : QWidget, app_model : App_Model, **kwargs): 

        self._app_model = app_model

        self._xBlend = app_model.airfoil.geo.TE_GAP_XBLEND           # start with initial value
        self._te_gap = app_model.airfoil.geo.te_gap

        super().__init__ (parent, **kwargs)

        # switch on TE gap mode in diagram
        self.app_model.notify_airfoil_geo_te_gap (self.xBlend)


    @property
    def app_model (self) -> App_Model:
        return self._app_model
    
    @property
    def airfoil (self) -> Airfoil:
        return self.app_model.airfoil


    @property
    def xBlend (self) -> float:
        """ blending range x/c from TE"""
        return self._xBlend
    
    def set_xBlend (self, aVal: float):

        self._xBlend = aVal
        self.airfoil.geo.set_te_gap (self.te_gap, xBlend=aVal, moving=True)
        self.app_model.notify_airfoil_geo_te_gap (self.xBlend)
        self.refresh()


    @property
    def te_gap (self) -> float:
        """  TE gap as y/c """
        return self._te_gap
    
    def set_te_gap (self, aVal: float):

        self._te_gap = aVal
        self.airfoil.geo.set_te_gap (aVal, xBlend=self.xBlend, moving=True)
        self.app_model.notify_airfoil_geo_te_gap (self.xBlend)
        self._has_been_set = True
        self.refresh()


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r,c = 0,0 
        SpaceR (l, r, stretch=0, height=5) 
        r += 1
        FieldF  (l,r,c, lab="Blend from TE", width=75, step=1, lim=(10, 100), dec=1, unit="%",
                        obj=self, prop=TE_Gap_Dialog.xBlend)
        Slider  (l,r,c+3, colSpan=2, width=100,  
                        lim=(0.1, 1.0), dec=2,  
                        obj=self, prop=TE_Gap_Dialog.xBlend)
        r += 1
        SpaceR  (l, r, stretch=1, height=10) 
        r += 1
        FieldF  (l,r,c, lab="TE gap", width=75, unit="%", step=0.1, lim=(0.0, 10),
                        obj=self, prop=TE_Gap_Dialog.te_gap)

        Slider  (l,r,c+3, colSpan=2, width=100, lim=(0.0, 0.1), step=0.001, dec=3, 
                        obj=self, prop=TE_Gap_Dialog.te_gap)

        l.setColumnMinimumWidth (0,90)
        l.setColumnMinimumWidth (2,10)
        l.setColumnMinimumWidth (3,50)
        l.setColumnStretch (5,2)   

        return l

    @override
    def done(self, result: int) -> None:
        """ close or x-Button pressed"""

        if self._changes:
            # finalize modifications
            self.airfoil.geo.set_te_gap (self.te_gap, xBlend=self.xBlend)
            self.app_model.notify_airfoil_changed ()

        # switch off TE gap mode in diagram
        self.app_model.notify_airfoil_geo_te_gap (None)  

        return super().done(result)



class Matcher_Run_Info (Dialog_Modal):
    """ Little Info dialog (with stop button) show information during match run"""

    _width  = 230

    name = "Match Curve"

    def __init__ (self, parent : QWidget, 
                  matcher : Matcher, 
                  **kwargs): 

        self._result : Match_Result | None = None  # Current match result

        self._ncp       = 0                     
        self._ipass     = 1
        self._nevals    = 0
        self._global_search = False

        # connect to matcher signals to get updates during optimization

        matcher.finished.connect (self._on_finished)
        matcher.sig_pass_start.connect (self._on_pass_start)
        matcher.sig_new_results.connect (self._on_results)

        self._matcher = matcher

        # init layout etc 

        self._stop_btn : QPushButton = None

        super().__init__ (parent, title=self._titletext(),
                          flags = Qt.WindowType.Dialog  
                                | Qt.WindowType.CustomizeWindowHint        # take full control of title bar
                                | Qt.WindowType.WindowTitleHint,           # show title text
                           **kwargs)

        self._stop_btn.clicked.connect (self._cancel_thread)    # after super init to get button instance

        set_background (self._panel, color='magenta', alpha=0.2)

        # start matcher after dialog is shown 

        QTimer.singleShot(0, self._matcher.start)     


    def _titletext (self) -> str: 
        """ headertext depending on state """
        return f"Match {self._matcher._side.name} side"

    @property
    def targets (self) -> Match_Targets:
        return self._matcher._targets


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0
        Label  (l,r,0, colSpan=3, height=30, fontSize=size.HEADER_SMALL,
                get=lambda: f"Pass {self._ipass} with {self._ncp} Control Points")
        r += 1
        Label  (l,r,0, colSpan=2,get=lambda: f"Initial global search", height=15,
                hide=lambda: not self._global_search, style=style.COMMENT)
        r += 1
        SpaceR (l, r, stretch=3, height=5) 
        r += 1
        FieldI (l,r,0, width=60, lab="Evaluations", get=lambda: self._nevals), 
        r += 1
        FieldF (l,r,0, width=60, dec=4, lab="Deviation RMS",unit='%', 
                    get=lambda: self._result.rms if self._result else 0.0, 
                    style=lambda: self._result.style_deviation if self._result else style.NORMAL)
        r += 1
        FieldF (l,r,0, width=60, dec=0, lab="LE curvature",
                    get=lambda: self._result.le_curvature if self._result else 0.0,
                    style=lambda: self._result.style_curv_le if self._result else style.NORMAL)
        r += 1
        FieldF (l,r,0, width=60, dec=1, lab="TE curvature",
                    get=lambda: self._result.te_curvature if self._result else 0.0,
                    style=lambda: self._result.style_curv_te if self._result else style.NORMAL)
        r += 1
        SpaceR (l, r, stretch=0, height=10) 

        l.setColumnMinimumWidth (0,100)
        l.setColumnStretch (2,1)
        return l


    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        self._stop_btn = QPushButton ("Stop", parent=self)
        self._stop_btn.setFixedWidth (80)

        buttonBox = QDialogButtonBox()
        buttonBox.addButton (self._stop_btn, QDialogButtonBox.ButtonRole.RejectRole)

        return buttonBox 

    # --------------------

    def _on_results (self, ipass, nevals, result : Match_Result):
        """ slot to receive new results from running thread"""

        self._ipass   = ipass
        self._nevals  = nevals
        self._result  = result  # Store the entire result object

        self.refresh ()
        QCoreApplication.processEvents()


    def _on_pass_start (self, ipass : int, ncp: int, global_search: bool):
        """ slot for pass start - could be new ncp or new weighting """

        self._ipass = ipass
        self._ncp = ncp
        self._global_search = global_search
        self._result = None  # Clear previous results at the start of a new pass
        self._nevals = 0

        self.refresh()
        QCoreApplication.processEvents()


    def _on_finished(self):
        """ slot for thread finished """

        self.close()


    def _cancel_thread (self):
        """ request thread termination"""
    
        self._matcher.requestInterruption()


    @override
    def reject(self): 
        """ close or x-Button pressed"""

        # stop running matcher if x-Button pressed
        if self._matcher.isRunning():
            self._matcher.requestInterruption()
        
        # normal close 
        super().reject()



class LE_Radius_Dialog (Dialog_Modeless):
    """ Dialog to set LE Radius of airfoil"""

    _width  = 320

    name = "Set Leading Edge Radius"


    def __init__ (self, parent : QWidget, app_model : App_Model, **kwargs): 

        self._app_model = app_model

        self._xBlend    = app_model.airfoil.geo.LE_RADIUS_XBLEND           # start with initial value
        self._le_radius = app_model.airfoil.geo.le_radius

        super().__init__ (parent, **kwargs)

        # switch on LE radius mode in diagram
        self.app_model.notify_airfoil_geo_le_radius (self.xBlend)


    @property
    def app_model (self) -> App_Model:
        return self._app_model
    
    @property
    def airfoil (self) -> Airfoil:
        return self.app_model.airfoil


    @property
    def xBlend (self) -> float:
        """ blending range x/c from LE"""
        return self._xBlend
    
    def set_xBlend (self, aVal: float):

        self._xBlend = aVal
        self.airfoil.geo.set_le_radius (self.le_radius, xBlend=aVal, moving=True)
        self.app_model.notify_airfoil_geo_le_radius (self.xBlend)
        self.refresh()


    @property
    def le_radius (self) -> float:
        """ LE radius as y/c """
        return self._le_radius
    
    def set_le_radius (self, aVal: float):

        self._le_radius = aVal
        self.airfoil.geo.set_le_radius (aVal, xBlend=self.xBlend, moving=True)
        self.app_model.notify_airfoil_geo_le_radius (self.xBlend)
        self.refresh()

    @property
    def le_curvature (self) -> float:
        """ LE curvature """
        return 1 / self.le_radius if self.le_radius != 0 else 0.0
    
    def set_le_curvature (self, aVal: float):
        if aVal != 0.0:
            self.set_le_radius (1 / aVal)


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r,c = 0,0 
        SpaceR (l, r, stretch=0, height=5) 
        r += 1
        FieldF  (l,r,c, lab="Blend from LE", width=75, step=1, lim=(1, 100), dec=1, unit="%",
                        obj=self, prop=LE_Radius_Dialog.xBlend)
        Slider  (l,r,c+3, colSpan=2, width=100,  
                        lim=(0.01, 1.0), dec=2,  
                        obj=self, prop=LE_Radius_Dialog.xBlend)
        r += 1
        SpaceR  (l, r, stretch=1, height=10) 
        r += 1
        FieldF  (l,r,c, lab="LE radius", width=75, unit="%", step=0.1, lim=(0.1, 3),
                        obj=self, prop=LE_Radius_Dialog.le_radius)

        Slider  (l,r,c+3, colSpan=2, width=100, lim=(0.001, 0.03), step=0.001, dec=3, 
                        obj=self, prop=LE_Radius_Dialog.le_radius)
        r += 1
        FieldF  (l,r,c, lab="LE curvature", width=75, dec=0, step=1.0, lim=(10, 1000),
                        obj=self, prop=LE_Radius_Dialog.le_curvature)
        Slider  (l,r,c+3, colSpan=2, width=100, lim=(10, 1000), step=10, dec=0, 
                        obj=self, prop=LE_Radius_Dialog.le_curvature)

        l.setColumnMinimumWidth (0,90)
        l.setColumnMinimumWidth (2,10)
        l.setColumnMinimumWidth (3,50)
        l.setColumnStretch (5,2)   

        return l


    def done(self, result: int) -> None:
        """ close or x-Button pressed"""

        if self._changes:
            # finalize modifications
            self.airfoil.geo.set_le_radius (self.le_radius, xBlend=self.xBlend)
            self.app_model.notify_airfoil_changed ()

        # switch off LE radius mode in diagram
        self.app_model.notify_airfoil_geo_le_radius (None)  

        return super().done(result)
