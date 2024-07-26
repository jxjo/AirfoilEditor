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
from PyQt6.QtWidgets        import QApplication, QMainWindow, QWidget, QMessageBox
from PyQt6.QtWidgets        import QGridLayout, QVBoxLayout, QHBoxLayout

# let python find the other modules in modules relativ to path of self  
sys.path.append(os.path.join(Path(__file__).parent , 'modules'))

from common_utils           import * 

from model.airfoil          import Airfoil 
from model.airfoil_geometry import Geometry

from ui.panels              import Panel, Edit_Panel
from ui.widgets             import *

from airfoil_diagrams       import Airfoil_Diagram
from airfoil_widgets        import * 


#-------------------------------------------------------------------------------
# The App   
#-------------------------------------------------------------------------------

AppName    = "Airfoil Editor"
AppVersion = "2.0 beta"

class MainWindow (QMainWindow):
    '''
        The AirfoilEditor App

        If parentApp is passed, the AirfoilEditor is called from eg PlanformEditor,
        so it will be modal with a reduced File Menu 
    '''

    name = AppName  


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

        self._airfoil = None
        self.parentApp = parentApp
        self.initial_geometry = None                # window geometry at the ebginning

        self.set_airfoil (create_airfoil_from_path(airfoil_file), initial=True)

        # init main layout of app

        l_main = self.init() 

        container = QWidget()
        container.setLayout (l_main) 
        self.setCentralWidget(container)


    def init (self): 
        """ init main layout with the different panels """

        # lower data area 

        lower = QWidget ()
        l_lower = QHBoxLayout()

        l_lower.addWidget (self._get_file_panel())
        l_lower.addWidget (Panel_Geometry   (self, self.airfoil), stretch= 1)
        l_lower.addWidget (Panel_Panels     (self, self.airfoil), stretch= 1)
        l_lower.addWidget (Panel_Coordinates(self, self.airfoil))
        l_lower.addStretch (1)
        l_lower.setContentsMargins (QMargins(0, 0, 0, 0))
        lower.setLayout (l_lower)

        # upper diagram area  

        upper = Airfoil_Diagram (self, self.airfoil)

        # main layout with both 

        l_main = QVBoxLayout () 
        l_main.addWidget (upper, stretch=2)
        l_main.addWidget (lower)
        l_main.setContentsMargins (QMargins(5, 5, 5, 5))

        return l_main 


    def refresh(self):
        """ refreshes all child panels of self """
        Panel.refresh_childs (self)
        Airfoil_Diagram.refresh_childs (self)


    def airfoil (self) -> Airfoil:
        """ encapsulates current airfoil. Childs should acces only via this function
        to enable a new airfoil to be set """
        return self._airfoil


    def set_airfoil (self, aNew : Airfoil , initial=False):
        """ encapsulates current airfoil. Childs should acces only via this function
        to enable a new airfoil to be set """

        self._airfoil = aNew

        self.setWindowTitle (AppName + "  v" + str(AppVersion) + "  [" + self.airfoil().fileName + "]")

        if not initial: 
            self.refresh()


    def _get_file_panel (self):
        """ returns the file panel with open, select, etc"""

        l = QGridLayout()
        r,c = 0, 0 
        Airfoil_Select_Open_Widget (l,r,c, withOpen=True, asSpin=False,
                                    get=self.airfoil, set=self.set_airfoil)
        r += 1
        l.setRowStretch (r,2)
        l.setColumnStretch (1,2)

        panel_file = Edit_Panel (self, header="File", layout=l, width=220, height=180)

        return panel_file


#-------------------------------------------------------------------------------
# Single info panels    
#-------------------------------------------------------------------------------



class Panel_Geometry (Edit_Panel):

    name = 'Airfoil'
    _width  = (350, 500)

    @property
    def a (self) -> Airfoil: 
        return self.dataObject
    
    def init (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Label  (l,r,c,  get="Name")
        Field  (l,r,c+1,width=(100,None), colSpan=4, get=lambda: self.a.name)

        r,c = 1, 0 
        Label  (l,r,c,  get="Thickness", width=80)
        FieldF (l,r,c+1,get=lambda: self.a.maxThickness, width=70, unit="%")
        r += 1
        Label  (l,r,c,  get="Camber")
        FieldF (l,r,c+1,get=lambda: self.a.maxCamber, width=70, unit="%")
        r += 1
        Label  (l,r,c,  get="TE gap")
        FieldF (l,r,c+1,get=lambda: self.a.teGap_perc, width=70, unit="%")

        r,c = 1, 2 
        SpaceC (l,c)
        c += 1 
        Label  (l,r,c  ,get="at", width=60)
        FieldF (l,r,c+1,get=lambda: self.a.maxThicknessX, width=70, unit="%")
        r += 1
        Label  (l,r,c  ,get="at")
        FieldF (l,r,c+1,get=lambda: self.a.maxCamberX, width=70, unit="%")
        r += 1
        Label  (l,r,c  ,get="LE radius")
        FieldF (l,r,c+1,get=lambda: self.a.leRadius_perc, width=70, unit="%")
        r += 1
        SpaceR (l,r)
        r += 1
        Label  (l,r,0,colSpan=4, get=lambda : "Data " + self.a.geo.description, style=STYLE_COMMENT)

        l.setColumnStretch (5,2)
        l.setRowStretch    (r-1,2)

        return l 



class Panel_Panels (Edit_Panel):

    name = 'Panels'
    _width  = (280, 350)

    @property
    def a (self) -> Airfoil: 
        return self.dataObject

    def init (self):

        l = QGridLayout()

        r,c = 0, 0 
        Label  (l,r,c,  get="No of panels", width=80)
        FieldI (l,r,c+1,get=lambda: self.a.geo.nPanels, width=70, style=self._style_panel)
        r += 1
        Label  (l,r,c,  get="Angle at LE")
        FieldF (l,r,c+1,get=lambda: self.a.geo.panelAngle_le, width=70, dec=1, unit="°", style=self._style_angle)
        SpaceC (l,c+2, stretch=0)
        Label  (l,r,c+3,get=lambda: f"at index {self.a.geo.iLe}")
        r += 1
        Label  (l,r,c,  get="Angle min")
        FieldF (l,r,c+1,get=lambda: self.a.geo.panelAngle_min[0], width=70, dec=1, unit="°")
        Label  (l,r,c+3,get=lambda: f"at index {self.a.geo.panelAngle_min[1]}")
        r += 1
        SpaceR (l,r,height=5)
        r += 1
        Label  (l,r,0,colSpan=4, get=self._messageText, style=STYLE_COMMENT)

        l.setColumnStretch (c+3,2)
        l.setRowStretch    (r-1,2)
        
        return l
 


    def _style_panel (self):
        """ returns STYLE_WARNING if panels not in range"""
        if self.a.geo.nPanels < 160 or self.a.geo.nPanels > 260: 
            return STYLE_WARNING
        else: 
            return STYLE_NORMAL

    def _style_angle (self):
        """ returns STYLE_WARNING if panel angle too blunt"""
        if self.a.geo.panelAngle_le > 172.0: 
            return STYLE_WARNING
        else: 
            return STYLE_NORMAL

    def _messageText (self): 

        text = []
        minAngle, atIndex = self.a.geo.panelAngle_min

        if self.a.geo.panelAngle_le > 172.0: 
            text.append("- Panel angle at LE (%d°) is too blunt" %(self.a.geo.panelAngle_le))
        if minAngle < 150.0: 
            text.append("- Min. angle of two panels is < 150°")
        if self.a.geo.panelAngle_le == 180.0: 
            text.append("- Leading edge has 2 points")
        if self.a.geo.nPanels < 160 or self.a.geo.nPanels > 260: 
            text.append("- No of panels should be > 160 and < 260")
        
        text = '\n'.join(text)
        return text 




class Panel_Coordinates (Edit_Panel):

    name = 'Coordinates'

    @property
    def a (self) -> Airfoil: 
        return self.dataObject
    
    @property
    def geo (self) -> Geometry:
        return self.a.geo

    def init(self): 

        l = QGridLayout()
         
        r,c = 0, 0 
        Label  (l,r,c,  get="Leading edge", width=80)
        FieldF (l,r,c+1,get=lambda: self.geo.le[0], width=75, dec=7, style=lambda: self._style (self.geo.le[0], 0.0))
        r += 1
        Label  (l,r,c,  get="Trailing edge")
        FieldF (l,r,c+1,get=lambda: self.geo.te[0], width=75, dec=7, style=lambda: self._style (self.geo.te[0], 1.0))
        r += 1
        # Label  (l,r,c,  get="TE gap")
        FieldF (l,r,c+1,get=lambda: self.geo.te[2], width=75, dec=7, style=lambda: self._style (self.geo.te[0], 1.0))

        r,c = 0, 2 
        SpaceC (l,c, width=10)
        c += 1 
        FieldF (l,r,c+1,get=lambda: self.geo.le[1], width=75, dec=7, style=lambda: self._style (self.geo.le[1], 0.0))
        r += 1
        FieldF (l,r,c+1,get=lambda: self.geo.te[1], width=75, dec=7, style=lambda: self._style (self.geo.te[1], -self.geo.te[3]))
        r += 1
        FieldF (l,r,c+1,get=lambda: self.geo.te[3], width=75, dec=7, style=lambda: self._style (self.geo.te[3], -self.geo.te[1]))
        r += 1
        SpaceR (l,r, height=5)
        r += 1
        Label  (l,r,0,colSpan=4, get=self._messageText, style=STYLE_COMMENT)

        l.setColumnStretch (5,2)
        l.setRowStretch    (r-1,2)

        return l


    def _style (self, val, target_val):
        """ returns STYLE_WARNING if val isn't target_val"""
        if val != target_val: 
            return STYLE_WARNING
        else: 
            return STYLE_NORMAL


    def _messageText (self): 

        text = []
        if self.geo.le[0] != 0.0 or self.geo.le[1] != 0.0:
            text.append("- Leading edge is not at 0,0")
        if self.geo.te[0] != 1.0 or self.geo.te[2] != 1.0 : 
           text.append("- Trailing edge is not at 1")
        if self.geo.te[1] != -self.geo.te[3]: 
           text.append("- Trailing not symmetric")

        if not text and self.geo.isSymmetrical: 
            text.append("- Airfoil is symmetrical")
        
        text = '\n'.join(text)
        return text 



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
            airfoil_files = [f for f in airfoil_files if f.endswith('.dat')]       
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

    main = MainWindow (airfoil_file)
    main.show()
    app.exec()

    