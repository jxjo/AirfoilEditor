#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

UI small data panels 

"""

from PyQt6.QtWidgets        import QDialog, QFileDialog
from PyQt6.QtCore           import Qt

from base.widgets           import * 
from base.panels            import Edit_Panel, MessageBox

from model.case             import Case_Optimize
from model.xo2_input        import *
from model.xo2_driver       import Xoptfoil2

from ui.ae_dialogs          import Polar_Definition_Dialog
from ui.ae_widgets          import Airfoil_Select_Open_Widget, mode_color
from ui.xo2_dialogs         import *

from app_model              import App_Model


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)



def create_case_from_path (parent, pathFilename,  message_delayed=False) -> Case_Optimize:
    """
    Create and return a optimization case based on pathFilename.
        Return None if Case couldn't be loaded
    """

    try: 
        case = Case_Optimize (pathFilename)
        case_loaded = True
    except:
        case = None
        case_loaded = False

    if not case_loaded and pathFilename:
        msg     =  f"<b>{pathFilename}</b> couldn't be loaded."
        if message_delayed:
            QTimer.singleShot (100, lambda: MessageBox.error   (parent,'Load Input File', msg, min_height= 60))
        else:
            MessageBox.error   (parent,'Load Airfoil', msg, min_height= 60)

    return case  



class Panel_Xo2_Abstract (Edit_Panel):
    """ 
    Abstract superclass for Edit/View-Panels of AirfoilEditor Optimize mode
        - has semantics of App
        - connect / handle signals 
    """

    sig_toggle_panel_size = pyqtSignal()                        # wants to toggle panel size

    MAIN_MARGINS        = (10, 5,20, 5)
    MAIN_MARGINS_MINI   = ( 0, 5,10, 5)
    MAIN_MARGINS_FILE   = (10, 5,10, 5)

    _main_margins = MAIN_MARGINS

    def __init__ (self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.app_model.sig_xo2_run_started.connect  (self.refresh)      # disable panel when xo2 run started
        self.app_model.sig_xo2_run_finished.connect (self.refresh)      # enable panel when xo2 run finished


    @property
    def app_model (self) -> App_Model:
        return self.dataObject
        
    @property
    def case (self) -> Case_Optimize:
        return self.app_model.case

    @property
    def input_file (self) -> Input_File:
        return self.case.input_file

    @property
    def is_mode_optimize (self) -> bool:
        """ panel in optimize_mode or disabled ? - from App """
        return self.app_model.is_mode_optimize


    @override
    @property
    def _isDisabled (self) -> bool:
        """ overloaded: only enabled when not running """
        return self.case.isRunning if self.is_mode_optimize else False
    

    @override
    def _set_panel_layout (self ):
        """ Set layout of self._panel """
        # overridden to connect to widgets changed signal

        super()._set_panel_layout ()
        w : Widget
        for w in self.widgets:
            w.sig_changed.connect (self._on_widget_changed)
        for w in self.header_widgets:
            w.sig_changed.connect (self._on_widget_changed)


    def _on_widget_changed (self, widget):
        """ user changed data in widget"""
        logger.debug (f"{self} {widget} widget changed slot")
        self.app_model.notify_xo2_input_changed()

    @override
    def refresh (self,**kwargs):
        """ refresh data in panel from model"""
        logger.debug (f"{self} refresh - is visible: {self.isVisible()} - should be visible: {self.shouldBe_visible}")
        super().refresh(**kwargs)


class Panel_Xo2_File (Panel_Xo2_Abstract):
    """ File panel with open / save / ... """

    name = 'Optimize Mode'

    sig_finish      = pyqtSignal()                              # wants to finish optimize mode - ok / cancel
    sig_open_next   = pyqtSignal(str)                           # wants to open next xo2 input file
    sig_new         = pyqtSignal()                              # wants to create new xo2 input file
    sig_new_version = pyqtSignal()                              # wants to create new version of xo2 input file
    sig_run_xo2     = pyqtSignal()                              # wants to run xo2 optimizer

    def __init__(self, *args, 
                 **kwargs):
        
        self._run_dialog_open = False

        super().__init__(*args, **kwargs)


    def _set_run_dialog_open(self, value: bool):
        """ set if run dialog is open - to avoid multiple instances """

        self._run_dialog_open = value

    @override
    @property
    def _isDisabled (self) -> bool:
        """ overloaded: disable when optimize run dialog is open"""
        return super()._isDisabled or self._run_dialog_open


    @override
    def _on_widget_changed (self, *_):
        """ user changed data in widget"""
        # no automatic change handling 
        pass

    def _on_run_dialog_closed (self):
        """ slot run dialog closed"""
        self._set_run_dialog_open(False)
        self.refresh()


    @property
    def workingDir (self) -> str:
        return self.input_file.workingDir

    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        l_head.addStretch(1)
        if Xoptfoil2.ready:
            Label  (l_head, get=f"{Xoptfoil2.NAME} {Xoptfoil2.version}", 
                    style=style.COMMENT, fontSize=size.SMALL, align=Qt.AlignmentFlag.AlignBottom)
        ToolButton   (l_head, icon=Icon.EXPAND, set=self.sig_toggle_panel_size.emit,
                      toolTip='Minimize lower panel -<br>Alternatively, you can double click on the lower panels')


    def _init_layout (self): 

        self.set_background_color (**mode_color.OPTIMIZE)

        l = QGridLayout()
        r,c = 0, 0 
        ComboBox    (l,r,c, colSpan=3,  
                        get=lambda:self._input_fileName, set=self._set_input_fileName,
                        options= lambda: Input_File.files_in_dir (self.workingDir),
                        toolTip="The Xoptfoil2 input file")
        ToolButton  (l,r,c+3, icon=Icon.OPEN, set=self._open_input_file, toolTip="Select a Xoptfoil2 input file")
        r += 1
        Button      (l,r,c, width=100, text="New Version", set=self.sig_new_version.emit,
                        toolTip="Create a new version of the existing input file")
        Button      (l,r,c+2, width=80, text="New ...", set=self.sig_new.emit,
                        toolTip="Create a new input file")
        r += 1
        Button      (l,r,c, width=100, text="&Run Xoptfoil2", button_style = button_style.PRIMARY,
                        set=self._open_run_dialog, toolTip="Run Optimizer Xoptfoil2")        
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Button      (l,r,c,  text="&Finish",  width=100,
                        set=self.sig_finish.emit, toolTip="Leave optimization mode")

        l.setColumnMinimumWidth (1,12)
        l.setColumnStretch (1,2)
        return l


    @property
    def _input_fileName (self) -> str:
        return self.input_file.fileName

    def _set_input_fileName (self, aFileName : str, workingDir=None):
        """ set new case by name of input file"""
        if workingDir is None: 
            workingDir = self.workingDir

        self.sig_open_next.emit (os.path.join (workingDir, aFileName))


    def _open_input_file (self):
        """ open a new airfoil and load it"""

        # build something like "*.inp *.xo2" as filter for the dialog
        filter_string = ""
        for extension in Input_File.INPUT_FILE_EXT:
            filter_string += f" *{extension}" if filter_string else f"*{extension}"

        filters  = f"Xoptfoil2 Input files ({filter_string})"

        newPathFileName, *_ = QFileDialog.getOpenFileName(self, filter=filters, directory=self.workingDir)

        if newPathFileName:                         # user pressed open
            self.sig_open_next.emit (newPathFileName)


    def _open_run_dialog (self):
        """ open optimize run dialog"""

        if self._run_dialog_open:
            return                                                  # do nothing if already open

        diag = Xo2_Run_Dialog (self, self.app_model, parentPos=(0.02,0.8), dialogPos=(0,1))
        diag.finished.connect (self._on_run_dialog_closed)          # activate self again when dialog closed

        self._set_run_dialog_open(True)
        QTimer.singleShot(0, self.refresh)                          # disable self - after button callback to disable
        
        diag.show()                            


class Panel_Xo2_File_Small (Panel_Xo2_File):
    """ File panel in small mode """

    def _init_layout (self): 

        self.set_background_color (**mode_color.OPTIMIZE)

        l = QGridLayout()
        r,c = 0, 0 
        Button      (l,r,c, width=100, text="&Run Xoptfoil2", button_style = button_style.PRIMARY,
                        set=self.sig_run_xo2.emit, toolTip="Run Optimizer Xoptfoil2")        
        ToolButton  (l,r,c+3, icon=Icon.COLLAPSE, set=self.sig_toggle_panel_size.emit,
                        toolTip='Maximize lower panel -<br>Alternatively, you can double click on the lower panels')
        r += 1
        Button      (l,r,c,  text="&Finish",  width=100, 
                        set=self.sig_finish.emit, toolTip="Leave optimization mode")

        l.setColumnStretch (2,2)
        return l



class Panel_Xo2_Case (Panel_Xo2_Abstract):
    """ Case data"""

    name = 'Case'

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
        r += 1
        Field       (l,r,c, lab="Final Airfoil", 
                     get=lambda: self.input_file.airfoil_final_fileName,
                     style=lambda: style.GOOD if self.case.airfoil_final else style.NORMAL,
                     toolTip=lambda: (self.case.airfoil_final.info_as_html if self.case.airfoil_final else "it does not yet exist"))
        r += 1
        Label       (l,r,c, get="Seed Airfoil", lab_disable=True)
        w = Airfoil_Select_Open_Widget (l,r,c+1, colSpan=2, textOpen="&Open", widthOpen=90, 
                                    obj=lambda: self.input_file, prop=Input_File.airfoil_seed)
        w.sig_changed.connect (self._airfoil_seed_changed)                  # check working dir 

        r += 1
        ComboBox    (l,r,c, lab="Shape functions", lab_disable=True,
                     obj=lambda:self.optimization_options, prop=Nml_optimization_options.shape_functions_label_long,
                     options=lambda: self.optimization_options.shape_functions_list,
                     disable=lambda: self.input_file.airfoil_seed.isBezierBased,
                     toolTip=lambda: "Bezier based seed airfoil is master of shape functions" if self.input_file.airfoil_seed.isBezierBased \
                                     else "Select shape functions for optimization")     
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self._edit_shape_functions,
                     toolTip="Edit options of shape functions")

        r += 1
        l.setRowStretch (r,1)
        l.setColumnMinimumWidth (0,90)
        l.setColumnMinimumWidth (1,140)     # the widest shape_functions_label_long defines the width
        l.setColumnStretch (1,1)
        return l 


    def _edit_description (self):
        """ open text editor to edit Xoptfoil2 input description"""

        dialog = Xo2_Description_Dialog (self,self.input_file.nml_info.descriptions_string, 
                                         parentPos=(0.8,0,3), dialogPos=(0,1))
        dialog.exec () 

        if dialog.result() == QDialog.DialogCode.Accepted:
            descriptions = dialog.new_text.split ("\n")
            self.input_file.nml_info.set_descriptions (descriptions)
            
            self.app_model.notify_xo2_input_changed ()


    def _edit_shape_functions (self):
        """ open editor to change the parameters of the shape functions"""
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
            self.app_model.notify_xo2_input_changed ()


    def _airfoil_seed_changed (self, *_):
        """ slot seed airfoil changed - check if still in working dir"""

        airfoil_seed = self.input_file.airfoil_seed
        # the airfoil may not have a directory as it should be relative to its working dir 
        if airfoil_seed.pathName:

            # copy seed airfoil to working dir 
            airfoil_seed.saveAs (dir=self.input_file.workingDir, isWorkingDir=True)

            self.input_file.set_airfoil_seed (airfoil_seed)   # make sure new path is written to namelist

            text = f"Seed airfoil <b>{airfoil_seed.fileName}</b> copied to working directory."
            MessageBox.info(self, "Copy seed airfoil", text)



class Panel_Xo2_Case_Small (Panel_Xo2_Case):
    """ Case Info - small mode"""

    name = 'Case'
    _panel_margins = (0, 0, 0, 0)

    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        r += 1
        Field       (l,r,c, lab="Final Airfoil", 
                     get=lambda: self.input_file.airfoil_final_fileName,
                     style=lambda: style.GOOD if self.case.airfoil_final else style.NORMAL,
                     toolTip=lambda: (self.case.airfoil_final.info_as_html if self.case.airfoil_final else "it does not yet exist"))
        r += 1
        Label       (l,r,c, get="Seed Airfoil", lab_disable=True)
        w = Airfoil_Select_Open_Widget (l,r,c+1, colSpan=2, textOpen="&Open", widthOpen=90, 
                                    obj=lambda: self.input_file, prop=Input_File.airfoil_seed)
        w.sig_changed.connect (self._airfoil_seed_changed)                  # check working dir 

        l.setColumnMinimumWidth (0,90)
        l.setColumnMinimumWidth (1,130)
        l.setColumnMinimumWidth (2,22)
        return l 


class Panel_Xo2_Operating_Conditions (Panel_Xo2_Abstract):
    """ Define operating conditions"""

    name = 'Operating Conditions'

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
                     toolTip="Edit flap definition")
        
        r += 1
        l.setRowStretch (r,3)
        l.setColumnMinimumWidth (0,180)
        l.setColumnStretch (0,1)

        return l


    def _edit_polar_def (self):
        """ edit default polar definition"""

        polar_def = self.opPoint_defs.polar_def_default
        diag = Polar_Definition_Dialog (self, polar_def, small_mode=True, parentPos=(0.9,0.1), dialogPos=(0,1))

        diag.setWindowTitle ("Default Polar of Op Points")
        diag.exec()

        self.opPoint_defs.set_polar_def_default (polar_def)
        self.app_model.notify_xo2_input_changed()


    def _edit_flap_def (self):
        """ edit default flap definition"""

        diag = Xo2_Flap_Definition_Dialog (self, getter=self.operating_conditions,
                                         parentPos=(0.9, 0.1), dialogPos=(0,1))        
        diag.exec()     

        self.app_model.notify_xo2_input_changed()



class Panel_Xo2_OpPoint_Defs (Panel_Xo2_Abstract):
    """ Define op Points of namelist operating_conditions"""

    name = 'Operating Points'

    def __init__ (self, *args, **kwargs):

        self._opPoint_def_dialog : Xo2_OpPoint_Def_Dialog = None        # instance of dialog to edit opPoint def

        super().__init__ (*args, **kwargs)

        self.app_model.sig_xo2_input_changed.connect        (self.refresh)              # refresh list
        self.app_model.sig_xo2_opPoint_def_selected.connect (self.refresh)              # refresh list
        self.app_model.sig_xo2_opPoint_def_selected.connect (self.edit_opPoint_def)     # open edit dialog

    
    @property
    def opPoint_defs (self) -> OpPoint_Definitions:
        return self.input_file.opPoint_defs

    @property
    def cur_opPoint_def (self) -> OpPoint_Definition:
        """ current, selected opPoint def"""
        return self.app_model.cur_opPoint_def

    def set_cur_opPoint_def (self, opPoint_def: OpPoint_Definition):
        self.app_model.set_cur_opPoint_def (opPoint_def)                # will signal selected changed


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        ListBox    (l,r,c, rowSpan=4, height=140, 
                    get=lambda: self.cur_opPoint_def.labelLong if self.cur_opPoint_def else None ,
                    set=self.set_cur_opPoint_def_from_label,
                    signal=False,                                               # do not signal xo2_input changed
                    doubleClick=self.edit_opPoint_def,
                    options=lambda:  [opPoint_def.labelLong for opPoint_def in self.opPoint_defs])
        c += 1
        ToolButton  (l,r,c, icon=Icon.EDIT, align=ALIGN_RIGHT, 
                     set=self.edit_opPoint_def,
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
        l.setColumnMinimumWidth (0,150)
        l.setColumnStretch (1,1)

        return l

 
    def set_cur_opPoint_def_from_label (self, aStr: str):
        """ set from labelLong - for ComboBox"""
        for opPoint_def in self.opPoint_defs:
            if opPoint_def.labelLong == aStr:
                self.set_cur_opPoint_def (opPoint_def)
                break


    def _delete_opPoint_def (self):
        """ delete me opPoint_dev"""

        next_opPoint_def = self.opPoint_defs.delete (self.cur_opPoint_def)

        self.set_cur_opPoint_def (next_opPoint_def)
        self.app_model.notify_xo2_input_changed()


    def _add_opPoint_def (self):
        """ add a new opPoint_dev after current """

        next_opPoint_def = self.opPoint_defs.create_after (self.cur_opPoint_def)

        self.set_cur_opPoint_def (next_opPoint_def)
        self.app_model.notify_xo2_input_changed()


    @override
    def hideEvent(self, event):
        """ self is hidden - close edit dialog if open"""

        if self._opPoint_def_dialog is not None:
            self._opPoint_def_dialog.close()

        super().hideEvent(event)


    def edit_opPoint_def (self):
        """ slot user action - open floating dialog to edit current xo2 opPoint def """

        if not self.isVisible():
            return                                  # do nothing if panel not visible (normal/small panel)

         # open dialog if not yet existing

        if self._opPoint_def_dialog is None:
            parentPos=(0.95, 0.5) 
            dialogPos=(0,1)
            self._opPoint_def_dialog = Xo2_OpPoint_Def_Dialog (self, self.app_model, parentPos=parentPos, dialogPos=dialogPos)
            self._opPoint_def_dialog.finished.connect (self._on_opPoint_dialog_closed)
        else: 
            self._opPoint_def_dialog.activateWindow ()

        self._opPoint_def_dialog.show () 


    def _on_opPoint_dialog_closed (self, *_):
        """ slot - dialog to edit current opPoint def finished"""

        if self._opPoint_def_dialog is not None:
            self._opPoint_def_dialog.finished.disconnect (self._on_opPoint_dialog_closed)
            self._opPoint_def_dialog.deleteLater()
            self._opPoint_def_dialog = None     




class Panel_Xo2_Operating_Small (Panel_Xo2_OpPoint_Defs):
    """ Define operating conditions - small mode"""

    _panel_margins = (0, 0, 0, 0)

    _width = 320

    @property
    def operating_conditions (self) -> Nml_operating_conditions:
        return self.input_file.nml_operating_conditions    

    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Label       (l,r,c, get="Default Polar", lab_disable=True)
        Field       (l,r,c+1, width=None, 
                    get=lambda: self.opPoint_defs.polar_def_default.name)
        ToolButton  (l,r,c+2, icon=Icon.EDIT,   set=self._edit_polar_def)
        r += 1
        Label       (l,r,c, get="Current Op Point", lab_disable=True)
        ComboBox    (l,r,c+1, 
                    get=lambda: self.cur_opPoint_def.labelLong if self.cur_opPoint_def else None ,
                    set=self.set_cur_opPoint_def_from_label,
                    options=lambda:  [opPoint_def.labelLong for opPoint_def in self.opPoint_defs])
        ToolButton  (l,r,c+2, icon=Icon.EDIT, 
                     set=self.edit_opPoint_def,
                     disable=lambda: not self.cur_opPoint_def)

        l.setColumnMinimumWidth (0,100)
        l.setColumnStretch (1,1)
        return l


    def _edit_polar_def (self):
        """ edit default polar definition"""

        polar_def = self.opPoint_defs.polar_def_default
        diag = Polar_Definition_Dialog (self, polar_def, small_mode=True, parentPos=(0.9,0.1), dialogPos=(0,1))

        diag.setWindowTitle ("Default Polar of Op Points")
        diag.exec()

        self.opPoint_defs.set_polar_def_default (polar_def)
        self.app_model.notify_xo2_input_changed ()



class Panel_Xo2_Geometry_Targets (Panel_Xo2_Abstract):
    """ Edit geometry target """

    name = 'Geometry Targets'

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




class Panel_Xo2_Geometry_Targets_Small (Panel_Xo2_Geometry_Targets):
    """ Edit geometry targets - small mode """

    _panel_margins = (0, 0, 0, 0)

    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0
        CheckBox    (l,r,c, text="Thickness", 
                     get=lambda: self.thickness is not None, 
                     set=lambda x: self.geometry_targets.activate_thickness(x))
        FieldF      (l,r,c+1, width=70, unit="%", step=0.01,
                     obj=lambda: self.thickness, prop=GeoTarget_Definition.optValue,
                     hide=lambda: not self.thickness)

        r += 1
        CheckBox    (l,r,c, text="Camber", 
                     get=lambda: self.camber is not None, 
                     set=lambda x: self.geometry_targets.activate_camber(x))
        FieldF      (l,r,c+1, width=70, unit="%", step=0.01,
                     obj=lambda: self.camber, prop=GeoTarget_Definition.optValue,
                     hide=lambda: not self.camber)
        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (2,2)
        return l



class Panel_Xo2_Curvature (Panel_Xo2_Abstract):
    """ Edit curvature parameters """

    name = 'Curvature'
    _width  = 200


    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if mode optimize and not camb_thick """
        return super().shouldBe_visible and self.is_mode_optimize and \
               self.shape_functions != Nml_optimization_options.CAMB_THICK


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
        self.app_model.notify_xo2_input_changed()



class Panel_Xo2_Advanced (Panel_Xo2_Abstract):
    """ Panel with the advanced input options """

    name = 'Advanced'
    _width  = 210

    sig_edit_input_file = pyqtSignal()              # wants to edit input file directly


    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        Button (l_head, text="Input File", width=70, button_style = button_style.SUPTLE,
                set=self.sig_edit_input_file.emit, toolTip="Direct editing of the Xoptfoil2 input file")


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
        self.app_model.notify_xo2_input_changed()


    def _edit_xfoil_run_options (self): 

        diag = Xo2_Xfoil_Run_Dialog (self, getter=self.input_file.nml_xfoil_run_options, 
                                            parentPos=(0.5, 0.0), dialogPos=(0.8,1.1))
        diag.exec()
        self.refresh ()
        self.app_model.notify_xo2_input_changed()


    def _edit_paneling_options (self): 

        diag = Xo2_Paneling_Dialog (self, getter=self.input_file.nml_paneling_options, 
                                            parentPos=(0.5, 0.0), dialogPos=(0.8,1.1))
        diag.exec()
        self.refresh ()
        self.app_model.notify_xo2_input_changed()


    def _edit_constraints (self): 

        diag = Xo2_Constraints_Dialog (self, getter=self.input_file.nml_constraints, 
                                            parentPos=(0.5, 0.0), dialogPos=(0.8,1.1))
        diag.exec()
        self.refresh ()
        self.app_model.notify_xo2_input_changed()
