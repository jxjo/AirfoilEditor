#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Additional generic (compound) widgets based on original CTK widgets

"""
import os
import logging
import copy
import types
import typing 

from PyQt6.QtCore import QEvent, QSize, Qt, QMargins, pyqtSignal

from PyQt6.QtWidgets import QLayout, QFormLayout, QGridLayout, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import (
                            QApplication, QWidget, QPushButton, 
                            QMainWindow, QLineEdit, QSpinBox, QDoubleSpinBox,
                            QLabel, QToolButton, QCheckBox,
                            QSpinBox, QComboBox,
                            QSizePolicy)
from PyQt6.QtGui import QColor, QPalette, QFont, QIcon


PRIMARY             = 1                           # buttonstyle for highlighted button 
SECONDARY           = 2                           # buttonstyle for normal action
SUPTLE              = 3                           # buttonstyle for subtle appearance 
ICON                = 4                           # buttonstyle for icon only button 
RED                 = 5                           # buttonstyle for red - stop - style 
BUTTON_STYLES = [PRIMARY, SECONDARY, SUPTLE, ICON, RED]

# enums for style getter  - tuple for light and dark theme 
# color see https://www.w3.org/TR/SVG11/types.html#ColorKeywords

                    #  light dark
STYLE_NORMAL        = (None, None)
STYLE_COMMENT       = ("dimgray","lightGray")  
STYLE_ERROR         = ('red', 'red')
STYLE_HINT          = ("blue", "blue")
STYLE_WARNING       = ('orange','orange')

SIZE_HEADER         = 14
SIZE_NORMAL         = None 

ALIGN_RIGHT         = Qt.AlignmentFlag.AlignRight
ALIGN_LEFT          = Qt.AlignmentFlag.AlignLeft



#-------------------------------------------------------------------------------
# Helper functions   
#-------------------------------------------------------------------------------

def set_background (aWidget : QWidget, 
                     darker_factor : int | None = None,
                     color : QColor | int | None  = None,
                     alpha : float | None = None):
    """ 
    Set background color of a QWidget either by
        - darker_factor > 100  
        - color: QColor or string for new color
        - alpha: transparency 0..1 
    Returns the QPalette before changes were applied
    """

    new_color = None 
    aWidget.setAutoFillBackground(True)

    palette_org = aWidget.palette()
    palette     = aWidget.palette()

    if darker_factor:
        new_color = palette.color(QPalette.ColorRole.Window).darker (darker_factor)
    elif color:
        new_color = QColor(color) 
        if alpha: 
            new_color.setAlphaF (alpha)

    if new_color:
        palette.setColor(QPalette.ColorRole.Window, new_color)
        aWidget.setPalette(palette)

    return palette_org


#-------------------------------------------------------------------------------
# Widgets  
#-------------------------------------------------------------------------------

class Widget:
    """
    Extends QtWidgets to get an "access path" usage of widgets
    where a widget 'get' and 'set' its data by itself.

    A widgets add itsself to a 'QLayout' 

    Signals:

        sig_changed         a Value in an input field was changed and set into object 


    """

    # Signals

    sig_changed = pyqtSignal()    # (Object class name, Method as string, new value)


    @staticmethod
    def refresh_childs (parent: QWidget):
        """ refresh all childs of parent"""
        w : Widget
        for w in parent.findChildren (Widget):
            w.refresh() 


    LIGHT_INDEX = 0                             # = Qt color index 
    DARK_INDEX  = 1 

    light_mode = True                           # common setting of light/dark mode 
                                       
    default_width  = None
    default_height = None 


    def __init__(self,
                 layout: QLayout, 
                 *args,                     # optional: row:int, col:int, 
                 rowSpan = 1, colSpan=1, 
                 align = None,          # alignment within layout 
                 width :int = None,
                 height:int = None,
                 obj = None,                # object | bound method  
                 prop = None,               # Property 
                 get = None, 
                 set = None, 
                 signal : bool | None = None, 
                 id = None,
                 disable = None, 
                 hide = None,
                 style = STYLE_NORMAL,
                 fontSize= SIZE_NORMAL): 
        
        # needed to build reference so self won't be garbage collected 
        super().__init__ ()

        self._layout = layout  

        self._row = None                    # optional positional arguments 
        self._col = None 
        if len(args) > 0: 
            self._row = args[0]
        if len(args) > 1: 
            self._col = args[1] 

        self._rowSpan = rowSpan
        self._colSpan = colSpan 
        self._alignment = align 
        self._width  = width  if width  is not None else self.default_width
        self._height = height if height is not None else self.default_height

        # "get & set" or "obj & prop" variant    

        self._val = None

        if obj is not None and prop is None: 
            raise ValueError (f"{self}: argment 'prop' is missing")
        if obj is None and prop is not None: 
            raise ValueError (f"{self}: argument 'obj' is missing")
        if prop is not None and get is not None: 
            raise ValueError (f"{self}: arguments 'obj' and 'get' can't be mixed together")

        self._obj = obj 
        if isinstance (prop, property): 
            self._obj_property : property = prop
            self._obj_setter   : function = self._build_obj_setter   (obj, prop)
        else:
            self._obj_property = None
            self._obj_setter   = None

        self._getter = get 
        self._setter = set 
        self._id = id 

        self._while_setting = False 

        # handle disable / hide  

        if isinstance(disable, bool):
            self._disabled   = disable                     
            self._disabled_getter = bool(disable)
        elif callable (disable):
            self._disabled   = None                          
            self._disabled_getter = disable
        else: 
            self._disabled   = False                        # default values 
            self._disabled_getter = None

        if (self._setter is None and self._obj_setter is None) and self._disabled == False: 
            self._disabled_getter = True
            self._disabled = True  

        self._hidden   = False                          
        if callable (hide):
            self._hidden_getter = hide
        else: 
            self._hidden_getter = None

        # emit signal 

        self._emit = signal if isinstance (signal, bool) else True  

        # style of widget 

        self._style_getter = style 
        self._style = None 
        self._palette_normal = None       # will be copy of palette - for style reset  
        self._fontSize = fontSize

        self._toolTip = None


    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        if self._val is None: 
            text = '' 
        else: 
            text = f" '{str(self._val)}'"
        return f"<{type(self).__name__}{text}>"


    #---  public methods 

    def refresh (self):
        """refesh self by re-reading the 'getter' path 
        """

        if self._while_setting:                           # avoid circular actions with refresh()
            # logging.debug (str(self) + " - refresh skipped while set callback")
            pass
        else: 
            # print (str(self) + " - refresh")
            self._get_properties ()
            self._set_Qwidget ()


    def set_enabled (self, aBool : bool):
        """ 
        enable/disable self 
            - disable: always
            - enable:  depending on 'disable' and 'set'argument and 'set' 
        """
        # to overload by subclass
        disable = not bool(aBool) 
        if disable: 
            self._disabled = True 
            self._set_Qwidget_disabled () 
        else: 
            if self._disabled_getter == True: 
                pass                        # disable is fixed 
            else:
                self._disabled = False
                self._set_Qwidget_disabled () 



    #---  from / to outside 

    def _get_properties (self): 
        """
        Read all the properties like disablee, style as they can be 
            - bound methods
            - fixed values 
            - property (only for self._val)
        """
        # should be overloaded for additional properties 

        # access value' either via property approach or via getter (bound method) 
        if self._obj: 
            self._val = self._get_property_value (self._obj, self._obj_property)
        else: 
            self._val = self._get_value (self._getter, self._id)

        self._disabled  = self._get_value (self._disabled_getter, default=self._disabled)
        self._hidden    = self._get_value (self._hidden_getter, default=self._hidden)
        self._style     = self._get_value (self._style_getter)
        
 
    def _get_value(self, getter, id=None, default=None):
        """
        Read the value. 'getter' can be 
            - bound method 
            - object of basic type: str, int, float as widget value 
        Optional 'id' is used as argument of bound method 'getter'
        'default' is taken, if 'getter' results in None 
        """

        if callable(getter):                            # getter is a method ?
            if not id is None:                          # an object Id was set to identify object
                val =  getter(id=self._id) 
            else:            
                val =  getter()                         # normal callback
        else:                                           # ... no - getter is base type 
            val =  getter 

        if val is None and default is not None: 
            val = default

        return val 


    def _get_property_value(self, obj : object, obj_property : property):
        """
        Read a value of the 'obj_property' in model object 'obj'.
        """
        o = obj() if callable (obj) else obj            # obj either bound methed or object

        return  obj_property.__get__(o, type(o))        # access value of property in obj 



    def  _build_obj_setter (self, obj , obj_property : property) :  # -> function | None
        """ build a setter function like 'set_thickness' out of the (get) obj_property"""

        o = obj() if callable (obj) else obj            # obj either bound methed or object

        prop_name = obj_property.fget.__name__ 
        set_name  = "set_" + prop_name          
        try: 
            set_function = getattr (o.__class__, set_name)
        except: 
            logging.warning (f"{self} setter function '{set_name} does not exist in {o.__class__}")
            set_function = None
        return set_function 


    def _set_value(self, newVal):
        """write the current value of the widget to model via setter path
        """

       
        if newVal is None:                          # None for button 
            pass
        elif self._val == newVal :                  # different signals could have beem emitted
            return
        else:                                        
            self._val = newVal                      # keep value for change detection

        self._while_setting = True                  # avoid circular actions with refresh()

        # set value bei property and object 

        if self._obj_setter is not None:            

            obj = self._obj() if callable (self._obj) else self._obj
            self._obj_setter (obj, newVal)          # Python magic: _obj_setter is a function 

            self._emit_change (newVal) 


        # set value bei bound method or function (lambda)

        elif callable(self._setter):                # setter is a method ?
            if newVal is None:                      # typically a button method which has no arg
                if self._id is None:                # an object Id was set to identify object
                    self._setter()                  # normal callback
                else:            
                    self._setter(id=self._id) 
            else:                                   # a method like: def myMth(self, newVal)
                if self._id is None:                # an id was set to identify object?
                    self._setter(newVal)            # normal callback
                else:            
                    self._setter(newVal, id=self._id) 

                self._emit_change (newVal) 

        self._while_setting = False                


    def _emit_change (self, newVal):
        """ emit change signal""" 

        if not self._emit: return 

        if isinstance(self._setter, types.FunctionType):
            qualname  = self._setter.__qualname__
        elif callable(self._setter):        
            qualname  = self._setter.__qualname__
        elif isinstance(self._obj_setter, types.FunctionType):
            qualname  = self._obj_setter.__qualname__
        else: 
            qualname = ''

        logging.debug (f"{self} sig_changed: {qualname} ({newVal})")

        self.sig_changed.emit ()


    def _layout_add (self, widget = None, col = None):
        """ adds self to layout"""

        if widget is None: 
            widget : QWidget = self

        if col is None:                         # alternate col 
            col = self._col

        if isinstance (self._layout, QGridLayout): 
            if self._alignment is None: 
                self._layout.addWidget(widget, self._row, col, 
                                                self._rowSpan, self._colSpan)
            else: 
                self._layout.addWidget(widget, self._row, col, 
                                                self._rowSpan, self._colSpan,
                                                alignment = self._alignment)
        elif isinstance (self._layout, (QFormLayout,QVBoxLayout, QHBoxLayout)):
            self._layout.addWidget(widget)

        # strange (bug?): if layout is on main window the stretching works as expected
        # on a sub layoutthe widget doesn't stretch if on widget in the column is fixed 
        widget.setSizePolicy( QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed )


    #---  from / to CTkControl - inside the widget 

    def _set_Qwidget (self): 
        """ set value and properties of self Qwidget"""
        # must be overloaded 

        # minimum for all 
        self._set_Qwidget_style ()              # NORMAL, WARNING, etc 

        self._set_Qwidget_disabled ()

        widget : QWidget = self
        if self._hidden_getter:
            widget.ensurePolished()
            # if widget.isHidden() != self._hidden:
            widget.setVisible(not self._hidden)


    def _set_Qwidget_static (self, widget = None): 
        """ set static properties of self Qwidget like width"""
        # can be overlaoed 

        if widget is None: 
            widget : QWidget = self

        # set font 
        if self._fontSize == SIZE_HEADER:
            font = widget.font() 
            font.setPointSize(14)
            font.setWeight (QFont.Weight.ExtraLight) #Medium #DemiBold
            widget.setFont(font)

        # set width 
        if self._width is not None: 
            if isinstance (self._width, tuple):
                min_width = self._width[0]
                max_width = self._width[1]
            elif isinstance (self._width, int):
                min_width = self._width
                max_width = self._width
            else: 
                min_width = None
                max_width = None
            if min_width: widget.setMinimumWidth(min_width)
            if max_width: widget.setMaximumWidth(max_width)

        # set height 
        if self._height is not None: 
            if isinstance (self._height, tuple):
                min_height = self._height[0]
                max_height = self._height[1]
            elif isinstance (self._height, int):
                min_height = self._height
                max_height = self._height
            else: 
                min_height = None
                max_height = None
            if min_height: widget.setMinimumHeight(min_height)
            if max_height: widget.setMaximumHeight(max_height)

        # toolTip 
        if self._toolTip is not None:
            widget.setToolTip (self._toolTip)


    def _set_Qwidget_disabled (self):
        """ set self Qwidget according to self._disabled"""

        # can be overlaoded to suppress enable/disable 
        widget : QWidget = self
        if widget.isEnabled() != (not self._disabled) :
            widget.setDisabled(self._disabled)


    def _set_Qwidget_style (self): 
        """ set (color) style of QWidget based on self._style"""

        # default color_role is change the text color according to style
        # can be olverlaoded by subclass  

        # QPalette.ColorRole.Text, .ColorRole.WindowText, .ColorRole.Base, .ColorRole.Window
        self._set_Qwidget_style_color (self._style, QPalette.ColorRole.Base)  


    def _set_Qwidget_style_color (self, style, color_role : QPalette.ColorRole= None):
        """ 
        low level set of colored part of widget accordings to style and color_role
            color_role = .Text, .Base (background color), .Window
        """

        # ! ColorRole.Base and ColorRole.Window not implemented up to now
        # if not color_role in [QPalette.ColorRole.Text, QPalette.ColorRole.WindowText]:
        #     raise ValueError (f"{self}: color_role '{color_role}' not implemented")

        if style in [STYLE_WARNING, STYLE_ERROR, STYLE_COMMENT]:

            palette : QPalette = self.palette()
            if self._palette_normal is None:                     # store normal palette for later reset 
                self._palette_normal =  QPalette(palette)        # create copy (otherwise is just a pointer) 
            if self.light_mode:
                index = self.LIGHT_INDEX
            else: 
                index = self.DARK_INDEX
            color = QColor (style [index])

            # if it's background color apply alpha
            if color_role == QPalette.ColorRole.Base:
                color.setAlphaF (0.2)

            palette.setColor(color_role, color)

            self._update_palette (palette)                      # Qt strange : on init 'setPalette' is needed
                                                                # later compounds like SpinBox need different treatment
        elif style == STYLE_NORMAL and self._palette_normal is not None:
            self._update_palette (self._palette_normal)


    def _update_palette (self, palette: QPalette):
        """ set new QPalette for self"""

        # to overwrite if self is compound like QSpinbox ()  
        self.setPalette (palette) 
          

    def _getFrom_Qwidget (self):
        """returns the current value of QWidget  
        """
        # must be over written by specific widget 
        return None
    
                    
    @property     
    def _name (self): 
        """ name for error messages etc. """

        return self.__class__



# ----------------------------------------------------------------
#  abstract widget super classes 
# ----------------------------------------------------------------
 
class Field_With_Label (Widget):
    """
    Abstract Field which adds an optional Label before the widget 

    If 'lab':  
        col=i   : Label
        col=i+1 : Field | ComboBox 

        In this case, only QGridLayout is supported    
    """
    def __init__(self, *args, 
                 lab : str | None = None, 
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._label = None 

        if lab is not None: 
            if not isinstance (self._layout, QGridLayout):
                raise ValueError (f"{self} Only QGridLayout supported for Field with a Label")
            else: 
                self._label = Label(self._layout, self._row, self._col, get=lab)
            

    def _layout_add (self, widget=None):
        # overloaded

        # put into grid / layout - if there is a label one col more 
        if self._label:
            col = self._col + 1 if self._col is not None else None 
        else: 
            col = self._col 

        # strange (bug?): if layout is on main window the stretching works as expected
        # on a sub layoutthe widget doesn't stretch if on widget in the column is fixed 
        super()._layout_add (col=col, widget=widget)

        if self._label and self._alignment is not None:
            self._layout.setAlignment (self._label, self._alignment)

        self.setSizePolicy( QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed )


    def _set_Qwidget (self): 
        """ set value and properties of self Qwidget"""
        super()._set_Qwidget ()

        # overloaded to also hide self label 
        if self._label and self._hidden_getter:
            self._label.setVisible(not self._hidden)




    def _on_finished(self):
      self._set_value (self.text())



# ----------------------------------------------------------------
# -----------  real generic widget subclasses --------------------
# ----------------------------------------------------------------


class Label (Widget, QLabel):
    """
    label text with word wrap 
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


        self._set_Qwidget_static ()
        self._get_properties ()
        self._set_Qwidget ()

        # put into grid / layout 
        self._layout_add ()


    def _set_Qwidget_style (self): 
        """ set (color) style of QWidget based on self._style"""

        # overloaded QLabel uses QPalette.ColorRole.WindowText
        self._set_Qwidget_style_color (self._style, QPalette.ColorRole.WindowText)  


    def _set_Qwidget (self):
        """ set value and properties of self Qwidget"""

        super()._set_Qwidget ()
        self.setText (self._val)


    def _set_Qwidget_disabled (self):
        """ set self Qwidget according to self._disabled"""
        # do not disable Labe (color ...) 
        pass


 
class Field (Field_With_Label, QLineEdit):
    """
    String entry field  
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._set_Qwidget_static ()
        self._get_properties ()
        self._set_Qwidget ()

        # put into grid / layout 
        self._layout_add ()

        # connect signals 
        self.editingFinished.connect(self._on_finished)
        self.returnPressed.connect(self._on_finished)


    def _set_Qwidget (self):
        """ set value and properties of self Qwidget"""
        super()._set_Qwidget ()
        self.setText (self._val)


    def _on_finished(self):
      self._set_value (self.text())



class FieldI (Field_With_Label, QSpinBox):
    """
    Integer entry field with spin buttons
    """
    
    default_height = 26 

    def __init__(self, *args, 
                 step = None,
                 lim = None, 
                 unit : str = None, 
                 specialText : str = None,   # Qt specialValueText
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._step = int(step) if step is not None else None
        self._spin = step is not None 
        self._unit = unit
        self._lim = None 
        self._lim_getter = lim
        self._specialText = specialText

        self._set_Qwidget_static ()
        self._get_properties ()
        self._set_Qwidget ()

        # put into grid / layout 
        self._layout_add ()

        # connect signals 
        self.editingFinished.connect (self._on_finished)
        # self.valueChanged.connect    (self._on_finished)


    def _get_properties (self): 
        # overloaded
        super()._get_properties () 
        self._val = int (self._val) 
        self._lim = self._get_value (self._lim_getter)


    def _set_Qwidget (self):
        """ set value and properties of self Qwidget"""

        super()._set_Qwidget ()

        if self._lim: 
            self.setRange (self._lim[0], self._lim[1])
        self.setValue (self._val)

        # parent could be disabled - so also remove spin buttons 
        if self._spin and not self._disabled and self.isEnabled():
            self.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        else: 
            self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)


    def _set_Qwidget_static (self): 
        """ set static properties of self Qwidget like width"""
        super()._set_Qwidget_static ()

        self.setRange (-999999999, 999999999)                  # Qt default is 0.0 and 99

        if self._unit: 
            self.setSuffix (" " + self._unit)
        if self._spin:
            self.setSingleStep (self._step)
            if self._specialText:
                self.setSpecialValueText (self._specialText)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)


    def _update_palette (self, palette: QPalette):
        """ set new QPalette for self"""

        # Qt bug?
        # overwritten as Palette has to be set for LineEdit of self  
        self.lineEdit().setPalette (palette) 


    def stepBy (self, step):
        # Qt overloaded: Detect when a Spin Button is pressed with new value 
        value = self.value()
        super().stepBy(step)
        if self.value() != value:
            self._on_finished ()


    def _on_finished(self):
      self._set_value (self.value())




class FieldF (Field_With_Label, QDoubleSpinBox):
    """
    Float entry field with spin buttons
    """

    default_height = 26 

    def __init__(self, *args, 
                 step : float = None,
                 lim = None, 
                 unit : str = None,
                 dec : int = 2,
                 specialText : str = None,   # Qt specialValueText
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._step = float(step) if step is not None else None
        self._spin = step is not None 
        self._unit = unit
        self._dec  = int(dec) 
        self._lim = None 
        self._lim_getter = lim
        self._specialText = specialText

        self._get_properties ()
        self._set_Qwidget_static ()
        self._set_Qwidget ()

        self._layout_add ()

        # connect signals 
        self.editingFinished.connect(self._on_finished)


    def _get_properties (self): 
        # overloaded
        super()._get_properties () 
        self._lim = self._get_value (self._lim_getter)


    def _set_Qwidget (self):
        """ set value and properties of self Qwidget"""

        super()._set_Qwidget ()

        if self._lim: 
            self.setRange (self._lim[0], self._lim[1])

        # set val into Qwidget handle - percent unit automatically 
        if self._unit == '%':
            self.setValue (self._val * 100.0)
        else: 
            self.setValue (self._val)

        # parent could be disabled - so also remove spin buttons 
        if self._spin and not self._disabled and self.isEnabled():
            self.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        else: 
            self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)



    def _set_Qwidget_static (self): 
        """ set static properties of self Qwidget like width"""
        super()._set_Qwidget_static ()

        self.setRange (-999999999, 999999999)                  # Qt default is 0.0 and 99
        self.setDecimals(self._dec) 
        if self._unit: 
            self.setSuffix (" " + self._unit)
        if self._spin:
            self.setSingleStep (self._step)
            if self._specialText:
                self.setSpecialValueText (self._specialText)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)


    def _update_palette (self, palette: QPalette):
        """ set new QPalette for self"""

        # Qt bug?
        # overwritten as Palette has to be set for LineEdit of self  
        self.lineEdit().setPalette (palette) 


    def stepBy (self, step):
        # Qt overloaded: Detect when a Spin Button is pressed with new value 
        value = self.value()
        super().stepBy(step)
        if self.value() != value:
            self._on_finished ()


    def _on_finished(self):
        """ signal slot finished"""
        new_val = round(self.value(), self._dec)  # Qt sometimes has float artefacts 

        # get val from Qwidget - handle percent unit automatically 
        if self._unit == '%':
            self._set_value (round(new_val / 100.0, 10))
        else: 
            self._set_value (new_val)




class Button (Widget, QPushButton):
    """
    Button 
        - gets its label via 'text' 
        - when clicked, 'set' is called without argument 
    """
    def __init__(self, *args, 
                 text = None, 
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._text = text 

        self._get_properties ()
        self._set_Qwidget_static ()
        self._set_Qwidget ()

        # put into grid / layout 
        self._layout_add ()

        # connect signals 
        self.pressed.connect(self._on_pressed)


    def _set_Qwidget_static (self): 
        """ set static properties of self Qwidget like width"""
        super()._set_Qwidget_static ()
        self.setText (self._text)


    def _on_pressed(self):
      self._set_value (None)



class ToolButton (Widget, QToolButton):
    """
    Icon tool button 
        - when clicked, 'set' is called without argument 
    """

    default_width  = 24
    default_height = 24 

    # --- icons ---- 

    # <a target="_blank" href="https://icons8.com/icon/15813/pfeil%3A-einklappen">Pfeil: Einklappen</a> 
    # Icon von https://icons8.com
    # Windows 11 icon style 
    # color dark theme #C5C5C5, light theme #303030
    # size 96x96

    ICON_SETTINGS   = "settings" 
    ICON_COLLAPSE   = "collapse" 
    ICON_OPEN       = "open"     
    ICON_EDIT       = "edit"            # https://icons8.com/icon/set/edit/family-windows--static
    ICON_DELETE     = "delete"          # https://icons8.com/icon/set/delete/family-windows--static
    ICON_ADD        = "add"      
    ICON_NEXT       = "next"     
    ICON_PREVIOUS   = "previous" 

    ICONS = {                           # icon dict with an tuple of QIcons for light and dark mode 
        ICON_SETTINGS: None,
        ICON_COLLAPSE: None,
        ICON_OPEN    : None,
        ICON_EDIT    : None,            # https://icons8.com/icon/set/edit/family-windows--static
        ICON_DELETE  : None,            # https://icons8.com/icon/set/delete/family-windows--static
        ICON_ADD     : None,
        ICON_NEXT    : None,
        ICON_PREVIOUS: None,
        }


    ICON_LEFT         = Qt.ArrowType.LeftArrow
    ICON_RIGHT        = Qt.ArrowType.RightArrow
    ICON_UP           = Qt.ArrowType.UpArrow
    ICON_DOWN         = Qt.ArrowType.DownArrow

    @classmethod
    def _get_icon(cls, icon_name, light_mode = True):
        """ load icon_name from file and store into class dict (cache) """

        if icon_name not in cls.ICONS:
            raise ValueError (f"Icon name '{icon_name} not available")

        # icon not loaded up to now  - load it 

        if cls.ICONS[icon_name] is None:
            dirname = os.path.dirname(os.path.realpath(__file__))
            image_path_light = os.path.join(dirname, 'icons', icon_name + '_light'+ '.png')
            image_path_dark  = os.path.join(dirname, 'icons', icon_name + '_dark'+ '.png')

            if not os.path.isfile (image_path_light):
                raise ValueError (f"Icon '{image_path_light} not available")
            if not os.path.isfile (image_path_dark):
                raise ValueError (f"Icon '{image_path_dark} not available")

            icon_light = QIcon (image_path_light)
            icon_dark  = QIcon (image_path_dark)
            cls.ICONS[icon_name] = (icon_light, icon_dark)

        if light_mode: 
            return cls.ICONS[icon_name][0]
        else: 
            return cls.ICONS[icon_name][1]


    def __init__(self, *args, 
                 icon : str =None, 
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._icon = icon                           # icon name 

        self._get_properties ()
        self._set_Qwidget_static ()
        self._set_Qwidget ()

        self._layout_add ()

        self.clicked.connect(self._on_pressed)


    def _set_Qwidget (self):
        """ set value and properties of self Qwidget"""

        super()._set_Qwidget ()

        if self.isEnabled() != (not self._disabled) :
            self.setDisabled(self._disabled)


    def _set_Qwidget_static (self): 
        """ set static properties of self Qwidget like width"""
        super()._set_Qwidget_static ()

        self.setAutoRaise (True)

        if self._icon is not None: 

            icon_qt = self._get_icon (self._icon, self.light_mode)
            self.setIcon (icon_qt)
            self.setIconSize (QSize(16,16))


    def _on_pressed(self):
      self._set_value (None)



class CheckBox (Widget, QCheckBox):
    """
    Checkbox 
        - gets its label via 'text' 
        - when clicked, 'set' is called with argument of checkSTate 
    """
    def __init__(self, *args, 
                 text=None,
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._text = text 

        self._get_properties ()
        self._set_Qwidget_static ()
        self._set_Qwidget ()

        # put into grid / layout 
        self._layout_add ()

        # connect signals 
        self.checkStateChanged.connect(self._on_checked)


    def _get_properties (self): 
        """ get properties from parent"""
        super()._get_properties () 
        self._val = self._val is True 


    def _set_Qwidget (self):
        """ set value and properties of self Qwidget"""
        super()._set_Qwidget ()
        self.setChecked (self._val)


    def _set_Qwidget_static (self): 
        """ set static properties of self Qwidget like width"""
        super()._set_Qwidget_static ()
        self.setText (self._text)


    def _on_checked(self):
      self._set_value (self.isChecked())



class ComboBox (Field_With_Label, QComboBox):
    """
    ComboBox  
        - values list via 'options' (bound method or list)
        - when clicked, 'set' is called argument with selected text as argument 
    """
        
    default_height = 24 

    def __init__(self, *args, 
                 options = [], 
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._options_getter = options
        self._options = None

        self._get_properties ()
        self._set_Qwidget_static ()
        self._set_Qwidget ()

        # put into grid / layout 
        self._layout_add ()

        # connect signals 
        self.activated.connect(self._on_selected)


    def _get_properties (self): 
        # overloaded
        super()._get_properties () 
        self._options = self._get_value (self._options_getter)
        self._val = str(self._val) if self._val is not None else None


    def _set_Qwidget (self):
        """ set value and properties of self Qwidget"""

        super()._set_Qwidget ()

        self.addItems (self._options)
        self.setCurrentText (self._val)

        self._set_placeholder_text()


    def _on_selected (self):
      self._set_value (self.currentText())
      self._set_placeholder_text()


    def _set_placeholder_text (self):
        if not self._val and len(self._options) > 1: 
            self.setPlaceholderText ("Select")
            self.setCurrentIndex (-1)



class ComboSpinBox (Field_With_Label, QComboBox):
    """
    ComboBox  with spin buttons 'next' and 'rev'
        - values list via 'options' (bound method or list)
        - when clicked, 'set' is called argument with selected text as argument 
    """
    def __init__(self, *args, 
                 options = [], 
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._options_getter = options
        self._options = None
        self._get_properties ()

        self._toolTip = 'Use mouse wheel to browse through items'

        # add spin buttons on helper widget 

        helper   = QWidget()
        l_helper = QHBoxLayout ()
        l_helper.setSpacing (1)
        l_helper.setContentsMargins (QMargins(0, 0, 0, 0))
        l_helper.addWidget (self,stretch=2) 

        self._wButton_prev = ToolButton (l_helper, icon=ToolButton.ICON_PREVIOUS,  set=self._on_pressed_prev, disable=self._prev_disabled)
        self._wButton_next = ToolButton (l_helper, icon=ToolButton.ICON_NEXT, set=self._on_pressed_next, disable=self._next_disabled)
        helper.setLayout (l_helper) 

        self._wButton_prev.setAutoRepeat(True)
        self._wButton_next.setAutoRepeat(True)

        self._set_Qwidget_static (widget=helper)
        self._set_Qwidget ()

        # put into grid / layout 
        self._layout_add (widget=helper)

        # connect signals 
        self.currentTextChanged.connect(self._on_selected)


    def refresh (self): 
        """ refresh self """
        #overloaded to refresh also (state) of spin buttons
        super().refresh() 
        self._refresh_buttons () 


    def _refresh_buttons (self):
        """ refresh (disable) spin buttons """
        self._wButton_prev._get_properties ()
        self._wButton_prev._set_Qwidget ()
        self._wButton_next._get_properties ()
        self._wButton_next._set_Qwidget ()


    def _on_pressed_prev (self): 
        """ prev button pressed """
        cur_index = self.currentIndex() 
        if cur_index > 0:
            self.setCurrentIndex (cur_index - 1)
            self._refresh_buttons ()


    def _on_pressed_next (self): 
        " next button pressed  """
        cur_index = self.currentIndex() 
        if cur_index < (len(self._options)) - 1:
            self.setCurrentIndex (cur_index + 1)
            self._refresh_buttons ()


    def _prev_disabled (self) -> bool: 
        """ prev button disabled"""
        return self.currentIndex() <= 0


    def _next_disabled (self) -> bool: 
        """ prev button disabled"""
        return self.currentIndex() >= (len(self._options)) - 1


    def _get_properties (self): 
        # overloaded
        super()._get_properties () 
        self._options = self._get_value (self._options_getter)
        self._val = str(self._val)


    def _set_Qwidget (self):
        """ set value and properties of self Qwidget"""

        super()._set_Qwidget ()

        self.addItems (self._options)
        self.setCurrentText (self._val)


    def _on_selected (self):
      self._set_value (self.currentText())




class SpaceC:
    def __init__ (self, layout : QGridLayout, col, width=20, stretch=1): 
        """ sets properties of a space column in a grid layout  """
        if isinstance (layout, QGridLayout):
            layout.setColumnMinimumWidth (col,width)
            layout.setColumnStretch (col,stretch)

class SpaceR:
    def __init__ (self, layout : QGridLayout, row, height=10, stretch=1): 
        """ sets properties of a space row in a grid layout  """
        if isinstance (layout, QGridLayout):
            layout.setRowMinimumHeight (row,height)
            layout.setRowStretch (row,stretch)


# ------------------------------------------------------------------------------
# ------------ test functions - to activate  -----------------------------------
# ------------------------------------------------------------------------------


class Test_Widgets (QMainWindow):


    def __init__(self):
        super().__init__()

        self.setWindowTitle('Test all widgets')
        self.setMinimumSize(QSize(600, 400))

        self.disabled = False
        l = QGridLayout()

        r = 0
        Label  (l,r,0,get="Header")
        Label  (l,r,1,fontSize=SIZE_HEADER, colSpan=2,get="This is my header in 2 columns")
        CheckBox (l,r,3,fontSize=SIZE_HEADER, text="Header", width=(90, 120), disable=lambda: self.disabled, )
        r += 1
        Label  (l,r,0,get="Label",width=(90,None))
        Label  (l,r,1,get=lambda: f"Disabled: {str(self.disabled)}")
        Label  (l,r,2,get=self.str_val)
        Label  (l,r,3,get=self.str_val, style=self.style )
        r += 1
        Label  (l,r,0,get="Field")
        Field  (l,r,1,get="initial", set=self.set_str, width=(80, 120))
        Field  (l,r,2,get=self.str_val, set=self.set_str, disable=lambda: self.disabled)
        Field  (l,r,3,get="Error", set=self.set_str, width=80, style=self.style, disable=lambda: self.disabled)
        r += 1
        Field  (l,r,0,lab="Field with label", get="initial", set=self.set_str, width=(80, 120))
        r += 1
        Label  (l,r,0,get="FieldI")
        FieldI (l,r,1,get=15, set=self.set_int, lim=(0,100), unit="kg", step=1, specialText="Automatic", width=80)
        FieldI (l,r,2,get=self.int_val, set=self.set_int, lim=(1,100), step=1, disable=lambda: self.disabled, width=(80, 100))
        FieldI (l,r,3,get=self.int_val, set=self.set_int, lim=(1,100), step=1, disable=lambda: self.disabled, style=self.style, width=(80, 100))
        r += 1
        Label  (l,r,0,get="FieldF")
        FieldF (l,r,1,get=-0.1234, set=self.set_float, width=80, lim=(-1,1), unit="m", step=0.1, dec=2, specialText="Automatic")
        FieldF (l,r,2,get=self.float_val, set=self.set_float, lim=(1,100), dec=4, step=1.0, disable=lambda: self.disabled)
        FieldF (l,r,3,get=self.float_val, set=self.set_float, lim=(1,100), width=80, dec=4, step=1.0, disable=True, style=self.style)
        r += 1
        Label  (l,r,0,get="ComboBox")
        ComboBox (l,r,1,options=["first","second"], set=self.set_str, width=80)
        ComboBox (l,r,2,options=["first","second"], set=self.set_str, disable=lambda: self.disabled)
        r += 1
        Label  (l,r,0,get="ComboSpinBox")
        ComboSpinBox (l,r,1,options=["first","second"], set=self.set_str, width=100)
        ComboSpinBox (l,r,2,options=["first","second"], set=self.set_str, disable=lambda: self.disabled)
        r += 1
        Label  (l,r,0,get="CheckBox")
        CheckBox (l,r,1,text="Check to disable", width=(90, 120), get=self.bool_val, set=self.set_disabled)
        CheckBox (l,r,2,text="Slave check", get=self.bool_val, disable=lambda: self.disabled)
        r += 1
        Label  (l,r,0,get="SpaceR height=10")
        SpaceR (l,r, height=10)
        r += 1
        Label  (l,r,0,get="Button")
        Button (l,r,1,text="Toggle Disable", set=self.toggle_disabled, width=80)
        Button (l,r,2,text='Refresh', set=lambda: Widget.refresh_childs(self) )
        r += 1
        Label  (l,r,0,get="ToolButtons")
        l_tools = QHBoxLayout()
        l_tools.setSpacing (1)
        for icon_style in ToolButton.ICONS: 
            ToolButton (l_tools, icon=icon_style, set=self.toggle_disabled)
        l_tools.addStretch(2)
        l.addLayout (l_tools,r,1, 1, 2)

        l.setColumnStretch (0,1)
        l.setColumnStretch (1,1)
        l.setColumnStretch (2,2)
        l.setColumnStretch (4,1)

        l.setRowStretch (r+1,1)

        container = QWidget()
        container.setLayout (l) 
        self.setCentralWidget(container)

    def str_val (self):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

    def int_val (self):
        return random.randrange(1, 100)
    
    def bool_val (self):
        return bool (random.randrange(0,1))
    
    def float_val (self):
        return random.uniform(0.0001, 99.9999)
    
    def style (self):
        if self.disabled:
            return STYLE_ERROR
        else: 
            return STYLE_NORMAL
    
    def set_str(self, aStr):
        if not isinstance (aStr, str): raise ValueError ("no string: ", aStr)
        print (f"Set string: {aStr}")
    def set_int(self, aInt):
        if not isinstance (aInt, int): raise ValueError ("no int: ", aInt)
        print (f"Set int: {aInt}")
    def set_float(self, aFloat):
        if not isinstance (aFloat, float): raise ValueError ("no int: ", aFloat)
        print (f"Set float: {aFloat}")
    def button_pressed(self):
        print (f"Button pressed")
    def toggle_disabled (self): 
        self.disabled = not self.disabled 
        Widget.refresh_childs (self) 
    def set_disabled (self, aBool): 
        self.disabled = aBool 
        Widget.refresh_childs (self) 




if __name__ == "__main__":

    from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout
    import random
    import string
    logging.basicConfig(level=logging.DEBUG)
 
    app = QApplication([])
    app.setStyle('fusion')
    # Strange: Without setStyleSheet, reset Widget.setPalette doesn't work .. !?
    # Segoe UI is the font of 'fusion' sttyle 
    # font = QFont ()
    # print (font.defaultFamily(), font.family(), font.families())
    app.setStyleSheet ("QWidget { font-family: 'Segoe UI' }")

    w = Test_Widgets()
    w.show()
    app.exec() 
