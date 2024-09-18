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

from PyQt6.QtCore           import QSize, QMargins, QEvent
from PyQt6.QtWidgets        import QApplication, QMainWindow, QWidget, QMessageBox, QStackedWidget 
from PyQt6.QtWidgets        import QGridLayout, QVBoxLayout, QHBoxLayout, QDialog
from PyQt6.QtGui            import QShowEvent, QCloseEvent

# let python find the other modules in modules relativ to path of self  
sys.path.append(os.path.join(Path(__file__).parent , 'modules'))

from model.airfoil          import Airfoil, usedAs, GEO_SPLINE
from model.airfoil_geometry import Geometry, Geometry_Bezier, Curvature_Abstract
from model.airfoil_geometry import Panelling_Spline, Panelling_Bezier
from model.airfoil_examples import Example

from base.common_utils      import * 
from base.panels            import Panel, Edit_Panel
from base.widgets           import *
from base.diagram           import * 

from airfoil_widgets        import * 
from airfoil_artists        import *

from airfoil_dialogs        import Match_Bezier, Matcher, Repanel, Blend, Airfoil_Save_Dialog

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)



#-------------------------------------------------------------------------------
# The App   
#-------------------------------------------------------------------------------

# ------ globals -----

AppName    = "Airfoil Editor"
AppVersion = "2.0 beta 6"

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

    sig_bezier_changed          = pyqtSignal(Line.Type) # new bezier during match bezier 
    sig_new_panelling           = pyqtSignal()          # new panelling

    sig_enter_edit_mode         = pyqtSignal(bool)      # starting modify airfoil
    sig_enter_bezier_mode       = pyqtSignal(bool)      # starting bezier match dialog 
    sig_enter_panelling         = pyqtSignal()          # starting panelling dialog
    sig_enter_blend             = pyqtSignal()          # starting blend airfoil with


    def __init__(self, airfoil_file, parentApp=None):
        super().__init__()

        self._airfoil = None                        # current airfoil 
        self._airfoil_org = None                    # airfoil saved in edit_mode 
        self._airfoil_ref1 = None                   # reference airfoils 
        self._airfoil_ref2 = None  
        self._airfoil_target = None                 # target for match Bezier     

        self._edit_mode = False                     # edit/view mode of app 
        self._data_panel = None 
        self._file_panel = None

        self.parentApp = parentApp
        self.initial_geometry = None                # window geometry at the beginning

        # get icon either in modules or in icons 
        
        self.setWindowIcon (Icon ('AE_ico.ico'))

        # get initial window size from settings

        Settings.belongTo (__file__, nameExtension=None, fileExtension= '.settings')
        geometry = Settings().get('window_geometry', [])
        maximize = Settings().get('window_maximize', False)
        Win_Util.set_initialWindowSize (self, size_frac= (0.80, 0.70), pos_frac=(0.1, 0.1),
                                        geometry=geometry, maximize=maximize)
        
        self._load_panelling_settings ()

        # init airfoil 

        if airfoil_file and (not os.path.isfile (airfoil_file)): 
            QMessageBox.critical (self, self.name , f"\n'{airfoil_file}' does not exist.\nShowing example airfoil.\n")
            airfoil = Example()
            self.move (200,150)                     # messagebox will move main window 
        elif airfoil_file is None : 
            airfoil = Example()
        else:
            airfoil = create_airfoil_from_path(airfoil_file)

        self.set_airfoil (airfoil, silent=True)

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
        #  || file panel ||        data panel             >||
        #                 | Geometry  | Coordinates | ... >| 

        self._data_panel  = Panel (title="Data panel")
        l_data = QHBoxLayout()
        l_data.addWidget (Panel_Geometry    (self, self.airfoil))
        l_data.addWidget (Panel_Panels      (self, self.airfoil))
        l_data.addWidget (Panel_LE_TE       (self, self.airfoil))
        l_data.addWidget (Panel_Bezier      (self, self.airfoil))
        l_data.addWidget (Panel_Bezier_Match(self, self.airfoil))
        l_data.addStretch (1)        
        l_data.setContentsMargins (QMargins(0, 0, 0, 0))
        self._data_panel.setLayout (l_data)

        self._file_panel  = Panel (title="File panel", width=220)
        l_file = QHBoxLayout()
        l_file.addWidget (Panel_File_Edit   (self, self.airfoil))
        l_file.addWidget (Panel_File_View   (self, self.airfoil))
        l_file.setContentsMargins (QMargins(0, 0, 0, 0))
        self._file_panel.setLayout (l_file)

        l_lower = QHBoxLayout()
        l_lower.addWidget (self._file_panel)
        l_lower.addWidget (self._data_panel, stretch=1)
        # l_lower.addStretch (1)
        l_lower.setContentsMargins (QMargins(0, 0, 0, 0))
        lower = QWidget ()
        lower.setMinimumHeight(180)
        lower.setMaximumHeight(180)
        lower.setLayout (l_lower)

        # upper diagram area  

        upper = Diagram_Airfoil (self, self.airfoils, welcome=self._welcome_message())

        # main layout with both 

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

        # enter edit_mode - create working copy as splined airfoil 
        try:                                            # normal airfoil - allows new geometry
            airfoil  = self._airfoil.asCopy (nameExt=None, geometry=GEO_SPLINE)
        except:                                         # bezier or hh does not allow new geometry
            airfoil  = self._airfoil.asCopy (nameExt=None)
        airfoil.useAsDesign()                           # will have another visualization 
        airfoil.normalize(just_basic=True)              # just normalize coordinates - not spline         

        self.set_edit_mode (True, airfoil)       


    def modify_airfoil_finished (self, ok=False):
        """ modify airfoil finished - switch to view mode """

        if not self.edit_mode: return 

        if ok:
            dlg = Airfoil_Save_Dialog (parent=self, getter=self.airfoil)
            ok_save = dlg.exec()
            if not ok_save: return                      # save was cancelled - return to edit mode 

        # leave edit_mode - restore original airfoil 
        if not ok:
            airfoil = self._airfoil_org                 # restore old airfoil 
        else: 
            airfoil = self._airfoil

        airfoil.useAsDesign (False)                     # will have another visualization 
        airfoil.set_isModified (False)                  # just sanity

        self.set_edit_mode (False, airfoil)       


    def new_as_Bezier (self):
        """ create new Bezier airfoil based on current airfoil and switch to edit mode """

        # enter edit_mode - create working copy as splined airfoil 
        airfoil_bez = Airfoil_Bezier.onAirfoil (self._airfoil)
        airfoil_bez.useAsDesign()                           # will have another visualization 

        self.set_edit_mode (True, airfoil_bez)       

        self.set_airfoil_target (None, refresh=False)       # current will be reference for Bezier
        self.sig_enter_bezier_mode.emit(True)


    def set_edit_mode (self, aBool : bool, for_airfoil):
        """ switch edit / view mode """

        if self._edit_mode != aBool: 
            self._edit_mode = aBool
            
            if self._edit_mode:
                self._airfoil_org = self._airfoil       # enter edit_mode - save original 

                # save possible example to file to ease consistent further handling in widgets
                if self._airfoil.isExample: self._airfoil.save()
            else: 
                self._airfoil_org = None                # leave edit_mode - remove original 
                self._airfoil_target = None            

            self.set_airfoil (for_airfoil, silent=True)

            self.sig_enter_edit_mode.emit(aBool)
            self.sig_airfoil_changed.emit()             # signal new airfoil 
        

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
        if self.airfoil_org:        airfoils.append (self.airfoil_org)

        # remove duplicates 
        airfoils = list(dict.fromkeys(airfoils))

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
        """ airfoil for reference 1"""
        return self._airfoil_ref1
    def set_airfoil_ref1 (self, airfoil: Airfoil | None = None, silent=False): 
        self._airfoil_ref1 = airfoil 
        if airfoil: airfoil.set_usedAs (usedAs.REF1)
        if not silent: self.sig_airfoil_ref_changed.emit()


    @property
    def airfoil_ref2 (self) -> Airfoil:
        """ airfoil for reference 2"""
        return self._airfoil_ref2
    def set_airfoil_ref2 (self, airfoil: Airfoil | None = None, silent=False): 
        self._airfoil_ref2 = airfoil 
        if airfoil: airfoil.set_usedAs (usedAs.REF2)
        if not silent: self.sig_airfoil_ref_changed.emit()


    @property
    def airfoil_target (self) -> Airfoil:
        """ target airfoil for match Bezier or 2nd airfoil doing Blend"""
        if self._airfoil_target is None: 
            return self._airfoil_org
        else: 
            return self._airfoil_target
    

    def set_airfoil_target (self, airfoil: Airfoil | None = None, refresh=True): 

        if airfoil is not None: 
            airfoil.set_usedAs (usedAs.TARGET)
        elif self._airfoil_target:                                  # reset the current/old target 
            self._airfoil_target.set_usedAs (usedAs.NORMAL) 
        self._airfoil_target = airfoil 
        
        self.sig_airfoil_target_changed.emit(refresh)


    @property
    def airfoil_org (self) -> Airfoil:
        """ the original airfoil during edit mode"""
        return self._airfoil_org


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

        message = """
<p><span style="background-color: black">
<span style="font-size: 18pt; color: lightgray; ">Welcome to the <strong>Airfoil<span style="color:deeppink">Editor</span></strong></span></p>
<p><span style="background-color: black">
This is an example airfoil as no airfoil was provided on startup. Try out the functionality with this example airfoil or <strong><span style="color: silver;">Open&nbsp;</span></strong>an existing airfoil.
</span></p>
<p><span style="background-color: black">
You can view the properties of an airfoil like thickness distribution or camber, analyze the curvature of the surface or <strong><span style="color: silver;">Modify</span></strong> the airfoils geometry.<br>
<strong><span style="color: silver;">New as Bezier</span></strong> allows to convert the airfoil into an airfoil which is based on two Bezier curves.
</span></p>
<p><span style="background-color: black">
<span style="color: deepskyblue;">Tip: </span>Assign the file extension '.dat' to the Airfoil Editor to open an airfoil with a double click.
</span></p>
    """
        
        return message


    def _save_settings (self):
        """ save settings to file """

        # save Window size and position 
        Settings().set('window_geometry', self.normalGeometry ().getRect())
        Settings().set('window_maximize', self.isMaximized())

        # save panelling values 
        Settings().set('spline_nPanels',  Panelling_Spline().nPanels)
        Settings().set('spline_le_bunch', Panelling_Spline().le_bunch)
        Settings().set('spline_te_bunch', Panelling_Spline().te_bunch)

        Settings().set('bezier_nPanels',  Panelling_Bezier().nPanels)
        Settings().set('bezier_le_bunch', Panelling_Bezier().le_bunch)
        Settings().set('bezier_te_bunch', Panelling_Bezier().te_bunch)


    def _load_panelling_settings (self):
        """ load default panelling settings from file """

        nPanels  = Settings().get('spline_nPanels', None)
        le_bunch = Settings().get('spline_le_bunch', None)
        te_bunch = Settings().get('spline_te_bunch', None)

        if nPanels:     Panelling_Spline._nPanels = nPanels
        if le_bunch is not None:    Panelling_Spline._le_bunch = le_bunch
        if te_bunch is not None:    Panelling_Spline._te_bunch = te_bunch

        nPanels  = Settings().get('bezier_nPanels', None)
        le_bunch = Settings().get('bezier_le_bunch', None)
        te_bunch = Settings().get('bezier_te_bunch', None)

        if nPanels:     Panelling_Bezier._nPanels = nPanels
        if le_bunch is not None:    Panelling_Bezier._le_bunch = le_bunch
        if te_bunch is not None:    Panelling_Bezier._te_bunch = te_bunch


    @override
    def closeEvent  (self, event : QCloseEvent):
        """ main window is closed """

        self._save_settings ()

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
        for w in self.header_widgets:
            w.sig_changed.connect (self._on_airfoil_widget_changed)


    def _on_airfoil_widget_changed (self, widget):
        """ user changed data in widget"""
        logger.debug (f"{self} {widget} widget changed slot")
        signal_airfoil_changed ()


    @override
    @property
    def _isDisabled (self) -> bool:
        """ overloaded: only enabled in edit mode of App """
        return not self.myApp.edit_mode
    


class Panel_File_View (Panel_Airfoil_Abstract):
    """ File panel with open / save / ... """

    name = 'File'


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
        Airfoil_Select_Open_Widget (l,r,c, colSpan=2, signal=False, textOpen="&Open",
                                    get=self.airfoil, set=self.myApp.set_airfoil)
        r += 1
        SpaceR (l,r, height=5)
        r += 1
        Button (l,r,c, text="&Modify Airfoil", width=100, 
                set=self.myApp.modify_airfoil, toolTip="Modify geometry, Normalize, Repanel",
                button_style=button_style.PRIMARY)
        r += 1
        SpaceR (l,r, height=2, stretch=0)
        r += 1
        Button (l,r,c, text="&New as Bezier", width=100, 
                set=self.myApp.new_as_Bezier, disable=lambda: self.airfoil().isBezierBased,
                toolTip="Create new Bezier airfoil based on current airfoil")
        r += 1
        SpaceR (l,r, stretch=4)
        r += 1
        Button (l,r,c, text="&Exit", width=100, set=self.myApp.close)
        r += 1
        SpaceR (l,r, height=5, stretch=0)        
        l.setColumnStretch (1,2)
        l.setContentsMargins (QMargins(0, 0, 0, 0)) 

        return l 
 


class Panel_File_Edit (Panel_Airfoil_Abstract):
    """ File panel with open / save / ... """

    name = 'Edit Mode'

    @property
    def _shouldBe_visible (self) -> bool:
        """ overloaded: only visible if edit_moder """
        return self.myApp.edit_mode


    def _init_layout (self): 

        self.set_background_color (color='deeppink', alpha=0.2)

        l = QGridLayout()
        r,c = 0, 0 
        Field (l,r,c, colSpan=3, get=lambda: self.airfoil().fileName, 
                                 set=self.airfoil().set_fileName, disable=True)
        r += 1
        SpaceR (l,r)
        l.setRowStretch (r,2)
        r += 1
        Button (l,r,c,  text="&Finish ...", width=100, 
                        set=lambda : self.myApp.modify_airfoil_finished(ok=True), 
                        toolTip="Save current airfoil, optionally modifiy name and leave edit mode")
        r += 1
        SpaceR (l,r, height=5, stretch=0)
        r += 1
        Button (l,r,c,  text="&Cancel",  width=100, 
                        set=lambda : self.myApp.modify_airfoil_finished(ok=False),
                        toolTip="Cancel modifications of airfoil and leave edit mode")
        r += 1
        SpaceR (l,r, height=5, stretch=0)
        l.setColumnStretch (1,2)
        l.setContentsMargins (QMargins(0, 0, 0, 0)) 

        return l
        


class Panel_Geometry (Panel_Airfoil_Abstract):
    """ Main geometry data of airfoil"""

    name = 'Geometry'
    _width  = (350, None)

    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout) -> QLayout:
        """ add Widgets to header layout"""

        l_head.addStretch(1)

        # blend with airfoil - currently Bezier is not supported
        Button (l_head, text="&Blend", width=80,
                set=self._blend_with, 
                hide=lambda: not self.myApp.edit_mode or self.airfoil().isBezierBased,
                toolTip="Blend original airfoil with another airfoil")


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        # Field  (l,r,c, lab="Name", width=(100,None), colSpan=5,
        #         obj=self.airfoil, prop=Airfoil.name)
        # r += 1
        FieldF (l,r,c, lab="Thickness", width=75, unit="%", step=0.1,
                obj=self.geo, prop=Geometry.max_thick,
                disable=self._disabled_for_airfoil)
        r += 1
        FieldF (l,r,c, lab="Camber", width=75, unit="%", step=0.1,
                obj=self.geo, prop=Geometry.max_camb,
                disable=self._disabled_for_airfoil)
        r += 1
        FieldF (l,r,c, lab="TE gap", width=75, unit="%", step=0.1,
                obj=self.geo, prop=Geometry.te_gap)

        r,c = 0, 2 
        SpaceC (l,c, stretch=0)
        c += 1 
        FieldF (l,r,c, lab="at", width=75, unit="%", step=0.1,
                obj=self.geo, prop=Geometry.max_thick_x,
                disable=self._disabled_for_airfoil)
        r += 1
        FieldF (l,r,c, lab="at", width=75, unit="%", step=0.1,
                obj=self.geo, prop=Geometry.max_camb_x,
                disable=self._disabled_for_airfoil)
        r += 1
        FieldF (l,r,c, lab="LE radius", width=75, unit="%", step=0.1,
                obj=self.geo, prop=Geometry.le_radius,
                disable=self._disabled_for_airfoil)
        r += 1
        SpaceR (l,r)
        r += 1
        Label  (l,r,0,colSpan=4, get=lambda : "Geometry " + self.geo().description, style=style.COMMENT)

        l.setColumnMinimumWidth (0,80)
        l.setColumnMinimumWidth (3,60)
        l.setColumnStretch (5,2)
        return l 

    def _disabled_for_airfoil (self):
        """ returns disable for eg. bezier based - thickness can't be changed """
        return self.airfoil().isBezierBased


    def _blend_with (self): 
        """ run blend airfoil with dialog""" 

        self.myApp.sig_enter_blend.emit()

        dialog = Blend (self.myApp, self.airfoil(), self.myApp.airfoil_org)    
        dialog.sig_airfoil_changed.connect (self.myApp.sig_airfoil_changed.emit)
        dialog.sig_airfoil2_changed.connect (self.myApp.set_airfoil_target)
        dialog.exec()     

        if dialog.airfoil2 is not None: 
            # do final blend with high quality (splined) 
            self.airfoil().geo.blend (self.myApp.airfoil_org.geo, 
                                      dialog.airfoil2.geo, 
                                      dialog.blendBy) 

        self.myApp.sig_airfoil_changed.emit()


class Panel_Panels (Panel_Airfoil_Abstract):
    """ Panelling information """

    name = 'Panels'
    _width  =  (290, None)

    def _add_to_header_layout(self, l_head: QHBoxLayout) -> QLayout:
        """ add Widgets to header layout"""

        l_head.addStretch(1)

        # repanel airfoil - currently Bezier is not supported
        Button (l_head, text="&Repanel", width=80,
                set=self._repanel, hide=lambda: not self.myApp.edit_mode,
                toolTip="Repanel airfoil with a new number of panels" ) 


    def _init_layout (self):

        l = QGridLayout()

        r,c = 0, 0 
        FieldI (l,r,c, lab="No of panels", disable=True, width=70, style=self._style_panel,
                get=lambda: self.geo().nPanels, )
        r += 1
        FieldF (l,r,c, lab="Angle at LE", width=70, dec=1, unit="°", style=self._style_angle,
                obj=self.geo, prop=Geometry.panelAngle_le)
        SpaceC (l,c+2, width=10, stretch=0)
        Label  (l,r,c+3,width=70, get=lambda: f"at index {self.geo().iLe}")
        r += 1
        FieldF (l,r,c, lab="Angle min", width=70, dec=1, unit="°",
                get=lambda: self.geo().panelAngle_min[0], )
        r += 1
        SpaceR (l,r,height=5)
        r += 1
        Label  (l,r,0,colSpan=4, get=self._messageText, style=style.COMMENT, height=(None,None))

        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (c+4,1)
        l.setRowStretch    (r-1,2)
        
        return l
 
    def _repanel (self): 
        """ run repanel dialog""" 

        self.myApp.sig_enter_panelling.emit()

        dialog = Repanel (self.myApp, self.geo())    
        dialog.sig_new_panelling.connect (self.myApp.sig_new_panelling.emit)
        dialog.exec()     # delayed emit 

        geo : Geometry_Bezier = self.geo()

        if dialog.has_been_repaneled:
            geo.repanel (just_finalize=True)       # finalize modifications          

        self.myApp.sig_airfoil_changed.emit()

     
    def refresh(self):
        super().refresh()

    def _on_panelling_finished (self, aSide : Side_Airfoil_Bezier):
        """ slot for panelling (dialog) finished - reset airfoil"""



    def _style_panel (self):
        """ returns style.WARNING if panels not in range"""
        if self.geo().nPanels < 120 or self.geo().nPanels > 260: 
            return style.WARNING
        else: 
            return style.NORMAL

    def _style_angle (self):
        """ returns style.WARNING if panel angle too blunt"""
        if self.geo().panelAngle_le > 175.0: 
            return style.WARNING
        else: 
            return style.NORMAL

    def _messageText (self): 

        text = []
        minAngle, _ = self.geo().panelAngle_min

        if self.geo().panelAngle_le > 175.0: 
            text.append("- Panel angle at LE (%d°) is too blunt" %(self.geo().panelAngle_le))
        if minAngle < 150.0: 
            text.append("- Min. angle of two panels is < 150°")
        if self.geo().panelAngle_le == 180.0: 
            text.append("- Leading edge has 2 points")
        if self.geo().nPanels < 120 or self.geo().nPanels > 260: 
            text.append("- No of panels should be > 120 and < 260")
        
        text = '\n'.join(text)
        return text 



class Panel_LE_TE  (Panel_Airfoil_Abstract):
    """ info about LE and TE coordinates"""

    name = 'LE, TE'

    _width  = 320

    @property
    def _shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is not Bezier """
        return not (self.geo().isBezier and self.myApp.edit_mode)


    def _add_to_header_layout(self, l_head: QHBoxLayout) -> QLayout:
        """ add Widgets to header layout"""

        l_head.addStretch(1)
        Button (l_head, text="&Normalize", width=80,
                set=lambda : self.airfoil().normalize(), signal=True, 
                hide=lambda: not self.myApp.edit_mode,
                toolTip="Normalize airfoil to get leading edge at 0,0")


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
        Label  (l,r,0,colSpan=4, get=self._messageText, style=style.COMMENT, height=(None,None))

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
            if self.geo().isSplined and not self.geo().isLe_closeTo_le_real:
                text.append("- Leading edge of spline is not at 0,0")
            else: 
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

    @property
    def target_curv_le (self) -> float:
        return self.target_airfoil.geo.curvature.best_around_le

    @property
    def max_curv_te_upper (self) -> Line:
        if self.target_airfoil: return self.target_airfoil.geo.curvature.at_upper_te

    @property
    def max_curv_te_lower (self) -> Line:
        if self.target_airfoil: return self.target_airfoil.geo.curvature.at_lower_te

    def norm2_upper (self): 
        """ norm2 deviation of airfoil to target - upper side """
        if self._norm2_upper is None: 
            self._norm2_upper = Matcher.norm2_deviation_to (self.upper.bezier, self.target_upper) 
        return  self._norm2_upper    


    def norm2_lower (self): 
        """ norm2 deviation of airfoil to target  - upper side """
        if self._norm2_lower is None: 
            self._norm2_lower = Matcher.norm2_deviation_to (self.lower.bezier, self.target_lower)  
        return self._norm2_lower


    def _add_to_header_layout(self, l_head: QHBoxLayout) -> QLayout:
        """ add Widgets to header layout"""

        l_head.addSpacing (20)
  
        Airfoil_Select_Open_Widget (l_head, width=(100,200),
                    get=lambda: self.myApp.airfoil_target, set=self.myApp.set_airfoil_target,
                    initialDir=self.myApp.airfoils()[0], addEmpty=True)


    def __init__ (self,*args, **kwargs):
        super().__init__(*args,**kwargs)

        self.myApp.sig_airfoil_target_changed.connect(self._on_airfoil_target_changed)


    def _init_layout (self):

        self._norm2_upper = None                                # cached value of norm2 deviation 
        self._norm2_lower = None                                # cached value of norm2 deviation 
        self._target_curv_le = None 
        self._target_curv_le_weighting = None

        l = QGridLayout()

        if self.target_airfoil is not None: 

            self._target_curv_le = self.target_airfoil.geo.curvature.best_around_le 

            r,c = 0, 0 
            Label  (l,r,c+1, get="Deviation", width=70)

            r += 1
            Label  (l,r,c,   get="Upper Side")
            FieldF (l,r,c+1, width=60, dec=3, unit="%", get=self.norm2_upper,
                             style=lambda: Match_Bezier.style_deviation (self.norm2_upper()))
            r += 1
            Label  (l,r,c,   get="Lower Side")
            FieldF (l,r,c+1, width=60, dec=3, unit="%", get=self.norm2_lower,
                             style=lambda: Match_Bezier.style_deviation (self.norm2_lower()))

            r,c = 0, 2 
            SpaceC(l,  c, width=5)
            c += 1
            Label (l,r,c, colSpan=2, get="LE curvature TE")
    
            r += 1
            FieldF (l,r,c  , get=lambda: self.curv_upper.max_xy[1], width=40, dec=0, 
                    style=lambda: Match_Bezier.style_curv_le(self._target_curv_le, self.curv_upper))
            FieldF (l,r,c+1, get=lambda: self.curv_upper.te[1],     width=40, dec=1, 
                    style=lambda: Match_Bezier.style_curv_te(self.max_curv_te_upper, self.curv_upper))

            r += 1
            FieldF (l,r,c  , get=lambda: self.curv_lower.max_xy[1], width=40, dec=0, 
                    style=lambda: Match_Bezier.style_curv_le(self._target_curv_le, self.curv_lower))
            FieldF (l,r,c+1, get=lambda: self.curv_lower.te[1],     width=40, dec=1, 
                    style=lambda: Match_Bezier.style_curv_te(self.max_curv_te_lower, self.curv_lower))

            r,c = 0, 5 
            SpaceC (l,  c, width=10)
            c += 1
            r += 1
            Button (l,r,c  , text="Match...", width=70,
                            set=lambda: self._match_bezier (self.upper, self.target_upper, 
                                                            self.target_curv_le, self.max_curv_te_upper))
            r += 1
            Button (l,r,c  , text="Match...", width=70,
                            set=lambda: self._match_bezier (self.lower, self.target_lower, 
                                                            self.target_curv_le, self.max_curv_te_lower))
            c = 0 
            r += 1
            SpaceR (l,r, height=5, stretch=2)
            r += 1
            Label  (l,r,0, get=self._messageText, colSpan=7, height=(40, None), style=style.COMMENT)
            l.setColumnMinimumWidth (0,70)
            l.setColumnStretch (c+6,2)

        else: 
            SpaceR (l,0)
            Label  (l,1,0, get="Select a target airfoil to match...", style=style.COMMENT)
            SpaceR (l,2, stretch=2)
        return l
 

    def _match_bezier (self, aSide : Side_Airfoil_Bezier, aTarget_line : Line, 
                            target_curv_le: float, max_curv_te : float  ): 
        """ run match bezier (dialog) """ 

        matcher = Match_Bezier (self.myApp, aSide, aTarget_line,
                                target_curv_le = target_curv_le,
                                max_curv_te = max_curv_te)

        matcher.sig_new_bezier.connect     (self.myApp.sig_bezier_changed.emit)
        matcher.sig_match_finished.connect (self._on_match_finished)

        # leave button press callback 
        timer = QTimer()                                
        timer.singleShot(10, lambda: matcher.exec())     # delayed emit 
       


    def _on_match_finished (self, aSide : Side_Airfoil_Bezier):
        """ slot for match Bezier finished - reset airfoil"""

        geo : Geometry_Bezier = self.geo()
        geo.finished_change_of (aSide)              # will reset and handle changed  

        self.myApp.sig_airfoil_changed.emit()


    def _on_airfoil_target_changed (self,refresh):
        """ slot for changed target airfoil"""  
        if refresh:      
            self.refresh(reinit_layout=True)              # refresh will also set new layout 

    @override
    def refresh (self, reinit_layout=False):

        # reset cached deviations
        self._norm2_lower = None
        self._norm2_upper = None 
        super().refresh(reinit_layout)
        

    def _messageText (self): 
        """ user warnings"""
        text = []
        r_upper_dev = Matcher.result_deviation (self.norm2_upper())
        r_lower_dev = Matcher.result_deviation (self.norm2_lower())

        r_upper_le = Matcher.result_curv_le (self._target_curv_le, self.curv_upper)
        r_lower_le = Matcher.result_curv_le (self._target_curv_le, self.curv_lower)
        r_upper_te = Matcher.result_curv_te (self.max_curv_te_upper,self.curv_upper)
        r_lower_te = Matcher.result_curv_te (self.max_curv_te_lower, self.curv_lower)

        is_bad = Matcher.result_quality.BAD
        if r_upper_dev == is_bad or r_lower_dev == is_bad:
           text.append("- Deviation is quite high")
        if r_upper_le == is_bad or r_lower_le == is_bad:
           text.append(f"- Curvature at LE differs too much from target ({int(self._target_curv_le)})")
        if r_upper_te == is_bad or r_lower_te == is_bad:
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
        self.myApp.sig_new_panelling.connect   (self.refresh_artists)

        self.myApp.sig_enter_edit_mode.connect (self._on_enter_edit_mode)
        self.myApp.sig_enter_panelling.connect (self._on_enter_panelling)
        self.myApp.sig_enter_blend.connect     (self._on_blend_airfoil)

    @property
    def myApp (self) -> App_Main:
        return self._parent.myApp

    def airfoils (self) -> list[Airfoil]: 
        return self._getter()
    
    def _one_is_bezier_based (self) -> bool: 
        """ is one of airfoils Bezier based? """
        a : Airfoil
        for a in self.airfoils():
            if a.isBezierBased: return True
        return False 


    def _on_enter_edit_mode (self, is_enter : bool):
        """ slot user started edit mode """

        if is_enter and self._edit_mode_first_time and not self.airfoils()[0].isBezierBased:
            # switch on show thickness/camber if it is the first time 
            # - only for not bezier airfoils 
            self.line_artist.set_show (True)
            self.section_panel.refresh() 
            self._edit_mode_first_time = False

            logger.debug (f"{str(self)} on_enter_edit_mode {is_enter}")


    def _on_enter_panelling (self):
        """ slot user started panelling dialog - show panels """

        # switch on show panels , switch off thciknes, camber 
        self.airfoil_artist.set_show_points (True)
        self.line_artist.set_show (False)
        self.section_panel.refresh() 

        logger.debug (f"{str(self)} _on_enter_panelling")


    def _on_blend_airfoil (self):
        """ slot to handle blend airfoil entered signal -> show org airfoil"""

        # switch to show reference airfoils 
        self.line_artist.set_show (False)
        self.section_panel.refresh()

        logger.debug (f"{str(self)} _on_blend_airfoil")


    @override
    def setup_artists (self, initial_show=True):
        """ create and setup the artists of self"""
        
        self.airfoil_artist = Airfoil_Artist   (self, self.airfoils, show=initial_show, show_legend=True)
        self.airfoil_artist.sig_airfoil_changed.connect (signal_airfoil_changed)

        self.line_artist = Airfoil_Line_Artist (self, self.airfoils, show=False, show_legend=True)
        self.line_artist.sig_airfoil_changed.connect (signal_airfoil_changed)

        self.bezier_artist = Bezier_Artist (self, self.airfoils, show= initial_show)
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
    

    @override
    def set_show (self, aBool):
        """ switch on/off artists of self when diagram_item is switched on/off"""
        super().set_show (aBool)

        self.curvature_artist.set_show (aBool)



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

    def setup_artists (self, initial_show=True):
        """ create and setup the artists of self"""
        
        self.curvature_artist = Curvature_Artist (self, self.airfoils, show=initial_show, 
                                                  show_derivative=False, show_legend=True)


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
                                              height=160, switchable=True, switched_on=False, on_switched=self.setVisible)

        return self._section_panel 




class Diagram_Airfoil (Diagram):
    """    
    Diagram view to show/plot airfoil diagrams 
    """

    def __init__(self, *args, welcome=None, **kwargs):

        self._airfoil_ref1 = None
        self._airfoil_ref2 = None

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

        self.myApp.sig_enter_edit_mode.connect (self._on_edit_mode)
        self.myApp.sig_enter_bezier_mode.connect (self._on_bezier_mode)
        self.myApp.sig_enter_blend.connect (self._on_blend_airfoil)



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
    def airfoil_target_fileName (self) -> str:
        return self.myApp.airfoil_target.fileName if self.myApp.airfoil_target else ''


    @property
    def airfoil_org_fileName (self) -> str:
        return self.myApp.airfoil_org.fileName if self.myApp.airfoil_org else ''


    @property
    def show_airfoils_ref (self) -> bool: 
        """ is switch show_reference_airfoils on """
        if self._section_panel is not None: 
            return self.section_panel.switched_on
        else: 
            return False
        
    def set_show_airfoils_ref (self, aBool : bool): 
        self.section_panel.set_switched_on (aBool, silent=True)
        self.section_panel.refresh ()
   

    def airfoils (self) -> list[Airfoil]: 
        """ the airfoil(s) currently to show as list"""
        if not self.show_airfoils_ref:
            airfoils = [self.data_list()[0]]
        else: 
            airfoils = self.data_list()
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
            Field (l,r,c, width=155, get=lambda: self.airfoil_org_fileName, disable=True,
                            hide=self._hide_airfoil_org,
                            toolTip="Original airfoil")
            r += 1
            Field (l,r,c, width=155, get=lambda: self.airfoil_target_fileName, disable=True,
                            hide=lambda: not self.airfoil_target_fileName,
                            toolTip="Target airfoil")
            r += 1
            Airfoil_Select_Open_Widget (l,r,c, widthOpen=60,
                            get=lambda: self.airfoil_ref1, set=self.set_airfoil_ref1,
                            initialDir=self.airfoils()[0], addEmpty=True,
                            toolTip="Reference 1 airfoil")
            r += 1
            Airfoil_Select_Open_Widget (l,r,c, widthOpen=60,
                            get=lambda: self.airfoil_ref2, set=self.set_airfoil_ref2,
                            initialDir=self.airfoils()[0], addEmpty=True,
                            hide=lambda: not self.airfoil_ref1 and not self.airfoil_ref2,
                            toolTip="Reference 2 airfoil")
            r += 1
            SpaceR (l,r)
            l.setColumnStretch (0,2)

            self._section_panel = Edit_Panel (title="Reference Airfoils", layout=l, height=(80,None),
                                              switchable=True, switched_on=False, on_switched=self.refresh)

        return self._section_panel 

    def _hide_airfoil_org (self) -> bool:
        """ hide original airfoil if it is the same like target"""
        return (not self.airfoil_org_fileName) or (self.airfoil_org_fileName == self.airfoil_target_fileName)


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
                self.set_show_airfoils_ref (True)
                break
        
        if refresh: 
            self.refresh()
        elif self.section_panel is not None:                    # refresh just section panel
            self.section_panel.refresh()


    def _on_blend_airfoil (self):
        """ slot to handle blend airfoil entered signal -> show org airfoil"""

        self.set_show_airfoils_ref (True)
        self.refresh()                          # plot ref airfoils 
        logger.debug (f"{str(self)} _on_blend_airfoil")


    def _on_edit_mode (self, is_enter):
        """ slot to handle edit mode entered signal"""

        self.section_panel.refresh()                        # to show additional airfoils in edit 
        logger.debug (f"{str(self)} _on_edit_mode {is_enter}")


    def _on_bezier_mode (self, is_enter):
        """ slot to handle bezier mode entered signal -> show ref airfoil"""

        # ensure to show target airfoil in bezier 
        if is_enter:
            self.set_show_airfoils_ref (True)
            self.refresh()                          # plot ref airfoils 
            logger.debug (f"{str(self)} _on_edit_mode {is_enter}")


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
        if os.path.isdir(".\\test_airfoilsss"):
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

    