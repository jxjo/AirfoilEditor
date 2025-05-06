#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

UI panels 

"""

import fnmatch   
from shutil                 import copyfile

from PyQt6.QtWidgets        import QDialog, QFileDialog

from base.widgets           import * 
from base.panels            import Edit_Panel, Toaster, MessageBox

from airfoil_widgets        import Airfoil_Select_Open_Widget

from xo2_dialogs            import Xo2_Input_File_Dialog, Xo2_Description_Dialog, Xo2_OpPoint_Def_Dialog

from model.airfoil          import Airfoil
from model.polar_set        import Polar_Definition
from model.case             import Case_Optimize
from model.xo2_input        import *


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
        return self.dataObject

    @property
    def input_file (self) -> Input_File:
        return self.case.input_file

    @property
    def mode_optimize (self) -> bool:
        """ panel in optimize_mode or disabled ? - from App """
        return isinstance (self.case, Case_Optimize) 


    @override
    @property
    def _isDisabled (self) -> bool:
        """ overloaded: only enabled when not running """
        return self.case.isRunning if self.mode_optimize else True


    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if mode optimize """
        return self.mode_optimize
    

    @override
    def _set_panel_layout (self ):
        """ Set layout of self._panel """
        # overridden to connect to widgets changed signal

        super()._set_panel_layout ()
        for w in self.widgets:
            w.sig_changed.connect (self._on_widget_changed)   


    def _on_widget_changed (self, widget):
        """ user changed data in widget"""
        logger.debug (f"{self} {widget} widget changed slot")
        self.myApp._on_xo2_input_changed ()




class Panel_File_Optimize (Panel_Xo2_Abstract):
    """ File panel with open / save / ... """

    name = 'Optimize Mode'

    
    @property
    def workingDir (self) -> str:
        #todo 
        return self.myApp.workingDir


    def _init_layout (self): 

        self.set_background_color (color='darkturquoise', alpha=0.2)

        l = QGridLayout()
        r,c = 0, 0 
        ComboBox (l,r,c, colSpan=2, width=160, 
                        get=lambda:self._input_fileName, set=self._set_input_fileName,
                        options= lambda: Case_Optimize.input_fileNames_in_dir (self.workingDir),
                        toolTip="The Xoptfoil2 input file")
        ToolButton (l,r,c+3, icon=Icon.OPEN, set=self._open_input_file, toolTip="Select a Xoptfoil2 input file")
        ToolButton (l,r,c+4, icon=Icon.EDIT, set=self._edit_input_file,
                    toolTip="Direct editing of the Xoptfoil2 input file")

        r += 1
        Button   (l,r,c, width=90, text="New Version", set=self._new_version,
                  toolTip="Create a new version of the existing input file")

        # Field (l,r,c, colSpan=3, width=190, get=lambda: self.airfoil.fileName)
        # r += 1
        # ComboSpinBox (l,r,c, colSpan=2, width=160, get=self.airfoil_fileName, 
        #                      set=self.set_airfoil_by_fileName,
        #                      options=self.airfoil_fileNames,
        #                      signal=False)
        r += 1
        SpaceR (l,r)
        l.setRowStretch (r,2)
        r += 1
        Button (l,r,c,  text="&Finish ...", width=90, 
                        set=lambda : self.myApp.mode_optimize_finished(ok=True), 
                        toolTip="Save current airfoil, optionally modifiy name and leave optimize mode")
        r += 1
        Button (l,r,c,  text="&Cancel",  width=90, 
                        set=lambda : self.myApp.mode_optimize_finished(ok=False),
                        toolTip="Cancel optimization of airfoil")
        r += 1
        SpaceR (l,r, height=5, stretch=0)
        l.setColumnStretch (4,2)
        l.setContentsMargins (QMargins(0, 0, 0, 0)) 

        return l


    @property
    def _input_fileName (self) -> str:
        return self.input_file.fileName

    def _set_input_fileName (self, aFileName : str, workingDir=None):

        if workingDir is None: 
            workingDir = self.workingDir

        self.myApp.change_case_optimize (aFileName, workingDir)


    def _new_version (self): 
        """ create new version of an existing case self.input_file"""

        new_fileName = Case_Optimize.new_input_fileName_version (self._input_fileName, self.workingDir)

        if new_fileName:
            copyfile (os.path.join (self.workingDir,self._input_fileName), os.path.join (self.workingDir,new_fileName))
            self._set_input_fileName (new_fileName)
            self.refresh()
        else: 
            MessageBox.error   (self,'Create new version', f"New Version of {self._input_fileName} could not be created.",
                                min_width=350)


    def _open_input_file (self):
        """ open a new airfoil and load it"""

        # build somethinglike "*.inp *.xo2" as filter for the dialog
        filter_string = ""
        for extension in Case_Optimize.INPUT_FILE_EXT:
            filter_string += f" *{extension}" if filter_string else f"*{extension}"

        filters  = f"Xoptfoil2 Input files ({filter_string})"

        newPathFileName, *_ = QFileDialog.getOpenFileName(self, filter=filters, directory=self.workingDir)

        if newPathFileName:                         # user pressed open

            self._set_input_fileName (os.path.basename (newPathFileName), workingDir=os.path.dirname (newPathFileName))

            self.refresh()


    def _edit_input_file (self):
        """ open text editor to edit Xoptfoil2 input file"""

        saved = self.input_file.save_nml ()

        if saved: 
            msg = "Input data saved to Input file"
            Toaster.showMessage (self, msg, corner=Qt.Corner.BottomLeftCorner, margin=QMargins(0, 0, 0, 0),
                                 toast_style=style.HINT)

        dialog = Xo2_Input_File_Dialog (self,self.input_file, parentPos=(0.8,0,9), dialogPos=(0,1))
        dialog.exec () 

        if dialog.result() == QDialog.DialogCode.Accepted:
            msg = "Input file successfully checked and saved"
            Toaster.showMessage (self, msg, corner=Qt.Corner.BottomLeftCorner, margin=QMargins(0, 0, 0, 0),
                                 toast_style=style.GOOD)
            
            self.myApp._on_xo2_input_changed()




class Panel_Xo2_Case (Panel_Xo2_Abstract):
    """ Main panel of optimization"""

    name = 'Case'
    _width  = (350, 350)

    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        l_head.addStretch(1)
        Button (l_head, text="Run Optimizer", width=100, button_style = button_style.PRIMARY,
                # style=style.GOOD, 
                set=self.myApp.optimize_run, toolTip="Run Optimizer Xoptfoil2")        
        l_head.addSpacing (23)

    @property
    def optimization_options (self) -> Nml_optimization_options:
        return self.case.input_file.nml_optimization_options

    @property
    def hicks_henne_options (self) -> Nml_hicks_henne_options:
        return self.case.input_file.nml_hicks_henne_options


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Label  (l,r,c,  colSpan=2, height=(None,None), style=style.COMMENT,
                        get=lambda: self.input_file.nml_info.descriptions_string)
        ToolButton (l,r,c+2, icon=Icon.EDIT, align=ALIGN_TOP,
                        set=self._edit_description)
        r += 1
        SpaceR (l,r, stretch=0)
        # r += 1
        # Label  (l,r,c,  style=style.COMMENT, get='Author',
        #                 hide=lambda: not self.input_file.nml_info.author)
        # Label  (l,r,c+1,style=style.COMMENT,
        #                 get=lambda: self.input_file.nml_info.author,
        #                 hide=lambda: not self.input_file.nml_info.author)
        r += 1
        ComboBox (l,r,c, lab="Shape functions", lab_disable=True,
                        get=lambda: self.shape_functions, set=self.set_shape_functions,
                        options=lambda: self.optimization_options.SHAPE_FUNCTIONS if self.case else [])

        r += 1
        Label    (l,r,c, get="Seed Airfoil", lab_disable=True)
        Airfoil_Select_Open_Widget (l,r,c+1, colSpan=2, signal=False, 
                                    textOpen="&Open", widthOpen=90, 
                                    get=lambda: self.input_file.airfoil_seed,
                                    set=self.input_file.set_airfoil_seed)
        r += 1
        CheckBox (l,r,c+1, text="Smooth Seed",
                    get=lambda: self.hicks_henne_options.smooth_seed,
                    set=self.hicks_henne_options.set_smooth_seed,
                    hide=lambda: not self._show_smooth_seed())
        r += 1
        l.setRowStretch (r,1)
        l.setColumnMinimumWidth (0,90)
        l.setColumnStretch (1,5)
        return l 


    def _edit_description (self):
        """ open text editor to edit Xoptfoil2 input description"""

        dialog = Xo2_Description_Dialog (self,self.input_file.nml_info.descriptions_string, 
                                         parentPos=(0.8,0,3), dialogPos=(0,1))
        dialog.exec () 

        if dialog.result() == QDialog.DialogCode.Accepted:
            descriptions = dialog.new_text.split ("\n")
            self.input_file.nml_info.set_descriptions (descriptions)
            
            self.myApp._on_xo2_input_changed ()


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


    def _show_smooth_seed (self) -> bool:

        shape_functions = self.input_file.nml_optimization_options.shape_functions
        return shape_functions == Nml_optimization_options.HICKS_HENNE and \
                not self.input_file.airfoil_seed.isBezierBased


class Panel_Xo2_Shape_Bezier (Panel_Xo2_Abstract):
    """ Edit Bezier options """

    name = 'Bezier Options '
    _width  = (250, None)


    @override
    @property
    def shouldBe_visible (self) -> bool:
        return self.isBezier

    @property
    def isBezier (self) -> bool:
        return super().mode_optimize and self.optimization_options.shape_functions == Nml_optimization_options.BEZIER

    @property
    def bezier_options (self) -> Nml_bezier_options:
        return self.case.input_file.nml_bezier_options

    @property
    def optimization_options (self) -> Nml_optimization_options:
        return self.case.input_file.nml_optimization_options


    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0
        Label (l,r,c, get="Bezier control Points", colSpan=4)
        r += 1
        FieldI (l,r,c, lab='Upper side', width=50, step=1, lim=(3,10),
                obj=lambda: self.bezier_options, prop=Nml_bezier_options.ncp_top)
        r += 1
        FieldI (l,r,c, lab='Lower side', width=50, step=1, lim=(3,10),
                obj=lambda: self.bezier_options, prop=Nml_bezier_options.ncp_bot)
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Label (l,r,c, colSpan=4, style=style.COMMENT,
               get=lambda: f"Will be {self.bezier_options.ndesign_var} design variables")        
        l.setColumnMinimumWidth (0,70)
        l.setColumnStretch (4,2)

        return l
       



class Panel_Xo2_Shape_Hicks_Henne (Panel_Xo2_Abstract):
    """ Edit Hicks Henne options """

    name = 'Hicks-Henne Options '
    _width  = (250, None)


    @override
    @property
    def shouldBe_visible (self) -> bool:
        return self.isHicks_Henne

    @property
    def isHicks_Henne (self) -> bool:
        return super().mode_optimize and self.optimization_options.shape_functions == Nml_optimization_options.HICKS_HENNE

    @property
    def hicks_henne_options (self) -> Nml_hicks_henne_options:
        return self.case.input_file.nml_hicks_henne_options

    @property
    def optimization_options (self) -> Nml_optimization_options:
        return self.case.input_file.nml_optimization_options


    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0
        Label (l,r,c, get="Hicks-Henne Functions", colSpan=4)
        r += 1
        FieldI (l,r,c, lab='Upper side', width=50, step=1, lim=(0, 8),
                obj=lambda: self.hicks_henne_options, prop=Nml_hicks_henne_options.nfunctions_top)
        r += 1
        FieldI (l,r,c, lab='Lower side', width=50, step=1, lim=(0, 8),
                obj=lambda: self.hicks_henne_options, prop=Nml_hicks_henne_options.nfunctions_bot)
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Label (l,r,c, colSpan=4, style=style.COMMENT,
               get=lambda: f"Will be {self.hicks_henne_options.ndesign_var} design variables")        
        l.setColumnMinimumWidth (0,70)
        l.setColumnStretch (4,2)

        return l
       



class Panel_Xo2_Shape_Camb_Thick (Panel_Xo2_Abstract):
    """ Edit Camb Thick options """

    name = 'Camb-Thick Options '
    _width  = (250, None)


    @override
    @property
    def shouldBe_visible (self) -> bool:
        return self.isCamb_Thick

    @property
    def isCamb_Thick (self) -> bool:
        return super().mode_optimize and self.optimization_options.shape_functions == Nml_optimization_options.CAMB_THICK

    @property
    def camb_thick_options (self) -> Nml_camb_thick_options:
        return self.case.input_file.nml_camb_thick_options

    @property
    def optimization_options (self) -> Nml_optimization_options:
        return self.case.input_file.nml_optimization_options


    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0
        Label (l,r,c, get="Geometry parameters", colSpan=4)
        r += 1
        CheckBox (l,r,c, text="Thickness",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.thickness)
        CheckBox (l,r,c+1, text="... position",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.thickness_pos)
        r += 1
        CheckBox (l,r,c, text="Camber",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.camber)
        CheckBox (l,r,c+1, text="... position",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.camber_pos)
        r += 1
        CheckBox (l,r,c, text="LE radius",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.le_radius)
        CheckBox (l,r,c+1, text="... blend dist",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.le_radius_blend)
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Label (l,r,c, colSpan=4, style=style.COMMENT,
               get=lambda: f"Will be {self.camb_thick_options.ndesign_var} design variables")        
        l.setColumnMinimumWidth (0,110)
        l.setColumnStretch (4,2)

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
        return self.input_file.nml_operating_conditions
    
    @property
    def opPoint_defs (self) -> OpPoint_Definitions:
        return self.input_file.opPoint_defs

    @property
    def polar_defs (self) -> list[Polar_Definition]:
        return self.myApp.polar_definitions()

    @property
    def cur_opPoint_def (self) -> OpPoint_Definition:
        """ current, selected opPoint def"""
        if not (self._cur_opPoint_def in self.opPoint_defs):                    # in case, case changed 
            self._cur_opPoint_def = self.opPoint_defs [0] if self.opPoint_defs else None
        return self._cur_opPoint_def

    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        ComboBox (l,r,c, lab="Default Polar", lab_disable=True, width=130, 
                get=lambda: self.opPoint_defs.polar_def_default.name, set=self.set_polar_def,
                options=lambda: [polar_def.name for polar_def in self.polar_defs])
        r += 1
        ComboBox (l,r,c, lab="Op Point", lab_disable=True, width=200,  
                get=lambda: self.cur_opPoint_def.labelLong if self.cur_opPoint_def else None ,
                set=self.set_cur_opPoint_def_from_label,
                options=lambda:  [opPoint_def.labelLong for opPoint_def in self.opPoint_defs])
        ToolButton (l,r,c+2, icon=Icon.EDIT,   set=self._edit_opPoint_def,
                    disable=lambda: not self.cur_opPoint_def)
        ToolButton (l,r,c+3, icon=Icon.DELETE, set=self._delete_opPoint_def,
                    disable=lambda: not self.opPoint_defs)
        ToolButton (l,r,c+4, icon=Icon.ADD, set=self._add_opPoint_def)

        r += 1
        SpaceR   (l,r)
        r += 1
        CheckBox (l,r,c, text="Dynamic Weighting", colSpan=2,
                get=lambda: self.operating_conditions.dynamic_weighting, 
                set=self.operating_conditions.set_dynamic_weighting)
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

    def _delete_opPoint_def (self):
        """ delete me opPoint_dev"""

        if not self.opPoint_defs: return 

        # define new current after deletion 
        if len(self.opPoint_defs) > 1: 
            if self.cur_opPoint_def.iPoint == len(self.opPoint_defs):
                new_index = -1
            elif self.cur_opPoint_def.iPoint > 1:
                new_index = self.cur_opPoint_def.iPoint - 1
            else:
                new_index = 0 
        else: 
            new_index = None

        self.cur_opPoint_def.delete_me ()

        # set new current 
        if new_index is not None: 
            self._cur_opPoint_def = self.opPoint_defs [new_index]
        else: 
            self._cur_opPoint_def = None

        self.refresh ()
        self.myApp._on_xo2_input_changed()
        self.myApp.sig_opPoint_def_selected.emit(self.cur_opPoint_def)


    def _add_opPoint_def (self):
        """ add a new opPoint_dev after current """

        self._cur_opPoint_def = self.opPoint_defs.create_after (self.cur_opPoint_def)

        self.refresh ()
        self.myApp._on_xo2_input_changed()
        self.myApp.sig_opPoint_def_selected.emit(self.cur_opPoint_def)


    def _edit_opPoint_def (self):
        """ open dialog to edit current opPoint def"""

        parentPos=(0.8, 0.2) 
        dialogPos=(0,1)

        self.myApp.edit_opPoint_def (self, parentPos, dialogPos, self.cur_opPoint_def)



class Panel_Xo2_Geometry_Targets (Panel_Xo2_Abstract):
    """ Edit geometry target """

    name = 'Geometry Targets'
    _width  = (230, None)

    @property
    def geometry_targets (self) -> Nml_geometry_targets:
        return self.case.input_file.nml_geometry_targets

    @property
    def thickness (self) -> GeoTarget_Definition | None: 
        return self.geometry_targets.thickness

    @property
    def camber (self) -> GeoTarget_Definition | None: 
        return self.geometry_targets.camber

    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0
        CheckBox    (l,r,c, text="Thickness", colSpan=2, 
                     get=lambda: self.thickness is not None, set=self.geometry_targets.activate_thickness)
        FieldF      (l,r,c+2, width=70, unit="%", step=0.2,
                     get=lambda: self.thickness.optValue, set=lambda x:self.thickness.set_optValue(x), 
                     hide=lambda: not self.thickness)
        r += 1
        FieldF      (l,r,c+1, lab="Weighting", lab_disable=True, width=70, step=0.2, lim=(-10,10), dec=2,
                     get=lambda: self.thickness.weighting, set=lambda x: self.thickness.set_weighting(x),
                     hide=lambda: self.thickness is None)
        Label       (l,r,c+3, style=style.COMMENT, 
                     get=lambda: self.thickness.weighting_fixed_label,
                     hide=lambda: self.thickness is None)

        r += 1
        CheckBox    (l,r,c, text="Camber", colSpan=2, 
                     get=lambda: self.camber is not None, set=self.geometry_targets.activate_camber)
        FieldF      (l,r,c+2, width=70, unit="%", step=0.2,
                     get=lambda: self.camber.optValue, set=lambda x: self.camber.set_optValue(x), 
                     hide=lambda: not self.camber)
        r += 1
        FieldF      (l,r,c+1, lab="Weighting", lab_disable=True, width=70, step=0.2, lim=(-10,10), dec=2,
                     get=lambda: self.camber.weighting, set=lambda x: self.camber.set_weighting(x),
                     hide=lambda: self.camber is None)
        Label       (l,r,c+3, style=style.COMMENT, 
                     get=lambda: self.camber.weighting_fixed_label,
                     hide=lambda: self.camber is None)
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Label (l,r,c, colSpan=4, style=style.COMMENT,
               get=lambda: f"Will be {len (self.geometry_targets.geoTarget_defs)} design variables",
               hide=lambda: len (self.geometry_targets.geoTarget_defs )== 0)        
        l.setColumnMinimumWidth (0,20)
        l.setColumnMinimumWidth (1,70)
        l.setColumnStretch (4,2)

        return l
     