#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Airfoil Editor 

    Object model overview (a little simplified) 

    App                                         - root frame 
        |-- Panel_Geometry                      - geometry data 
        |-- Panel_Coordinates                   - LE and TE coordinates
                ...                             - ...

        |-- Airfoil_Diagram                     - main airfoil view 
                :
                |-- Airfoil_Diagram_Item        - Pygtgraph Plot item for airfoil contour
                |-- Curvature_Diagram_Item      - Pygtgraph Plot item for airfoil curvature 
                ...                             - ...

        |-- Airfoil                             - airfoil model object 
"""

import os
import sys
import argparse
from pathlib import Path
import logging

from PyQt6.QtCore           import QSize, QMargins
from PyQt6.QtWidgets        import QApplication, QMainWindow, QWidget, QMessageBox, QStackedWidget 
from PyQt6.QtWidgets        import QGridLayout, QVBoxLayout, QHBoxLayout, QStackedLayout

# let python find the other modules in modules relativ to path of self  
sys.path.append(os.path.join(Path(__file__).parent , 'modules'))


from model.airfoil          import Airfoil, usedAs, GEO_SPLINE
from model.airfoil_geometry import Geometry

from base.common_utils      import * 
from base.panels            import Panel, Edit_Panel
from base.widgets           import *
from base.diagram           import * 

from airfoil_widgets        import * 
from airfoil_artists        import *


#-------------------------------------------------------------------------------
# The App   
#-------------------------------------------------------------------------------

# ------ globals -----

AppName    = "Airfoil Editor"
AppVersion = "2.0 beta"

Main : 'App_Main' = None 

def signal_airfoil_changed ():
    """ main airfoil change signal """
    if Main: Main.sig_airfoil_changed.emit()

def signal_airfoil_ref_changed ():
    """ main airfoil change signal """
    if Main: Main.sig_airfoil_ref_changed.emit()


class App_Main (QMainWindow):
    '''
        The AirfoilEditor App

        If parentApp is passed, the AirfoilEditor is called from eg PlanformEditor,
        so it will be modal with a reduced File Menu 
    '''

    name = AppName  

    # Signals 

    sig_airfoil_changed     = pyqtSignal()          # airfoil data changed 
    sig_airfoil_ref_changed = pyqtSignal()          # reference airfoils changed 


    def __init__(self, airfoil_file, parentApp=None):
        super().__init__()

        # called from another App? Switch to modal window
        #
        #   self is not a subclass of ctk to support both modal and root window mode 

        if airfoil_file and (not os.path.isfile (airfoil_file)): 
            QMessageBox.critical (self, self.name , f"\n'{airfoil_file}'\n\n... does not exist. Showing example airfoil.\n")
            airfoil_file = "Root_Example"
        elif airfoil_file is None : 
            QMessageBox.information (self, self.name , f"\n'{airfoil_file}'\n\n... does not exist. Showing example airfoil.\n")
            airfoil_file = "Root_Example"

        self.setMinimumSize(QSize(1300, 700))

        self._airfoil = None                        # current airfoil 
        self._airfoil_sav = None                    # airfoil saved in edit_mode 
        self._airfoil_ref1 = None                   # reference airfoils 
        self._airfoil_ref2 = None       

        self._edit_mode = False                     # edit/view mode of app 
        self._data_panel = None 
        self._file_panel = None

        self.parentApp = parentApp
        self.initial_geometry = None                # window geometry at the ebginning

        self.set_airfoil (create_airfoil_from_path(airfoil_file), silent=True)

        # init main layout of app

        l_main = self._init_layout() 

        container = QWidget()
        container.setLayout (l_main) 
        self.setCentralWidget(container)

        # connect to signals 

        self.sig_airfoil_changed.connect (self._on_airfoil_changed)
        self.sig_airfoil_ref_changed.connect (self._on_airfoil_changed)

        # View mode is default 

        self.set_edit_mode (False) 

    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        text = f""  
        return f"<{type(self).__name__}{text}>"


    def _init_layout (self): 
        """ init main layout with the different panels """

        #  ||               lower                         >||
        #  || file panel ||        edit panel             >||
        #                 | Geometry  | Coordinates | ... >| 

        self._data_panel  = Panel ()
        l_edit = QHBoxLayout()
        l_edit.addWidget (Panel_Geometry    (self, self.airfoil), stretch= 2)
        l_edit.addWidget (Panel_Panels      (self, self.airfoil), stretch= 1)
        l_edit.addWidget (Panel_LE_TE       (self, self.airfoil), stretch= 1)
        l_edit.addWidget (Panel_Bezier      (self, self.airfoil), stretch= 2)
        l_edit.addWidget (Panel_Bezier_Match(self, self.airfoil), stretch= 2)
        
        l_edit.addStretch (2)
        l_edit.setContentsMargins (QMargins(0, 0, 0, 0))
        self._data_panel.setLayout (l_edit)

        self._file_panel  = Panel ()
        l_file = QHBoxLayout()
        l_file.addWidget (Panel_View_Mode        (self, self.airfoil))
        l_file.addWidget (Panel_Edit_Mode   (self, self.airfoil))
        l_file.setContentsMargins (QMargins(0, 0, 0, 0))
        self._file_panel.setLayout (l_file)


        l_lower = QHBoxLayout()
        l_lower.addWidget (self._file_panel)
        l_lower.addWidget (self._data_panel, stretch=2)
        l_lower.setContentsMargins (QMargins(0, 0, 0, 0))
        lower = QWidget ()
        lower.setLayout (l_lower)

        # upper diagram area  

        upper = Diagram_Airfoil (self, self.airfoils)

        # main layout with both 

        lower.setMinimumHeight(180)
        lower.setMaximumHeight(180)

        l_main = QVBoxLayout () 
        l_main.addWidget (upper, stretch=2)
        l_main.addWidget (lower)
        l_main.setContentsMargins (QMargins(5, 5, 5, 5))

        return l_main 

    @property
    def edit_mode (self) -> bool: 
        """ True if self is not in view mode"""
        return self._edit_mode


    def modify_airfoil (self):
        """ modify airfoil - switch to edit mode """
        if self.edit_mode: return 

        # enter edit_mode - save original, create working copy as splined airfoil 
        self._airfoil_sav = self._airfoil
        try:                                            # normal airfoil - allows new geometry
            airfoil  = self._airfoil.asCopy (nameExt=None, geometry=GEO_SPLINE)
        except:                                         # bezier or hh does not allow new geometry
            airfoil  = self._airfoil.asCopy (nameExt=None)
        airfoil.useAsDesign()                           # will have another visualization 
        airfoil.normalize()                     

        self.set_airfoil (airfoil, silent=True)         # set without signal   
        self.set_edit_mode (True)       


    def modify_airfoil_finished (self, ok=False):
        """ modify airfoil finished - switch to view mode """

        if not self.edit_mode: return 

        if ok:
            dlg = Airfoil_Save_Dialog (parent=self, getter=self.airfoil)
            ok_save = dlg.exec()
            if not ok_save: return                      # save was cancelled - return to edit mode 

        # leave edit_mode - restore original airfoil 
        if not ok:
            airfoil = self._airfoil_sav                 # restore old airfoil 
        else: 
            airfoil = self.airfoil()
        self._airfoil_sav = None 

        airfoil.useAsDesign (False)                     # will have another visualization 
        airfoil.set_isModified (False)                  # just sanity
        self.set_airfoil (airfoil, silent=True) 
        self.set_edit_mode (False)       


    def new_as_Bezier (self):
        """ create new Bezier airfoil based on current airfoil and switch to edit mode """

        # enter edit_mode - save original, create working copy as splined airfoil 
        self._airfoil_sav = self._airfoil
        airfoil = Airfoil_Bezier.onAirfoil (self._airfoil)
        airfoil.useAsDesign()                           # will have another visualization 
        airfoil.normalize()                     

        self.set_airfoil_ref1 (self._airfoil_sav)       # current will be reference for Bezier
        self.set_airfoil (airfoil, silent=True)         # set without signal   
        self.set_edit_mode (True)       


    def set_edit_mode (self, aBool : bool):
        """ switch edit / view mode """

        if self._edit_mode != aBool: 
            self._edit_mode = aBool
            signal_airfoil_changed ()               # signal new airfoil 
        else: 
            self.refresh()                          # set disable/enable during init 
        

    def refresh(self):
        """ refreshes all child panels of edit_panel """
        self._data_panel.refresh(disable=not self.edit_mode)
        self._file_panel.refresh(disable=False)


    def airfoil (self) -> Airfoil:
        """ encapsulates current airfoil. Childs should acces only via this function
        to enable a new airfoil to be set """
        return self._airfoil

    def airfoils (self) -> Airfoil:
        """ list of airfoils (current, ref1 and ref2) 
        Childs should acces only via this function to enable a new airfoil to be set """
        airfoils = [self._airfoil]
        if self.airfoil_ref1: airfoils.append (self.airfoil_ref1)
        if self.airfoil_ref2: airfoils.append (self.airfoil_ref2)
        return airfoils


    def set_airfoil (self, aNew : Airfoil , silent=False):
        """ encapsulates current airfoil. Childs should acces only via this function
        to enable a new airfoil to be set """

        self._airfoil = aNew
        self.setWindowTitle (AppName + "  v" + str(AppVersion) + "  [" + self.airfoil().fileName + "]")
        if not silent: 
            self.sig_airfoil_changed.emit ()

    @property
    def airfoil_ref1 (self) -> Airfoil:
        return self._airfoil_ref1
    def set_airfoil_ref1 (self, airfoil: Airfoil | None = None): 
        self._airfoil_ref1 = airfoil 
        if airfoil: airfoil.set_usedAs (usedAs.REF1)
        self.sig_airfoil_ref_changed.emit()


    @property
    def airfoil_ref2 (self) -> Airfoil:
        return self._airfoil_ref2
    def set_airfoil_ref2 (self, airfoil: Airfoil | None = None): 
        self._airfoil_ref2 = airfoil 
        if airfoil: airfoil.set_usedAs (usedAs.REF2)
        self.sig_airfoil_ref_changed.emit()



    def _on_leaving_edit_mode (self) -> bool: 
        """ handle user wants to leave edit_mode"""
        #todo 
        return True 

    def _on_airfoil_changed (self):
        """ slot to handle airfoil changed signal """

        logging.debug (f"{self} on airfoil changed")

        self.refresh()

#-------------------------------------------------------------------------------
# Single edit panels    
#-------------------------------------------------------------------------------


class Panel_Airfoil_Abstract (Edit_Panel):
    """ 
    Abstract superclass for Edit/View-Panels of AirfoilEditor
        - has semantics of App
        - connect / handle signals 
    """

    @property
    def myApp (self) -> App_Main:
        return self._parent 

    def airfoil (self) -> Airfoil: 
        return self.dataObject

    def geo (self) -> Geometry:
        return self.airfoil().geo
    

    def __init__ (self, *args, **kwargs):
        super().__init__ (*args, **kwargs)

        # connect to change signal of widget 
        for w in self.widgets:
            w.sig_changed.connect (self._on_airfoil_widget_changed)


    def _on_airfoil_widget_changed (self):
        """ user changed data in widget"""
        # logging.debug (f"{self} widget changed slot")
        signal_airfoil_changed ()



class Panel_View_Mode (Panel_Airfoil_Abstract):
    """ File panel with open / save / ... """

    name = 'File'
    _width  = 220                   # fixed width 


    @property
    def _isVisible (self) -> bool:
        """ overloaded: only visible if edit_moder """
        return not self.myApp.edit_mode


    def _on_airfoil_widget_changed (self, *_ ):
        """ user changed data in widget"""
        # overloaded - do not react on self widget changes 
        pass


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Airfoil_Select_Open_Widget (l,r,c, withOpen=True, asSpin=False, signal=False,
                                    get=self.airfoil, set=self.myApp.set_airfoil)
        r += 1
        SpaceR (l,r, height=10)
        r += 1
        Button (l,r,c, text="Modify Airfoil", width=100, 
                set=self.myApp.modify_airfoil, toolTip="Modify geometry, Normalize, Repanel")
        r += 1
        Button (l,r,c, text="New as Bezier", width=100, 
                set=self.myApp.new_as_Bezier, disable=lambda: self.airfoil().isBezierBased,
                toolTip="Create new Bezier airfoil based on current airfoil")
        r += 1
        SpaceR (l,r, stretch=4)
        r += 1
        Button (l,r,c, text="Exit", width=100, 
                set=self.myApp.close)
        l.setColumnStretch (1,2)
        l.setContentsMargins (QMargins(0, 0, 0, 0)) 

        return l 
 


class Panel_Edit_Mode (Panel_Airfoil_Abstract):
    """ File panel with open / save / ... """

    name = 'Edit Mode'
    _width  = 220                   # fixed width 

    @property
    def _isVisible (self) -> bool:
        """ overloaded: only visible if edit_moder """
        return self.myApp.edit_mode


    def _init_layout (self): 

        self.set_background_color (color='deeppink', alpha=0.2)

        l = QGridLayout()
        r,c = 0, 0 
        Field (l,r,c, colSpan=3, obj=self.airfoil, prop=Airfoil.fileName, disable=True)
        r += 1
        SpaceR (l,r)
        l.setRowStretch (r,2)
        r += 1
        Button (l,r,c,  text="Save && Close", width=100, button_style=button_style.PRIMARY,
                        set=lambda : self.myApp.modify_airfoil_finished(ok=True))
        r += 1
        SpaceR (l,r, stretch=0)
        r += 1
        Button (l,r,c,  text="Cancel",  width=100, 
                        set=lambda : self.myApp.modify_airfoil_finished(ok=False))
        r += 1
        l.setColumnStretch (1,2)
        l.setContentsMargins (QMargins(0, 0, 0, 0)) 

        return l
        


class Panel_Geometry (Panel_Airfoil_Abstract):
    """ Main geometry data of airfoil"""

    name = 'Airfoil'
    _width  = (350, None)

    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Field  (l,r,c, lab="Name", obj=self.airfoil, prop=Airfoil.name, width=(100,None), colSpan=4)

        r,c = 1, 0 
        FieldF (l,r,c, lab="Thickness", obj=self.geo, prop=Geometry.max_thick, width=70, unit="%", step=0.1,
                disable=self._disabled_for_airfoil)
        r += 1
        FieldF (l,r,c, lab="Camber", obj=self.geo, prop=Geometry.max_camb, width=70, unit="%", step=0.1,
                disable=self._disabled_for_airfoil)
        r += 1
        FieldF (l,r,c, lab="TE gap", obj=self.geo, prop=Geometry.te_gap, width=70, unit="%", step=0.1)

        r,c = 1, 2 
        SpaceC (l,c)
        c += 1 
        FieldF (l,r,c, lab="at", obj=self.geo, prop=Geometry.max_thick_x, width=70, unit="%", step=0.1,
                disable=self._disabled_for_airfoil)
        r += 1
        FieldF (l,r,c, lab="at", obj=self.geo, prop=Geometry.max_camb_x, width=70, unit="%", step=0.1,
                disable=self._disabled_for_airfoil)
        r += 1
        FieldF (l,r,c, lab="LE radius", obj=self.geo, prop=Geometry.le_radius, width=70, unit="%", step=0.1,
                disable=self._disabled_for_airfoil)
        r += 1
        SpaceR (l,r)
        r += 1
        Label  (l,r,0,colSpan=4, get=lambda : "Data " + self.geo().description, style=style.COMMENT)

        l.setColumnMinimumWidth (0,80)
        l.setColumnMinimumWidth (3,60)
        # l.setColumnStretch (0,1)
        l.setColumnStretch (1,2)
        l.setColumnStretch (2,1)
        l.setRowStretch    (r-1,2)
        return l 

    def _disabled_for_airfoil (self):
        """ returns disable for eg. bezier based - thickness can't be changed """
        return self.airfoil().isBezierBased


class Panel_Panels (Panel_Airfoil_Abstract):
    """ Panelling information """

    name = 'Panels'
    _width  = None # (260, None)

    def _init_layout (self):

        l = QGridLayout()

        r,c = 0, 0 
        FieldI (l,r,c, lab="No of panels", obj=self.geo, prop=Geometry.nPanels, disable=True, width=70, style=self._style_panel)
        r += 1
        FieldF (l,r,c, lab="Angle at LE", obj=self.geo, prop=Geometry.panelAngle_le, width=70, dec=1, unit="°", style=self._style_angle)
        SpaceC (l,c+2, width=10, stretch=0)
        Label  (l,r,c+3,width=70, get=lambda: f"at index {self.geo().iLe}",
                        hide=lambda: self.airfoil().isBezierBased)
        r += 1
        FieldF (l,r,c, lab="Angle min", get=lambda: self.geo().panelAngle_min[0], width=70, dec=1, unit="°")
        Label  (l,r,c+3,width=70, get=lambda: f"at index {self.geo().panelAngle_min[1]}",
                        hide=lambda: self.airfoil().isBezierBased)
        r += 1
        SpaceR (l,r,height=5)
        r += 1
        Label  (l,r,0,colSpan=4, get=self._messageText, style=style.COMMENT)

        l.setColumnMinimumWidth (0,80)
        # l.setColumnStretch (0,1)
        l.setColumnStretch (c+4,1)
        l.setRowStretch    (r-1,2)
        
        return l
 

    def _style_panel (self):
        """ returns style.WARNING if panels not in range"""
        if self.geo().nPanels < 160 or self.geo().nPanels > 260: 
            return style.WARNING
        else: 
            return style.NORMAL

    def _style_angle (self):
        """ returns style.WARNING if panel angle too blunt"""
        if self.geo().panelAngle_le > 172.0: 
            return style.WARNING
        else: 
            return style.NORMAL

    def _messageText (self): 

        text = []
        minAngle, _ = self.geo().panelAngle_min

        if self.geo().panelAngle_le > 172.0: 
            text.append("- Panel angle at LE (%d°) is too blunt" %(self.geo().panelAngle_le))
        if minAngle < 150.0: 
            text.append("- Min. angle of two panels is < 150°")
        if self.geo().panelAngle_le == 180.0: 
            text.append("- Leading edge has 2 points")
        if self.geo().nPanels < 140 or self.geo().nPanels > 260: 
            text.append("- No of panels should be > 140 and < 260")
        
        text = '\n'.join(text)
        return text 



class Panel_LE_TE  (Panel_Airfoil_Abstract):
    """ info about LE and TE coordinates"""

    name = 'Coordinates'

    _width  = (300, None)

    @property
    def _isVisible (self) -> bool:
        """ overloaded: only visible if geo is not Bezier """
        return not self.geo().isBezier


    def _add_to_header_layout(self, l_head: QHBoxLayout) -> QLayout:
        """ add Widgets to header layout"""

        l_head.addStretch(1)
        Button (l_head, text="&Normalize", width=80,
                set=lambda : self.airfoil().normalize(), signal=True, 
                hide=lambda: not self.myApp.edit_mode)


    def _init_layout (self): 

        l = QGridLayout()     
        r,c = 0, 0 
        FieldF (l,r,c, lab="Leading edge", get=lambda: self.geo().le[0], width=75, dec=7, style=lambda: self._style (self.geo().le[0], 0.0))
        r += 1
        FieldF (l,r,c, lab=" ... of spline", get=lambda: self.geo().le_real[0], width=75, dec=7, style=self._style_le_real,
                hide=lambda: not self.myApp.edit_mode)
        r += 1
        FieldF (l,r,c, lab="Trailing edge", get=lambda: self.geo().te[0], width=75, dec=7, style=lambda: self._style (self.geo().te[0], 1.0))
        r += 1
        FieldF (l,r,c+1,get=lambda: self.geo().te[2], width=75, dec=7, style=lambda: self._style (self.geo().te[0], 1.0))

        r,c = 0, 2 
        SpaceC (l,c, width=10, stretch=0)
        c += 1 
        FieldF (l,r,c+1,get=lambda: self.geo().le[1], width=75, dec=7, style=lambda: self._style (self.geo().le[1], 0.0))
        r += 1
        FieldF (l,r,c+1,get=lambda: self.geo().le_real[1], width=75, dec=7, style=self._style_le_real,
                hide=lambda: not self.myApp.edit_mode)
        r += 1
        FieldF (l,r,c+1,get=lambda: self.geo().te[1], width=75, dec=7, style=lambda: self._style (self.geo().te[1], -self.geo().te[3]))
        r += 1
        FieldF (l,r,c+1,get=lambda: self.geo().te[3], width=75, dec=7, style=lambda: self._style (self.geo().te[3], -self.geo().te[1]))
        # SpaceC (l,c+2)

        r += 1
        SpaceR (l,r, height=5)
        r += 1
        Label  (l,r,0,colSpan=4, get=self._messageText, style=style.COMMENT)

        l.setColumnMinimumWidth (0,80)
        # l.setColumnStretch (0,1)
        l.setColumnStretch (c+3,1)
        l.setRowStretch    (r-1,2)
        return l


    def _style_le_real (self):
        """ returns style.WARNING if LE spline isn't close to LE"""
        if self.geo().isLe_closeTo_le_real: 
            return style.NORMAL
        else: 
            return style.WARNING


    def _style (self, val, target_val):
        """ returns style.WARNING if val isn't target_val"""
        if val != target_val: 
            return style.WARNING
        else: 
            return style.NORMAL


    def _messageText (self): 

        text = []
        if not self.geo().isNormalized:
            if not self.geo().isLe_closeTo_le_real:
                text.append("- Leading edge is not at 0,0")
        if self.geo().te[0] != 1.0 or self.geo().te[2] != 1.0 : 
           text.append("- Trailing edge is not at 1")
        if self.geo().te[1] != -self.geo().te[3]: 
           text.append("- Trailing not symmetric")

        if not text:
            if self.geo().isSymmetrical: 
                text.append("Airfoil is symmetrical")
            else: 
                text.append("Airfoil is normalized")

        text = '\n'.join(text)
        return text 




class Panel_Bezier (Panel_Airfoil_Abstract):
    """ Info about Bezier curves upper and lower  """

    name = 'Bezier'
    _width  = (260, None)

    @property
    def _isVisible (self) -> bool:
        """ overloaded: only visible if geo is Bezier """
        return self.geo().isBezier

    def upper (self) -> Side_Airfoil_Bezier:
        if self.geo().isBezier:
            return self.geo().upper

    def lower (self) -> Side_Airfoil_Bezier:
        if self.geo().isBezier:
            return self.geo().lower

    def curv_upper (self) -> Line:
        if self.geo().isBezier:
            return self.geo().curvature.upper

    def curv_lower (self) -> Line:
        if self.geo().isBezier:
            return self.geo().curvature.lower


    def _init_layout (self):

        l = QGridLayout()

        r,c = 0, 0 
        FieldI (l,r,c,   lab="No of points", obj=self.upper, prop=Side_Airfoil_Bezier.nControlPoints,  width=70)
        FieldI (l,r,c+2,                     obj=self.lower, prop=Side_Airfoil_Bezier.nControlPoints,  width=70)
        r += 1
        FieldF (l,r,c,   lab="Curv at LE",   get=lambda: self.curv_upper().y[0],  width=70,
                                             style=self._style_curv_le)
        FieldF (l,r,c+2,                     get=lambda: self.curv_lower().y[0],  width=70,
                                             style=self._style_curv_le)
        r += 1
        FieldF (l,r,c,   lab="Curv at TE",   get=lambda: self.curv_upper().y[-1],  width=70,
                                             style=lambda: self._style_curv_te(self.curv_upper()))
        FieldF (l,r,c+2,                     get=lambda: self.curv_lower().y[-1],  width=70, 
                                             style=lambda: self._style_curv_te(self.curv_lower()))
 
        r += 1
        SpaceR (l,r, height=5)
        r += 1
        Label  (l,r,0,colSpan=4, get=self._messageText, style=style.COMMENT)        
        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (c+3,1)
        l.setRowStretch    (r-1,2)
        
        return l
 
    def _style_curv_le (self):
        """ returns style.WARNING if curvature at LE is too different"""
        if abs(self.curv_upper().y[0] - self.curv_lower().y[0]) > 10: 
            return style.WARNING
        else: 
            return style.NORMAL

    def _style_curv_te (self, aCurv: Line):
        """ returns style.WARNING if curvature at LE is too different"""
        if abs(aCurv.y[-1]) > 10: 
            return style.WARNING
        else: 
            return style.NORMAL


    def _messageText (self): 

        text = []
        if abs(self.curv_upper().y[0] - self.curv_lower().y[0]) > 10 : 
           text.append("- Curvature at LE is too different")
        if abs(self.curv_upper().y[-1]) > 10: 
           text.append("- Curvature at TE (upper) is quite high")
        if abs(self.curv_lower().y[-1]) > 10: 
           text.append("- Curvature at TE (lower) is quite high")

        text = '\n'.join(text)
        return text 




class Panel_Bezier_Match (Panel_Airfoil_Abstract):
    """ Match Bezier functions  """

    name = 'Bezier Match'
    _width  = (250, None)

    def _on_airfoil_widget_changed (self):
        """ user changed data in widget"""
        # overloaded - do not signal signal_airfoil_changed
        # signal_airfoil_changed ()


    @property
    def _isVisible (self) -> bool:
        """ overloaded: only visible if geo is Bezier """
        return self.geo().isBezier and self.myApp.edit_mode

    def upper (self) -> Side_Airfoil_Bezier:
        if self.geo().isBezier:
            return self.geo().upper

    def lower (self) -> Side_Airfoil_Bezier:
        if self.geo().isBezier:
            return self.geo().lower

    def _init_layout (self):

        l = QGridLayout()

        r,c = 0, 0 
        Label  (l,r,c, get="Reference", width=60)
        Airfoil_Select_Open_Widget (l,r,c+1, withOpen=True, asSpin=False,
                    get=lambda: self.myApp.airfoil_ref1, set=self.myApp.set_airfoil_ref1,
                    initialDir=self.myApp.airfoils()[0], addEmpty=True)
 
        r += 1
        SpaceR (l,r, height=5)
        r += 1
        Label  (l,r,0,colSpan=4, get=self._messageText, style=style.COMMENT)        
        l.setColumnMinimumWidth (0,60)
        l.setColumnStretch (c+1,1)
        l.setRowStretch    (r-1,2)
        
        return l
 
 

    def _messageText (self): 

        text = []
        text = '\n'.join(text)
        return text 



#-------------------------------------------------------------------------------
# Diagram   
#-------------------------------------------------------------------------------



class Diagram_Item_Airfoil (Diagram_Item):
    """ 
    Diagram (Plot) Item for airfoils shape 
    """

    name = "View Airfoil"           # used for link and section header 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.airfoil_artist = Airfoil_Artist   (self, self.airfoils, show=True, show_legend=True)
        self.airfoil_artist.sig_airfoil_changed.connect (signal_airfoil_changed)

        self.line_artist = Airfoil_Line_Artist (self, self.airfoils, show=False, show_legend=True)
        self.line_artist.sig_airfoil_changed.connect (signal_airfoil_changed)

        self.bezier_artist = Bezier_Artist (self, self.airfoils, show= self._is_bezier_based())
        self.bezier_artist.sig_airfoil_changed.connect (signal_airfoil_changed)
         
        # setup view box 

        self.viewBox.setDefaultPadding(0.05)
        self.viewBox.setXRange( 0, 1) # , padding=0.05

        self.viewBox.setAspectLocked()
        self.viewBox.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        # self.viewBox.setAutoPan(y=None)
        self.showGrid(x=True, y=True)


    def airfoils (self) -> list[Airfoil]: 
        return self.data_list()
    
    def _is_bezier_based (self) -> bool: 
        """ is one of airfoils Bezier based? """
        a : Airfoil
        for a in self.airfoils():
            if a.isBezierBased: return True
        return False 


    def refresh_artists (self):
        self.airfoil_artist.refresh() 
        self.line_artist.refresh() 
        self.bezier_artist.refresh() 

    @property
    def section_panel (self) -> Edit_Panel:
        """ return section panel within view panel"""

        if self._section_panel is None:    
            l = QGridLayout()
            r,c = 0, 0 
            CheckBox (l,r,c, text="Coordinate points", 
                    get=lambda: self.airfoil_artist.show_points,
                    set=self.airfoil_artist.set_show_points) 
            r += 1
            CheckBox (l,r,c, text="Thickness && Camber", 
                    get=lambda: self.line_artist.show,
                    set=self.line_artist.set_show) 
            r += 1
            CheckBox (l,r,c, text="Shape function (Bezier)", 
                    get=lambda: self.bezier_artist.show,
                    set=self.bezier_artist.set_show,
                    disable=lambda : not self._is_bezier_based()) 
            r += 1
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (title=self.name, layout=l, height=140, 
                                              switchable=True, on_switched=self.setVisible)

        return self._section_panel 



class Diagram_Item_Curvature (Diagram_Item):
    """ 
    Diagram (Plot) Item for airfoils curvature 
    """

    name = "View Curvature"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._logMode = False
        self._link_x  = False 

        self.curvature_artist = Curvature_Artist (self, self.airfoils, 
                                                show=True,
                                                show_derivative=False,
                                                show_legend=True)
        # setup view box 

        self._set_YRange () 
        self.viewBox.setDefaultPadding (0.05)
        self.viewBox.setXRange (0, 1, padding=0.05)  
        self.showGrid(x=True, y=True)


    def airfoils (self) -> list[Airfoil]: 
        return self.data_list()
    
    @property
    def logMode (self) -> bool:
        """ log scale of y axes"""
        return self._logMode
    def set_logMode (self, aBool):
        self._logMode = aBool is True
        self._set_YRange ()

    @property
    def link_x (self) -> bool:
        """ is x axes linked with View Airfoil"""
        return self._link_x
    def set_link_x (self, aBool):
        """ link x axes to View Airfoil"""
        self._link_x = aBool is True
        if self.link_x:
            self.setXLink(Diagram_Item_Airfoil.name)
        else: 
            self.setXLink(None)


    def refresh_artists (self):
        self.curvature_artist.refresh() 


    @property
    def section_panel (self) -> Edit_Panel:
        """ return section panel within view panel"""

        if self._section_panel is None:            
            l = QGridLayout()
            r,c = 0, 0 
            CheckBox (l,r,c, text="Upper side", 
                    get=lambda: self.curvature_artist.show_upper,
                    set=self.curvature_artist.set_show_upper) 
            r += 1
            CheckBox (l,r,c, text="Lower side", 
                    get=lambda: self.curvature_artist.show_lower,
                    set=self.curvature_artist.set_show_lower) 
            r += 1
            CheckBox (l,r,c, text="Derivative of curvature", 
                    get=lambda: self.curvature_artist.show_derivative,
                    set=self.curvature_artist.set_show_derivative) 
            r += 1
            SpaceR   (l,r)
            r += 1
            CheckBox (l,r,c, text=f"X axes linked to '{Diagram_Item_Airfoil.name}'", 
                    get=lambda: self.link_x, set=self.set_link_x) 
            r += 1
            CheckBox (l,r,c, text="Y axes log scale", 
                    get=lambda: self.logMode,
                    set=self.set_logMode) 
            r += 1
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (title=self.name, layout=l, 
                                              height=200, switchable=True, switched=False, on_switched=self.setVisible)

        return self._section_panel 


    def _set_YRange (self):
        """ set range of axes"""

        if self.logMode: 
            self.setLogMode (y=True)
            self.viewBox.setYRange(-1, 3)    # this is the exponent 
        else: 
            self.setLogMode (y=False)
            self.viewBox.setYRange(-2.0, 2.0)

        self.viewBox.setDefaultPadding (0.05)



class Diagram_Airfoil (Diagram):
    """    
    Diagram view to show/plot airfoil diagrams 
    """

    def __init__(self, *args, **kwargs):

        self._airfoil_ref1 = None
        self._airfoil_ref2 = None
        self._show_airfoils_ref = False 

        super().__init__(*args, **kwargs)

        self._viewPanel.setMinimumWidth(220)
        self._viewPanel.setMaximumWidth(220)

        # connect to change signal 

        self.myApp.sig_airfoil_changed.connect (self._on_airfoil_changed)
        self.myApp.sig_airfoil_ref_changed.connect (self._on_airfoil_changed)

    @property
    def myApp (self) -> App_Main:
        return super().myApp  

    @property
    def airfoil_ref1 (self) -> Airfoil | None:
        for a in self.airfoils():
            if a.usedAs == usedAs.REF1: return a

    def set_airfoil_ref1 (self, airfoil: Airfoil | None = None): 
        self.myApp.set_airfoil_ref1 (airfoil) 
        self.refresh ()

    @property
    def airfoil_ref2 (self) -> Airfoil:
        for a in self.airfoils():
            if a.usedAs == usedAs.REF2: return a
    def set_airfoil_ref2 (self, airfoil: Airfoil | None = None): 
        self.myApp.set_airfoil_ref2 (airfoil) 
        self.refresh ()


    @property
    def show_airfoils_ref (self) -> bool: 
        return self._show_airfoils_ref
    def set_show_airfoils_ref (self, aBool : bool): 
        self._show_airfoils_ref = aBool is True 
        self.refresh ()
   

    def airfoils (self) -> list[Airfoil]: 
        airfoils = self.data_list()
        if not self.show_airfoils_ref:
            #remove reference airfoils from list 
            airfoil : Airfoil
            for airfoil in airfoils: 
                if airfoil.usedAs == usedAs.REF1 or airfoil.usedAs == usedAs.REF2:
                    airfoils.remove (airfoil)
        return airfoils


    def create_diagram_items (self):
        """ create all plot Items and add them to the layout """

        item = Diagram_Item_Airfoil (self, getter=self.airfoils, show=True)
        self._add_item (item, 0, 0)

        item = Diagram_Item_Curvature (self, getter=self.airfoils, show=False)
        self._add_item (item, 1, 0)


    @property
    def section_panel (self) -> Edit_Panel:
        """ return section panel within view panel"""

        if self._section_panel is None:
        
            l = QGridLayout()
            r,c = 0, 0 
            Airfoil_Select_Open_Widget (l,r,c, withOpen=True, asSpin=False,
                                get=lambda: self.airfoil_ref1, set=self.set_airfoil_ref1,
                                initialDir=self.airfoils()[0], addEmpty=True)
            r += 1
            Airfoil_Select_Open_Widget (l,r,c, withOpen=True, asSpin=False,
                                get=lambda: self.airfoil_ref2, set=self.set_airfoil_ref2,
                                initialDir=self.airfoils()[0], addEmpty=True)
            r += 1
            l.setColumnStretch (0,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (title="Reference Airfoils", layout=l, height=100,
                                              switchable=True, switched=False, on_switched=self.set_show_airfoils_ref)

        return self._section_panel 


    def _on_airfoil_changed (self):
        """ slot to handle airfoil changed signal """

        # logging.debug (f"{self} on airfoil changed")
        self.refresh()

#--------------------------------

if __name__ == "__main__":

    dev_mode = os.path.isdir(os.path.dirname(os.path.realpath(__file__)) +"\\test_airfoils")

    # init logging  

    if dev_mode:   
        init_logging (level= logging.DEBUG)             # INFO, DEBUG or WARNING
    else:                       
        init_logging (level= logging.WARNING)


    # command line arguments? 
    
    parser = argparse.ArgumentParser(prog=AppName, description='View and edit an airfoil')
    parser.add_argument("airfoil", nargs='*', help="Airfoil .dat or .bez file to show")
    args = parser.parse_args()
    if args.airfoil: 
        airfoil_file = args.airfoil[0]
    else: 
        if os.path.isdir(".\\test_airfoils"):
            airfoil_dir   =".\\test_airfoils"
            airfoil_files = [os.path.join(airfoil_dir, f) for f in os.listdir(airfoil_dir) if os.path.isfile(os.path.join(airfoil_dir, f))]
            airfoil_files = [f for f in airfoil_files if (f.endswith('.dat') or f.endswith('.bez'))]       
            airfoil_files = sorted (airfoil_files, key=str.casefold)
            airfoil_file = airfoil_files[0]
            NoteMsg ("No airfoil file as argument. Showing example airfoils in '%s'" %airfoil_dir)
        else:
            airfoil_file = None

    app = QApplication(sys.argv)
    app.setStyle('fusion')

    # Strange: Without setStyleSheet, reset Widget.setPalette doesn't work .. !?
    # Segoe UI is the font of 'fusion' sttyle 
    # font = QFont ()
    # print (font.defaultFamily(), font.family(), font.families())
    app.setStyleSheet ("QWidget { font-family: 'Segoe UI' }")

    Main = App_Main (airfoil_file)
    Main.show()
    app.exec()

    