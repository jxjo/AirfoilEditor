#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Higher level ui components / widgets like Edit_Panel, Diagram 

"""

import os

from copy               import copy
from typing             import override, Callable

from PyQt6.QtCore       import Qt, QEvent, QPoint, QRectF
from PyQt6.QtCore       import QSize, QMargins, QTimer, QPropertyAnimation, QAbstractAnimation
from PyQt6.QtWidgets    import (QLayout, QGridLayout, QVBoxLayout, QHBoxLayout, QSizePolicy,
                                QWidget, QDialog, QDialogButtonBox, QLabel, QMessageBox, QFrame,
                                QGraphicsOpacityEffect, QTabWidget)
from PyQt6.QtGui        import QGuiApplication, QScreen, QColor, QPalette, QPainterPath, QRegion, QTransform
from PyQt6              import sip

from .widgets           import set_background, style
from .widgets           import Widget, Label, CheckBox, size, Icon

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


#------------------------------------------------------------------------------
# Utils for QMainWindow and QDialog  
#------------------------------------------------------------------------------

class Win_Util: 
    """ 
    Utility functions for window handling 
    """

    @staticmethod
    def set_initialWindowSize (qwindow : QWidget,
                               size : tuple | None = None,
                               size_frac : tuple | None = None,
                               pos : tuple | None = None,
                               pos_frac: tuple | None = None,
                               geometry : tuple | None = None,
                               maximize : bool = False):
        """
        Set size and position of Qt window in fraction of screensize or absolute
        """

        # geometry argument has priority 

        if geometry: 
            qwindow.setGeometry (*geometry)
            if maximize:
                qwindow.showMaximized()
            return
        else:  
            x, y, width, height = None, None, None, None
 
        # set size 

        if size_frac: 

            screen : QScreen = QGuiApplication.primaryScreen()
            screenGeometry = screen.geometry()
 
            width_frac, height_frac  = size_frac

            if width_frac:   width  = screenGeometry.width()  * width_frac
            if height_frac:  height = screenGeometry.height() * height_frac

        if size:
            width, height = size

        width  = int (width)  if width  is not None else 1000
        height = int (height) if height is not None else  700
        
        qwindow.resize (QSize(width, height))

        if maximize: 
            qwindow.showMaximized()

        # set position 

        if pos: 
            x, y = pos

        if pos_frac: 

            screen : QScreen = QGuiApplication.primaryScreen()
            screenGeometry = screen.geometry()
 
            x_frac = pos_frac[0]
            y_frac = pos_frac[1]
            if x_frac: x = screenGeometry.width()  * x_frac
            if y_frac: y = screenGeometry.height() * y_frac

        x = int (x) if x  is not None else 200
        y = int (y) if y is not None else  200
        
        qwindow.move (x, y)



#------------------------------------------------------------------------------
# Panels - QWidgets like a field group within a context 
#------------------------------------------------------------------------------


class Panel_Abstract (QWidget):
    """ 
    Superclass for other types of panels like Edit or Container
        - handle size of widget  
        - having title / header name 
        - has dataObject via getter (callable) 
    """

    name = "Panel"                          # will be title 

    _width  = None
    _height = None 

    _n_doubleClick = 0                      # no of double clicks - common counter for all panels
    _doubleClick_hint : str|None = None     # hint for double click at the end of box layout for all panels


    # ------------------------------------------------------

    @staticmethod
    def widgets_of_layout  (layout: QLayout) -> list[Widget]:
        """ list of Widgets defined in layout"""

        # iterate over layout - not self._panel.findChildren (Widget) as widgets are "deleted later"
        #       and can still exist although they are no more in the layout 

        widgets = []
        if isinstance (layout,QLayout): 
            for i in range(layout.count()):
                widget = layout.itemAt(i).widget()
                if isinstance (widget, Widget):                
                    widgets.append(widget)
                elif isinstance (widget,QWidget):                       # could be helper QWidget with seperate layout
                    widgets.extend (Panel_Abstract.widgets_of_layout (widget.layout()))
        return widgets


    @staticmethod
    def panels_of_layout  (layout: QLayout) -> list['Edit_Panel']:
        """ list of first level Edit_Panels defined in layout"""

        # iterate over layout - not self._panel.findChildren (Widget) as widgets are "deleted later"
        #       and can still exist although they are no more in the layout 

        panels = []
        if isinstance (layout,QLayout): 
            for i in range(layout.count()):
                widget = layout.itemAt(i).widget()
                if isinstance (widget, Edit_Panel):                
                    panels.append(widget)
        return panels


    # ------------------------------------------------------

    def __init__(self,  
                 app = None,
                 getter : Callable|None = None,                 # data object or callable returning it
                 width : int|None = None, 
                 height : int|None = None, 
                 hide : Callable|bool|None = None,              # either callable or bool
                 doubleClick: Callable|None = None,             # callable when doubleClick event occurs
                 hint : str|None = None,                        # hint for double click at the end of box layout
                 title=None, **kwargs):                         # title of panel (default self.name)

        super().__init__( **kwargs)

        self._app = app
        self._getter = getter

        if width is not None: 
            self._width = width
        if height is not None: 
            self._height = height

        # handle visibility  
        self._shouldBe_visible = True                               # default visibility of self 
        self._hidden_fn = None                                      # altern. callable to set visibility
        if isinstance(hide, bool):
            self._shouldBe_visible = not hide
        elif callable (hide):
            self._hidden_fn = hide

        # set width and height 
        Widget._set_width  (self, self._width)
        Widget._set_height (self, self._height)

        if title is not None: 
            self.name = title 

        # handle double click event
        self._doubleClick : callable|None = doubleClick
        self._doubleClick_hint_widget : Label | None = None
        Panel_Abstract._doubleClick_hint : str|None = hint          # class variable - common for all instances


    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        name = self.name if self.name else type(self).__name__
        return f"<Panel '{name}'>"


    @override
    def mouseDoubleClickEvent(self, event):
        """ default double click event - call self._doubleClick if defined"""

        if callable(self._doubleClick):
            Panel_Abstract._n_doubleClick += 1                  # count no of double clicks
            if Panel_Abstract._n_doubleClick == 2:              # remove hint when user learned to doubleclick
                Panel_Abstract._doubleClick_hint = None         # class variable - common for all instances
            if self._doubleClick_hint_widget:
                self._doubleClick_hint_widget.refresh()

            self._doubleClick()                                 # callback to parent
        else:
            super().mouseDoubleClickEvent(event)

    @property
    def dataObject (self): 
        # to be overloaded - or implemented with semantic name 
        if callable(self._getter):
            return self._getter()
        else: 
            return self._getter

    @property 
    def shouldBe_visible (self) -> bool:
        """ True if self should be visible 
            - can be overridden to control visibility in subclass """
        
        if callable (self._hidden_fn):
            self._shouldBe_visible = not self._hidden_fn ()
        return self._shouldBe_visible


    def set_visibilty (self, aBool : bool):
        """ 
        set the visibility of self 
            - use this, when instances of Edit_Panel are used (not subclassing)
              to control hide/show
        """

        if self._shouldBe_visible != aBool:
            self._shouldBe_visible = aBool        
            self.setVisible (aBool)     


    def set_doubleClick (self, doubleClick: Callable|None):
        """ set double click callable """
        self._doubleClick = doubleClick


    @property 
    def _isDisabled (self) -> bool:
        """ True if the widgets of self are disabled  - can be overloaded """
        return False

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


#-------------------------------------------

class Container_Panel (Panel_Abstract):
    """ 
    Panel as container for other (Edit) panels  
    """

    def __init__(self, *args, 
                 layout : QLayout | None = None,
                 margins  : tuple = (0,0,0,0), 
                 spacing : int = 5, 
                 **kwargs):
        super().__init__(*args, **kwargs)

        if layout:
            layout.setContentsMargins (QMargins(*margins))  
            layout.setSpacing (spacing) 
            self.setLayout (layout)

        # add hint for double click at the end of box layout

        if self._doubleClick_hint is not None:
            self.add_hint (self._doubleClick_hint)

        # initial visibility 

        if not self.shouldBe_visible:         
            self.setVisible (False)                     # setVisible(True) results in a dummy window on startup 


    def calc_min_width (self) -> int:
        """ calculate minimum width of self based on visible panels of self layout """

        layout = self.layout()

        # only QHBoxLayout supported here
        if not isinstance (layout, QHBoxLayout):
            return

        min_width = 0
        ncols = layout.count()
        ncols_filled = 0

        # loop over rows to find maximum row height
        for i in range(ncols):
            col_width = 0
            item = layout.itemAt(i)
            if item:
                qwidget = item.widget()
                if isinstance (qwidget, Panel_Abstract) and not qwidget.isHidden():
                    col_width = max(col_width, qwidget.width()) 
                elif isinstance (qwidget, Widget) and not qwidget.isHidden():
                    col_width = max(col_width, qwidget.minimumWidth()) 
                # print (f"panel {qwidget} width: {qwidget.width()} minWidth: {qwidget.minimumWidth()}" )
            min_width += col_width
            if col_width > 0:
                ncols_filled += 1

        # add horizontal spacings + margins
        margins = layout.contentsMargins()
        min_width = min_width + (ncols_filled-1) * layout.spacing() + margins.left() + margins.right()

        return min_width


    def add_hint (self, hint : str):
        """ add stretchable hint for double click at the end of layout """

        Panel_Abstract._doubleClick_hint = hint         # class variable - common for all instances
        l = self.layout()

        if self._doubleClick_hint_widget is not None:
            self._doubleClick_hint_widget.refresh()

        elif hint is not None and isinstance(l, (QHBoxLayout, QVBoxLayout)):
            w = Label (l, get=lambda: Panel_Abstract._doubleClick_hint, width=(1, None),
                      style=style.HINT, align=Qt.AlignmentFlag.AlignCenter)
            l.setStretch (l.count()-1,2)
            self._doubleClick_hint_widget = w

        self.setToolTip (hint)
              


    @property
    def edit_panels (self) -> list['Edit_Panel']:
        """ list of first level Edit_Panels defined in self"""

        return self.panels_of_layout (self.layout())


    def refresh (self):
        """ refresh all child Panels self"""

        show_now = self.isHidden () and self.shouldBe_visible

        self.setVisible (self.shouldBe_visible)

        if self.shouldBe_visible:

            # first hide the now not visible panels so layout won't be stretched
            for p in self.edit_panels:
                if not p.shouldBe_visible: p.refresh() 

            # now show the now visible panels - reinit layout if needed (with lazy there can be no layout yet)
            for p in self.edit_panels:
                reinit = show_now or (self.shouldBe_visible and p._panel.layout() is None)
                if p.shouldBe_visible: p.refresh (reinit_layout=reinit) 

            # refresh double click hint
            if self._doubleClick_hint_widget:
                self._doubleClick_hint_widget.refresh()
            if self.toolTip() != self._doubleClick_hint:
                self.setToolTip (self._doubleClick_hint)


class Edit_Panel (Panel_Abstract):
    """ 
    Panel with/out a title and an optional on/off switch 
    having a layout area for content  
    """

    _height = (None, None) 

    _main_margins  = (10, 5,10, 5)             
    _head_margins  = ( 0, 0, 0, 5)             
    _panel_margins = (10, 0, 0, 0)           

    def __init__(self, *args, 
                 layout : QLayout | None = None,
                 lazy = False, 
                 switchable : bool = False,
                 switched_on : bool = True, 
                 on_switched = None, 
                 hide_switched : bool = True,
                 has_head : bool = True,
                 auto_height : bool = False,                # if True fix min height after layout init
                 main_margins  : tuple = None,             
                 head_margins  : tuple = None,             
                 panel_margins : tuple = None,          
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._switchable = switchable
        self._hide_switched = hide_switched
        self._switched_on = switched_on
        self._on_switched = on_switched
        self._auto_height = auto_height

        self._head  = None
        self._panel = None

        self._main_margins  = main_margins  if isinstance(main_margins, tuple)  else self._main_margins
        self._head_margins  = head_margins  if isinstance(head_margins, tuple)  else self._head_margins   
        self._panel_margins = panel_margins if isinstance(panel_margins, tuple) else self._panel_margins

        # set background color depending light/dark mode

        if Widget.light_mode:
            self.set_background_color (darker_factor = 104)                 # make it darker 
        else: 
            self.set_background_color (darker_factor = 80)                  # make it lighter 

        # title layout - with optional on/off switch 

        if has_head and self.title_text() is not None: 

            self._head = QWidget(self)

            if not lazy: 
                self._set_header_layout ()

 
        # inital content panel content - layout in >init  

        self._panel  = QWidget() 
        self._initial_layout = layout 

        if not lazy: 
            self._set_panel_layout () 

        # main layout with title and panel 

        l_main   = QVBoxLayout()
        if self._head: 
            l_main.addWidget (self._head)
        l_main.addWidget (self._panel, stretch=1)
        l_main.setContentsMargins (QMargins(*self._main_margins))  
        l_main.setSpacing(2)
        self.setLayout (l_main)

        # initial switch state 
        self.set_switched_on (self._switched_on, silent=True)

        # initial enabled/disabled state
        if self._isDisabled: 
            self.refresh_widgets (self._isDisabled) 

        # initial visibility 
        if not self.shouldBe_visible:         
            self.setVisible (False)             # setVisible(True) results in a dummy window on startup 


    def title_text (self) -> str: 
        """ returns text of title - default self.name"""
        # can be overwritten 
        return self.name 

    @override
    def mouseDoubleClickEvent(self, a0):
        """ default double click event - toggle switch if switchable"""

        if self._switchable and not callable(self._doubleClick):
            self.toggle_switched()
        else:
            return super().mouseDoubleClickEvent(a0)


    @property 
    def switched_on (self) -> bool:
        """ True if self is switched on"""
        return self._switched_on
    
    def set_switched_on (self, aBool : bool, silent=False):
        """ switch on/off 
            - optional hide main panel 
            - option callback on_switched
        """
        self._switched_on = aBool is True 
        
        if self._hide_switched:
            self._panel.setVisible (self.switched_on)

            if self.switched_on:
                Widget._set_height (self, self._height)
            else: 
                Widget._set_height (self, 35)

        # refresh also header checkbox
        for w in self.header_widgets:
            w.refresh ()

        if not silent and callable (self._on_switched):                                          # set by checkbox - callback to Diagram_Item 
            self._on_switched (self._switched_on)


    def toggle_switched (self):
        """ toggle switched on/off """
        self.set_switched_on (not self.switched_on)

    @property
    def widgets (self) -> list[Widget]:
        """ list of Widgets defined in self panel area"""

        return self.widgets_of_layout (self._panel.layout())


    @property
    def header_widgets (self) -> list[Widget]:
        """ list of widgets defined in self header area"""

        if self._head: 
            return self.widgets_of_layout (self._head.layout())
        else: 
            return []
 

    def refresh(self, reinit_layout=False):
        """ refreshes all Widgets on self """

        hide = not self.shouldBe_visible and     self.isVisible()
        show =     self.shouldBe_visible and not self.isVisible()

        # hide / show self 

        if hide or show: 
            self.setVisible (self.shouldBe_visible)
            logger.debug (f"{self} - setVisible ({self.shouldBe_visible})")

        if self.shouldBe_visible: 

            # reinit layout 
            if show or reinit_layout:
                if self._head:
                    self._set_header_layout ()
                self._set_panel_layout () 
                logger.debug (f"{self} - refresh - reinit_layout: {reinit_layout} ")

            # refresh widgets of self only if visible 
            self.refresh_widgets (self._isDisabled)
            logger.debug (f"{self} - refresh widgets   disable: {self._isDisabled}")


    def refresh_widgets (self, disable : bool, reinit_layout=False):
        """ enable / disable all widgets of self - except Labels (color!) """

        for w in self.widgets:
            w.refresh (disable=disable)

        # refresh child edit panels like Polar_Panel
        for p in self.panels_of_layout (self._panel.layout()):
            p.refresh (reinit_layout=reinit_layout)

        # refresh also header 
        for w in self.header_widgets:
            w.refresh (disable=disable)


    def _set_header_layout(self):
        """ set layout of self._head 
            - with title text either checkbox or label
            - a subclass may add widgets to header layout in _add_to_header_layout
        """

        if self._head.layout(): return       # already set

        l_head = QHBoxLayout()
        l_head.setContentsMargins (*self._head_margins)

        if self._switchable:
            CheckBox (l_head, fontSize=size.HEADER, text=self.title_text(),
                    get=lambda: self.switched_on, set=self.set_switched_on,
                    toolTip='Show or hide -<br>Alternatively, you can double click on the panel')
        else: 
            Label (l_head, fontSize=size.HEADER, get=self.title_text)
        l_head.setStretch (0,1)

        self._add_to_header_layout (l_head)     # optional individual widgets

        # assign layout to head widget
        self._head.setLayout (l_head)



    def _set_panel_layout (self):
        """ 
        Set layout of self._panel   
            - typically defined in subclass in _init_layout
            - or as init argument 'layout'"""

        # remove and rebuild only in case of _init_layout done in a subclass

        if isinstance(self._initial_layout, QLayout):

            layout = self._initial_layout

        else:
            if self._panel.layout() is not None:
                self._clear_existing_panel_layout ()

            if self.shouldBe_visible:
                layout = self._init_layout()        # subclass will create layout 
            else: 
                # if the panel shouldn't be visible repalce the normal panel layout
                # with a dummy, so get/set of the normal panel widgets won't get trouble 
                layout = QVBoxLayout()               
                wdt = QLabel ("This shouldn't be visible")
                layout.addWidget (wdt)

        if layout:
            layout.setContentsMargins (QMargins(*self._panel_margins))   # inset left 

            # set default spacings 
            layout.setSpacing (2)
            if isinstance (layout, QGridLayout):
                layout.setVerticalSpacing(4)

            self._panel.setLayout (layout)

            # if height of panel to height of layout with all the widgets
            if self._auto_height:
                self._set_auto_height_panel ()


    def _clear_existing_panel_layout(self):
        """ removes all items from the existing panel layout"""
        layout = self._panel.layout()
        if layout is not None: 
            while layout.count():
                child = layout.takeAt(0)
                childWidget = child.widget()
                if childWidget:                
                    childWidget.deleteLater() # sip.delete (childWidget)
                sip.delete (child)
                # if childWidget:
                #     childWidget.disconnect()
                #     childWidget.setParent(None)
                #     sip.delete (childWidget)
                #     # childWidget.deleteLater()                             # will create ghost widget due to async event loop
            logger.debug (f"{self} - clear layout ")

            # finally remove self 
            sip.delete (self._panel.layout())


    def _set_auto_height_panel (self):
        """ fix minimum height of self._panel to nrows of widgets """

        layout = self._panel.layout()

        # only GridLayout supported here
        if not isinstance (layout, QGridLayout):
            return

        min_height = 0
        nrows = layout.rowCount()
        ncols = layout.columnCount()
        nrows_filled = 0

        # loop over rows to find maximum row height
        for row in range(nrows):
            row_height = 0
            for col in range(ncols):
                item = layout.itemAtPosition(row, col)
                if item:
                    widget = item.widget()
                    if isinstance (widget, Widget):
                        if not widget._hidden:
                            row_height = max(row_height, widget.height()) 
                    elif isinstance(widget, QWidget) and widget.isVisible():
                        row_height = max(row_height, widget.height())
            min_height += row_height
            if row_height > 0:
                nrows_filled += 1

        # add vertical spacings and margins
        min_height = min_height + (nrows_filled-1) * layout.verticalSpacing() + self._panel_margins[1] + self._panel_margins[3]

        if min_height > 0:
            logger.debug (f"{self} - fix min height of panel to {min_height} ")

            self._panel.setMinimumHeight (min_height)


    def _init_layout(self) -> QLayout:
        """ init and return main layout"""

        # to be implemented by sub class
        pass


    def _add_to_header_layout(self, l_head : QHBoxLayout):
        """ add Widgets to header layout"""

        # to be implemented by sub class
        pass



# ------------ MessageBox  -----------------------------------


class MessageBox (QMessageBox):
    """ 
    Subclass of QMessagebox 
        - new default icons 
        - more width and height 
    """

    _min_width  = 250
    _min_height = 80 

    def __init__(self, parent: object, 
                 title : str, 
                 text : str, 
                 icon: Icon, 
                 min_width=None,                            # width of text widget 
                 min_height=None):                          # height of text widget 
        super().__init__(parent)

        # set properties 

        self.setWindowTitle (title)
        self.setText (text)

        # set icon 

        if isinstance (icon, Icon):
            pixmap = icon.pixmap((QSize(32, 32)))
            self.setIconPixmap (pixmap)

        # set width and height 
        #   size of QMessageBox must be set via layout - which is a bit hacky 

        layout : QGridLayout = self.layout()
        if isinstance (layout, QGridLayout):

            cols = layout.columnCount()
            if cols > 1:
                min_width = min_width if min_width is not None else self._min_width
                # set minimum width of last column (which should be text) 
                layout.setColumnMinimumWidth (cols-1,min_width)
                layout.setColumnStretch (cols-1,3)
                # set minimum width of first column (which should be icon) 
                layout.setColumnMinimumWidth (0,60)
                item = layout.itemAtPosition (0,1)
                item.setAlignment (Qt.AlignmentFlag.AlignVCenter )

                # increase right margin 
                left, top, right, bottom = layout.getContentsMargins()
                layout.setContentsMargins (left, top, right+20, bottom)

            rows = layout.columnCount()
            if rows > 1:
                min_height = min_height if min_height is not None else self._min_height
                # set minimum widthof last column (which should be text) 
                layout.setRowMinimumHeight (0,min_height)
                # set center alignment of icon 
                item = layout.itemAtPosition (0,0)
                item.setAlignment (Qt.AlignmentFlag.AlignCenter )

        if os.name == 'posix':
            # strange posix - wayland bug 
            #   With first call of MessageBox the box is positioned at 0,0 -> manually move to the center of parent 
            point = parent.geometry().center()
            x = point.x() - 200
            y = point.y() - 100
            self.move(x,y)
 

    @staticmethod
    def success (parent: object, title : str, text : str, min_width=None, min_height=None):
        """ success message with Ok button"""

        msg = MessageBox (parent, title, text, Icon (Icon.SUCCESS), min_width=min_width, min_height= min_height)
        msg.exec()


    @staticmethod
    def info (parent: object, title : str, text : str, min_width=None, min_height=None):
        """ info message with Ok button"""

        msg = MessageBox (parent, title, text, Icon (Icon.INFO), min_width=min_width, min_height= min_height)
        msg.exec()


    @staticmethod
    def error (parent: object, title : str, text : str, min_width=None, min_height=None):
        """ critical message with Ok button"""

        msg = MessageBox (parent, title, text, Icon (Icon.ERROR), min_width=min_width, min_height= min_height)
        msg.exec()


    @staticmethod
    def confirm (parent: object, title : str, text : str, min_width=None):
        """ confirmation with Ok and Cancel"""

        msg = MessageBox (parent, title, text, Icon (Icon.INFO), min_width=min_width)

        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton  (QMessageBox.StandardButton.Ok)

        return msg.exec()


    @staticmethod
    def warning (parent: object, title : str, text : str, min_width=None):
        """ warning with Ok and Cancel"""

        msg = MessageBox (parent, title, text, Icon (Icon.WARNING), min_width=min_width)

        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton  (QMessageBox.StandardButton.Ok)

        return msg.exec()


    @staticmethod
    def save (parent: object, title : str, text : str, min_width=None, buttons=None):
        """ ask to save or discard - returns QMessageBox.StandardButton"""

        msg = MessageBox (parent, title, text, Icon (Icon.WARNING), min_width=min_width)

        if buttons is None: 
            buttons = QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel 
        msg.setStandardButtons(buttons)
        msg.setDefaultButton  (QMessageBox.StandardButton.Save)

        return msg.exec()



# ------------ Toaster  -----------------------------------


class Toaster (QFrame):

    """ 
    Show a little notification toaster 

    based on https://stackoverflow.com/questions/59251823/is-there-an-equivalent-of-toastr-for-pyqt
    """

    def __init__(self, *args, **kwargs):

        super (Toaster, self).__init__(*args, **kwargs)
        QHBoxLayout(self)

        self.label = None

        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        #                 border: 1px solid blue;
        # background: palette(window);

        # self.setStyleSheet('''
        #     QToaster {
        #         border-radius: 2px; 
        #     }
        # ''')
        # alternatively:

        self.setAutoFillBackground(True)
        # set_background (self, color="red")
        # self.setFrameShape(self.Box)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

        if self.parent():
            self.opacityEffect = QGraphicsOpacityEffect(opacity=0)
            self.setGraphicsEffect (self.opacityEffect)
            self.opacityAni = QPropertyAnimation (self.opacityEffect, b'opacity')
            # we have a parent, install an eventFilter so that when it's resized
            # the notification will be correctly moved to the right corner
            self.parent().installEventFilter(self)
        else:
            # there's no parent, use the window opacity property, assuming that
            # the window manager supports it; if it doesn't, this won'd do
            # anything (besides making the hiding a bit longer by half a second)
            self.opacityAni = QPropertyAnimation(self, b'windowOpacity')
        self.opacityAni.setStartValue(0.)
        self.opacityAni.setEndValue(1.)
        self.opacityAni.setDuration(100)
        self.opacityAni.finished.connect(self.checkClosed)

        self.corner = Qt.Corner.TopLeftCorner
        self.margin = QMargins(10, 10, 10, 10)


    def checkClosed(self):
        # if we have been fading out, we're closing the notification
        if self.opacityAni.direction() == QAbstractAnimation.Direction.Backward:
            self.close()

    def restore(self):
        # this is a "helper function", that can be called from mouseEnterEvent
        # and when the parent widget is resized. We will not close the
        # notification if the mouse is in or the parent is resized
        self.timer.stop()
        # also, stop the animation if it's fading out...
        self.opacityAni.stop()
        # ...and restore the opacity
        if self.parent():
            self.opacityEffect.setOpacity(1)
        else:
            self.setWindowOpacity(1)

    def hide(self):
        # start hiding
        self.opacityAni.setDirection(QAbstractAnimation.Direction.Backward)
        self.opacityAni.setDuration(300)
        self.opacityAni.start()

    def eventFilter(self, source, event : QEvent):
        if source == self.parent() and event.type() == QEvent.Type.Resize:

            self.opacityAni.stop()

            parentRect : QRectF = self.parent().rect()
            geo = self.geometry()

            corner = self.corner
            margin = self.margin

            if corner == Qt.Corner.TopLeftCorner:
                geo.moveTopLeft(parentRect.topLeft() + QPoint(margin.left(), margin.top()))
            elif corner == Qt.Corner.TopRightCorner:
                geo.moveTopRight(parentRect.topRight() + QPoint(-margin.right(), margin.top()))
            elif corner == Qt.Corner.BottomRightCorner:
                geo.moveBottomRight(parentRect.bottomRight() + QPoint(-margin.right(), -margin.bottom()))
            else:
                geo.moveBottomLeft(parentRect.bottomLeft() + QPoint(margin.left(), -margin.bottom()))

            self.setGeometry(geo)
            self.restore()
            self.timer.start()
        return super(Toaster, self).eventFilter(source, event)

    # def enterEvent(self, event):
    #     deactivated - when the mouse is by accident over the notification, 
    #           the toaster would wouldn't close
    #     self.restore()
    #     super().enterEvent(event)


    def leaveEvent(self, event):
        self.timer.start()

    def closeEvent(self, event):
        # we don't need the notification anymore, delete it!
        self.deleteLater()

    def resizeEvent(self, event):
        super(Toaster, self).resizeEvent(event)
        # if you don't set a stylesheet, you don't need any of the following!
        if not self.parent():
            # there's no parent, so we need to update the mask
            path = QPainterPath()
            path.addRoundedRect(QRectF (self.rect()).translated(-.5, -.5), 4, 4)
            self.setMask(QRegion(path.toFillPolygon(QTransform()).toPolygon()))
        else:
            self.clearMask()

    @staticmethod
    def showMessage(parent, message, 
                    corner = Qt.Corner.BottomLeftCorner, 
                    margin =          QMargins(10,10,10,10), 
                    contentsMargins = QMargins(30, 7,30, 7),
                    toast_style = style.HINT,
                    duration = 1500,
                    alpha :int = 255,
                    parentWindow = False):
        """
        show a toaster for a while

        Args:
            parent : parent Toasters position is relative 
            message: message to show 
            corner : position in parents window 
            margin : offset of position
            style : color style 
            duration: duration of message 
            parentWindow : take parent window of parent
        """

        if parent and parentWindow:
            parent = parent.window()

        if isinstance (margin, int):
            margin = QMargins(margin, margin, margin, margin)

        if toast_style is None: 
            toast_style = style.HINT

        self = Toaster(parent)
        parentRect : QRectF = parent.rect()

        self.timer.setInterval(duration)

        self.label = QLabel(message)
        self.layout().addWidget(self.label)
        self.layout().setContentsMargins (contentsMargins)

        # set background color style 

        if toast_style in [style.WARNING, style.ERROR, style.COMMENT, style.GOOD, style.HINT]:

            palette : QPalette = self.palette()
            index = Widget.LIGHT_INDEX if Widget.light_mode else Widget.DARK_INDEX
            color = QColor (toast_style.value[index])

            # adapt color 

            h,s,l,a = color.getHsl()
            a = alpha if isinstance(alpha,int) else a
            if Widget.light_mode:
                s = int(s*0.8)                                  # less saturation (more gray) 
                l = int(l*1.4)                                  # lighter 
            else:
                s = int(s*0.8)                                  # less saturation (more gray) 
                l = int(l*0.5)                                  # darker 
            color.setHsl (h, s, l, a)

            palette.setColor(QPalette.ColorRole.Window, color)
            self.setPalette(palette)

        # start hide timer 

        self.timer.start()

        # raise the widget and adjust its size to the minimum

        self.raise_()
        self.adjustSize()

        self.corner = corner
        self.margin = margin

        geo = self.geometry()

        # now the widget should have the correct size hints, let's move it to the right place
        
        if corner == Qt.Corner.TopLeftCorner:
            geo.moveTopLeft(parentRect.topLeft() + QPoint(margin.left(), margin.top()))
        elif corner == Qt.Corner.TopRightCorner:
            geo.moveTopRight(parentRect.topRight() + QPoint(-margin.right(), margin.top()))
        elif corner == Qt.Corner.BottomRightCorner:
            geo.moveBottomRight(parentRect.bottomRight() + QPoint(-margin.right(), -margin.bottom()))
        else:
            geo.moveBottomLeft(parentRect.bottomLeft() + QPoint(margin.left(), -margin.bottom()))

        self.setGeometry(geo)
        self.show()
        self.opacityAni.start()



# ------------ Dialog  -----------------------------------

class Dialog (QDialog):
    """
    Abstract super class for modal top windows with action buttons at bottom.
    Extends QDialog with a dataObject (via 'getter') and common background color.

    The content of the dialog is defined in a subclass via _init_layout() which returns the
    layout for the dialog.
    """

    name = "Dialog"             # will be title 

    _width  = None
    _height = None 


    def __init__(self,  
                 parent : QWidget = None,
                #  flags : Qt.WindowType = None, 
                 getter = None, 
                 width  : int | None =None,             # optional width of dialog
                 height : int | None =None,             # optional height of dialog
                 dialogPos : tuple = (0.4,0.5),         # reference point for positioning - (0,0) is upper, left corner
                 parentPos : tuple = (0.3,0.6),         # position anchor in parent - (0,0) is upper, left corner
                 dx : int | None = None,                # optional move dialog dx pixels to the right
                 dy : int | None = None,                # optional move dialog dy pixels down
                 title=None,                            # optional title of dialog
                 flags=Qt.WindowType.Dialog, **kwargs):
        super().__init__(parent, flags=flags, **kwargs)

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

        # move self relative to parent bottom left
        #       calc from the relative parentPos and dialogPos arguments the absolute positioning

        parent_topLeft     = self._parent.mapToGlobal (self._parent.rect().topLeft())
        parent_bottomRight = self._parent.mapToGlobal (self._parent.rect().bottomRight())
        parent_width  = parent_bottomRight.x() - parent_topLeft.x()
        parent_height = parent_bottomRight.y() - parent_topLeft.y()

        parentPos_rel = QPoint (int(parent_width * parentPos[0]), int(parent_height * parentPos[1]))
        parentPos_abs = parent_topLeft + parentPos_rel

        self_width  = self.rect().width()
        self_height = self.rect().height()
        selfPos_rel = QPoint (int(self_width * dialogPos[0]), int(self_height * dialogPos[1]))

        if dx is not None and dy is not None:
            dxy_rel = QPoint (int(dx), int(dy))
        else:
            dxy_rel = QPoint (0,0)

        self.move (parentPos_abs - selfPos_rel + dxy_rel)

        # title of dialog 

        if title is not None: 
            self.name = title 
        self.setWindowTitle (self.name)

        # enable custom window hint, disable (but not hide) close button
        # self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        # inital content panel content - layout in _init_layout()  

        self._panel = QWidget () 
        self.set_background_color (darker_factor=105)

        l_panel = self._init_layout()                               # subclass will create layout 
        l_panel.setContentsMargins (QMargins(15, 10, 15, 10))       # inset left 
        self._panel.setLayout (l_panel)

        # Qt buttonBox at footer

        button_box = self._button_box()
        if button_box:
            l_button = QHBoxLayout()
            l_button.addWidget(self._button_box())
            l_button.setContentsMargins (QMargins(5, 0, 25, 0))
 
        # main layout with title and panel 

        l_main   = QVBoxLayout()
        l_main.addWidget (self._panel, stretch=1)
        if button_box:
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

    def _button_box (self) -> QDialogButtonBox:
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
        return Panel_Abstract.widgets_of_layout (self._panel.layout())


    def _on_widget_changed (self,*_):
        """ slot for change of widgets"""
        # to be overloaded 
        pass


    def button_clicked (self, aButton): 
        """ slot for button of buttonbox clicked. Can be overridden"""
        pass


    def refresh(self, disable=None):
        """ refreshes all Widgets on self """

        for w in self.widgets:
            w.refresh(disable=disable)
        logger.debug (f"{self} - refresh")


    @override
    def reject (self): 
        """ handle reject (close) actions"""
        # to override 
        super().reject()


#-------------------------------------------------------------------------------
# Tab panel    
#-------------------------------------------------------------------------------


class Tab_Panel (QTabWidget):
    """ 
    Tab Widget as parent for other items 
    """

    name = "Panel"             # will be title 

    _width  = None
    _height = None 


    def __init__(self,  
                 parent=None,
                 width=None, 
                 height=None, 
                 **kwargs):
        super().__init__(parent=parent, **kwargs)

        self._parent = parent

        if width  is not None: self._width = width
        if height is not None: self._height = height

        # set width and height 
        Widget._set_width  (self, self._width)
        Widget._set_height (self, self._height)

        font = self.font() 
        _font = size.HEADER.value
        font.setPointSize(_font[0])
        font.setWeight   (_font[1])  
        self.setFont(font)

        # see https://doc.qt.io/qt-6/stylesheet-examples.html

        if Widget.light_mode:
            tab_style = """
            QTabWidget::pane { /* The tab widget frame */
                border-top:1px solid #ababab;
            }

            QTabWidget::tab-bar {
                left: 400px; /* move to the right by 5px */
            }

            /* Style the tab using the tab sub-control. Note that
                it reads QTabBar _not_ QTabWidget */
            QTabBar::tab {
                /*background: green; */
                border: 1px solid #C4C4C3;
                border-bottom: 0px;                                     /*remove */
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                min-width: 25ex;
                padding: 6px;
            }

            QTabBar::tab:!selected {
                margin-top: 2px; /* make non-selected tabs look smaller */
                background: #e5e5e5
            }
                            
            QTabBar::tab:hover {
                background: rgba(255, 255, 255, 0.2) /* rgba(255, 20, 147, 0.1); */              
            }

            QTabBar::tab:selected {
                background: #000000 /*rgba(255, 255, 255, 0.9) */;               
            }

            QTabBar::tab:selected {
                color: #E0E0E0 /* #303030*/;
                font-weight: 600;
                border-color: #9B9B9B;
                /*border-bottom-color: #C2C7CB;  */
                border-bottom-color: red; /* same as pane color */
            }
            """
 
        else: 

            tab_style = """
            QTabWidget::pane { /* The tab widget frame */
                border-top:1px solid #505050;
            }

            QTabWidget::tab-bar {
                left: 400px; /* move to the right by 5px */
            }

            /* Style the tab using the tab sub-control. Note that
                it reads QTabBar _not_ QTabWidget */
            QTabBar::tab {
                /*background: green; */
                border: 1px solid #505050;  
                border-bottom: 0px;                                     /*remove */
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                min-width: 25ex;
                padding: 6px;
            }

            QTabBar::tab:!selected {
                margin-top: 2px; /* make non-selected tabs look smaller */
                color: #D0D0D0;
                background: #353535
            }
                            
            QTabBar::tab:hover {
                background: rgba(255, 255, 255, 0.2) /* rgba(255, 20, 147, 0.1); */             
            }

            QTabBar::tab:selected {
                background: rgba(77, 77, 77, 0.9) /* background: rgba(255, 20, 147, 0.2); */                   
            }

            QTabBar::tab:selected {
                /*color: white; */
                color: #E0E0E0;
                font-weight: 600;
                border-color: #909090;
                border-bottom-color: #C2C7CB;   /* same as pane color */
            }
            """


        self.setStyleSheet (tab_style) 


    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        return f"<Tab_Panel '{self.name}'>"


    def add_tab (self, aWidget : QWidget, name : str = None):
        """ at an item having 'name' to self"""

        if name is None:
            name = aWidget.name

        self.addTab (aWidget, name)


    def set_tab (self, class_name : str):
        """ set the current tab to tab with widgets class name"""

        if class_name:
            for itab in range (self.count()):
                if self.widget(itab).__class__.__name__ == class_name:
                    self.setCurrentIndex (itab)
                    return
        else:
            self.setCurrentIndex (0)
