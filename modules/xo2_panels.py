#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

UI panels 

"""

from PyQt6.QtWidgets        import QDialog

from base.widgets           import * 
from base.panels            import Edit_Panel, Toaster

from airfoil_widgets        import Airfoil_Select_Open_Widget

from xo2_dialogs            import Xo2_Input_File_Dialog, Xo2_Description_Dialog, Xo2_OpPoint_Def_Dialog

from model.airfoil          import Airfoil
from model.polar_set        import Polar_Definition
from model.case             import Case_Optimize
from model.xo2_input        import Input_File
from model.xo2_input        import Nml_bezier_options, Nml_hicks_henne_options, Nml_camb_thick_options
from model.xo2_input        import Nml_operating_conditions, OpPoint_Definitions, OpPoint_Definition
from model.xo2_input        import Nml_info
from model.xo2_input        import Nml_optimization_options


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)




class Panel_Xo2_Abstract (Edit_Panel):
    """ 
    Abstract superclass for Edit/View-Panels of AirfoilEditor Optimize mode
        - has semantics of App
        - connect / handle signals 
    """

    @property
    def myApp (self):
        return self._parent 
    
    @property
    def case (self) -> Case_Optimize:
        return self.myApp.case()

    @property
    def input_file (self) -> Input_File:
        return self.case.input_file

    @property
    def mode_optimize (self) -> bool:
        """ panel in optimize_mode or disabled ? - from App """
        return self.myApp.mode_optimize 


    @override
    @property
    def _isDisabled (self) -> bool:
        """ overloaded: only enabled when not running """
        return self.case.isRunning if self.mode_optimize else True


    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is not Bezier """
        return self.mode_optimize
    

    @override
    def _set_panel_layout (self ):
        """ Set layout of self._panel """
        # overridden to connect to widgets changed signal

        super()._set_panel_layout ()
        for w in self.widgets:
            w.sig_changed.connect (self.refresh)   



class Panel_File_Optimize (Panel_Xo2_Abstract):
    """ File panel with open / save / ... """

    name = 'Optimize Mode'


    @property
    def airfoil (self) -> Airfoil:
        return self.myApp.airfoil_org


    def _init_layout (self): 

        self.set_background_color (color='darkturquoise', alpha=0.2)

        l = QGridLayout()
        r,c = 0, 0 
        Field (l,r,c, colSpan=3, width=190, get=lambda: self.airfoil.fileName)
        r += 1
        ComboSpinBox (l,r,c, colSpan=2, width=160, get=self.airfoil_fileName, 
                             set=self.set_airfoil_by_fileName,
                             options=self.airfoil_fileNames,
                             signal=False)
        r += 1
        SpaceR (l,r)
        l.setRowStretch (r,2)
        r += 1
        Button (l,r,c,  text="&Finish ...", width=90, 
                        set=lambda : self.myApp.mode_optimize_finished(ok=True), 
                        toolTip="Save current airfoil, optionally modifiy name and leave optimize mode")
        r += 1
        SpaceR (l,r, height=5, stretch=0)
        r += 1
        Button (l,r,c,  text="&Cancel",  width=90, 
                        set=lambda : self.myApp.mode_optimize_finished(ok=False),
                        toolTip="Cancel optimization of airfoil")
        r += 1
        SpaceR (l,r, height=5, stretch=0)
        l.setColumnStretch (3,2)
        l.setContentsMargins (QMargins(0, 0, 0, 0)) 

        return l



    def airfoil_fileName(self) -> list[str]:
        """ fileName of current airfoil without extension"""
        return os.path.splitext(self.airfoil.fileName)[0]


    def airfoil_fileNames(self) -> list[str]:
        """ list of design airfoil fileNames without extension"""

        fileNames = []
        for airfoil in []: # self.case.airfoil_designs:
            fileNames.append (os.path.splitext(airfoil.fileName)[0])
        return fileNames


    def set_airfoil_by_fileName (self, fileName : str):
        """ set new current design airfoil by fileName"""

        pass
        # airfoil = self.case.get_design_by_name (fileName)
        # self.myApp.set_airfoil (airfoil)



class Panel_Xo2_Case (Panel_Xo2_Abstract):
    """ Main panel of optimization"""

    name = 'Case'
    _width  = (300, 300)

    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        l_head.addStretch(1)
        Button (l_head, text="Run Optimizer", width=100, button_style = button_style.PRIMARY,
                set=self.myApp.optimize_run, toolTip="Run Optimizer Xoptfoil2")        
        l_head.addSpacing (23)


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Field  (l,r,c,  lab="Input file", 
                        obj=self.input_file, prop=Input_File.fileName)
        ToolButton (l,r,c+2, icon=Icon.EDIT, set=self._edit_input_file)
        r += 1
        SpaceR (l,r,    height=5, stretch=0)
        r += 1
        Label  (l,r,c,  colSpan=2, height=(None,None), style=style.COMMENT,
                        get=lambda: self.input_file.nml_info.descriptions_string)
        ToolButton (l,r,c+2, icon=Icon.EDIT, align=ALIGN_TOP,
                        set=self._edit_description)
        l.setRowStretch (r,4)
        r += 1
        Label  (l,r,c,  style=style.COMMENT, get='Author',
                        hide=lambda: not self.input_file.nml_info.author)
        Label  (l,r,c+1,style=style.COMMENT,
                        get=lambda: self.input_file.nml_info.author,
                        hide=lambda: not self.input_file.nml_info.author)
        r += 1
        l.setRowStretch (r,1)
        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (1,3)
        return l 


    def _edit_input_file (self):
        """ open text editor to edit Xoptfoil2 input file"""

        saved = self.input_file.save_nml ()

        if saved: 
            msg = "Input data saved to Input file"
            Toaster.showMessage (self, msg, corner=Qt.Corner.BottomLeftCorner, margin=QMargins(0, 0, 0, 0),
                                 toast_style=style.HINT)

        dialog = Xo2_Input_File_Dialog (self,self.input_file, dx=200, dy=-900)
        dialog.exec () 

        if dialog.result() == QDialog.DialogCode.Accepted:
            msg = "Input file successfully checked and saved"
            Toaster.showMessage (self, msg, corner=Qt.Corner.BottomLeftCorner, margin=QMargins(0, 0, 0, 0),
                                 toast_style=style.GOOD)
            
            self.myApp.sig_xo2_input_changed.emit()


    def _edit_description (self):
        """ open text editor to edit Xoptfoil2 input description"""

        dialog = Xo2_Description_Dialog (self,self.input_file.nml_info.descriptions_string, dx=250, dy=-250)
        dialog.exec () 

        if dialog.result() == QDialog.DialogCode.Accepted:
            descriptions = dialog.new_text.split ("\n")
            self.input_file.nml_info.set_descriptions (descriptions)
            
            self.myApp.sig_xo2_input_changed.emit()



class Panel_Xo2_Shape_Functions (Panel_Xo2_Abstract):
    """ Main panel of optimization"""

    name = 'Shaping'
    _width  = (230, None)

        
    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        l_head.addStretch(1)
        ComboBox (l_head, width=100, 
                get=lambda: self.shape_functions, set=self.set_shape_functions,
                options=lambda: self.available_shape_functions)

    @property
    def shape_functions (self) -> str:
        return self.optimization_options.shape_functions if self.case else None
    def set_shape_functions (self, aFunc : str):
        if self.case:
            self.optimization_options.set_shape_functions (aFunc)
            # manuel refresh as sub panels are no Widgets
            w : Edit_Panel
            for w in self._panel.findChildren (Edit_Panel):
                w.refresh ()
            self.refresh()


    @property
    def available_shape_functions (self) -> list[str]:
        return self.optimization_options.SHAPE_FUNCTIONS if self.case else []

    @property
    def bezier_options (self) -> Nml_bezier_options:
        return self.case.input_file.nml_bezier_options

    @property
    def hicks_henne_options (self) -> Nml_hicks_henne_options:
        return self.case.input_file.nml_hicks_henne_options

    @property
    def camb_thick_options (self) -> Nml_camb_thick_options:
        return self.case.input_file.nml_camb_thick_options

    @property
    def optimization_options (self) -> Nml_optimization_options:
        return self.case.input_file.nml_optimization_options


    class Panel_Shape_Function_Def (Edit_Panel):
        """ Mini sub panel to edit the shape functions properties """

        name = None                                         # suppress header

        _height = (None, None) 
        _panel_margins = (0, 0, 0, 0)                       # no inset of panel data 
        _main_margins  = (0, 0, 0, 0)                       # margins of Edit_Panel

        @override
        def set_background_color (self, **_):
            # no darker background 
            pass

        @override
        @property
        def _isDisabled (self) -> bool:
            """ overloaded: only enabled when not running"""
            parent : Panel_Xo2_Shape_Functions = self._parent
            return parent.case.isRunning


    @property
    def _panel_bezier_options (self) -> Panel_Shape_Function_Def:

        l = QGridLayout()
        r,c = 0, 0
        Label (l,r,c, get="Bezier control Points", colSpan=4)
        r += 1
        FieldI (l,r,c, lab='Upper side', width=50, step=1, lim=(3,10),
                get=lambda: self.bezier_options.ncp_top,
                set=self.bezier_options.set_ncp_top)
        r += 1
        FieldI (l,r,c, lab='Lower side', width=50, step=1, lim=(3,10),
                get=lambda: self.bezier_options.ncp_bot,
                set=self.bezier_options.set_ncp_bot)
        r += 1
        l.setRowStretch (r,2)
        l.setColumnMinimumWidth (0,70)
        l.setColumnStretch (4,2)

        return self.Panel_Shape_Function_Def (parent=self, layout=l, 
                    hide=lambda: not self.shape_functions == Nml_optimization_options.BEZIER)
       

    @property
    def _panel_hicks_henne_options (self) -> Panel_Shape_Function_Def:

        l = QGridLayout()
        r,c = 0, 0
        Label (l,r,c, get="Hicks Henne Functions", colSpan=4)
        r += 1
        FieldI (l,r,c, lab='Upper side', width=50, step=1, lim=(0, 8),
                get=lambda: self.hicks_henne_options.nfunctions_top,
                set=self.hicks_henne_options.set_nfunctions_top)
        r += 1
        FieldI (l,r,c, lab='Lower side', width=50, step=1, lim=(0, 8),
                get=lambda: self.hicks_henne_options.nfunctions_bot,
                set=self.hicks_henne_options.set_nfunctions_bot)
        r += 1
        l.setRowStretch (r,2)
        l.setColumnMinimumWidth (0,70)
        l.setColumnStretch (4,2)

        return self.Panel_Shape_Function_Def (parent=self, layout=l,
                    hide=lambda: not self.shape_functions == Nml_optimization_options.HICKS_HENNE)


    @property
    def _panel_camb_thick_options (self) -> Panel_Shape_Function_Def:

        l = QGridLayout()
        r,c = 0, 0
        Label (l,r,c, get="Geometry parameters", colSpan=4)
        r += 1
        CheckBox (l,r,c, text="Thickness",
                    get=lambda: self.camb_thick_options.thickness,
                    set=self.camb_thick_options.set_thickness)
        CheckBox (l,r,c+1, text="... position",
                    get=lambda: self.camb_thick_options.thickness_pos,
                    set=self.camb_thick_options.set_thickness_pos)
        r += 1
        CheckBox (l,r,c, text="Camber",
                    get=lambda: self.camb_thick_options.camber,
                    set=self.camb_thick_options.set_camber)
        CheckBox (l,r,c+1, text="... position",
                    get=lambda: self.camb_thick_options.camber_pos,
                    set=self.camb_thick_options.set_camber_pos)
        r += 1
        CheckBox (l,r,c, text="LE radius",
                    get=lambda: self.camb_thick_options.le_radius,
                    set=self.camb_thick_options.set_le_radius)
        CheckBox (l,r,c+1, text="... blend dist",
                    get=lambda: self.camb_thick_options.le_radius_blend,
                    set=self.camb_thick_options.set_le_radius_blend)
        r += 1
        l.setRowStretch (r,2)
        l.setColumnMinimumWidth (0,90)
        l.setColumnMinimumWidth (1,90)
        l.setColumnStretch (4,2)

        return self.Panel_Shape_Function_Def (parent=self, layout=l,
                    hide=lambda: not self.shape_functions == Nml_optimization_options.CAMB_THICK)


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        l.addWidget (self._panel_bezier_options,      r, c, 1, 3)
        l.addWidget (self._panel_hicks_henne_options, r, c, 1, 3)
        l.addWidget (self._panel_camb_thick_options,  r, c, 1, 3)

        r += 1
        l.setRowStretch (r,2)
        r += 1
        Label (l,r,c, get=self._info_design_variables, colSpan=4, style=style.COMMENT)
        l.setColumnMinimumWidth (0,70)
        l.setColumnStretch (2,2)
        return l 


    def _info_design_variables (self) -> str:

        if self.optimization_options.shape_functions == Nml_optimization_options.HICKS_HENNE:
            n = self.hicks_henne_options.ndesign_var
        elif self.optimization_options.shape_functions == Nml_optimization_options.BEZIER:
            n = self.bezier_options.ndesign_var
        elif self.optimization_options.shape_functions == Nml_optimization_options.CAMB_THICK:
            n = self.camb_thick_options.ndesign_var
        else:
            n = 0 

        return f"Will be {n} design variables"




class Panel_Xo2_Seed_Airfoil (Panel_Xo2_Abstract):
    """ Define seed airfoil"""

    name = 'Seed Airfoil'
    _width  = (220, 250)

    @property
    def hicks_henne_options (self) -> Nml_hicks_henne_options:
        return self.case.input_file.nml_hicks_henne_options
    

    def show_smooth_seed (self) -> bool:

        shape_functions = self.input_file.nml_optimization_options.shape_functions
        return shape_functions == Nml_optimization_options.HICKS_HENNE and \
                not self.input_file.airfoil_seed.isBezierBased


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Airfoil_Select_Open_Widget (l,r,c, colSpan=4, signal=False, 
                                    textOpen="&Open", widthOpen=90, 
                                    get=lambda: self.input_file.airfoil_seed,
                                    set=self.input_file.set_airfoil_seed)
        r += 1

        CheckBox (l,r,c, text="Smooth Seed",
                    get=lambda: self.hicks_henne_options.smooth_seed,
                    set=self.hicks_henne_options.set_smooth_seed,
                    hide=lambda: not self.show_smooth_seed())

        r += 1
        l.setRowStretch (r,2)
#        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (1,3)
        return l 




class Panel_Xo2_Operating_Conditions (Panel_Xo2_Abstract):
    """ Define seed airfoil"""

    name = 'Operating Conditions'
    _width  = (450, None)

    def __init__ (self, *args, **kwargs):

        self._cur_opPoint_def = None 

        super().__init__ (*args, **kwargs)

        # connect to update for changes made in diagram 
        self.myApp.sig_opPoint_def_selected.connect  (self.set_cur_opPoint_def)


    @property
    def operating_conditions (self) -> Nml_operating_conditions:
        return self.case.input_file.nml_operating_conditions
    
    @property
    def opPoint_defs (self) -> OpPoint_Definitions:
        return self.case.input_file.opPoint_defs

    @property
    def polar_defs (self) -> list[Polar_Definition]:
        return self.myApp.polar_definitions()

    @property
    def cur_opPoint_def (self) -> OpPoint_Definition:
        """ current, selected opPoint def"""
        if self._cur_opPoint_def is None: 
            self._cur_opPoint_def = self.opPoint_defs [0] if self.opPoint_defs else None
        return self._cur_opPoint_def

    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        ComboBox (l,r,c, lab="Default Polar", width=130, 
                get=lambda: self.opPoint_defs.polar_def_default.name, set=self.set_polar_def,
                options=lambda: [polar_def.name for polar_def in self.polar_defs])
        r += 1
        ComboSpinBox (l,r,c, lab="Op Point", width=240,  
                get=lambda: self.cur_opPoint_def.labelLong,
                set=self.set_cur_opPoint_def_from_label,
                options=lambda:  [opPoint_def.labelLong for opPoint_def in self.opPoint_defs])
        ToolButton (l,r,c+2, icon=Icon.EDIT, set=self._edit_opPoint_def)

        r += 1
        SpaceR   (l,r)
        r += 1
        CheckBox (l,r,c, text="Use Flaps", colSpan=2,
                get=lambda: self.operating_conditions.use_flap, 
                set=self.operating_conditions.set_use_flap)
        r += 1

        l.setRowStretch (r,3)
        l.setColumnMinimumWidth (0,80)
        # l.setColumnStretch (2,1)
        l.setColumnStretch (5,3)
        return l 


    def set_polar_def (self, polar_def_str: str):
        """ set defualt polar definition by string"""
        polar_defs : list [Polar_Definition] = self.myApp.polar_definitions()
        for polar_def in polar_defs:
            if polar_def.name == polar_def_str:
                self.opPoint_defs.set_polar_def_default (polar_def)
                break

    def set_cur_opPoint_def (self, opPoint_def):
        """ slot - set from diagram"""
        self._cur_opPoint_def = opPoint_def
        self.refresh()

 
    def set_cur_opPoint_def_from_label (self, aStr: str):
        """ set from labelLong - for ComboBox"""
        for opPoint_def in self.opPoint_defs:
            if opPoint_def.labelLong == aStr: 
                self._cur_opPoint_def = opPoint_def
                self.myApp.sig_opPoint_def_selected.emit(opPoint_def)
                break


    def _edit_opPoint_def (self):
        """ open dialog to edit current opPoint def"""
        self.myApp.edit_opPoint_def (self.cur_opPoint_def)

