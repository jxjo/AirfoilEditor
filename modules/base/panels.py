#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Higher level ui components / widgets like Edit_Panel, Diagram 

"""

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

from copy               import copy

from PyQt6.QtCore       import Qt
from PyQt6.QtCore       import QSize, QMargins, pyqtSignal 
from PyQt6.QtWidgets    import QLayout, QGridLayout, QVBoxLayout, QHBoxLayout, QGraphicsGridLayout
from PyQt6.QtWidgets    import QMainWindow, QWidget, QDialog, QDialogButtonBox, QLabel
from PyQt6.QtGui        import QPalette, QColor, QShowEvent
from PyQt6              import sip

from base.widgets       import set_background
from base.widgets       import Widget, Label, CheckBox, size, Button, FieldI, SpaceR



#-------------------------------------------

class Panel (QWidget):
    """ 
    Just a plain Panel - as container for other Edit_Panels
    Superclass for other types of panels like Edit
        - handle size of widget  
        - having title / header name 
        - has dataObject via getter (callable) 
    """

    name = "Panel"             # will be title 

    _width  = None
    _height = None 


    def __init__(self,  
                 parent=None,
                 getter = None, 
                 width=None, 
                 height=None, 
                 title=None, **kwargs):
        super().__init__(parent=parent, **kwargs)

        self._parent = parent
        self._getter = getter

        if width is not None: 
            self._width = width
        if height is not None: 
            self._height = height

        # set width and height 
        Widget._set_width  (self, self._width)
        Widget._set_height (self, self._height)

        if title is not None: 
            self.name = title 


    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        return f"<Panel '{self.name}'>"


    @property
    def dataObject (self): 
        # to be overloaded - or implemented with semantic name 
        if callable(self._getter):
            return self._getter()
        else: 
            return self._getter

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


    def refresh_panels (parent: QWidget):
        """ refresh all child Panels self"""
        p : Edit_Panel
        for p in parent.findChildren (Panel):
            p.refresh() 


#-------------------------------------------


class Edit_Panel (Panel):
    """ 
    Panel with a title and an optional on/off switch 
    having a layout area for content  
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

        # set background color  

        self.set_background_color (darker_factor = 105)

        # title layout - with optional on/off switch 

        self._head = QWidget(self)
        l_head = QHBoxLayout(self._head)
        l_head.setContentsMargins (QMargins(0,0,0,5))

        if self._switchable:
            CheckBox (l_head, fontSize=size.HEADER, text=self.title_text(),
                      get=lambda: self.switched_on, set=self.set_switched_on)
            if on_switched is not None: 
                self.sig_switched.connect (on_switched)
        else: 
            Label (l_head, fontSize=size.HEADER, get=self.title_text)

        self._add_to_header_layout (l_head)     # optional individual widgets
 
        # inital content panel content - layout in >init  

        self._panel  = QWidget() 
        self._set_panel_layout (layout=layout) 

        # main layout with title and panel 

        l_main   = QVBoxLayout()
        l_main.addWidget (self._head)
        l_main.addWidget (self._panel, stretch=2)
        l_main.setContentsMargins (QMargins(10, 5, 15, 5))
        l_main.setSpacing(2)
        self.setLayout (l_main)

        # initial switch state 
        self.set_switched_on (self._switched_on, initial=True)

        # initial enabled/disabled state
        self.refresh_widgets (self._isDisabled) 

        # initial visibility 
        if not self._shouldBe_visible:         
            self.setVisible (False)             # setVisible(True) results in a dummy window on startup 



    def title_text (self) -> str: 
        """ returns text of title - default self.name"""
        # can be overwritten 
        return self.name 


    @property 
    def _shouldBe_visible (self) -> bool:
        """ True if self is visible - can be overloaded """
        return True


    @property 
    def _isDisabled (self) -> bool:
        """ True if the widgets of self are disabled  - can be overloaded """
        return False


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
                Widget._set_height (self, self._height)
            else: 
                Widget._set_height (self, 40)

        # signal to Diagram_Item - but not during init 
        if not initial: 
            self.sig_switched.emit (self._switched_on)


    @property
    def widgets (self) -> list[Widget]:
        """ list of widgets defined in self panel area"""
        return self._panel.findChildren (Widget)   # options=Qt.FindChildOption.FindDirectChildrenOnly


    @property
    def header_widgets (self) -> list[Widget]:
        """ list of widgets defined in self panel area"""
        return self._head.findChildren (Widget)   # options=Qt.FindChildOption.FindDirectChildrenOnly
 

    def refresh(self, reinit_layout=False):
        """ refreshes all Widgets on self """

        # reinit layout if visbility changed or if requested
        reinit_layout = (self._shouldBe_visible != self.isVisible()) or reinit_layout

        # logger.debug (f"{self} - refresh - reinit_layout: {reinit_layout}")

        if reinit_layout:

            self._set_panel_layout () 
            # hide / show self 
            self.setVisible (self._shouldBe_visible)
            logger.debug (f"{self} - setVisible({self._shouldBe_visible})")

        # refresh widgets of self only if visible 
        if self._shouldBe_visible:
            self.refresh_widgets (self._isDisabled)


    def refresh_widgets (self, disable : bool):
        """ enable / disable all widgets of self - except Labels (color!) """

        w : Widget
        for w in self.widgets:
            w.refresh (disable=disable)

        # refresh also header 
        for w in self.header_widgets:
            w.refresh (disable=disable)


    def _set_panel_layout (self, layout = None ):
        """ 
        Set layout of self._panel   
            - typically defined in subclass in _init_layout
            - or as init argument 'layout'"""

        # remove existing layout with all its content 
        if self._panel.layout():
            self._clear_existing_panel_layout ()

        if layout is None:
            if self._shouldBe_visible:
                layout = self._init_layout()        # subclass will create layout 
            else: 
                # if the panel shouldn't be visible repalce the normal panel layout
                # with a dummy, so get/set of the normal panel widgets won't get trouble 
                layout = QVBoxLayout()               
                wdt = QLabel ("This shouldn't be visible")
                layout.addWidget (wdt)

        layout.setContentsMargins (QMargins(15, 0, 0, 0))   # inset left 
        layout.setSpacing(2)
        self._panel.setLayout (layout)


    def _clear_existing_panel_layout(self):
        """ removes all items from the existing panel layout"""
        layout = self._panel.layout()
        if layout is not None: 
            while layout.count():
                child = layout.takeAt(0)
                childWidget = child.widget()
                if childWidget:
                    childWidget.setParent(None)
                    childWidget.deleteLater()
        # finally remove self 
        sip.delete (self._panel.layout())


    def _init_layout(self) -> QLayout:
        """ init and return main layout"""

        # to be implemented by sub class
        pass


    def _add_to_header_layout(self, l_head : QHBoxLayout) -> QLayout:
        """ add Widgets to header layout"""

        # to be implemented by sub class
        pass


# ------------ Dialog  -----------------------------------

class Dialog (QDialog):

    name = "Dialog"             # will be title 

    _width  = None
    _height = None 


    def __init__(self,  
                 parent=None,
                 getter = None, 
                 width=None, 
                 height=None, 
                 title=None, **kwargs):
        super().__init__(parent=parent, **kwargs)

        self._parent = parent
        self._getter = getter

        self._dataObject_copy = copy (self.dataObject)

        if width is not None: 
            self._width = width
        if height is not None: 
            self._height = height

        # set width and height 
        Widget._set_width  (self, self._width)
        Widget._set_height (self, self._height)

        if title is not None: 
            self.name = title 

        self.setWindowTitle (self.name)

        # inital content panel content - layout in >init  

        self._panel = QWidget () 
        self.set_background_color (darker_factor=105)

        l_panel = self._init_layout()       # subclass will create layout 
        l_panel.setContentsMargins (QMargins(15, 10, 15, 10))   # inset left 
        # l_panel.setSpacing(2)
        self._panel.setLayout (l_panel)

        # Qt buttonBox at footer

        l_button = QHBoxLayout()
        l_button.addWidget(self._button_box())
        l_button.setContentsMargins (QMargins(5, 0, 25, 0))
        # set_background (buttonBox, darker_factor=120)

 
        # main layout with title and panel 

        l_main   = QVBoxLayout()
        l_main.addWidget (self._panel, stretch=1)
        l_main.addLayout (l_button)
        l_main.setContentsMargins (QMargins(5, 5, 5, 15))
        l_main.setSpacing(15)
        self.setLayout (l_main)

        # connect to change signal of widget 
        for w in self.widgets:
            w.sig_changed.connect (self._on_widget_changed)


    def set_background_color (self, darker_factor : int | None = None,
                                    color : QColor | int | None  = None,
                                    alpha : float | None = None):
        """ 
        Set background color of a QWidget either by
            - darker_factor > 100  
            - color: QColor or string for new color
            - alpha: transparency 0..1 
        """
        set_background (self._panel, darker_factor=darker_factor, color=color, alpha=alpha)


    def _init_layout(self) -> QLayout:
        """ init and return main layout"""

        # to be implemented by sub class
        return QVBoxLayout ()

    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""
        buttons = QDialogButtonBox.StandardButton.Ok | \
                  QDialogButtonBox.StandardButton.Cancel
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        return buttonBox 

    def _QButtons (self):
        """return QButtons enum for button box at footer """
        # to overload 
        return QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel


    @property
    def dataObject (self): 
        """ dataObject the dialog got from parent """
        # to be overloaded - or implemented with semantic name 
        if callable(self._getter):
            return self._getter()
        else: 
            return self._getter

    @property
    def dataObject_copy (self): 
        """ shallow copy of dataObject"""
        # to be overloaded - or implemented with semantic name 
        return self._dataObject_copy

    @property
    def widgets (self) -> list[Widget]:
        """ list of widgets defined in self """
        return self.findChildren (Widget)   # options=Qt.FindChildOption.FindDirectChildrenOnly
 
    def _on_widget_changed (self,*_):
        """ slot for change of widgets"""
        # to be overloaded 
        pass


    def button_clicked (self, aButton): 
        """ slot for button of buttonbox clicked. Can be overriden"""
        pass


    def refresh(self, disable=None):
        """ refreshes all Widgets on self """

        for w in self.widgets:
            w.refresh(disable=disable)
        logger.debug (f"{self} - refresh")



# ------------------------------------------------------------------------------
# ------------ test functions - to activate  -----------------------------------
# ------------------------------------------------------------------------------

class Test_Panel (Edit_Panel):

    name = "Airfoil Data"
    _width  = 200
    _height = (100, None)

    def _init_layout (self)-> QLayout: 
        l = QGridLayout()
        Label  (l,0,0,get="Ein Label")
        Button (l,2,0, text= "Open dialog", set=self._open_dialog)
        l.setRowStretch (0,1)
        return l 

    def _open_dialog (self):

        dlg = Test_Dialog(parent=self, title="mein Titel", height=400, width=600)
        dlg.exec ()


class Test_Dialog (Dialog):

    def _init_layout(self) -> QLayout:
        l = QGridLayout()
        Label  (l,0,0,get="Hallo Dialog")
        SpaceR (l,1)
        Label  (l,2,0,get="ganz unten")
        l.setRowStretch (1,1)
        return l 


class Test_Panel2 (Edit_Panel):

    name   = "Curvature"
    _width  = 200
    _height = (200, None)

    def _init_layout (self) -> QLayout: 
        l = QGridLayout()
        r = 0 
        Label  (l,0,0, colSpan=2, get="Ein Läbele extra lang")
        r += 1
        Label  (l,r,0,get="Weight", width=70)
        FieldI (l,r,1,get=15, lim=(0,100), unit="kg", step=1, width=(70,90)) # (70, 90)
        r += 1
        Label  (l,r,0,get="Span")
        FieldI (l,r,1,get="2980", lim=(0,9999), unit="mm", step=10, width=(100, None))
        r+= 1
        SpaceR (l,r)
        l.setColumnStretch (1,3)
        l.setColumnStretch (2,1)
        l.setRowStretch (r, 1)
        return l 


class Test_Panels (QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle('Test Edit_Panel')
        self.setMinimumSize(QSize(400, 200))

        air_panel  = Test_Panel  (self) 
        curv_panel = Test_Panel2 (self, switchable=True,hide_switched=True) 

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
    app.setStyleSheet ("QWidget { font-family: 'Segoe UI' }")

    w = Test_Panels()
    w.show()
    app.exec() 
