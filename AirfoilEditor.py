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


from PyQt6.QtCore           import QSize, QMargins, QEvent
from PyQt6.QtWidgets        import QApplication, QMainWindow, QWidget, QMessageBox, QStackedWidget 
from PyQt6.QtWidgets        import QGridLayout, QVBoxLayout, QHBoxLayout, QStackedLayout
from PyQt6.QtGui            import QShowEvent, QCloseEvent

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

from match_bezier           import Match_Bezier, Matcher

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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

    sig_airfoil_changed         = pyqtSignal()          # airfoil data changed 
    sig_airfoil_ref_changed     = pyqtSignal()          # reference airfoils changed 
    sig_airfoil_target_changed  = pyqtSignal(bool)      # target airfoil changed 
    sig_bezier_changed          = pyqtSignal(linetype)  # new bezier during match bezier 

    sig_enter_edit_mode         = pyqtSignal()          # starting modify airfoil
    sig_enter_bezier_match      = pyqtSignal()          # starting modify airfoil


    def __init__(self, airfoil_file, parentApp=None):
        super().__init__()

        # called from another App? Switch to modal window
        #
        #   self is not a subclass of ctk to support both modal and root window mode 

        if airfoil_file and (not os.path.isfile (airfoil_file)): 
            QMessageBox.critical (self, self.name , f"\n'{airfoil_file}' does not exist.\nShowing example airfoil.\n")
            airfoil_file = Example.fileName
            self.move (200,150)                     # messagebox will move main window 
        elif airfoil_file is None : 
            airfoil_file = Example.fileName


        # get icon either in modules or in icons 
        
        self.setWindowIcon (Icon ('AE_ico.ico'))

        # init settings - get initial window size 

        Settings.belongTo (__file__)
        geometry = tuple (Settings().get('window_geometry', []))
        Win_Util.set_initialWindowSize (self, size_frac= (0.7, 0.6), pos_frac=(0.1, 0.1),
                                        geometry=geometry, maximize=False)

        self._airfoil = None                        # current airfoil 
        self._airfoil_sav = None                    # airfoil saved in edit_mode 
        self._airfoil_ref1 = None                   # reference airfoils 
        self._airfoil_ref2 = None  
        self._airfoil_target = None                 # target for match Bezier     

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


    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        text = f""  
        return f"<{type(self).__name__}{text}>"


    def _init_layout (self): 
        """ init main layout with the different panels """

        #  ||               lower                         >||
        #  || file panel ||        edit panel             >||
        #                 | Geometry  | Coordinates | ... >| 

        self._data_panel  = Panel (title="Data panel")
        l_edit = QHBoxLayout()
        l_edit.addWidget (Panel_Geometry    (self, self.airfoil), stretch= 2)
        l_edit.addWidget (Panel_Panels      (self, self.airfoil), stretch= 1)
        l_edit.addWidget (Panel_LE_TE       (self, self.airfoil), stretch= 1)
        l_edit.addWidget (Panel_Bezier      (self, self.airfoil), stretch= 1)
        l_edit.addWidget (Panel_Bezier_Match(self, self.airfoil), stretch= 2)
        
        l_edit.addStretch (3)
        l_edit.setContentsMargins (QMargins(0, 0, 0, 0))
        self._data_panel.setLayout (l_edit)

        self._file_panel  = Panel (title="File panel")
        l_file = QHBoxLayout()
        l_file.addWidget (Panel_File_View        (self, self.airfoil))
        l_file.addWidget (Panel_File_Edit   (self, self.airfoil))
        l_file.setContentsMargins (QMargins(0, 0, 0, 0))
        self._file_panel.setLayout (l_file)


        l_lower = QHBoxLayout()
        l_lower.addWidget (self._file_panel)
        l_lower.addWidget (self._data_panel, stretch=2)
        l_lower.setContentsMargins (QMargins(0, 0, 0, 0))
        lower = QWidget ()
        lower.setLayout (l_lower)

        # upper diagram area  

        upper = Diagram_Airfoil (self, self.airfoils, welcome=self._welcome_message())

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

        self.sig_enter_edit_mode.emit()


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
        self.set_airfoil_target (None, refresh=False)   # set_edit_mode will do refresh

        self.set_edit_mode (False)       


    def new_as_Bezier (self):
        """ create new Bezier airfoil based on current airfoil and switch to edit mode """

        # enter edit_mode - save original, create working copy as splined airfoil 
        self._airfoil_sav = self._airfoil
        airfoil = Airfoil_Bezier.onAirfoil (self._airfoil)
        airfoil.useAsDesign()                           # will have another visualization 
        airfoil.normalize()                     

        self.set_airfoil_target (self._airfoil_sav, refresh=False) # current will be reference for Bezier
        self.set_airfoil (airfoil, silent=True)       # set_edit_mode will do refresh
        self.set_edit_mode (True)       

        self.sig_enter_bezier_match.emit()


    def set_edit_mode (self, aBool : bool):
        """ switch edit / view mode """

        if self._edit_mode != aBool: 
            self._edit_mode = aBool
            signal_airfoil_changed ()               # signal new airfoil 
        

    def refresh(self):
        """ refreshes all child panels of edit_panel """
        self._data_panel.refresh_panels()
        self._file_panel.refresh_panels()


    def airfoil (self) -> Airfoil:
        """ encapsulates current airfoil. Childs should acces only via this function
        to enable a new airfoil to be set """
        return self._airfoil

    def airfoils (self) -> Airfoil:
        """ list of airfoils (current, ref1 and ref2) 
        Childs should acces only via this function to enable a new airfoil to be set """
        airfoils = [self._airfoil]
        if self.airfoil_ref1:       airfoils.append (self.airfoil_ref1)
        if self.airfoil_ref2:       airfoils.append (self.airfoil_ref2)
        if self.airfoil_target:     airfoils.append (self.airfoil_target)
        return airfoils


    def set_airfoil (self, aNew : Airfoil , silent=False):
        """ encapsulates current airfoil. Childs should acces only via this function
        to enable a new airfoil to be set """

        self._airfoil = aNew
        logger.debug (f"New airfoil: {aNew.name}")
        self.setWindowTitle (AppName + "  v" + str(AppVersion) + "  [" + self.airfoil().fileName + "]")
        if not silent: 
            self.sig_airfoil_changed.emit ()

    @property
    def airfoil_ref1 (self) -> Airfoil:
        return self._airfoil_ref1
    def set_airfoil_ref1 (self, airfoil: Airfoil | None = None, silent=False): 
        self._airfoil_ref1 = airfoil 
        if airfoil: airfoil.set_usedAs (usedAs.REF1)
        if not silent: self.sig_airfoil_ref_changed.emit()

    @property
    def airfoil_ref2 (self) -> Airfoil:
        return self._airfoil_ref2
    def set_airfoil_ref2 (self, airfoil: Airfoil | None = None, silent=False): 
        self._airfoil_ref2 = airfoil 
        if airfoil: airfoil.set_usedAs (usedAs.REF2)
        if not silent: self.sig_airfoil_ref_changed.emit()

    @property
    def airfoil_target (self) -> Airfoil:
        return self._airfoil_target
    def set_airfoil_target (self, airfoil: Airfoil | None = None, refresh=True): 
        if airfoil: 
            airfoil.set_usedAs (usedAs.TARGET)
        elif self._airfoil_target:
            self._airfoil_target.set_usedAs (usedAs.NORMAL) 
        self._airfoil_target = airfoil 
        
        self.sig_airfoil_target_changed.emit(refresh)


    def _on_leaving_edit_mode (self) -> bool: 
        """ handle user wants to leave edit_mode"""
        #todo 
        return True 

    def _on_airfoil_changed (self):
        """ slot to handle airfoil changed signal """

        logger.debug (f"{str(self)} on airfoil changed")

        self.refresh()


    def _welcome_message (self) -> str: 
        """ returns a HTML welcome message which is shown on first start up """

        # use Notepad++ or https://froala.com/online-html-editor/ to edit 

        message = """<p><span style="font-size: 18pt; color: whiteSmoke">Welcome to the Airfoil</span> <span style="font-size: 18pt; color: deeppink">Editor</span></p>
<p>
This is an example airfoil as no airfoil was provided on startup. Try out the functionality with this example airfoil or <strong><span style="color: rgb(209, 213, 216);">Open&nbsp;</span></strong>an existing airfoil.
</p>
<p>
You can view the properties of an airfoil like thickness distribution or camber, analyze the curvature of the surface or <strong><span style="color: rgb(209, 213, 216);">Modify</span></strong> the airfoils geometry.<br>
<strong><span style="color: rgb(209, 213, 216);">New as Bezier</span></strong> allows to convert the airfoil into an airfoil which is based on two Bezier curves.<br>
</p>    """
        
        return message


    @override
    def closeEvent  (self, event : QCloseEvent):
        """ main window is closed """

        Settings().set('window_geometry', tuple(self.geometry().getRect()))
        event.accept()

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
    

    def _set_panel_layout (self, layout = None ):
        """ Set layout of self._panel """
        # overloaded to connect to widgets changed signal

        super()._set_panel_layout (layout=layout)
        for w in self.widgets:
            w.sig_changed.connect (self._on_airfoil_widget_changed)


    def _on_airfoil_widget_changed (self, widget):
        """ user changed data in widget"""
        logger.debug (f"{self} {widget} widget changed slot")
        signal_airfoil_changed ()


    # ---- overloaded 

    @property
    def _isDisabled (self) -> bool:
        """ overloaded: only enabled in edit mode of App """
        return not self.myApp.edit_mode
    


class Panel_File_View (Panel_Airfoil_Abstract):
    """ File panel with open / save / ... """

    name = 'File'
    _width  = 220                   # fixed width 


    @property
    def _shouldBe_visible (self) -> bool:
        """ overloaded: only visible if edit_moder """
        return not self.myApp.edit_mode

    @property
    def _isDisabled (self) -> bool:
        """ override: always enabled """
        return False
    

    def _on_airfoil_widget_changed (self, *_ ):
        """ user changed data in widget"""
        # overloaded - do not react on self widget changes 
        pass

    
    def refresh (self):
        super().refresh()

    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Airfoil_Select_Open_Widget (l,r,c, colSpan=2, withOpen=True, asSpin=False, signal=False,
                                    get=self.airfoil, set=self.myApp.set_airfoil,
                                    hide=lambda: self.airfoil().isExample)
        r += 1
        Airfoil_Open_Widget (l,r,c, colSpan=2, width=100, set=self.myApp.set_airfoil,
                                    hide=lambda: not self.airfoil().isExample)
        r += 1
        SpaceR (l,r, height=5)
        r += 1
        Button (l,r,c, text="Modify Airfoil", width=100, 
                set=self.myApp.modify_airfoil, toolTip="Modify geometry, Normalize, Repanel",
                button_style=button_style.PRIMARY)
        r += 1
        SpaceR (l,r, height=5, stretch=0)
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
 


class Panel_File_Edit (Panel_Airfoil_Abstract):
    """ File panel with open / save / ... """

    name = 'Edit Mode'
    _width  = 220                   # fixed width 

    @property
    def _shouldBe_visible (self) -> bool:
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
        Button (l,r,c,  text="Finish ...", width=100, 
                        set=lambda : self.myApp.modify_airfoil_finished(ok=True))
        r += 1
        SpaceR (l,r, height=5, stretch=0)
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
        l.setColumnStretch (1,2)
        l.setColumnStretch (2,1)
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
        Label  (l,r,c+3,width=70, get=lambda: f"at index {self.geo().iLe}")
                        # hide=lambda: self.airfoil().isBezierBased)
        r += 1
        FieldF (l,r,c, lab="Angle min", get=lambda: self.geo().panelAngle_min[0], width=70, dec=1, unit="°")
        # Label  (l,r,c+3,width=70, get=lambda: f"at index {self.geo().panelAngle_min[1]}",
        #                 hide=lambda: self.airfoil().isBezierBased)
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

    name = 'Leading, Trailing Edge'

    _width  = (320, None)

    @property
    def _shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is not Bezier """
        return not (self.geo().isBezier and self.myApp.edit_mode)


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
            if self.geo().isBasic:
                return style.NORMAL
            else: 
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
    _width  = (180, None)


    # ---- overloaded 

    @property
    def _shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is Bezier """
        return self.geo().isBezier
    
    # ----

    def geo (self) -> Geometry_Bezier:
        return super().geo()

    @property
    def upper (self) -> Side_Airfoil_Bezier:
        if self.geo().isBezier:
            return self.geo().upper

    @property
    def lower (self) -> Side_Airfoil_Bezier:
        if self.geo().isBezier:
            return self.geo().lower


    def _init_layout (self):

        l = QGridLayout()

        r,c = 0, 0 
        Label (l,r,c+1, get="Points")

        r += 1
        FieldI (l,r,c,   lab="Upper side", get=lambda: self.upper.nControlPoints,  width=50, step=1, lim=(3,10),
                         set=lambda n : self.geo().set_nControlPoints_of (self.upper, n))
        r += 1
        FieldI (l,r,c,   lab="Lower side",  get=lambda: self.lower.nControlPoints,  width=50, step=1, lim=(3,10),
                         set=lambda n : self.geo().set_nControlPoints_of (self.lower, n))

        r += 1
        SpaceR (l,r, height=10, stretch=2)
        l.setColumnMinimumWidth (0,70)
        l.setColumnStretch (c+2,4)
        
        return l
 




class Panel_Bezier_Match (Panel_Airfoil_Abstract):
    """ Match Bezier functions  """

    name = 'Bezier Match'
    _width  = (370, None)


    # ---- overloaded 

    @property
    def _shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is Bezier """
        return self.geo().isBezier and self.myApp.edit_mode

    # ----

    @property
    def upper (self) -> Side_Airfoil_Bezier:
        if self.geo().isBezier: return self.geo().upper

    @property
    def lower (self) -> Side_Airfoil_Bezier:
        if self.geo().isBezier: return self.geo().lower

    @property
    def curv_upper (self) -> Line:
        if self.geo().isBezier:
            return self.geo().curvature.upper

    @property
    def curv_lower (self) -> Line:
        if self.geo().isBezier:
            return self.geo().curvature.lower

    @property
    def curv (self) -> Curvature_Abstract:
        return self.geo().curvature

    @property
    def target_airfoil (self) -> Airfoil:
        return self.myApp.airfoil_target

    @property
    def target_upper (self) -> Line:
        if self.target_airfoil: return self.target_airfoil.geo.upper

    @property
    def target_lower (self) -> Line:
        if self.target_airfoil: return self.target_airfoil.geo.lower
        

    def _add_to_header_layout(self, l_head: QHBoxLayout) -> QLayout:
        """ add Widgets to header layout"""

        l_head.addSpacing (20)
  
        Airfoil_Select_Open_Widget (l_head, withOpen=True, asSpin=False,  width=(100,None),
                    get=lambda: self.myApp.airfoil_target, set=self.myApp.set_airfoil_target,
                    initialDir=self.myApp.airfoils()[0], addEmpty=True)

    def __init__ (self,*args, **kwargs):
        super().__init__(*args,**kwargs)

        self.myApp.sig_airfoil_target_changed.connect(self._on_airfoil_target_changed)


    def _init_layout (self):

        self._target_curv_le = None 
        self._target_curv_le_weighting = None
        self._max_te_curv = None 

        l = QGridLayout()

        if self.target_airfoil is not None: 

            self._target_curv_le = self.target_airfoil.geo.curvature.best_around_le 

            r,c = 0, 0 
            Label  (l,r,c+1, get="Deviation", width=70)

            r += 1
            Label  (l,r,c,   get="Upper Side")
            FieldF (l,r,c+1, width=60, dec=3, unit="%",
                             get=lambda: self._norm2 (self.upper),
                             style=lambda: Match_Bezier.style_deviation (self._norm2 (self.upper)))
            r += 1
            Label  (l,r,c,   get="Lower Side")
            FieldF (l,r,c+1, width=60, dec=3, unit="%",
                             get=lambda: self._norm2 (self.lower),
                             style=lambda: Match_Bezier.style_deviation (self._norm2 (self.lower)))

            r,c = 0, 2 
            SpaceC(l,  c, width=5)
            c += 1
            Label (l,r,c, colSpan=2, get="LE curvature TE")
    
            r += 1
            FieldF (l,r,c  , get=lambda: self.curv_upper.max_xy[1], width=40, dec=0, 
                    style=lambda: Match_Bezier.style_curv_le(self._target_curv_le, self.curv_upper))
            FieldF (l,r,c+1, get=lambda: self.curv_upper.te[1],     width=40, dec=1, 
                    style=lambda: Match_Bezier.style_curv_te(self.curv_upper))

            r += 1
            FieldF (l,r,c  , get=lambda: self.curv_lower.max_xy[1], width=40, dec=0, 
                    style=lambda: Match_Bezier.style_curv_le(self._target_curv_le, self.curv_lower))
            FieldF (l,r,c+1, get=lambda: self.curv_lower.te[1],     width=40, dec=1, 
                    style=lambda: Match_Bezier.style_curv_te(self.curv_lower))

            r,c = 0, 5 
            SpaceC (l,  c, width=10)
            c += 1
            r += 1
            Button (l,r,c  , text="Match...", width=70,
                            set=lambda: self._match_bezier (self.upper, self.target_upper))
            r += 1
            Button (l,r,c  , text="Match...", width=70,
                            set=lambda: self._match_bezier (self.lower, self.target_lower))
            c = 0 
            r += 1
            SpaceR (l,r, height=5, stretch=2)
            r += 1
            Label  (l,r,0, get=self._messageText, colSpan=5, height=(40, None), style=style.COMMENT)
            l.setColumnMinimumWidth (0,70)
            l.setColumnStretch (c+6,2)

        else: 
            SpaceR (l,0)
            Label  (l,1,0, get="Select a target airfoil to match...", style=style.COMMENT)
            SpaceR (l,2, stretch=2)
        return l
 

    def _match_bezier (self, aSide : Side_Airfoil_Bezier, aTarget_line : Line ): 
        """ run match bezier (dialog) """ 

        matcher = Match_Bezier (self.myApp, aSide, aTarget_line,
                                target_curv_le = self.target_airfoil.geo.curvature.best_around_le)

        matcher.sig_new_bezier.connect     (self.myApp.sig_bezier_changed.emit)
        matcher.sig_match_finished.connect (self._on_match_finished)
        matcher.exec ()


    def _on_match_finished (self, aSide : Side_Airfoil_Bezier):
        """ slot for match Bezier finished - reset airfoil"""

        geo : Geometry_Bezier = self.geo()
        geo.finished_change_of (aSide)              # will reset and handle changed  

        self.myApp.sig_airfoil_changed.emit()


    def _on_airfoil_target_changed (self,*_):
        """ slot for changed target airfoil"""        
        self.refresh()                              # refresh will also set new layout 


    def _norm2 (self, side: Side_Airfoil_Bezier): 
        """ norm2 deviation of airfoil to target """
        if side.isUpper:
            return Matcher.norm2_deviation_to (self.upper.bezier, self.target_upper)  
        else:          
            return Matcher.norm2_deviation_to (self.lower.bezier, self.target_lower)  


    def _messageText (self): 
        """ user warnings"""
        text = []
        s_upper_dev = Match_Bezier.style_deviation (self._norm2 (self.upper))
        s_lower_dev = Match_Bezier.style_deviation (self._norm2 (self.lower))

        s_upper_le = Match_Bezier.style_curv_le (self._target_curv_le, self.curv_upper)
        s_lower_le = Match_Bezier.style_curv_le (self._target_curv_le, self.curv_lower)
        s_upper_te = Match_Bezier.style_curv_te (self.curv_upper)
        s_lower_te = Match_Bezier.style_curv_te (self.curv_lower)

        if s_upper_dev == style.WARNING or s_lower_dev == style.WARNING:
           text.append("- Deviation is quite high")
        if s_upper_le == style.WARNING or s_lower_le == style.WARNING:
           text.append("- Curvature at LE differs too much from target")
        if s_upper_te == style.WARNING or s_lower_te == style.WARNING:
           text.append("- Curvature at TE is quite high")

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

        self._edit_mode_first_time = True           # switch to edit first time 

        super().__init__(*args, **kwargs)

        self.myApp.sig_bezier_changed.connect  (self.bezier_artist.refresh_from_side)
        self.myApp.sig_enter_edit_mode.connect (self._on_enter_edit_mode)


    @property
    def myApp (self):
        return self._parent.myApp

    def airfoils (self) -> list[Airfoil]: 
        return self.data_list()
    
    def _one_is_bezier_based (self) -> bool: 
        """ is one of airfoils Bezier based? """
        a : Airfoil
        for a in self.airfoils():
            if a.isBezierBased: return True
        return False 


    def _on_enter_edit_mode (self):
        """ slot user started edit mode """

        if self._edit_mode_first_time and not self.airfoils()[0].isBezierBased:
            # switch on show thickness/camber if it is the first time 
            # - only for not bezier airfoils 
            self.line_artist.set_show (True)
            self.section_panel.refresh() 
            self._edit_mode_first_time = False

            logger.debug (f"{str(self)} on_enter_edit_mode")


    @override
    def setup_artists (self):
        """ create and setup the artists of self"""
        
        self.airfoil_artist = Airfoil_Artist   (self, self.airfoils, show=True, show_legend=True)
        self.airfoil_artist.sig_airfoil_changed.connect (signal_airfoil_changed)

        self.line_artist = Airfoil_Line_Artist (self, self.airfoils, show=False, show_legend=True)
        self.line_artist.sig_airfoil_changed.connect (signal_airfoil_changed)

        self.bezier_artist = Bezier_Artist (self, self.airfoils, show= True)
        self.bezier_artist.sig_airfoil_changed.connect (signal_airfoil_changed)


    @override
    def setup_viewRange (self):
        """ define view range of this plotItem"""

        self.viewBox.setDefaultPadding(0.05)

        self.viewBox.autoRange ()               # first ensure best range x,y 
        self.viewBox.setXRange( 0, 1)           # then set x-Range

        self.viewBox.setAspectLocked()

        self.viewBox.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)

        self.showGrid(x=True, y=True)


    @override
    def refresh_artists (self):
        self.airfoil_artist.refresh() 
        self.line_artist.refresh() 

        # show Bezier shape function when current airfoil is Design and Bezier 
        cur_airfoil : Airfoil = self.airfoils()[0]
        if cur_airfoil.isBezierBased and cur_airfoil.usedAsDesign:
            self.bezier_artist.set_show (True)
        else: 
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
                    disable=lambda : not self._one_is_bezier_based()) 
            r += 1
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (title=self.name, layout=l, height=130, 
                                              switchable=True, on_switched=self.setVisible)

        return self._section_panel 


    def set_welcome (self, aText : str):
        """ set a Welcome text into the first artist"""

        self.airfoil_artist.set_welcome (aText)


class Diagram_Item_Curvature (Diagram_Item):
    """ 
    Diagram (Plot) Item for airfoils curvature 
    """

    name = "View Curvature"

    def __init__(self, *args, **kwargs):

        self._link_x  = False 

        super().__init__(*args, **kwargs)


    def airfoils (self) -> list[Airfoil]: 
        return self.data_list()
    

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

    def setup_artists (self):
        """ create and setup the artists of self"""
        
        self.curvature_artist = Curvature_Artist (self, self.airfoils, 
                                                show=True, show_derivative=False, show_legend=True)


    def setup_viewRange (self):
        """ define view range of this plotItem"""

        self.viewBox.setDefaultPadding(0.05)

        self.viewBox.autoRange ()               # first ensure best range x,y 
        self.viewBox.setXRange( 0, 1)           # then set x-Range
        self.viewBox.setYRange(-2.0, 2.0)

        self.showGrid(x=True, y=True)


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
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (title=self.name, layout=l, 
                                              height=160, switchable=True, switched=False, on_switched=self.setVisible)

        return self._section_panel 




class Diagram_Airfoil (Diagram):
    """    
    Diagram view to show/plot airfoil diagrams 
    """

    def __init__(self, *args, welcome=None, **kwargs):

        self._airfoil_ref1 = None
        self._airfoil_ref2 = None
        self._show_airfoils_ref = False 


        self._bezier_match_first_time = True        # switch to show target airfoil 

        super().__init__(*args, **kwargs)

        self._viewPanel.setMinimumWidth(220)
        self._viewPanel.setMaximumWidth(220)

        # set welcome message into the first diagram item 

        self.diagram_items[0].set_welcome (welcome) 

        # connect to change signal 

        self.myApp.sig_airfoil_changed.connect (self._on_airfoil_changed)
        self.myApp.sig_airfoil_ref_changed.connect (self._on_airfoil_changed)
        self.myApp.sig_airfoil_target_changed.connect (self._on_target_changed)
        self.myApp.sig_enter_bezier_match.connect (self._on_bezier_match)

    @property
    def myApp (self) -> App_Main:
        return super().myApp  
 

    @property
    def airfoil_ref1 (self) -> Airfoil | None:
        return self.myApp.airfoil_ref1
    def set_airfoil_ref1 (self, airfoil: Airfoil | None = None): 
        self.myApp.set_airfoil_ref1 (airfoil) 
        self.refresh ()

    @property
    def airfoil_ref2 (self) -> Airfoil:
        return self.myApp.airfoil_ref2
    def set_airfoil_ref2 (self, airfoil: Airfoil | None = None): 
        self.myApp.set_airfoil_ref2 (airfoil) 
        self.refresh ()

    @property
    def airfoil_target (self) -> Airfoil | None:
        return self.myApp.airfoil_target
    def set_airfoil_target (self, airfoil: Airfoil | None = None): 
        self.myApp.set_airfoil_target (airfoil) 
        self.refresh ()
    @property
    def airfoil_target_name (self) -> str:
        if self.myApp.airfoil_target:
            return self.myApp.airfoil_target.name
        else:
            return '' 

    @property
    def show_airfoils_ref (self) -> bool: 
        return self._show_airfoils_ref
    def set_show_airfoils_ref (self, aBool : bool): 
        self._show_airfoils_ref = aBool is True 
        self.refresh ()
   

    def airfoils (self) -> list[Airfoil]: 
        """ the airfoil(s) currently to show as list"""
        if not self.show_airfoils_ref:
            return [self.data_list()[0]]
        else: 
            return self.data_list()


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
            Field (l,r,c, get=lambda: self.airfoil_target_name, disable=True,
                          hide=lambda: self.airfoil_target is None)
            r += 1
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

            self._section_panel = Edit_Panel (title="Reference Airfoils", layout=l, height=130,
                                              switchable=True, switched=False, on_switched=self.set_show_airfoils_ref)

        return self._section_panel 


    def _on_airfoil_changed (self):
        """ slot to handle airfoil changed signal """

        logger.debug (f"{str(self)} on airfoil changed")
        self.refresh()


    def _on_target_changed (self, refresh=True):
        """ slot to handle airfoil target changed signal """

        logger.debug (f"{str(self)} on airfoil target changed")

        # is there a target airfoil (match Bezier)? switch ref panel on
        airfoil : Airfoil
        for airfoil in self.data_list():            # ... self.airfoils() is filtered
            if airfoil.usedAs == usedAs.TARGET: 
                self._show_airfoils_ref = True
                self.section_panel.set_switched_on (True, initial=True)
                break
        
        if refresh: 
            self.refresh()

    def _on_bezier_match (self):
        """ slot to handle bezier match changed signal -> show target airfoil"""

        if self._bezier_match_first_time:
                # swtich to show reference airfoils 
                self._show_airfoils_ref = True
                self.section_panel.set_switched_on (True, initial=True)
                logger.debug (f"{str(self)} on_bezier_mtach")

        self._bezier_match_first_time = False


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
        if os.path.isdir(".\\test_airfoilsaaaaa"):
            airfoil_dir   =".\\test_airfoils"
            airfoil_files = [os.path.join(airfoil_dir, f) for f in os.listdir(airfoil_dir) if os.path.isfile(os.path.join(airfoil_dir, f))]
            airfoil_files = [f for f in airfoil_files if (f.endswith('.dat') or f.endswith('.bez'))]       
            airfoil_files = sorted (airfoil_files, key=str.casefold)
            airfoil_file = airfoil_files[0]
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

    