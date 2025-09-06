#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

UI panels 

"""

from shutil                 import copyfile

from PyQt6.QtWidgets        import QDialog, QFileDialog
from PyQt6.QtCore           import Qt


from base.widgets           import * 
from base.panels            import Edit_Panel, MessageBox

from airfoil_dialogs        import Airfoil_Info_Dialog, Polar_Definition_Dialog, Flap_Airfoil_Dialog
from airfoil_widgets        import Airfoil_Select_Open_Widget, mode_color

from xo2_dialogs            import *
from model.xo2_driver       import Xoptfoil2


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
    from app import Main

    @property
    def app (self) -> Main:
        return self._app 
    
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

    @override
    @property
    def _isDisabled (self) -> bool:
        """ overloaded: disable when optimize run dialog is open"""
        return self.app._xo2_run_dialog is not None

    @override
    def _on_widget_changed (self, *_):
        """ user changed data in widget"""
        # no automatic change handling 
        pass


    @property
    def workingDir (self) -> str:
        #todo 
        return self.app.workingDir

    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        if Xoptfoil2.ready:
            Label  (l_head, get=f"{Xoptfoil2.NAME} {Xoptfoil2.version}", 
                    style=style.COMMENT, fontSize=size.SMALL, align=Qt.AlignmentFlag.AlignBottom)


    def _init_layout (self): 

        self.set_background_color (**mode_color.OPTIMIZE)

        l = QGridLayout()
        r,c = 0, 0 
        ComboBox    (l,r,c, colSpan=2,  
                        get=lambda:self._input_fileName, set=self._set_input_fileName,
                        options= lambda: Input_File.files_in_dir (self.workingDir),
                        toolTip="The Xoptfoil2 input file")
        ToolButton  (l,r,c+3, icon=Icon.OPEN, set=self._open_input_file, toolTip="Select a Xoptfoil2 input file")
        r += 1
        Button      (l,r,c, width=90, text="New Version", set=self.app.case_optimize_new_version,
                        toolTip="Create a new version of the existing input file")
        Button      (l,r,c+1, width=90, text="New ...", set=self.app.optimize_new,
                        toolTip="Create a new input file")
        r += 1
        SpaceR      (l,r,height=10, stretch=0)
        r += 1
        Button      (l,r,c, text="&Run Xoptfoil2", colSpan=2, button_style = button_style.PRIMARY,
                        set=self.app.optimize_open_run, toolTip="Run Optimizer Xoptfoil2")        
        r += 1
        SpaceR      (l,r)
        r += 1
        Button      (l,r,c,  text="&Finish",  width=90, 
                        set=lambda : self.app.mode_optimize_finished(),
                        toolTip="Leave optimization mode")
        r += 1
        SpaceR      (l,r, height=5, stretch=0)

        l.setColumnStretch (1,2)
        l.setContentsMargins (QMargins(0, 0, 0, 0)) 

        return l


    @property
    def _input_fileName (self) -> str:
        return self.input_file.fileName

    def _set_input_fileName (self, aFileName : str, workingDir=None):
        """ set new case by name of input file"""
        if workingDir is None: 
            workingDir = self.workingDir

        self.app.optimize_change_case (aFileName, workingDir)


    def _open_input_file (self):
        """ open a new airfoil and load it"""

        # build somethinglike "*.inp *.xo2" as filter for the dialog
        filter_string = ""
        for extension in Input_File.INPUT_FILE_EXT:
            filter_string += f" *{extension}" if filter_string else f"*{extension}"

        filters  = f"Xoptfoil2 Input files ({filter_string})"

        newPathFileName, *_ = QFileDialog.getOpenFileName(self, filter=filters, directory=self.workingDir)

        if newPathFileName:                         # user pressed open

            self._set_input_fileName (os.path.basename (newPathFileName), workingDir=os.path.dirname (newPathFileName))

            self.refresh()



class Panel_Xo2_Case (Panel_Xo2_Abstract):
    """ Main panel of optimization"""

    name = 'Case'
    _width  = (320, 400)

    # @override
    # def _add_to_header_layout(self, l_head: QHBoxLayout):
    #     """ add Widgets to header layout"""

    #     Button (l_head, text="Run Xoptfoil2", width=120, button_style = button_style.PRIMARY,
    #             set=self.app.optimize_open_run, toolTip="Run Optimizer Xoptfoil2")        

    @property
    def optimization_options (self) -> Nml_optimization_options:
        return self.case.input_file.nml_optimization_options

    @property
    def info (self) -> Nml_info:
        return self.case.input_file.nml_info


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Label  (l,r,c,  colSpan=2, height=(None,None), style=style.COMMENT,
                        get=lambda: self.info.descriptions_string if self.info.descriptions_string else 'Enter a description ...')
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
        Field       (l,r,c, lab="Final Airfoil", 
                     get=lambda: self.input_file.airfoil_final_fileName,
                     style=lambda: style.GOOD if self.case.airfoil_final else style.NORMAL,
                     toolTip=lambda: (self.case.airfoil_final.info_as_html if self.case.airfoil_final else "it does not yet exist"))
        # ToolButton  (l,r,c+2, icon=Icon.SHOW_INFO, set=self._show_info_airfoil_final,
        #              hide=lambda: self.case.airfoil_final is None,
        #              toolTip="Edit options of shape functions")
        r += 1
        Label       (l,r,c, get="Seed Airfoil", lab_disable=True)
        w = Airfoil_Select_Open_Widget (l,r,c+1, colSpan=2, textOpen="&Open", widthOpen=90, 
                                    obj=lambda: self.input_file, prop=Input_File.airfoil_seed)
        w.sig_changed.connect (self._airfoil_seed_changed)                  # check working dir 

        r += 1
        ComboBox    (l,r,c, lab="Shape functions", lab_disable=True,
                     obj=self.optimization_options, prop=Nml_optimization_options.shape_functions_label_long,
                     options=lambda: self.optimization_options.shape_functions_list,
                     disable=lambda: self.input_file.airfoil_seed.isBezierBased,
                     toolTip=lambda: "Bezier based seed airfoil is master of shape functions" if self.input_file.airfoil_seed.isBezierBased \
                                     else "Select shape functions for optimization")     
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self._edit_shape_functions,
                     toolTip="Edit options of shape functions")


        r += 1
        l.setRowStretch (r,1)
        l.setColumnMinimumWidth (0,90)
        l.setColumnStretch (1,3)
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


    def _show_info_airfoil_final (self):
        """ show little info dialog about final airfoil"""

        dialog = Airfoil_Info_Dialog (self,self.case.airfoil_final, parentPos=(0.8,0,3), dialogPos=(0,1))
        dialog.exec () 


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


    def _airfoil_seed_changed (self, *_):
        """ slot seed airfoil changed - check if still in working dir"""

        airfoil_seed = self.input_file.airfoil_seed
        # the airfoil may not have a directory as it should be relative to its working dir 
        if airfoil_seed.pathName:

            # copy seed airfoil to working dir 
            airfoil_seed.saveAs (dir=self.input_file.workingDir, isWorkingDir=True)

            text = f"Seed airfoil <b>{airfoil_seed.fileName}</b> copied to working directory."
            MessageBox.info(self, "Copy seed airfoil", text)

            # QTimer.singleShot (10, self.refresh)




class Panel_Xo2_Operating_Conditions (Panel_Xo2_Abstract):
    """ Define operating conditions"""

    name = 'Operating Conditions'
    _width  = (230,350)


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
        ToolButton  (l,r,c+1, icon=Icon.EDIT, set=self._edit_flap_def,
                     hide= lambda: not self.operating_conditions.use_flap,
                     toolTip="Edit flap deinition")
        
        r += 1
        l.setRowStretch (r,3)
        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (0,1)

        return l


    def _edit_polar_def (self):
        """ edit default polar definition"""

        polar_def = self.opPoint_defs.polar_def_default
        diag = Polar_Definition_Dialog (self, polar_def, small_mode=True, parentPos=(0.9,0.1), dialogPos=(0,1))

        diag.setWindowTitle ("Default Polar of Op Points")
        diag.exec()

        self.opPoint_defs.set_polar_def_default (polar_def)
        self.app._on_xo2_input_changed()


    def _edit_flap_def (self):
        """ edit default flap definition"""

        diag = Xo2_Flap_Definition_Dialog (self, getter=self.operating_conditions,
                                         parentPos=(0.9, 0.1), dialogPos=(0,1))        
        diag.exec()     

        self.app._on_xo2_input_changed()



class Panel_Xo2_Operating_Points (Panel_Xo2_Abstract):
    """ Define op Points of namelist operating_conditions"""

    name = 'Operating Points'
    _width  = 270

    def __init__ (self, *args, **kwargs):

        self._cur_opPoint_def = None 

        super().__init__ (*args, **kwargs)

    
    @property
    def opPoint_defs (self) -> OpPoint_Definitions:
        return self.input_file.opPoint_defs

    @property
    def cur_opPoint_def (self) -> OpPoint_Definition:
        """ current, selected opPoint def"""
        return self.opPoint_defs.current_opPoint_def


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        ListBox    (l,r,c, width=None, rowSpan=4, height=140,
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


 
    def set_cur_opPoint_def_from_label (self, aStr: str):
        """ set from labelLong - for ComboBox"""
        for opPoint_def in self.opPoint_defs:
            if opPoint_def.labelLong == aStr:
                self.opPoint_defs.set_current_opPoint_def (opPoint_def) 
                self.app._on_xo2_opPoint_def_selected()
                break


    def _delete_opPoint_def (self):
        """ delete me opPoint_dev"""

        self.opPoint_defs.delete (self.cur_opPoint_def)

        self.refresh ()
        self.app._on_xo2_input_changed()


    def _add_opPoint_def (self):
        """ add a new opPoint_dev after current """

        self.opPoint_defs.create_after (self.cur_opPoint_def)

        self.refresh ()
        self.app._on_xo2_input_changed()


    def _edit_opPoint_def (self):
        """ open dialog to edit current opPoint def"""

        parentPos=(0.9, 0.2) 
        dialogPos=(0,1)

        self.app.edit_opPoint_def (self, parentPos, dialogPos)



class Panel_Xo2_Geometry_Targets (Panel_Xo2_Abstract):
    """ Edit geometry target """

    name = 'Geometry Targets'
    _width  = 250

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
        FieldF      (l,r,c+2, width=70, unit="%", step=0.01,
                     obj=lambda: self.thickness, prop=GeoTarget_Definition.optValue,
                     hide=lambda: not self.thickness)
        r += 1
        FieldF      (l,r,c+1, lab="Weighting", lab_disable=True, width=70, step=0.1, lim=(-10,10), dec=2,
                     obj=lambda: self.thickness, prop=GeoTarget_Definition.weighting_abs,
                     hide=lambda: self.thickness is None)
        CheckBox    (l,r,c+3, text="Fix", align=ALIGN_RIGHT,
                     obj=lambda: self.thickness, prop=OpPoint_Definition.weighting_fixed,
                     hide=lambda: self.thickness is None,
                     toolTip="Fix this weighting during Dynamic Weighting")

        r += 1
        CheckBox    (l,r,c, text="Camber", colSpan=2, 
                     get=lambda: self.camber is not None, 
                     set=lambda x: self.geometry_targets.activate_camber(x))
        FieldF      (l,r,c+2, width=70, unit="%", step=0.01,
                     obj=lambda: self.camber, prop=GeoTarget_Definition.optValue,
                     hide=lambda: not self.camber)
        r += 1
        FieldF      (l,r,c+1, lab="Weighting", lab_disable=True, width=70, step=0.1, lim=(-10,10), dec=2,
                     obj=lambda: self.camber, prop=GeoTarget_Definition.weighting_abs,
                     hide=lambda: self.camber is None)
        CheckBox    (l,r,c+3, text="Fix", align=ALIGN_RIGHT,
                     obj=lambda: self.camber, prop=OpPoint_Definition.weighting_fixed,
                     hide=lambda: self.camber is None,
                     toolTip="Fix this weighting during Dynamic Weighting")
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Label (l,r,c, colSpan=4, style=style.COMMENT,
               get=lambda: f"Will be {len (self.geometry_targets.geoTarget_defs)} design variables",
               hide=lambda: len (self.geometry_targets.geoTarget_defs )== 0)        
        l.setColumnMinimumWidth (0,20)
        l.setColumnMinimumWidth (1,70)
        l.setColumnMinimumWidth (3,50)
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
        Label       (l,r,c, style=style.COMMENT, colSpan=2, lab_disable=True,  
                     get="Allow reversal on ...",
                     hide=lambda: not self.curvature.check_curvature)
        r += 1
        CheckBox    (l,r,c, text="Top side (reflexed)", colSpan=2, 
                     get=lambda: self.curvature.max_curv_reverse_top == 1,
                     set=lambda x: self.curvature.set_max_curv_reverse_top(x),
                     hide=lambda: not self.curvature.check_curvature)
        r += 1
        CheckBox    (l,r,c, text="Bot side (rearloaded)", colSpan=2,   
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

        Button (l_head, text="Input File", width=70, button_style = button_style.SUPTLE,
                set=self._edit_input_file, toolTip="Direct editing of the Xoptfoil2 input file")        


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
