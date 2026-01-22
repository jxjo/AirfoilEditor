#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

Samller Utility dialogs not depending on app model   

"""

from PyQt6.QtWidgets                    import QLayout, QDialogButtonBox, QPushButton, QDialogButtonBox
from PyQt6.QtWidgets                    import QFileDialog, QWidget

from ..base.widgets                     import * 
from ..base.panels                      import Dialog

from ..model.airfoil                    import Airfoil, Flap_Definition
from ..model.polar_set                  import *

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class Airfoil_Save_Dialog (Dialog):
    """ 
    Common airfoil save dialog - optionally
        - set new filename
        - set new airfoil name
        - select directory
        - remove temp files 

    When user successfully selected an airfoil file, 'set' is called with 
    the new <Airfoil> as argument 
    """

    _width  = (520, None)
    _height = 300

    name = "Save Airfoil as..."

    def __init__ (self,*args, remove_designs=False, rename_mode=False, **kwargs):

        self._rename_mode    = rename_mode
        self._remove_designs = remove_designs

        if rename_mode:
            self.name = "Rename Airfoil"

        super().__init__ (*args, **kwargs)


    @property
    def airfoil (self) -> Airfoil:
        return self.dataObject_copy

    @property 
    def remove_designs (self) -> bool:
        """ remove designs and dir upon finish"""
        return self._remove_designs
    
    def set_remove_designs (self, aBool : bool):
        self._remove_designs = aBool


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0 
        Label  (l,r,0, colSpan=4, get="Change airfoil name and/or filename before saving the airfoil",
                       style=style.COMMENT )
        r += 1
        SpaceR (l, r, stretch=0) 
        r += 1
        Field  (l,r,0, lab="Name", obj= self.airfoil, prop=Airfoil.name, width=(150,None),
                       style=self._style_names, signal=True)
        Button (l,r,2, text="Use Filename", set=self.airfoil.set_name_from_fileName, width=90,
                       hide=self._names_are_equal, signal=True,
                       toolTip="Use filename as airfoil name")
        r += 1
        Label  (l,r,1, colSpan=4, get=self._messageText, style=style.COMMENT, height=20,
                       hide= lambda: not self._messageText())
        r += 1
        Field  (l,r,0, lab="Filename", obj=self.airfoil, prop=Airfoil.fileName, width=(150,None),
                signal=True)
        Button (l,r,2, text="Use Name", set=self.airfoil.set_fileName_from_name, width=90,
                       hide=self._names_are_equal, signal=True,
                       toolTip="Use airfoil name as filename")
        r += 1
        SpaceR (l, r, height=10, stretch=0) 
        r += 1
        Field  (l,r,0, lab="Directory", obj=self.airfoil, prop=Airfoil.pathName_abs, width=(150,None),
                       toolTip=lambda: f"{self.airfoil.pathName_abs}",
                       disable=True)
        ToolButton (l,r,2, icon=Icon.OPEN, set=self._open_dir, signal=True,
                    hide = self._rename_mode,
                    toolTip = 'Select directory of airfoil') 
        r += 1
        SpaceR (l, r, height=10, stretch=2) 
        r += 1
        CheckBox (l,r,0, text="Remove all designs and design directory", colSpan=4,
                        get=lambda: self.remove_designs, set=self.set_remove_designs)
        r += 1
        SpaceR (l, r, height=10, stretch=1) 

        l.setColumnStretch (1,5)
        l.setColumnMinimumWidth (0,80)
        l.setColumnMinimumWidth (2,35)

        return l


    def _on_widget_changed (self, *_):
        """ slot for change of widgets"""

        # delayed refresh as pressed button hides itself 
        timer = QTimer()                                
        timer.singleShot(20, self.refresh)     # delayed emit 


    def _names_are_equal (self) -> bool: 
        """ is airfoil name different from filename?"""
        fileName_without = os.path.splitext(self.airfoil.fileName)[0]
        return fileName_without == self.airfoil.name


    def _style_names (self):
        """ returns style.WARNING if names are different"""
        if not self._names_are_equal(): 
            return style.WARNING
        else: 
            return style.NORMAL


    def _messageText (self): 
        """ info / wanrning text"""
        if not self._names_are_equal():
             return "You may want to sync airfoil Name and Filename"


    def _open_dir (self):
        """ open directory and set to airfoil """

        select_dir = self.airfoil.pathName_abs     
        pathName_new = QFileDialog.getExistingDirectory(self, caption="Select directory",
                                                           directory=select_dir)
        if pathName_new:                         # user pressed open
            self.airfoil.set_pathName (pathName_new)



    def accept(self):
        """ Qt overloaded - ok - save airfoil"""

        # set original airfoil with data 
        airfoil : Airfoil = self.dataObject 
        airfoil_copy : Airfoil = self.dataObject_copy

        airfoil.set_name (airfoil_copy.name)
        airfoil.set_pathFileName (airfoil_copy.pathFileName, noCheck=True)

        airfoil.save ()

        super().accept() 



class Polar_Definition_Dialog (Dialog):
    """ Dialog to edit a single polar definition"""

    _width  = 480
    _height = (300, None)

    name = "Edit Polar Definition"

    def __init__ (self, parent : QWidget, polar_def : Polar_Definition, 
                  small_mode = False,                                       # with flap etc 
                  polar_type_fixed = False,                                 # change of polar type not allowed 
                  fixed_chord : float = None,                               # fixed chord length in mm
                  **kwargs): 

        self._polar_def         = polar_def
        self._small_mode        = small_mode
        self._polar_type_fixed  = polar_type_fixed
        self._fixed_chord       = fixed_chord
        self._has_xtrip         = polar_def.has_xtrip

        if small_mode:
            self._height = 140
            self._width  = 480

        # init layout etc 
        super().__init__ (parent=parent, **kwargs)

        if fixed_chord:
            self.setWindowTitle (f"{self.name} at Chord {fixed_chord}mm")


    @property
    def polar_def (self) -> Polar_Definition:
        return self._polar_def

    @property
    def flap_def (self) -> Flap_Definition:
        return self.polar_def.flap_def if self.polar_def else None

    @property
    def has_xtrip (self) -> bool:
        """ True if forced transition is or shall be set on top or bottom side"""
        return self._has_xtrip
    
    def set_has_xtrip (self, aBool : bool):
        self._has_xtrip = aBool
        if not aBool:
            self.polar_def.set_xtript (None)
            self.polar_def.set_xtripb (None)
        self.refresh()


    @property
    def v (self) -> float:
        """ velocity in m/s if chord is given"""
        if self._fixed_chord and self.polar_def:
            return v_from_re(self.polar_def.re, self._fixed_chord/1000, round_dec=None)
        else:
            return None

    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        l.setVerticalSpacing(3)                                     # strange - otherwise vertical spacing is too large
        r,c = 0,0 
        SpaceR (l, r, height=10,stretch=0) 
        r += 1 
        Label  (l,r,c, get="Polar type")
        ComboBox (l,r,c+1,  width=55, options=polarType.values(),
                        obj=self.polar_def, prop=Polar_Definition.type,
                        disable=self._polar_type_fixed)
        r += 1
        FieldF (l,r,c, width=70, step=10, lim=(1, 99999), unit="k", dec=0,
                        lab=lambda: "Re number" if self.polar_def.type == polarType.T1 else "Re · √Cl", 
                        obj=self.polar_def, prop=Polar_Definition.re_asK)
        l.setColumnMinimumWidth (c,80)
        c += 2
        ToolButton  (l,r,c, icon=Icon.EDIT, set=self.calc_re,
                        toolTip="Calculate Re from velocity and chord length")
        c += 1
        SpaceC  (l,c, width=10)
        c += 1
        FieldF (l,r,c, lab="Mach", width=60, step=0.1, lim=(0, 1.0), dec=2,
                        obj=self.polar_def, prop=Polar_Definition.ma)
        l.setColumnMinimumWidth (c,45)
        c += 2
        SpaceC  (l,c, width=10)
        c += 1
        FieldF (l,r,c, lab="Ncrit", width=60, step=1, lim=(1, 20), dec=1,
                        obj=self.polar_def, prop=Polar_Definition.ncrit)
        l.setColumnMinimumWidth (c,45)
        c += 2
        SpaceC  (l,c, width=10, stretch=5)

        c = 0 
        
        if not self._small_mode:
            r += 1
            FieldF (l,r,c, width=70, unit="m/s", dec=1,
                            lab=lambda: "Velocity", obj=self, prop=Polar_Definition_Dialog.v,
                            disable=True,
                            hide = lambda: self._fixed_chord is None or self.polar_def.type==polarType.T2)
            r += 1 
            SpaceR (l, r, height=10, stretch=0) 

            r += 1 
            CheckBox (l,r,c, text="Force transition at x ...", colSpan=7,
                            obj=self, prop=Polar_Definition_Dialog.has_xtrip)
            r += 1
            FieldF  (l,r,c, lab="Upper Side", width=60, step=1, lim=(0.0, 100), dec=0, unit='%',
                            obj=self.polar_def, prop=Polar_Definition.xtript,
                            hide=lambda: not self.has_xtrip)
            FieldF  (l,r,c+4, lab="Lower", width=60, step=1, lim=(0.0, 100), dec=0, unit='%',
                            obj=self.polar_def, prop=Polar_Definition.xtripb,
                            hide=lambda: not self.has_xtrip)
            r += 1 
            SpaceR (l, r, height=5, stretch=1) 

            r += 1 
            CheckBox (l,r,c, text="Set flap just for this polar ...", colSpan=7,
                            obj=self.polar_def, prop=Polar_Definition.is_flapped)
            r += 1
            FieldF  (l,r,c, lab="Flap Angle", width=60, step=0.1, lim=(-20,20), dec=1, unit='°', 
                            obj=lambda: self.flap_def, prop=Flap_Definition.flap_angle,
                            hide=lambda: not self.polar_def.is_flapped)
            FieldF  (l,r,c+4, lab="Hinge x", width=60, step=1, lim=(1, 98), dec=1, unit="%",
                            obj=lambda: self.flap_def, prop=Flap_Definition.x_flap,
                            hide=lambda: not self.polar_def.is_flapped)
            FieldF  (l,r,c+7, lab="Hinge y", width=60, step=1, lim=(0, 100), dec=0, unit='%',
                            obj=lambda: self.flap_def, prop=Flap_Definition.y_flap,
                            hide=lambda: not self.polar_def.is_flapped)
            # Label   (l,r,c+10, get="of thickness", style=style.COMMENT)

            r += 1
            SpaceR (l, r, height=5, stretch=1) 
            r += 1 
            CheckBox (l,r,c, text=lambda: f"Auto Range of polar {self.polar_def.specVar} values for a complete polar", colSpan=7,
                            get=self.polar_def.autoRange)
            r += 1
            FieldF (l,r,c, lab=f"Step {var.ALPHA}", width=60, step=0.1, lim=(0.1, 1.0), dec=2,
                            obj=self.polar_def, prop=Polar_Definition.valRange_step,
                            hide = lambda: self.polar_def.specVar != var.ALPHA)
            FieldF (l,r,c, lab=f"Step {var.CL}", width=60, step=0.01, lim=(0.01, 0.1), dec=2,
                            obj=self.polar_def, prop=Polar_Definition.valRange_step,
                            hide = lambda: self.polar_def.specVar != var.CL)
            Label  (l,r,c+3, style=style.COMMENT, colSpan=6, 
                            get="The smaller the value, the more time is needed")
        r += 1
        l.setRowStretch (r,1)
        return l


    def calc_re (self):
        """ calc re from velocity and chord length"""

        if self.polar_def.type == polarType.T1:
            dialog = Calc_Reynolds_Dialog (self, re_asK=self.polar_def.re_asK, fixed_chord=self._fixed_chord,
                                        parentPos=(0.5, 0.5), dialogPos=(0,1))
        else:
            dialog = Calc_Re_Sqrt_Cl_Dialog (self, re_asK=self.polar_def.re_asK, fixed_chord=self._fixed_chord,
                                        parentPos=(0.5, 0.5), dialogPos=(0,1))

        dialog.exec()     

        if dialog.has_been_set:
            self.polar_def.set_re_asK (dialog.re_asK)
            self.refresh()


    @override
    def _on_widget_changed (self):
        """ slot a input field changed - repanel and refresh"""
        self.refresh()
        # Adjust dialog size to fit content after widgets are shown/hidden
        self.adjustSize()


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.rejected.connect(self.close)

        return buttonBox 


    @override
    def reject(self): 
        """ close or x-Button pressed"""

        # ensure no flap def with flap angle == 0.0 
        if self.flap_def and self.flap_def.flap_angle == 0.0:
            self.polar_def.set_is_flapped (False) 

        # normal close 
        super().reject()



class Airfoil_Scale_Dialog (Dialog):
    """ small dialog to edit scale factor of an (reference) airfoil"""

    _width  = 320
    _height = 170

    name = "Set Scale Value"

    def __init__ (self, *args, **kwargs): 

        self._close_btn  : QPushButton = None 

        super().__init__ ( *args, **kwargs)

        self._close_btn.clicked.connect  (self.close)


    @property
    def scale_factor (self) -> float:
        return self.dataObject_copy

    def set_scale_factor (self, aVal):
        self._dataObject_copy = aVal


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r,c = 0,0 
        Label  (l,r,c, style=style.COMMENT, height=80, colSpan=3,
                get="Set a scale value for the selected reference airfoil.<br>" +\
                    "This also scales the Reynolds number of its polars<br>" +\
                    "allowing to compare airfoils at their wing section.<br>")
        r += 1
        FieldF (l,r,c, lab="Scale to", width=60, unit="%", step=10, dec=0, lim=(5,500),
                obj=self, prop=Airfoil_Scale_Dialog.scale_factor)
        r += 1

        l.setRowStretch (r,1)    
        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (2,2)

        return l


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttonBox = QDialogButtonBox (QDialogButtonBox.StandardButton.Close) #  | QDialogButtonBox.StandardButton.Cancel)
        self._close_btn  = buttonBox.button(QDialogButtonBox.StandardButton.Close)
        return buttonBox 



class Calc_Reynolds_Dialog (Dialog):
    """ Little dialog to calculate Reynolds from velocity and chord"""

    _width  = 310
    _height = 200

    name = "Calculate Reynolds Number"


    def __init__ (self, parent : QWidget,  
                  re_asK : int = None,                  # initial Reynolds in 1000
                  fixed_chord : float = None,           # fixed chord length in mm
                  **kwargs): 

       
        self._has_been_set = False
        self._v      = 30.0
        self._chord  = fixed_chord if fixed_chord is not None else 200
        self._chord_fixed = fixed_chord is not None

        super().__init__ (parent, **kwargs)
        
        if re_asK is not None:
            self.set_re_asK (re_asK)                # will also set v
            self._has_been_set = False              # but not yet confirmed by user


    @property
    def re_asK (self) -> int: 
        """ Reynolds number base 1000"""
        return int(re_from_v(self.v, self.chord/1000, round_to=None) / 1000)
     
    def set_re_asK (self, aVal : float): 

        if not isinstance(aVal, (int, float)):
            return
        self.set_v (v_from_re(aVal*1000, self.chord/1000, round_dec=None))              # chord in m


    @property
    def v (self) -> float:
        """ velocity in m/s """
        return self._v  
    
    def set_v (self, aVal : float):
        if not isinstance(aVal, (int, float)):
            return
        self._v = aVal
        self._has_been_set = True
        self.refresh()


    @property
    def chord (self) -> float:
        """ chord in mm """
        return self._chord
    def set_chord (self, aVal : float):
        if not isinstance(aVal, (int, float)):
            return
        self._chord = aVal
        self._has_been_set = True
        self.refresh()  


    @property
    def has_been_set (self) -> bool:
        """ True if Reynolds was been set in this dialog """
        return self._has_been_set 


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r,c = 0,0 
        SpaceR (l, r, stretch=0, height=5) 
        r += 1
        FieldF  (l,r,c, lab="Chord", width=80, step=10, lim=(10, 9999), dec=0, unit="mm",
                        obj=self, prop=Calc_Reynolds_Dialog.chord,
                        disable=self._chord_fixed)
        Slider  (l,r,c+3, width=80,  lim=(10, 500),   
                        obj=self, prop=Calc_Reynolds_Dialog.chord,
                        hide=self._chord_fixed)
        r += 1
        FieldF  (l,r,c, lab="Velocity", width=80, unit="m/s", step=1, lim=(1, 360), dec=1,
                        obj=self, prop=Calc_Reynolds_Dialog.v)

        Slider  (l,r,c+3, width=80, lim=(1,100), 
                        obj=self, prop=Calc_Reynolds_Dialog.v)
        r += 1
        SpaceR  (l, r, stretch=2, height=5) 
        r += 1
        FieldF  (l,r,c, lab="Reynolds", width=80, unit="k", step=10, lim=(1, 9999), dec=0,
                        obj=self, prop=Calc_Reynolds_Dialog.re_asK)
        r += 1
        Label   (l,r,c+1, style=style.COMMENT, colSpan=5, 
                        get=f"ρ={AIR_RHO}, η={AIR_ETA:.2E} at {TEMP_DEFAULT}°C and {ALT_DEFAULT}m")

        l.setColumnMinimumWidth (0,70)
        l.setColumnMinimumWidth (2,5)
        l.setColumnMinimumWidth (3,50)
        l.setColumnStretch (5,2)   

        return l


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.rejected.connect(self.close)

        return buttonBox 



class Calc_Re_Sqrt_Cl_Dialog (Dialog):
    """ Little dialog to calculate Re.sqrt(Cl) from wing load and chord"""

    _width  = 310
    _height = 200

    name = "Calculate Re·√Cl"

    def __init__ (self, parent : QWidget,  
                  re_asK : int = None,                  # initial Reynolds in 1000
                  fixed_chord : float = None,           # fixed chord length in mm
                  **kwargs): 

        self._has_been_set = False
        self._load   = 40.0                             # wing load in g/dm²
        self._chord  = fixed_chord if fixed_chord is not None else 200
        self._chord_fixed = fixed_chord is not None

        super().__init__ (parent, **kwargs)
        
        if re_asK is not None:
            self.set_re_asK (re_asK)                    # will also set load
            self._has_been_set = False                  # but not yet confirmed by user


    @property
    def re_asK (self) -> int: 
        """ Reynolds number base 1000"""
        return int(re_sqrt_from_load(self.load/10, self.chord/1000, round_to=None) / 1000)
     
    def set_re_asK (self, aVal : float): 

        if not isinstance(aVal, (int, float)):
            return
        self.set_load (load_from_re_sqrt(aVal*1000, self.chord/1000, round_dec=None)*10)   # chord in m


    @property
    def load (self) -> float:
        """ wing load in g/dm² """
        return self._load   
    def set_load (self, aVal : float):
        if not isinstance(aVal, (int, float)):
            return
        self._load = aVal
        self._has_been_set = True
        self.refresh()



    @property
    def chord (self) -> float:
        """ chord in mm """
        return self._chord
    def set_chord (self, aVal : float):
        if not isinstance(aVal, (int, float)):
            return
        self._chord = aVal
        self._has_been_set = True
        self.refresh()  


    @property
    def has_been_set (self) -> bool:
        """ True if Re sqrt(cl) was been set in this dialog """
        return self._has_been_set 


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r,c = 0,0 
        SpaceR (l, r, stretch=0, height=5) 
        r += 1
        FieldF  (l,r,c, lab="Chord", width=80, step=10, lim=(10, 9999), dec=0, unit="mm",
                        obj=self, prop=Calc_Re_Sqrt_Cl_Dialog.chord,
                        disable=self._chord_fixed)
        Slider  (l,r,c+3, width=80,  lim=(10, 500),   
                        obj=self, prop=Calc_Re_Sqrt_Cl_Dialog.chord,
                        hide=self._chord_fixed)
        r += 1
        FieldF  (l,r,c, lab="Wing load", width=80, unit="g/dm²", step=1, lim=(1, 999), dec=0,
                        obj=self, prop=Calc_Re_Sqrt_Cl_Dialog.load)

        Slider  (l,r,c+3, width=80, lim=(1,200), 
                        obj=self, prop=Calc_Re_Sqrt_Cl_Dialog.load)
        r += 1
        SpaceR  (l, r, stretch=2, height=5) 
        r += 1
        FieldF  (l,r,c, lab="Re·√Cl", width=80, unit="k", step=10, lim=(1, 999), dec=0,
                        obj=self, prop=Calc_Re_Sqrt_Cl_Dialog.re_asK)
        r += 1
        Label   (l,r,c+1, style=style.COMMENT, colSpan=5, 
                        get=f"ρ={AIR_RHO}, η={AIR_ETA:.2E} at {TEMP_DEFAULT}°C and {ALT_DEFAULT}m")

        l.setColumnMinimumWidth (0,70)
        l.setColumnMinimumWidth (2,5)
        l.setColumnMinimumWidth (3,50)
        l.setColumnStretch (5,2)   

        return l


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.rejected.connect(self.close)

        return buttonBox 

