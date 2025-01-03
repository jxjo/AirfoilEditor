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

from PyQt6.QtCore           import QMargins
from PyQt6.QtWidgets        import QApplication, QMainWindow, QWidget, QMessageBox 
from PyQt6.QtWidgets        import QGridLayout, QVBoxLayout, QHBoxLayout
from PyQt6.QtGui            import QCloseEvent

# let python find the other modules in modules relativ to path of self - ! before python system modules
# common modules hosted by AirfoilEditor 
sys.path.insert (1,os.path.join(Path(__file__).parent , 'AirfoilEditor_subtree/modules'))

# let python find the other modules in modules relativ to path of self  
sys.path.append(os.path.join(Path(__file__).parent , 'modules'))

from model.airfoil          import Airfoil, usedAs, GEO_SPLINE
from model.airfoil_geometry import Panelling_Spline, Panelling_Bezier
from model.airfoil_examples import Example
from model.polar_set        import Polar_Definition, Polar_Set
from model.xo2_driver       import Worker

from base.common_utils      import * 
from base.panels            import Container_Panel, MessageBox
from base.widgets           import *

from airfoil_widgets        import * 
from airfoil_diagrams       import * 

from airfoil_dialogs        import Airfoil_Save_Dialog, Blend_Airfoil, Repanel_Airfoil
from airfoil_ui_panels      import * 


import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)



#-------------------------------------------------------------------------------
# The App   
#-------------------------------------------------------------------------------

# ------ globals -----

AppName         = "Airfoil Polars"
AppVersion      = "0.1"


class App_Main (QMainWindow):
    '''
        The AirfoilPolars App

    '''

    name = AppName  

    WORKER_MIN_VERSION          = '1.0.3'

    # Signals 

    sig_airfoil_changed         = pyqtSignal()          # airfoil data changed 

    sig_airfoil_target_changed  = pyqtSignal()          # target airfoil changed 
    sig_airfoils_ref_changed    = pyqtSignal()          # list of reference airfoils changed
    sig_bezier_changed          = pyqtSignal(Line.Type) # new bezier during match bezier 
    sig_panelling_changed       = pyqtSignal()          # new panelling
    sig_polar_set_changed       = pyqtSignal()          # new polar sets attached to airfoil

    sig_enter_panelling         = pyqtSignal()          # starting panelling dialog
    sig_enter_blend             = pyqtSignal()          # starting blend airfoil with

    sig_closing                 = pyqtSignal(str)       # the app is closing with an airfoils pathFilename


    def __init__(self, airfoil_file, parent=None):
        super().__init__(parent)

        self._airfoil = None                        # current airfoil 
        self._airfoil_org = None                    # airfoil saved in edit_mode 
        self._airfoils_ref = []                     # reference airfoils 
        self._airfoil_target = None                 # target for match Bezier    

        self._polar_definitions = None              # current polar definitions  

        self._edit_mode = False                     # edit/view mode of app 

        self._data_panel = None 
        self._file_panel = None
        self._diagram_panel = None

        self.parentApp = parent
        self.initial_geometry = None                # window geometry at the beginning

        # if called from other applcation (PlanformCreator) make it modal to this 

        if parent is not None:
            self.setWindowModality(Qt.WindowModality.ApplicationModal)  

        # get icon either in modules or in icons 
        
        self.setWindowIcon (Icon ('AE_ico.ico'))

        # get initial window size from settings

        Settings.belongTo (__file__, nameExtension=None, fileExtension= '.settings')
        geometry = Settings().get('window_geometry', [])
        maximize = Settings().get('window_maximize', False)
        Win_Util.set_initialWindowSize (self, size_frac= (0.60, 0.70), pos_frac=(0.1, 0.1),
                                        geometry=geometry, maximize=maximize)
        
        # load settings

        self._load_settings ()

        # init airfoil 

        if airfoil_file and (not os.path.isfile (airfoil_file)): 
            MessageBox.error   (self,self.name, f"{airfoil_file} does not exist.\nShowing example airfoil.", min_height= 60)
            airfoil = Example()
            self.move (200,150)                     # messagebox will move main window 
        elif airfoil_file is None : 
            airfoil = Example()
        else:
            airfoil = create_airfoil_from_path(airfoil_file)

        self.set_airfoil (airfoil, silent=True)

        # Worker for polar generation ready? 

        Worker().isReady(min_version=self.WORKER_MIN_VERSION)
        if Worker.ready:
            Worker().clean_workingDir (self.airfoil().pathName)

        # init main layout of app

        self._data_panel    = Container_Panel (title="Data panel")
        self._file_panel    = Container_Panel (title="File panel", width=240)
        self._diagram_panel = Diagram_Airfoil_Polar (self, self.airfoils, 
                                                     polar_defs_fn = self.polar_definitions,
                                                     diagram_settings= Settings().get('diagram_settings', []))

        l_main = self._init_layout() 

        container = QWidget()
        container.setLayout (l_main) 
        self.setCentralWidget(container)

        # connect to signals from diagram

        self._diagram_panel.sig_airfoil_changed.connect     (self.refresh)
        self._diagram_panel.sig_polar_def_changed.connect   (self.refresh_polar_sets)
        self._diagram_panel.sig_airfoil_ref_changed.connect (self.set_airfoil_ref)

        # connect to signals of self

        self.sig_airfoil_changed.connect        (self.refresh)

        # connect signals to slots of diagram

        self.sig_airfoil_changed.connect        (self._diagram_panel.on_airfoil_changed)
        self.sig_airfoil_target_changed.connect (self._diagram_panel.on_target_changed)
        self.sig_bezier_changed.connect         (self._diagram_panel.on_bezier_changed)
        self.sig_panelling_changed.connect      (self._diagram_panel.on_airfoil_changed)
        self.sig_polar_set_changed.connect      (self._diagram_panel.on_polar_set_changed)
        self.sig_airfoils_ref_changed.connect   (self._diagram_panel.on_airfoils_ref_changed)


        self.sig_enter_blend.connect            (self._diagram_panel.on_blend_airfoil)
        self.sig_enter_panelling.connect        (self._diagram_panel.on_enter_panelling)



    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        text = f""  
        return f"<{type(self).__name__}{text}>"


    def _init_layout (self): 
        """ init main layout with the different panels """

        #  ||               lower                         >||
        #  || file panel ||        data panel             >||
        #                 | Geometry  | Coordinates | ... >| 

        l_data = QHBoxLayout()
        l_data.addWidget (Panel_Geometry    (self, self.airfoil))
        l_data.addWidget (Panel_Panels      (self, self.airfoil))
        l_data.addWidget (Panel_LE_TE       (self, self.airfoil))
        l_data.addWidget (Panel_Bezier      (self, self.airfoil))
        l_data.addWidget (Panel_Bezier_Match(self, self.airfoil))
        l_data.addStretch (1)        
        l_data.setContentsMargins (QMargins(0, 0, 0, 0))
        self._data_panel.setLayout (l_data)

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

        # main layout with diagram panel and lower 

        l_main = QVBoxLayout () 
        l_main.addWidget (self._diagram_panel, stretch=2)
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

            self.sig_airfoil_changed.emit()             # signal new airfoil 
        

    def refresh(self):
        """ refreshes all child panels of edit_panel """
        self._data_panel.refresh()
        self._file_panel.refresh()

        # airfoil was probably changed - reset polar set 
        self._airfoil.set_polarSet (Polar_Set (self._airfoil, polar_def=self.polar_definitions()))


    def refresh_polar_sets (self):
        """ refresh polar sets of all airfoils"""

        for airfoil in self.airfoils():
            airfoil.set_polarSet (Polar_Set (airfoil, polar_def=self.polar_definitions()))

        self.sig_polar_set_changed.emit()


    def airfoil (self) -> Airfoil:
        """ encapsulates current airfoil. Childs should acces only via this function
        to enable a new airfoil to be set """
        return self._airfoil

    def airfoils (self) -> list [Airfoil]:
        """ list of airfoils (current, ref1 and ref2) 
        Childs should acces only via this function to enable a new airfoil to be set """
        airfoils = [self._airfoil]
        if self.airfoil_target:     airfoils.append (self.airfoil_target)
        if self.airfoil_org:        airfoils.append (self.airfoil_org)
        if self.airfoils_ref:       airfoils.extend (self.airfoils_ref)

        # remove duplicates 
        airfoils = list(dict.fromkeys(airfoils))

        return airfoils


    def set_airfoil (self, aNew : Airfoil , silent=False):
        """ encapsulates current airfoil. Childs should acces only via this function
        to enable a new airfoil to be set """

        self._airfoil = aNew
        self._airfoil.set_polarSet (Polar_Set (aNew, polar_def=self.polar_definitions()))


        logger.debug (f"Load new airfoil: {aNew.name}")
        self.setWindowTitle (AppName + "  v" + str(AppVersion) + "  [" + self.airfoil().fileName + "]")
        if not silent: 
            self.sig_airfoil_changed.emit ()


    def polar_definitions (self) -> list [Polar_Definition]:
        """ list of current polar definitions """

        if self._polar_definitions is None: 
            self._polar_definitions = [Polar_Definition()]
        return self._polar_definitions
        
    @property
    def airfoils_ref (self) -> list[Airfoil]:
        """ reference airfoils"""
        return self._airfoils_ref
    
    def set_airfoil_ref (self, cur_airfoil_ref: Airfoil | None,
                               new_airfoil_ref: Airfoil | None):
        """ adds, replace, delete airfoil to the list of reference airfoils"""

        # check if already in list 
        if new_airfoil_ref in self.airfoils_ref: return 

        if new_airfoil_ref:
            new_airfoil_ref.set_polarSet (Polar_Set (new_airfoil_ref, polar_def=self.polar_definitions()))
            new_airfoil_ref.set_usedAs (usedAs.REF)   

        if cur_airfoil_ref:
            # replace or delete existing 
            i = self.airfoils_ref.index (cur_airfoil_ref)
            if new_airfoil_ref:
               self.airfoils_ref[i] = new_airfoil_ref
            else: 
                del self.airfoils_ref [i]
        else:
            # add new  
            self.airfoils_ref.append(new_airfoil_ref)

        self.sig_airfoils_ref_changed.emit()


    @property
    def airfoil_target (self) -> Airfoil:
        """ target airfoil for match Bezier or 2nd airfoil doing Blend"""
        if self._airfoil_target is None: 
            return self._airfoil_org
        else: 
            return self._airfoil_target
    

    def set_airfoil_target (self, airfoil: Airfoil | None = None, refresh=True): 

        if airfoil is not None: 
            airfoil.set_polarSet (Polar_Set (airfoil, polar_def=self.polar_definitions()))
            airfoil.set_usedAs (usedAs.TARGET)
        elif self._airfoil_target:                                  # reset the current/old target 
            self._airfoil_target.set_usedAs (usedAs.NORMAL) 
        self._airfoil_target = airfoil 
        
        self.sig_airfoil_target_changed.emit()              # refresh


    @property
    def airfoil_org (self) -> Airfoil:
        """ the original airfoil during edit mode"""
        return self._airfoil_org


    # --- airfoil functions -----------------------------------------------



    def blend_with (self): 
        """ run blend airfoil with dialog to blend current with another airfoil""" 

        self.sig_enter_blend.emit()

        dialog = Blend_Airfoil (self, self.airfoil(), self.airfoil_org)  

        dialog.sig_airfoil_changed.connect (self.sig_airfoil_changed.emit)
        dialog.sig_airfoil2_changed.connect (self.set_airfoil_target)
        dialog.exec()     

        if dialog.airfoil2 is not None: 
            # do final blend with high quality (splined) 
            self.airfoil().geo.blend (self.airfoil_org.geo, 
                                      dialog.airfoil2.geo, 
                                      dialog.blendBy) 

        self.sig_airfoil_changed.emit()


    def repanel_airfoil (self): 
        """ run repanel dialog""" 

        self.sig_enter_panelling.emit()

        dialog = Repanel_Airfoil (self, self.airfoil().geo)

        dialog.sig_new_panelling.connect (self.sig_panelling_changed.emit)
        dialog.exec()     

        if dialog.has_been_repaneled:
            # finalize modifications 
            self.airfoil().geo.repanel (just_finalize=True)                

        self.sig_airfoil_changed.emit()



    # --- private ---------------------------------------------------------

    def _on_leaving_edit_mode (self) -> bool: 
        """ handle user wants to leave edit_mode"""
        #todo 
        return True 


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

        # save reference airfoils
        ref_list = []
        for airfoil in self.airfoils_ref:
            ref_list.append (airfoil.pathFileName)
        Settings().set('reference_airfoils', ref_list)

        # save polar definitions 
        def_list = []
        for polar_def in self.polar_definitions():
            def_list.append (polar_def._as_dict())
        Settings().set('polar_definitions', def_list)

        # save polar diagram settings 
        Settings().set('diagram_settings', self._diagram_panel._as_dict_list())


    def _load_settings (self):
        """ load default settings from file """

        # panelling 

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

        # polar definitions 

        self._polar_definitions = []
        for def_dict in Settings().get('polar_definitions', []):
            self._polar_definitions.append(Polar_Definition(dataDict=def_dict))

        # reference airfoils 

        for pathFileName in Settings().get('reference_airfoils', []):
            try: 
                airfoil = Airfoil(pathFileName=pathFileName)
                airfoil.load ()
                self.set_airfoil_ref (None, airfoil)
            except: 
                pass


    @override
    def closeEvent  (self, event : QCloseEvent):
        """ main window is closed """

        # remove lost worker input files 
        if Worker.ready:
            Worker().clean_workingDir (self.airfoil().pathName)

        # save e..g diagram options 
        self._save_settings ()

        # inform parent (PlanformCreator) 
        self.sig_closing.emit (self.airfoil().pathFileName)

        event.accept()


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
        else:
            airfoil_file = None

    app = QApplication(sys.argv)
    app.setStyle('fusion')

    # Strange: Without setStyleSheet, reset Widget.setPalette doesn't work .. !?
    # Segoe UI is the font of 'fusion' style 
    app.setStyleSheet ("QWidget { font-family: 'Segoe UI' }")

    # set dark / light mode for widgets depending on system mode 

    scheme = QGuiApplication.styleHints().colorScheme()
    Widget.light_mode = not (scheme == Qt.ColorScheme.Dark)

    Main = App_Main (airfoil_file)
    Main.show()
    app.exec()

    