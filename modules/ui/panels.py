#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Higher level ui components / widgets like Edit_Panel, Diagram 

"""

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

from PyQt6.QtCore       import Qt
from PyQt6.QtCore       import QSize, QMargins, pyqtSignal 
from PyQt6.QtWidgets    import QLayout, QGridLayout, QVBoxLayout, QHBoxLayout, QGraphicsGridLayout
from PyQt6.QtWidgets    import QMainWindow, QWidget
from PyQt6.QtGui        import QPalette, QColor

from ui.widgets         import set_background
from ui.widgets         import Widget, Label, CheckBox, size



#-------------------------------------------


class Panel (QWidget):
    """ 
    Superclass for all types of panels like Edit, Diagram 
    """

    name = "Abstract Panel"             # will be title 

    _width  = None
    _height = None 

    @staticmethod
    def refresh_childs (parent: QWidget, disable=None):
        """ refresh all childs of parent"""
        p : Panel
        for p in parent.findChildren (Panel):
            p.refresh(disable=disable) 


    def __init__(self, parent = None, 
                 getter = None, 
                 width=None, 
                 height=None, 
                 header=None,
                 **kwargs):
        super().__init__(parent, **kwargs)

        self._getter = getter
        self._parent = parent

        if width is not None: 
            self._width = width
        if height is not None: 
            self._height = height

        if header is not None: 
            self.name = header 

        # set size limits 
        self._set_height (self._height)
        self._set_width  (self._width)


    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        return f"<Panel '{self.name}'>"


    @property
    def dataObject (self): 
        # to be ooverloaded - or implemented with semantic name 
        if callable(self._getter):
            return self._getter()
        else: 
            return self._getter
    
    def _set_height (self, height):
        """ set self min/max height """
        if isinstance (height, tuple):
            min_height = height[0]
            max_height = height[1]
        else:
            min_height = height
            max_height = height
        if min_height: self.setMinimumHeight(min_height)
        if max_height: self.setMaximumHeight(max_height)        

    def _set_width (self, width):
        """ set self min/max width """
        if isinstance (width, tuple):
            min_width = width[0]
            max_width = width[1]
        else:
            min_width = width
            max_width = width
        if min_width: self.setMinimumWidth(min_width)
        if max_width: self.setMaximumWidth(max_width)


    def refresh (parent: QWidget, disable=None):
        """ refresh all child panels self"""
        p : Panel
        for p in parent.findChildren (Panel):
            p.refresh(disable=disable) 



class Edit_Panel (Panel):
    """ 
    Abstract superclass for the edit like panels 
    """

    _height = (150, None) 

    # Signals 
    sig_switched = pyqtSignal(bool)


    def __init__(self, *args, 
                 layout : QLayout | None = None,
                 switchable : bool = False,
                 switched : bool = True, 
                 on_switched = None, 
                 hide_switched : bool = True,
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._switchable = switchable
        self._hide_switched = hide_switched
        self._switched_on = switched

        l_panel = layout 

        # set background color - save the original one 

        set_background (self, darker_factor = 105)
        self._palette_sav = self.palette()          # save this current color palette 

        # header layout - with optional on/off switch 

        self._head = QWidget(self)
        l_head = QHBoxLayout(self._head)
        l_head.setContentsMargins (QMargins(0,0,0,5))

        if self._switchable:
            CheckBox (l_head, fontSize=size.HEADER, text=self.header_text(),
                      get=lambda: self.switched_on, set=self.set_switched_on)
            if on_switched is not None: 
                self.sig_switched.connect (on_switched)
        else: 
            Label (l_head, fontSize=size.HEADER, get=self.header_text)

        self._add_to_header_layout (l_head)     # optional individual widgets
 
        # inital content panel content - layout in >init  

        self._panel  = QWidget() 

        if l_panel is None: l_panel = self._init_layout()       # subclass will create layout 

        if l_panel is None: 
            logger.warning (f"{self.name}: Layout for panel still missing ")
        else: 
            l_panel.setContentsMargins (QMargins(15, 0, 0, 0))   # inset left 
            l_panel.setSpacing(2)
            self._panel.setLayout (l_panel)
            # set_background (self._panel, darker_factor=150)

        # main layout with header and panel 

        l_main   = QVBoxLayout()
        l_main.addWidget (self._head)
        l_main.addWidget (self._panel)
        l_main.setContentsMargins (QMargins(10, 1, 15, 5))
        l_main.setSpacing(2)
        self.setLayout (l_main)

        # initial switch state 
        self.set_switched_on (self._switched_on, initial=True)


    def header_text (self) -> str: 
        """ returns text of header - default self.name"""
        # can be overwritten 
        return self.name 

    @property 
    def switched_on (self) -> bool:
        """ True if self is switched on"""
        return self._switched_on
    
    def set_switched_on (self, aBool : bool, initial=False):
        """ switch on/off 
            - optional hide main panel 
            - emit sig_switched
        """
        self._switched_on = aBool is True 
        
        if self._hide_switched:
            self._panel.setVisible (self.switched_on)

            if self.switched_on:
                self._set_height (self._height)
            else: 
                self._set_height (40)

        # signal to Diagram_Item - but not during init 
        if not initial: 
            self.sig_switched.emit (self._switched_on)


    @property
    def widgets (self) -> list[Widget]:
        """ list of widgets defined in self """
        return self.findChildren (Widget)   # options=Qt.FindChildOption.FindDirectChildrenOnly
 

    def refresh(self, disable=None):
        """ refreshes all Widgets on self """
        for w in self.widgets:
            w.refresh(disable=disable)
        logger.debug (f"{self} - refresh")


    def set_enabled_widgets (self, aBool):
        """ enable / disable all widgets of self - except Labels (color!) """

        w : Widget
        for w in self.widgets:
            if not isinstance (w, Label):       # label would become grey 
                w.set_enabled (aBool) 


    def set_background_color (self, darker_factor : int | None = None,
                                    color : QColor | int | None  = None,
                                    alpha : float | None = None):
        """ 
        Set background color of a QWidget either by
            - darker_factor > 100  
            - color: QColor or string for new color
            - alpha: transparency 0..1 
        """

        set_background (self, darker_factor=darker_factor, color=color, alpha=alpha)

    def reset__background_color (self): 
        """ reset background to color after __init__"""
        self.setPalette (self._palette_sav)


    def _init_layout(self) -> QLayout:
        """ init and return main layout"""

        # to be implemented by sub class
        pass


    def _add_to_header_layout(self, l_head : QHBoxLayout) -> QLayout:
        """ add Widgets to header layout"""

        # to be implemented by sub class
        pass



# ------------------------------------------------------------------------------
# ------------ test functions - to activate  -----------------------------------
# ------------------------------------------------------------------------------

class Test_Panel (Edit_Panel):

    name = "Airfoil Data"
    width  = (100, 140)
    height = (100, None)

    def _init_layout (self)-> QLayout: 
        l = QGridLayout()
        Label  (l,0,0,get="Ein Label")
        return l 


class Test_Panel2 (Edit_Panel):

    name   = "Curvature"
    width  = (150, None)
    height = (200, None)

    def _init_layout (self) -> QLayout: 
        from widgets import FieldI
        l = QGridLayout()
        r = 0 
        Label  (l,0,0, colSpan=2, get="Ein Läbele extra lang")
        r += 1
        Label  (l,r,0,get="Weight", width=70)
        FieldI (l,r,1,get=15, lim=(0,100), unit="kg", step=1, width=(70,90)) # (70, 90)
        r += 1
        Label  (l,r,0,get="Span")
        FieldI (l,r,1,get="2980", lim=(0,9999), unit="mm", step=10, width=(100, None))

        l.setColumnStretch (1,3)
        l.setColumnStretch (2,1)
        l.setRowStretch (r+1,1)
        return l 


class Test_Panels (QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle('Test Edit_Panel')
        self.setMinimumSize(QSize(400, 200))

        air_panel  = Test_Panel  (self) 
        curv_panel = Test_Panel2 (self) 

        container = QWidget()
        l = QHBoxLayout ()
        l.addWidget (air_panel) 
        l.addWidget (curv_panel)
        container.setLayout (l)  

        self.setCentralWidget(container)


if __name__ == "__main__":

    from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout
    # logging.basicConfig(level=logging.DEBUG)
 
    app = QApplication([])
    app.setStyle('fusion')
    app.setStyleSheet ("QWidget { font-family: 'Roboto' }")

    w = Test_Panels()
    w.show()
    app.exec() 
