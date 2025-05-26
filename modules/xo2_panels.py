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
from airfoil_ui_panels      import Polar_Definition_Dialog

from xo2_dialogs            import *

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
    from AirfoilEditor  import App_Main

    @property
    def app (self) -> App_Main:
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
        return self.case.isRunning if self.mode_optimize else False


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
        self.app._on_xo2_input_changed ()




class Panel_File_Optimize (Panel_Xo2_Abstract):
    """ File panel with open / save / ... """

    name = 'Optimize Mode'

    
    @property
    def workingDir (self) -> str:
        #todo 
        return self.app.workingDir


    def _init_layout (self): 

        self.set_background_color (color='darkturquoise', alpha=0.2)

        l = QGridLayout()
        r,c = 0, 0 
        ComboBox (l,r,c, colSpan=2,  
                        get=lambda:self._input_fileName, set=self._set_input_fileName,
                        options= lambda: Case_Optimize.input_fileNames_in_dir (self.workingDir),
                        toolTip="The Xoptfoil2 input file")
        ToolButton (l,r,c+3, icon=Icon.OPEN, set=self._open_input_file, toolTip="Select a Xoptfoil2 input file")

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
                        set=lambda : self.app.mode_optimize_finished(ok=True), 
                        toolTip="Save current airfoil, optionally modifiy name and leave optimize mode")
        r += 1
        Button (l,r,c,  text="&Cancel",  width=90, 
                        set=lambda : self.app.mode_optimize_finished(ok=False),
                        toolTip="Cancel optimization of airfoil")
        r += 1
        SpaceR (l,r, height=5, stretch=0)
        l.setColumnStretch (1,2)
        l.setContentsMargins (QMargins(0, 0, 0, 0)) 

        return l


    @property
    def _input_fileName (self) -> str:
        return self.input_file.fileName

    def _set_input_fileName (self, aFileName : str, workingDir=None):

        if workingDir is None: 
            workingDir = self.workingDir

        self.app.optimize_change_case (aFileName, workingDir)


    def _new_version (self): 
        """ create new version of an existing case self.input_file"""

        self.app.case_optimize_new_version ()


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



class Panel_Xo2_Case (Panel_Xo2_Abstract):
    """ Main panel of optimization"""

    name = 'Case'
    _width  = (320, 320)

    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        l_head.addStretch(1)
        Button (l_head, text="Run Xoptfoil2", width=120, button_style = button_style.PRIMARY,
                set=self.app.optimize_run, toolTip="Run Optimizer Xoptfoil2")        

    @property
    def optimization_options (self) -> Nml_optimization_options:
        return self.case.input_file.nml_optimization_options


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
        ComboBox    (l,r,c, lab="Shape functions", lab_disable=True,
                     get=lambda: self._shape_functions_label_long, set=self._set_shape_functions_label_long,
                     options=lambda: self.shape_functions_list)     
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self._edit_shape_functions,
                     toolTip="Edit options of shape functions")

        r += 1
        Label    (l,r,c, get="Seed Airfoil", lab_disable=True)
        Airfoil_Select_Open_Widget (l,r,c+1, colSpan=2, 
                                    textOpen="&Open", widthOpen=90, 
                                    obj=lambda: self.input_file, prop=Input_File.airfoil_seed)
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
            
            self.app._on_xo2_input_changed ()


    @property
    def shape_functions_list (self) -> list:
        l = []
        l.append (self.input_file.nml_bezier_options.label_long)
        l.append (self.input_file.nml_hicks_henne_options.label_long)
        l.append (self.input_file.nml_camb_thick_options.label_long)
        return l

    @property
    def _shape_functions_nml (self) -> Nml_Abstract:
        """ namelist of current shape functions"""

        if self.optimization_options.shape_functions == Nml_optimization_options.BEZIER:
            return self.input_file.nml_bezier_options
        if self.optimization_options.shape_functions == Nml_optimization_options.HICKS_HENNE:
            return self.input_file.nml_hicks_henne_options
        if self.optimization_options.shape_functions == Nml_optimization_options.CAMB_THICK:
            return self.input_file.nml_camb_thick_options

    @property
    def _shape_functions_label_long (self) -> str:

        return self._shape_functions_nml.label_long if self._shape_functions_nml.label_long else ''


    def _set_shape_functions_label_long (self, aLabel : str):
        """ setter for combobox"""

        if aLabel == self.input_file.nml_bezier_options.label_long:
            self.optimization_options.set_shape_functions (Nml_optimization_options.BEZIER)
        if aLabel == self.input_file.nml_hicks_henne_options.label_long:
            self.optimization_options.set_shape_functions (Nml_optimization_options.HICKS_HENNE)
        if aLabel == self.input_file.nml_camb_thick_options.label_long:
            self.optimization_options.set_shape_functions (Nml_optimization_options.CAMB_THICK)


    def _edit_shape_functions (self):
        """ open editor to change the paramters of the shape functions"""
        diag = None 
        parentPos=(0.8, 0.0)
        dialogPos=(0.2,1.1)
        if self.optimization_options.shape_functions == Nml_optimization_options.BEZIER:
            diag = Xo2_Bezier_Dialog (self, getter=self.input_file.nml_bezier_options, 
                                         parentPos=parentPos, dialogPos=dialogPos)
        if self.optimization_options.shape_functions == Nml_optimization_options.HICKS_HENNE:
            diag = Xo2_Hicks_Henne_Dialog (self, getter=self.input_file.nml_hicks_henne_options, 
                                         parentPos=parentPos, dialogPos=dialogPos)
        if self.optimization_options.shape_functions == Nml_optimization_options.CAMB_THICK:
            diag = Xo2_Camb_Thick_Dialog (self, getter=self.input_file.nml_camb_thick_options, 
                                         parentPos=parentPos, dialogPos=dialogPos)

        if diag:
            diag.exec()
            self.refresh ()
            self.app._on_xo2_input_changed()



class Panel_Xo2_Operating_Conditions (Panel_Xo2_Abstract):
    """ Define operating conditions"""

    name = 'Operating Conditions'
    _width  = 230


    @property
    def operating_conditions (self) -> Nml_operating_conditions:
        return self.input_file.nml_operating_conditions
    
    
    @property
    def opPoint_defs (self) -> OpPoint_Definitions:
        return self.input_file.opPoint_defs


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Label       (l,r,c, get="Default Polar", lab_disable=True)
        r += 1
        Field       (l,r,c, width=None, 
                    get=lambda: self.opPoint_defs.polar_def_default.name)
        ToolButton  (l,r,c+1, icon=Icon.EDIT,   set=self._edit_polar_def)
        r += 1
        CheckBox    (l,r,c, text="Dynamic Weighting", 
                    obj=lambda:  self.operating_conditions, prop=Nml_operating_conditions.dynamic_weighting)
        r += 1
        CheckBox    (l,r,c, text="Use Flaps", 
                    obj=lambda:  self.operating_conditions, prop=Nml_operating_conditions.use_flap)
        
        r += 1
        l.setRowStretch (r,3)
        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (0,2)

        return l


    def set_polar_def (self, polar_def_str: str):
        """ set defualt polar definition by string"""
        polar_defs : list [Polar_Definition] = self.app.polar_definitions
        for polar_def in polar_defs:
            if polar_def.name == polar_def_str:
                self.opPoint_defs.set_polar_def_default (polar_def)
                break


    def _edit_polar_def (self):
        """ edit default polar definition"""

        polar_def = self.opPoint_defs.polar_def_default
        diag = Polar_Definition_Dialog (self, polar_def, small_mode=True, parentPos=(0.9,0.1), dialogPos=(0,1))

        diag.setWindowTitle ("Default Polar of Op Points")
        diag.exec()

        self.opPoint_defs.set_polar_def_default (polar_def)
        self.app._on_xo2_input_changed()



class Panel_Xo2_Operating_Points (Panel_Xo2_Abstract):
    """ Define op Points of namelist operating_conditions"""

    name = 'Operating Points'
    _width  = 270

    def __init__ (self, *args, **kwargs):

        self._cur_opPoint_def = None 

        super().__init__ (*args, **kwargs)

        # connect to update for changes made in diagram 
        self.app.sig_opPoint_def_selected.connect  (self.set_cur_opPoint_def)

    
    @property
    def opPoint_defs (self) -> OpPoint_Definitions:
        return self.input_file.opPoint_defs

    @property
    def cur_opPoint_def (self) -> OpPoint_Definition:
        """ current, selected opPoint def"""
        if not (self._cur_opPoint_def in self.opPoint_defs):                    # in case, case changed 
            self._cur_opPoint_def = self.opPoint_defs [0] if self.opPoint_defs else None
        return self._cur_opPoint_def


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        ListBox    (l,r,c, width=None, rowSpan=4, height=(50,None),
                    get=lambda: self.cur_opPoint_def.labelLong if self.cur_opPoint_def else None ,
                    set=self.set_cur_opPoint_def_from_label,
                    signal=False,                                               # do not signal xo2_input changed
                    doubleClick=self._edit_opPoint_def,
                    options=lambda:  [opPoint_def.labelLong for opPoint_def in self.opPoint_defs])
        c += 1
        ToolButton  (l,r,c, icon=Icon.EDIT, align=ALIGN_RIGHT, 
                     set=self._edit_opPoint_def,
                     disable=lambda: not self.cur_opPoint_def)
        r += 1
        ToolButton  (l,r,c, icon=Icon.DELETE, align=ALIGN_RIGHT,
                     set=self._delete_opPoint_def,
                     disable=lambda: not self.opPoint_defs)
        r += 1
        ToolButton  (l,r,c, icon=Icon.ADD, align=ALIGN_RIGHT, 
                     set=self._add_opPoint_def)
        r += 1
        l.setRowStretch (r,3)
        l.setColumnStretch (0,2)
        l.setColumnMinimumWidth (c,30)

        return l


    def set_cur_opPoint_def (self, opPoint_def):
        """ slot - set from diagram"""
        self._cur_opPoint_def = opPoint_def
        self.refresh()

 
    def set_cur_opPoint_def_from_label (self, aStr: str):
        """ set from labelLong - for ComboBox"""
        for opPoint_def in self.opPoint_defs:
            if opPoint_def.labelLong == aStr: 
                self._cur_opPoint_def = opPoint_def
                self.app.sig_opPoint_def_selected.emit(opPoint_def)
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
        self.app._on_xo2_input_changed()
        self.app.sig_opPoint_def_selected.emit(self.cur_opPoint_def)


    def _add_opPoint_def (self):
        """ add a new opPoint_dev after current """

        self._cur_opPoint_def = self.opPoint_defs.create_after (self.cur_opPoint_def)

        self.refresh ()
        self.app._on_xo2_input_changed()
        self.app.sig_opPoint_def_selected.emit(self.cur_opPoint_def)


    def _edit_opPoint_def (self):
        """ open dialog to edit current opPoint def"""

        parentPos=(0.9, 0.2) 
        dialogPos=(0,1)

        self.app.edit_opPoint_def (self, parentPos, dialogPos, self.cur_opPoint_def)



class Panel_Xo2_Geometry_Targets (Panel_Xo2_Abstract):
    """ Edit geometry target """

    name = 'Geometry Targets'
    _width  = 210

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
                     get=lambda: self.thickness is not None, 
                     set=lambda x: self.geometry_targets.activate_thickness(x))
        FieldF      (l,r,c+2, width=70, unit="%", step=0.2,
                     obj=lambda: self.thickness, prop=GeoTarget_Definition.optValue,
                     hide=lambda: not self.thickness)
        r += 1
        FieldF      (l,r,c+1, lab="Weighting", lab_disable=True, width=70, step=0.2, lim=(-10,10), dec=2,
                     obj=lambda: self.thickness, prop=GeoTarget_Definition.weighting,
                     hide=lambda: self.thickness is None)
        Label       (l,r,c+3, style=style.COMMENT, 
                     get=lambda: self.thickness.weighting_fixed_label,
                     hide=lambda: self.thickness is None)

        r += 1
        CheckBox    (l,r,c, text="Camber", colSpan=2, 
                     get=lambda: self.camber is not None, 
                     set=lambda x: self.geometry_targets.activate_camber(x))
        FieldF      (l,r,c+2, width=70, unit="%", step=0.2,
                     obj=lambda: self.camber, prop=GeoTarget_Definition.optValue,
                     hide=lambda: not self.camber)
        r += 1
        FieldF      (l,r,c+1, lab="Weighting", lab_disable=True, width=70, step=0.2, lim=(-10,10), dec=2,
                     obj=lambda: self.camber, prop=GeoTarget_Definition.weighting,
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



class Panel_Xo2_Curvature (Panel_Xo2_Abstract):
    """ Edit curvature paramters """

    name = 'Curvature'
    _width  = 200


    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if mode optimize and not camb_thick """
        return super().shouldBe_visible and self.shape_functions != Nml_optimization_options.CAMB_THICK


    @property
    def shape_functions (self) -> str:
        return self.input_file.nml_optimization_options.shape_functions

    @property
    def curvature (self) -> Nml_curvature:
        return self.input_file.nml_curvature


    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0
        CheckBox    (l,r,c, text="Check curvature ", 
                     obj=lambda: self.curvature, prop=Nml_curvature.check_curvature)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, 
                     toolTip="Edit options",
                     set=self._edit_curvature_options,
                     hide=lambda: not self.curvature.check_curvature)
        r += 1
        Label       (l,r,c, style=style.COMMENT, colSpan=2, 
                     get="Allow reversal on ...",
                     hide=lambda: not self.curvature.check_curvature)
        r += 1
        CheckBox    (l,r,c, text="Top side (reflexed)", colSpan=2, 
                     get=lambda: self.curvature.max_curv_reverse_top == 1,
                     set=lambda x: self.curvature.set_max_curv_reverse_top(x),
                     hide=lambda: not self.curvature.check_curvature)
        r += 1
        CheckBox    (l,r,c, text="Bot side (rearloading)", colSpan=2,   
                     get=lambda: self.curvature.max_curv_reverse_bot == 1,
                     set=lambda x: self.curvature.set_max_curv_reverse_bot(x),
                     hide=lambda: not self.curvature.check_curvature)
        r += 1
        l.setRowStretch (r,2)
        l.setColumnStretch (0,2)

        return l


    def _edit_curvature_options (self): 

        diag = Xo2_Curvature_Dialog (self, getter=self.input_file.nml_curvature,
                                     shape_functions = self.input_file.nml_optimization_options.shape_functions, 
                                     parentPos=(0.5, 0.0), dialogPos=(0.8,1.1))
        diag.exec()
        self.refresh ()
        self.app._on_xo2_input_changed()



class Panel_Xo2_Advanced (Panel_Xo2_Abstract):
    """ Panel with the advanced input options """

    name = 'Advanced'
    _width  = 210


    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        l_head.addStretch(1)
        Button (l_head, text="Input File", width=70, button_style = button_style.SUPTLE,
                set=self._edit_input_file, toolTip="Direct editing of the Xoptfoil2 input file")        
        # l_head.addSpacing (23)


    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0

        CheckBox    (l,r,c,   get=lambda: not self.input_file.nml_particle_swarm_options.isDefault)
        Label       (l,r,c+1, get="Particle Swarm Options", lab_disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self._edit_particle_swarm_options,
                     toolTip="Edit options")
        r += 1
        CheckBox    (l,r,c,   get=lambda: not self.input_file.nml_xfoil_run_options.isDefault)
        Label       (l,r,c+1, get="Xfoil Options",lab_disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self._edit_xfoil_run_options,
                     toolTip="Edit options")
        r += 1
        CheckBox    (l,r,c,   get=lambda: not self.input_file.nml_paneling_options.isDefault)
        Label       (l,r,c+1, get="Paneling Options", lab_disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self._edit_paneling_options,
                     toolTip="Edit options")

        r += 1
        CheckBox    (l,r,c,   get=lambda: not self.input_file.nml_constraints.isDefault)
        Label       (l,r,c+1, get="Constraints", lab_disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self._edit_constraints,
                     toolTip="Edit options")
        r += 1
        l.setRowStretch (r,2)
        # r += 1
        # Label       (l,r,c+1, get="Xoptfoil2 Input File", lab_disable=True)
        # ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self._edit_input_file,
        #              toolTip="Direct editing of the Xoptfoil2 input file")
        
        l.setColumnMinimumWidth (0,20)
        l.setColumnMinimumWidth (1,130)
        l.setColumnStretch (1,2)

        return l
     

    def _edit_particle_swarm_options (self): 

        diag = Xo2_Particle_Swarm_Dialog (self, getter=self.input_file.nml_particle_swarm_options, 
                                            parentPos=(0.5, 0.0), dialogPos=(0.8,1.1))
        diag.exec()
        self.refresh ()
        self.app._on_xo2_input_changed()


    def _edit_xfoil_run_options (self): 

        diag = Xo2_Xfoil_Run_Dialog (self, getter=self.input_file.nml_xfoil_run_options, 
                                            parentPos=(0.5, 0.0), dialogPos=(0.8,1.1))
        diag.exec()
        self.refresh ()
        self.app._on_xo2_input_changed()


    def _edit_paneling_options (self): 

        diag = Xo2_Paneling_Dialog (self, getter=self.input_file.nml_paneling_options, 
                                            parentPos=(0.5, 0.0), dialogPos=(0.8,1.1))
        diag.exec()
        self.refresh ()
        self.app._on_xo2_input_changed()


    def _edit_constraints (self): 

        diag = Xo2_Constraints_Dialog (self, getter=self.input_file.nml_constraints, 
                                            parentPos=(0.5, 0.0), dialogPos=(0.8,1.1))
        diag.exec()
        self.refresh ()
        self.app._on_xo2_input_changed()


    def _edit_input_file (self):

        saved = self.input_file.save_nml ()

        if saved: 
            self.app._toast_message ("Options saved to Input file", toast_style=style.HINT)

        dialog = Xo2_Input_File_Dialog (self,self.input_file, parentPos=(0.8,0,9), dialogPos=(1,1))
        dialog.exec () 

        if dialog.result() == QDialog.DialogCode.Accepted:
            msg = "Input file successfully checked and saved"
            self.app._toast_message (msg, toast_style=style.GOOD)
            
            self.app._on_xo2_input_changed()
