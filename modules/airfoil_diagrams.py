#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

airfoil diagram view and items  

"""

import logging

from PyQt6.QtCore       import QSize, QMargins
from PyQt6.QtWidgets    import QLayout, QGridLayout, QVBoxLayout, QHBoxLayout, QGraphicsGridLayout
from PyQt6.QtWidgets    import QMainWindow, QWidget
from PyQt6.QtGui        import QPalette

import pyqtgraph as pg # import PyQtGraph after PyQt6

from ui.widgets         import * 
from ui.diagram         import * 
from airfoil_artists    import *
from airfoil_widgets    import Airfoil_Select_Open_Widget


class Airfoil_Diagram_Item (Diagram_Item):
    """ 
    Diagram (Plot) Item for airfoils shape 
    """

    name = "View Airfoil"           # used for link and section header 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.airfoil_artist = Airfoil_Artist   (self, self.airfoils, 
                                                show=True,
                                                show_legend=False)
        self.thickness_artist = Thickness_Artist (self, self.airfoils, 
                                                show=False,
                                                show_legend=True)
        # setup view box 
             
        self.viewBox.setAspectLocked()
        self.viewBox.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        # self.viewBox.setAutoPan(y=None)
        self.showGrid(x=True, y=True)


    def airfoils (self) -> list[Airfoil]: 
        return self.data_list()
    

    def refresh (self):
        self.airfoil_artist.refresh() 
        self.thickness_artist.refresh() 

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
                    get=lambda: self.thickness_artist.show,
                    set=self.thickness_artist.set_show) 
            r += 1
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (header=self.name, layout=l, height=100, 
                                              switchable=True, on_switched=self.setVisible)

        return self._section_panel 



class Curvature_Diagram_Item (Diagram_Item):
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

        self._set_range () 
        self.showGrid(x=True, y=True)


    def airfoils (self) -> list[Airfoil]: 
        return self.data_list()
    
    @property
    def logMode (self) -> bool:
        """ log scale of y axes"""
        return self._logMode
    def set_logMode (self, aBool):
        self._logMode = aBool is True
        self._set_range ()

    @property
    def link_x (self) -> bool:
        """ is x axes linked with View Airfoil"""
        return self._link_x
    def set_link_x (self, aBool):
        """ link x axes to View Airfoil"""
        self._link_x = aBool is True
        if self.link_x:
            self.setXLink(Airfoil_Diagram_Item.name)
        else: 
            self.setXLink(None)


    def refresh (self):
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
            CheckBox (l,r,c, text=f"X axes linked to '{Airfoil_Diagram_Item.name}'", 
                    get=lambda: self.link_x, set=self.set_link_x) 
            r += 1
            CheckBox (l,r,c, text="Y axes log scale", 
                    get=lambda: self.logMode,
                    set=self.set_logMode) 
            r += 1
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (header=self.name, layout=l, 
                                              height=200, switchable=True, switched=False, on_switched=self.setVisible)

        return self._section_panel 


    def _set_range (self):
        """ set range of axes"""

        if self.logMode: 
            self.setLogMode (y=True)
            self.viewBox.setYRange(-1, 3)    # this is the exponent 
        else: 
            self.setLogMode (y=False)
            self.viewBox.setYRange(-2.0, 2.0)



class Airfoil_Diagram (Diagram):
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

    @property
    def airfoil_ref1 (self) -> Airfoil:
        return self._airfoil_ref1
    def set_airfoil_ref1 (self, airfoil: Airfoil | None = None): 
        self._airfoil_ref1 = airfoil 
        if airfoil: airfoil.set_usedAs (REF1)
        self.refresh ()


    @property
    def airfoil_ref2 (self) -> Airfoil:
        return self._airfoil_ref2
    def set_airfoil_ref2 (self, airfoil: Airfoil | None = None): 
        self._airfoil_ref2 = airfoil 
        if airfoil: airfoil.set_usedAs (REF2)
        self.refresh ()


    @property
    def show_airfoils_ref (self) -> bool: 
        return self._show_airfoils_ref
    def set_show_airfoils_ref (self, aBool : bool): 
        self._show_airfoils_ref = aBool is True 
        self.refresh ()
   

    def airfoils (self) -> list[Airfoil]: 
        airfoils = self.data_list()

        if self.show_airfoils_ref:
            if self.airfoil_ref1 is not None: airfoils.append(self.airfoil_ref1)
            if self.airfoil_ref2 is not None: airfoils.append(self.airfoil_ref2)

        return airfoils


    def create_diagram_items (self):
        """ create all plot Items and add them to the layout """

        item = Airfoil_Diagram_Item (self, getter=self.airfoils, show=True)
        self._add_item (item, 0, 0)

        item = Curvature_Diagram_Item (self, getter=self.airfoils, show=False)
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

            self._section_panel = Edit_Panel (header="Reference Airfoils", layout=l, height=100,
                                              switchable=True, switched=False, on_switched=self.set_show_airfoils_ref)

        return self._section_panel 
