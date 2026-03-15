#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

Extra functions (dialogs) to modify airfoil  

"""

import numpy as np

from PyQt6.QtCore               import Qt
from PyQt6.QtWidgets            import QWidget, QLayout, QDialogButtonBox, QPushButton, QDialogButtonBox

from ..base.widgets             import * 
from ..base.panels              import Dialog

from ..model.airfoil            import Airfoil, Flap_Setter
from ..model.airfoil_geometry   import Geometry, Geometry_Splined, Panelling_Spline
from ..model.case               import Match_Targets

from .ae_widgets                import Airfoil_Select_Open_Widget

from ..app_model                import App_Model
from ..match_runner             import Matcher_Base, Match_Result

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class Blend_Airfoil_Dialog (Dialog):
    """ Dialog to two airfoils into a new one"""

    _width  = 560
    _height = 180

    name = "Blend Airfoil with ..."

    sig_blend_changed      = pyqtSignal ()
    sig_airfoil_2_changed  = pyqtSignal (object)    # either airfoil or None


    def __init__ (self, parent : QWidget, 
                  airfoil  : Airfoil, 
                  airfoil_org : Airfoil,                # airfoil which will be blended...
                  **kwargs): 

        self._airfoil     = airfoil 
        self._airfoil_org = airfoil_org
        self._airfoil2    = None
        self._airfoil2_copy = None
        
        self._blendBy  = 0.5                            # initial blend value 

        # init layout etc 
        super().__init__ (parent=parent, **kwargs)


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0 
        # SpaceR (l, r, stretch=0, height=5) 
        # r += 1
        Label  (l,r,1, colSpan=5, get="Select airfoil to blend with and adjust blending value")
        r += 1
        SpaceR (l, r, stretch=0, height=5) 
        r += 1 
        Label  (l,r,1, get="Airfoil")
        Label  (l,r,3, get="Blended with")
        Label  (l,r,6, get="Airfoil 2")
        r += 1 
        Field  (l,r,1, get=self._airfoil_org.fileName, width = 130)
        SpaceC (l,2, width=10, stretch=0)
        Slider (l,r,3, width=110, lim=(0,1), get=lambda: self.blendBy,
                       set=self._set_blendBy, hide=lambda: self._airfoil2 is None)
        FieldF (l,r,4, width=60,  lim=(0, 100),get=lambda: self.blendBy, step=1, unit="%", dec=0,
                       set=self._set_blendBy, hide=lambda: self.airfoil2 is None)
        SpaceC (l,5, width=10, stretch=0)
        Airfoil_Select_Open_Widget (l,r,6, withOpen=True, signal=True, width=180, widthOpen=80,
                                    get=lambda: self.airfoil2, set=self._set_airfoil2,
                                    addEmpty=True,                                  # do not show first airfoil in directory
                                    initialDir=self._airfoil_org)

        SpaceC (l,7, width=5)
        r += 1
        SpaceR (l, r) 

        return l

    @property
    def blendBy (self) -> float:
        """ blend value"""
        return self._blendBy
    
    def _set_blendBy (self, aVal : float):
        """ set new value - do Blend - signal change"""
        self._blendBy = aVal
        self.refresh()

        # Blend with new blend value - use copy as airfoil2 could be normalized
        if self._airfoil2_copy is not None: 
            self._airfoil.geo.blend(self._airfoil_org.geo, self._airfoil2_copy.geo, 
                                     self._blendBy, moving=True)
            self.sig_blend_changed.emit()


    @property
    def airfoil2 (self) -> Airfoil:
        """ airfoil to blend with """
        return self._airfoil2
    
    def _set_airfoil2 (self, aAirfoil : Airfoil = None):
        """ set new 2nd airfoil - do blend - signal change"""
        self._airfoil2 = aAirfoil
        self.refresh()
        self.sig_airfoil_2_changed.emit (aAirfoil)

        # first blend with new airfoil - use copy as airfoil2 could be normalized

        self._airfoil2_copy = aAirfoil.asCopy() if aAirfoil is not None else None

        if aAirfoil is not None: 
            self._airfoil.geo.blend(self._airfoil_org.geo, self._airfoil2_copy.geo, 
                                     self._blendBy, moving=True)
            self.sig_blend_changed.emit()


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.rejected.connect(self.close)

        return buttonBox 


class Repanel_Airfoil_Dialog (Dialog):
    """ Dialog to repanel an airfoil"""

    _width  = 480
    _height = 240

    name = "Repanel Airfoil"


    def __init__ (self, parent : QWidget, app_model : App_Model, **kwargs): 


        self._app_model = app_model
        self._has_been_repaneled = False

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
        SpaceR (l, r, stretch=0, height=5) 
        r += 1
        Label  (l,r,0, colSpan=5, get="Adjust No of Panels and the extra density at leading and trailing edge")
        r += 1
        SpaceR (l, r, stretch=0, height=10) 
        r += 1 
        Label  (l,r,1, get="Panels", align=Qt.AlignmentFlag.AlignRight)
        FieldI (l,r,2, width=60, step=10, lim=(40, 400),
                        obj=self.geo.panelling, prop=Panelling_Spline.nPanels,
                        style=self._le_bunch_style)
        r += 1 
        Slider (l,r,1, colSpan=3, width=150, align=Qt.AlignmentFlag.AlignHCenter,
                        lim=(40, 400), dec=0, # step=10,
                        obj=self.geo.panelling, prop=Panelling_Spline.nPanels)
        # r += 1
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
        r += 1
        SpaceR (l, r, height=5) 

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
    def _on_widget_changed (self):
        """ slot a input field changed - repanel and refresh"""

        self.geo._repanel (based_on_org=True)              # repanel based on original x,y 
        self.refresh()
        self._app_model.notify_airfoil_geo_paneling (True)

        self._has_been_repaneled = True                      # for change detection 


    def close(self):
        """ close or x-Button pressed"""

        if self._has_been_repaneled:
            # finalize modifications
            self.geo.repanel (just_finalize=True)
            self._app_model.notify_airfoil_geo_paneling (False)     # switch off panel mode in diagram
            self._app_model.notify_airfoil_changed ()

        return super().close()


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.rejected.connect(self.close)

        return buttonBox 



class Flap_Airfoil_Dialog (Dialog):
    """ Dialog to set flap of airfoil"""

    _width  = 320
    _height = 200

    name = "Set Flap"

    sig_new_flap_settings    = pyqtSignal (bool)


    def __init__ (self, parent : QWidget, app_model : App_Model, **kwargs): 

        self._app_model = app_model
        self._has_been_flapped = False

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
        return self._has_been_flapped and self.flap_setter.flap_angle != 0.0  


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
    def _on_widget_changed (self):
        """ slot a input field changed - repanel and refresh"""

        self.refresh()
        self.flap_setter.set_flap()

        self._has_been_flapped = True                           # for change detection 
        self.app_model.notify_airfoil_flap_set (True)


    def close(self):
        """ close or x-Button pressed"""

        if self.has_been_flapped:
            # finalize modifications
            self.airfoil.do_flap ()                             # modify airfoil geometry
            self.app_model.notify_airfoil_flap_set (False)      # switch off flap mode in diagram
            self.app_model.notify_airfoil_changed()

        return super().close()


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.rejected.connect(self.close)
        return buttonBox 



class TE_Gap_Dialog (Dialog):
    """ Dialog to set TE gap of airfoil"""

    _width  = 320
    _height = 150

    name = "Set Trailing Edge Gap"

    def __init__ (self, parent : QWidget, app_model : App_Model, **kwargs): 

        self._app_model = app_model

        self._xBlend = app_model.airfoil.geo.TE_GAP_XBLEND           # start with initial value
        self._te_gap = app_model.airfoil.geo.te_gap
        self._has_been_set = False

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


    @property
    def has_been_set (self) -> bool:
        """ True if TE gap was set in this dialog """
        return self._has_been_set 


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
        r += 1
        SpaceR  (l, r, stretch=3) 

        l.setColumnMinimumWidth (0,90)
        l.setColumnMinimumWidth (2,10)
        l.setColumnMinimumWidth (3,50)
        l.setColumnStretch (5,2)   

        return l


    def close(self):
        """ close or x-Button pressed"""

        if self.has_been_set:
            # finalize modifications
            self.airfoil.geo.set_te_gap (self.te_gap, xBlend=self.xBlend)
            self.app_model.notify_airfoil_geo_te_gap (None)   # switch off TE gap mode in diagram
            self.app_model.notify_airfoil_changed ()

        return super().close()


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.rejected.connect(self.close)

        return buttonBox 



class LE_Radius_Dialog (Dialog):
    """ Dialog to set LE Radius of airfoil"""

    _width  = 320
    _height = 180

    name = "Set Leading Edge Radius"


    def __init__ (self, parent : QWidget, app_model : App_Model, **kwargs): 

        self._app_model = app_model

        self._xBlend = app_model.airfoil.geo.LE_RADIUS_XBLEND           # start with initial value
        self._le_radius = app_model.airfoil.geo.le_radius
        self._has_been_set = False

        super().__init__ (parent, **kwargs)

        # switch on TE gap mode in diagram
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
        self._has_been_set = True
        self.refresh()

    @property
    def le_curvature (self) -> float:
        """ LE curvature """
        return 1 / self.le_radius if self.le_radius != 0 else 0.0
    
    def set_le_curvature (self, aVal: float):
        if aVal != 0.0:
            self.set_le_radius (1 / aVal)

    @property
    def has_been_set (self) -> bool:
        """ True if TE gap was set in this dialog """
        return self._has_been_set 


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
        r += 1
        SpaceR  (l, r, stretch=3) 

        l.setColumnMinimumWidth (0,90)
        l.setColumnMinimumWidth (2,10)
        l.setColumnMinimumWidth (3,50)
        l.setColumnStretch (5,2)   

        return l


    def close(self):
        """ close or x-Button pressed"""

        if self.has_been_set:
            # finalize modifications
            self.airfoil.geo.set_le_radius (self.le_radius, xBlend=self.xBlend)
            self.app_model.notify_airfoil_geo_le_radius (None)   # switch off LE radius mode in diagram
            self.app_model.notify_airfoil_changed ()

        return super().close()


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.rejected.connect(self.close)

        return buttonBox 



class Matcher_Run_Info (Dialog):
    """ Little Info dialog (with stop button) show information durig match run"""

    _width  = 230
    _height = 230

    name = "Match Curve"

    def __init__ (self, parent : QWidget, 
                  matcher : Matcher_Base, 
                  **kwargs): 

        self._result : Match_Result | None = None  # Current match result

        self._ncp       = 0                     
        self._ipass     = 1
        self._nevals    = 0

        # connect to matcher siganls to get updates during optimization

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
        self.set_background_color (color='magenta', alpha=0.2)        

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
        # Label  (l,r,1, colSpan=2, height=30, fontSize=size.HEADER_SMALL,
        #         get=lambda: f"{self._ncp} Ctrl Points")
        r += 1
        SpaceR (l, r, stretch=0, height=10) 
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
        SpaceR (l, r) 

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
        self._ncp     = result.ncp
        self._nevals  = nevals
        self._result  = result  # Store the entire result object
        self.refresh ()


    def _on_pass_start (self, ipass, ncp):
        """ slot for pass start - could be new ncp or new weighting """

        self._ipass = ipass
        self._ncp = ncp
        self.refresh()

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

