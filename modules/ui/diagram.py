#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

All abstract diagram items to build a complete diagram view 

"""

import logging

from PyQt6.QtCore       import QSize, QMargins, pyqtSignal
from PyQt6.QtWidgets    import QLayout, QGridLayout, QVBoxLayout, QHBoxLayout, QGraphicsGridLayout
from PyQt6.QtWidgets    import QMainWindow, QWidget, QWidgetItem
from PyQt6.QtGui        import QPalette

import pyqtgraph as pg # import PyQtGraph after PyQt6

from ui.widgets         import Widget, Label
from ui.panels          import Edit_Panel


class Diagram (QWidget):
    """ 
    Abstract container panel/widget which may hold
     - serveral PlotItems 
     - each having optional view panel sections (to the left) 

    see: https://pyqtgraph.readthedocs.io/en/latest/getting_started/plotting.html

    """

    @staticmethod
    def refresh_childs (parent: QWidget):
        """ refresh all childs of parent"""
        p : Diagram
        for p in parent.findChildren (Diagram):
            p.refresh() 


    width  = (800, None)                # (min,max) 
    height = (400, None)                # (min,max)

    def __init__(self, parent, getter = None, **kwargs):
        super().__init__(parent, **kwargs)

        self._getter = getter
        self._myApp  = parent
        self._section_panel = None 

        # create graphics widget 

        self._graph_widget = pg.GraphicsLayoutWidget (parent=self, show=True, size=None, title=None)
        self._graph_layout.setContentsMargins (20,20,20,10)  # default margins

        # create all plot items and setup layout with them  

        self.create_diagram_items () 

        #  add a message view box at bottom   

        self._message_vb = pg.ViewBox()
        self._graph_layout.addItem (self._message_vb, 5, 0)
        self._message_vb.hide()
    

        # create optional view panel add the left side 

        self._viewPanel   = None
        self.create_view_panel ()

        # build layout with view panel and graphics

        l_main = QHBoxLayout()
        l_main.setContentsMargins (QMargins(0, 0, 0, 0))
        # l_main.setSpacing (0)

        if self._viewPanel is not None: 
            l_main.addWidget (self._viewPanel)
        l_main.addWidget (self._graph_widget, stretch=10)

        self.setLayout (l_main)

        
    def data_list (self): 
        # to be overloaded - or implemented with semantic name   

        if callable(self._getter):
            obj = self._getter()
        else: 
            obj = self._getter     

        return obj if isinstance (obj, list) else [obj]


    @property
    def myApp (self): 
        return self._myApp
    
    @property
    def diagram_items (self) -> list['Diagram_Item']:
        """ list of my diagram items """
        items = []
        for i in range (self._graph_layout.count()):
            item = self._graph_layout.itemAt(i)
            if isinstance (item, Diagram_Item):
                items.append (item)
        return items

    @property
    def diagram_items_visible (self) -> list['Diagram_Item']:
        """ list of my visible diagram items """
        return [item for item in self.diagram_items if item.isVisible()]


    @property 
    def _graph_layout (self) -> QGraphicsGridLayout:
        """ returns QLayout of self"""
        return self._graph_widget.ci.layout


    @property
    def section_panel (self):
        """ small section panel representing self in view panel"""
        # overload for constructor 
        return  self._section_panel
    

    def refresh(self): 
        """ refresh all childs (Diagram_Items) of self"""
        item : Diagram_Item
        for item in self.diagram_items:
            item.refresh() 


    def create_diagram_items ():
        """ create all plot Items and add them to the layout """
        # to be overlaoded 
        # like ... 
        #   item = Airfoil_Diagram_Item (self, getter=self.airfoil)
        #   self._add_item (item, 0, 0)
        pass


    def _add_item (self, anItem: 'Diagram_Item', row, col):
        """ adds a diagram item to self graphic layout """

        self._graph_widget.addItem (anItem, row, col)

        anItem.sig_visible.connect (self._on_item_visible)


    def create_view_panel (self):
        """ 
        creates a view panel to the left of at least one diagram item 
        has a section_panel
        """

        # build side view panel with the section panels 

        layout = QVBoxLayout()
        layout.setContentsMargins (QMargins(0, 0, 0, 0)) 
        for item in self.diagram_items:
            if item.section_panel is not None: 
                layout.addWidget (item.section_panel,stretch=1)

        # add section panel of self (master) 

        if self.section_panel is not None: layout.addWidget (self.section_panel,stretch=1)
        
        layout.addStretch (1)

        self._viewPanel = QWidget()
        self._viewPanel.setMinimumWidth(180)
        self._viewPanel.setMaximumWidth(250)
        self._viewPanel.setLayout (layout)


    def _on_item_visible (self, anItem, aBool):
        """ slot to handle switch on/off of diagram items"""

        nItems = len(self.diagram_items_visible)

        if nItems == 0: 
            text = pg.TextItem("No diagram items selected ", anchor=(0.5,0))
            self._message_vb.addItem (text)
            self._message_vb.show()
            text.setPos(0, 0)
        # the GraphicsLayout gets confused, if all items were switched off
        #     and then switched on again - recalc layout
        if aBool: 
            if nItems == 1:
                self._message_vb.clear()
                self._message_vb.hide()
 
                self.adjustSize ()





class Diagram_Item (pg.PlotItem):
    """ 
    Abstract PlotItem  

    see: https://pyqtgraph.readthedocs.io/en/latest/getting_started/plotting.html

    """

    name = "Abstract Diagram_Item"              # used for link and section header

    # Signals 
    sig_visible = pyqtSignal(object, bool)      # when self is set to show/hide 


    def __init__(self, parent, 
                 getter = None, 
                 show = True,                   # show initially 
                 **kwargs):

        super().__init__(name=self.name,        # to link view boxes 
                         **kwargs)

        self._parent : Diagram = parent
        self._getter = getter
        self._show   = show 
        self._section_panel = None 

        # initial show or hide 
        self.setVisible (show) 


    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        text = '' 
        return f"<{type(self).__name__}{text}>"
    

    def setVisible (self, aBool):
        """ Qt overloaded to signal parent """
        super().setVisible (aBool)
        self.sig_visible.emit (self, aBool)

    @property
    def viewBox (self) -> pg.ViewBox:
        """ viewBox of self""" 
        return self.getViewBox()

    def data_object (self): 
        # to be ooverloaded - or implemented with semantic name 
        if callable(self._getter):
            return self._getter()
        else: 
            return self._getter


    def data_list (self): 
        # to be overloaded - or implemented with semantic name        
        if isinstance (self.data_object(), list):
            return self.data_object()
        else: 
            return [self.data_object()]   


    def refresh (self): 
        """ refresh self"""
        # must be implmented by subclass
        pass

    @property
    def section_panel (self):
        """ small section panel representing self in view panel"""
        # overload for constructor 
        return  self._section_panel
    

    def _create_section_panel (self) -> Edit_Panel:
        """ 
        Create small section panel representing self in view panel
        
        The existence of a section_panel controls that 
        diagram will have a view panel 
        """

        self._section_panel = self.get_section_panel ()

        # connect to show switch signal of section panel 
        if self._section_panel:
            self._section_panel.sig_switched.connect (self.setVisible )

        return None 

