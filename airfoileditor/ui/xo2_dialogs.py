#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

Extra dialogs to optimize airfoil  

"""

from copy                   import copy 
from shutil                 import copyfile, copytree, rmtree

from PyQt6.QtWidgets        import QLayout, QDialogButtonBox, QPushButton, QDialogButtonBox
from PyQt6.QtWidgets        import QWidget, QTextEdit, QDialog, QFileDialog, QMessageBox
from PyQt6.QtGui            import QFontMetrics

from ..base.widgets         import * 
from ..base.panels          import Dialog, Edit_Panel, MessageBox, Panel_Abstract

from ..model.airfoil        import Airfoil
from ..model.polar_set      import Polar_Definition
from ..model.case           import Case_Optimize
from ..model.xo2_controller import xo2_state, Xo2_Controller
from ..model.xo2_results    import Xo2_Results, Optimization_History_Entry
from ..model.xo2_input      import *

from .util_dialogs          import Polar_Definition_Dialog
from .ae_widgets            import Airfoil_Select_Open_Widget, mode_color
from .xo2_diagrams          import Diagram_Xo2_Progress, Diagram_Xo2_Airfoil_and_Polar

from ..app_model            import App_Model, Watchdog


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)



class Xo2_Select_Dialog (Dialog):
    """ 
    Dialog to choose what should be done when entering optimization mode:
    - open existing case
    - create new case for current airfoil
    - select case from file system

    """

    _width  = (480, None)
    _height = (200, None)

    name = "Airfoil Optimization"


    def __init__ (self, parent, app_model, **kwargs): 

        self._app_model       = app_model
        self._input_fileName  = None
        self._workingDir      = None 

        self._info_panel = None

        # is there an existing input file for airfoil

        if self.current_airfoil is not None:
            self._input_fileName = Input_File.fileName_of (self.current_airfoil)
            self._workingDir     = self.current_airfoil.pathName_abs 

        super().__init__ (parent, **kwargs)

    @property
    def app_model (self) -> App_Model:
        return self._app_model

    @property 
    def input_fileName (self) -> str:
        return self._input_fileName
    
    @property 
    def workingDir (self) -> str:
        return self._workingDir
    
    @property
    def current_airfoil (self) -> Airfoil:
        return self.app_model.airfoil
    

    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0
        if self.input_fileName:
            Button   (l,r,c, width=120, text="Open Case", set=self._open_case)
            Label    (l,r,c+2, wordWrap=True, height=(25,None),
                      get=lambda: f"Open input file <b>{self.input_fileName}</b> of airfoil {self.current_airfoil.fileName}" )
            r += 1
            Button   (l,r,c, width=120, text="New Version", set=self._new_version)
            Label    (l,r,c+2, wordWrap=True, height=(25,None),
                      get=lambda: f"Create new Version of input file <b>{self.input_fileName}</b>")
            r += 1
            SpaceR   (l,r,stretch=0, height=20)
            r += 1

        Button   (l,r,c, width=120, text="Select Case", set=self._select_open_open_case)
        Label    (l,r,c+2, wordWrap=True,
                  get=lambda: f"Select an Xoptfoil2 Input file and open it")
        r += 1
        Button   (l,r,c, width=120, text="New ...", set=self._new)
        Label    (l,r,c+2, wordWrap=True,
                  get=lambda: f"Create new Optimization Case for an airfoil")
        r += 1

        # add switchable info panel 
        SpaceR   (l,r,stretch=1, height=20)
        r += 1
        l.addWidget (self.info_panel, r,c, 1, 3)  
        l.setRowStretch (r,1)

        l.setColumnMinimumWidth (1,20)
        l.setColumnStretch (2,2)

        return l 


    @property
    def info_panel (self) -> Edit_Panel:
        """ return info panel holding additional user info"""

        if self._info_panel is None:    
            l = QGridLayout()
            r,c = 0, 0 
            lab = Label    (l,r,c, height=170, colSpan=3, wordWrap=True,
                    get="Airfoil optimization is based on <a href='https://github.com/jxjo/Xoptfoil2'>Xoptfoil2</a>, which will run in the background.<br><br>" +
                        "Xoptfoil2 is controlled via the Input file, whose parameters can be edited subsequently. "
                        "The Input file is equivalent to an Optimization Case in the AirfoilEditor." +
                        "<br><br>" +
                        "If you have no experience with airfoil optimization, please read the " + 
                        "<a href='https://jxjo.github.io/Xoptfoil2/'>description of Xoptfoil2</a> first and then run the examples:")
            lab.setOpenExternalLinks(True)

            r += 1
            examples_dict = self.app_model.xo2_example_files
            if examples_dict:
                for example_file, example_path in examples_dict.items():
                    #https://docs.python.org/3.4/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result
                    Button   (l,r,c,   width=100, text=Path(example_file).stem, 
                            set=lambda p=example_path: self._open_example_case (p))
                    c += 1 
                    if c > 2: break
                c = 0
            else:
               Label    (l,r,c, colSpan=3, style=style.ERROR,
                         get=f"No examples directory found ... ") 
            r += 1
            SpaceR   (l,r,height=10, stretch=0)
            r += 1
            Label    (l,r,c, colSpan=3, get="After that you are ready for your own projects...")
            r += 1
            SpaceR   (l,r,height=10, stretch=0)

            l.setColumnMinimumWidth (0,120)
            l.setColumnMinimumWidth (1,120)

            self._info_panel = Edit_Panel (title="Info and Examples", layout=l, height=(100,None), 
                                              switchable=True, switched_on=False, on_switched=lambda x: self.adjustSize())
            
            self._info_panel.set_background_color (**mode_color.OPTIMIZE)

        return self._info_panel 


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""
        buttonBox = QDialogButtonBox ( QDialogButtonBox.StandardButton.Cancel)

        buttonBox.rejected.connect  (self.close)

        return buttonBox 


    def _select_open_open_case (self): 
        """ file select of an input file and close self with input_fileName"""

        # build something like "*.inp *.xo2" as filter for the dialog
        filter_string = ""
        for extension in Input_File.INPUT_FILE_EXT:
            filter_string += f" *{extension}" if filter_string else f"*{extension}"

        filters  = f"Xoptfoil2 Input files ({filter_string})"
        caption  = "Select Input file"

        pathFileName, *_ = QFileDialog.getOpenFileName(self, caption=caption, filter=filters, directory=self.workingDir)

        if pathFileName:                         # user pressed open
            pathHandler = PathHandler (onFile=pathFileName)
            self._input_fileName = pathHandler.relFilePath (pathFileName)
            self._workingDir     = pathHandler.workingDir
            self.accept ()


    def _open_case (self): 
        """ open existing case self.input_file"""
        self.accept ()


    def _new (self): 
        """ create new case for a new airfoil"""
        self._input_fileName = None
        self.accept ()


    def _new_version (self): 
        """ create new version of an existing case self.input_file"""

        new_fileName = Input_File.new_fileName_version (self.input_fileName, self.workingDir)

        if new_fileName:
            copyfile (os.path.join (self.workingDir,self.input_fileName), os.path.join (self.workingDir,new_fileName))
            self._input_fileName = new_fileName
            self.accept ()
        else: 
            MessageBox.error   (self,'Create new version', f"New Version of {self.input_fileName} could not be created.",
                                min_width=350)


    def _open_example_case (self, pathFileName): 
        """ open existing case self.input_file"""

        pathHandler = PathHandler (onFile=pathFileName)
        self._input_fileName = pathHandler.relFilePath (pathFileName)
        self._workingDir     = pathHandler.workingDir
        self.accept ()



class Xo2_New_Dialog (Dialog):
    """ Dialog to create a new input file """

    _width  = (1200, None)
    _height = (700, None)

    name = "New Optimization Case"

    # -------------------------------------------------------------------------

    def __init__ (self, parent, workingDir : str,  current_airfoil : Airfoil, 
                  watchdog : Watchdog, **kwargs): 

        # create new, separate app_model (without watchdog thread - use watchdog of parent)

        self._app_model = App_Model (workingDir_default=workingDir, start_watchdog=False)
        self._watchdog  = watchdog

        self._app_model.set_airfoil (current_airfoil.asCopy())
        self._app_model.set_case (Case_Optimize (None, workingDir=workingDir))   


        # init empty input file with current seed airfoil

        self.input_file.set_airfoil_seed (current_airfoil.asCopy())
        self.input_file.nml_info.set_descriptions([f"e.g. improve max glide, while keep min cd", "and thickness"])
        self.optimization_options.set_shape_functions (Nml_optimization_options.BEZIER)
        self.operating_conditions.set_re_default_asK (400)
        self.geometry_targets.activate_thickness (True)

        self._create_opPoint_defs () 

        #  main panels 

        self._edit_panel      = None  
        self._info_panel      = None
        self._diagram         = None

        self._btn_ok : QPushButton = None 

        super().__init__ (parent, **kwargs)

        # initially disable ok button - see refresh 
        self._btn_ok.setDisabled(True)

        # connect to new polar loading
        self._watchdog.sig_new_polars.connect (self.refresh)


    @override
    @property
    def widgets (self) -> list[Widget]:
        """ list of widgets defined in self """
        # here edit_panel is the main panel
        return Panel_Abstract.widgets_of_layout (self._edit_panel.layout())

    @override
    def _on_widget_changed (self,*_):
        """ slot for change of widgets"""
        self.refresh() 


    @property
    def case (self) -> Case_Optimize:
        return self._app_model.case

    @property
    def input_file (self) -> Input_File:
        return self.case.input_file
    
    @property 
    def input_fileName (self) -> str:
        return self.input_file.fileName
    
    @property 
    def workingDir (self) -> str:
        return self.case.workingDir
    
    @property
    def airfoil_seed (self) -> Airfoil:
        return self.input_file.airfoil_seed
    
    @property
    def polarSet_seed (self) -> Polar_Set:
        return self.airfoil_seed.polarSet
    
    @property
    def optimization_options (self) -> Nml_optimization_options:
        return self.input_file.nml_optimization_options

    @property
    def operating_conditions (self) -> Nml_operating_conditions:
        return self.input_file.nml_operating_conditions

    @property
    def geometry_targets (self) -> Nml_geometry_targets:
        return self.case.input_file.nml_geometry_targets

    @property
    def thickness (self) -> GeoTarget_Definition | None: 
        return self.geometry_targets.thickness

    @property
    def curvature (self) -> Nml_curvature:
        return self.input_file.nml_curvature

    @property
    def opPoint_defs (self) -> OpPoint_Definitions:
        return self.input_file.opPoint_defs


    def _create_opPoint_defs (self): 
        """ create opPoint defs based on shape functions and seed airfoil"""

        self.airfoil_seed.set_polarSet (Polar_Set (self.airfoil_seed, polar_def=self.opPoint_defs.polar_def_default))
        self.polarSet_seed.load_or_generate_polars ()
        
        nOp = 3 if self.optimization_options.shape_functions == Nml_optimization_options.CAMB_THICK else 5

        # (re) create opPoint definitions 
        self.opPoint_defs.create_initial (self.polarSet_seed, nOp, 
                                          target_max_glide=1.05, target_min_cd=1.01, target_low_cd=1.03)


    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0

        l.addWidget (self.info_panel, r,c,1,5)
        r += 1
        SpaceR      (l,r, stretch=0)
        r += 1
        Label       (l,r,c, get="Name of Input file equals final airfoil and working directory", height=30, colSpan=4, style=style.COMMENT)
        r += 1
        Field       (l,r,c+1, lab="Outname", width=175, 
                     get=lambda: self.input_file.outName, set=self.input_file.set_outName,
                     style=lambda: style.WARNING if not self.input_file.outName else style.NORMAL)
        r += 1
        Field       (l,r,c+1, lab="Working directory",  
                     get=lambda: ('...'+self.workingDir[-26:]) if len(self.workingDir) > 26 else self.workingDir, 
                     toolTip=lambda: self.workingDir)
        ToolButton  (l,r,c+3, icon=Icon.OPEN, set=self._change_working_dir, 
                     toolTip="Select new working directory")

        r += 1
        SpaceR      (l,r, stretch=0)
        r += 1
        Label       (l,r,c, get="Seed airfoil and shape functions to apply for optimization", height=30, colSpan=4, style=style.COMMENT)
        r += 1
        Label       (l,r,c+1, get="Seed Airfoil")
        w = Airfoil_Select_Open_Widget (l,r,c+2, colSpan=2, width=198, textOpen="&Open", widthOpen=90, 
                                    obj=lambda: self.input_file, prop=Input_File.airfoil_seed)
        w.sig_changed.connect (self._airfoil_seed_changed)                          # copy seed to working Dir
        r += 1
        ComboBox    (l,r,c+1, lab="Shape functions", lab_disable=True,
                     obj=self.optimization_options, prop=Nml_optimization_options.shape_functions_label_long,
                     disable=lambda: self.input_file.airfoil_seed.isBezierBased,
                     options=lambda: self.optimization_options.shape_functions_list,     
                     toolTip=lambda: "Bezier based seed airfoil is master of shape functions" if self.input_file.airfoil_seed.isBezierBased \
                                     else "Select shape functions for optimization")     
        r += 1
        SpaceR      (l,r, stretch=0)
        r += 1
        Label       (l,r,c, get="Default polar and proposed, first operating points", height=30, colSpan=4, style=style.COMMENT)
        r += 1
        Field       (l,r,c+1, lab="Default Polar",  
                    get=lambda: self.opPoint_defs.polar_def_default.name)
        ToolButton  (l,r,c+3, icon=Icon.EDIT,   set=self._edit_polar_def)
        r += 1
        Label       (l,r,c+1, get="Operating Points")
        ListBox     (l,r,c+2, height=(None, None), autoHeight=True, rowSpan=2, width=175,          
                     options=lambda:  [opPoint_def.labelLong for opPoint_def in self.opPoint_defs],
                     hide = lambda: not self.opPoint_defs)
        Label       (l,r,c+2, get="Waiting for polar ...", colSpan=2, style=style.COMMENT,
                     hide = lambda: self.opPoint_defs or self.polarSet_seed.has_all_polars_loaded)
        Label       (l,r,c+2, get="Creation failed", colSpan=2, 
                     style=style.ERROR, styleRole = QPalette.ColorRole.Window,
                     hide = lambda: self.opPoint_defs or self.polarSet_seed.has_polars_not_loaded)

        r += 2
        SpaceR      (l,r, stretch=0)
        r += 1
        Label       (l,r,c, get="Geometry targets and curvature demands", height=30, colSpan=4, style=style.COMMENT)
        r += 1
        CheckBox    (l,r,c+1, text="Thickness", colSpan=2, 
                     get=lambda: self.thickness is not None, 
                     set=lambda x: self.geometry_targets.activate_thickness(x))
        FieldF      (l,r,c+2, width=70, unit="%", step=0.2,
                     obj=lambda: self.thickness, prop=GeoTarget_Definition.optValue,
                     hide=lambda: not self.thickness)
        r += 1
        CheckBox    (l,r,c+1, text="Reflexed (reversal on top side)", colSpan=2, 
                     get=lambda: self.curvature.max_curv_reverse_top == 1,
                     set=lambda x: self.curvature.set_max_curv_reverse_top(x),
                     hide=lambda: not self.airfoil_seed.isReflexed or 
                          self.optimization_options.shape_functions == Nml_optimization_options.CAMB_THICK)
        r += 1
        CheckBox    (l,r,c+1, text="Rearloaded (reversal on bottom)", colSpan=3,   
                     get=lambda: self.curvature.max_curv_reverse_bot == 1,
                     set=lambda x: self.curvature.set_max_curv_reverse_bot(x),
                     hide=lambda: not self.airfoil_seed.isRearLoaded or 
                        self.optimization_options.shape_functions == Nml_optimization_options.CAMB_THICK)

        r += 1
        l.setRowStretch (r,5)
        l.setColumnMinimumWidth (0,20)
        l.setColumnMinimumWidth (1,110)
        l.setColumnMinimumWidth (2,175)
        l.setColumnMinimumWidth (3,50)
        l.setColumnStretch (3,2)
        l.setColumnStretch (4,2)

        self._edit_panel      = Edit_Panel (self, layout=l, has_head=False, main_margins= (5,0,10,5), panel_margins=(0,0,0,0), width=380) 

        self._diagram         = Diagram_Xo2_Airfoil_and_Polar (self, self._app_model)
        
        l =  QHBoxLayout()
        l.addWidget (self._edit_panel)
        l.addWidget (self._diagram, stretch=2)   
        l.setContentsMargins (QMargins(0, 0, 0, 0))

        return l 


    @property
    def info_panel (self) -> Edit_Panel:
        """ return info panel holding additional user info"""

        if self._info_panel is None:    
            l = QGridLayout()
            r,c = 0, 0 
            Label  (l,r,c, style=style.COMMENT, wordWrap=True, height=(None,None),
                    get="Create a new optimization by defining the major parameters.<br>" +
                        "All parameters can be changed subsequently. Some typical operating points are " +
                        "created based on the selected shape functions. Adjust these operating points later " + 
                        "depending on the objectives of the optimization.")
            l.setRowStretch (r,1)
            self._info_panel = Edit_Panel (layout=l, has_head=False, main_margins= (0,0,0,0), panel_margins=(10,0,5,0), height=100)  
            self._info_panel.set_background_color (**mode_color.OPTIMIZE)

        return self._info_panel 



    def _change_working_dir (self): 
        """ set a new working directory - handle seed airfoil"""

        new_dir = QFileDialog.getExistingDirectory(self, directory=self.workingDir, caption="Select or create working directory")

        if new_dir and (os.path.abspath (new_dir) != os.path.abspath (self.workingDir)):

            seed_ok = self._ask_copy_airfoil_seed (new_dir)                 # ensure seed airfoil is copied 

            if seed_ok: 
                self.case.set_workingDir (new_dir)

                QTimer.singleShot (10, self.refresh)


    def _airfoil_seed_changed (self, *_):
        """ slot seed airfoil changed - check if still in working dir"""

        # the airfoil may not have a directory as it should be relative to its working dir 
        if self.airfoil_seed.pathName:

            # copy seed airfoil to working dir 
            self.airfoil_seed.saveAs (dir=self.workingDir, isWorkingDir=True)

            text = f"Seed airfoil <b>{self.airfoil_seed.fileName}</b> copied to working directory."
            MessageBox.info(self, "Copy seed airfoil", text)

            QTimer.singleShot (10, self.refresh)


    def _ask_copy_airfoil_seed (self, new_dir : str = None): 
        """ 
        ask if seed should be copied to new_dir and copy if yes
        Returns True if seed was copied or if it was already there
        """

        # check if seed is already in new_dir 
        if os.path.isfile (os.path.join (new_dir, self.airfoil_seed.fileName)): 
            self.airfoil_seed.set_pathFileName (self.airfoil_seed.fileName)
            self.airfoil_seed.set_workingDir (new_dir)
            return True 

        # ask if it should be copied 
        text = f"Seed airfoil <b>{self.airfoil_seed.fileName}</b><br>will be copied to the new working directory."
        button = MessageBox.confirm (self, "Copy seed airfoil", text)

        if button == QMessageBox.StandardButton.Cancel:
            return False
        
        # copy seed airfoil 
        self.airfoil_seed.saveAs (dir=new_dir, isWorkingDir=True)

        return True 


    def _edit_polar_def (self):
        """ edit default polar definition"""

        polar_def = self.opPoint_defs.polar_def_default
        diag = Polar_Definition_Dialog (self._edit_panel, polar_def, small_mode=True, parentPos=(1.05,0.2), dialogPos=(0,1))

        diag.setWindowTitle ("Default Polar of Op Points")
        diag.exec()

        self.opPoint_defs.set_polar_def_default (polar_def)
        self.airfoil_seed.set_polarSet (Polar_Set (self.airfoil_seed, polar_def=polar_def))

        self.refresh()


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""
        buttonBox = QDialogButtonBox (  QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        buttonBox.rejected.connect  (self.close)
        buttonBox.accepted.connect  (self.accept)

        self._btn_ok  = buttonBox.button(QDialogButtonBox.StandardButton.Ok)

        return buttonBox 


    def _open_case (self): 
        """ open existing case self.input_file"""
        self.accept ()


    @override
    def refresh (self,*_):
        """ refresh including diagram"""

        self._create_opPoint_defs ()

        super().refresh() 

        self._diagram.refresh()

        # activate ok button if all is ok 
        if self.input_file.outName and self.opPoint_defs:
            self._btn_ok.setEnabled(True)
        else: 
            self._btn_ok.setEnabled(False)


    @override
    def accept (self): 
        """ ok button pressed"""

        # sanity check 
        if not (self.input_file.outName and self.opPoint_defs): return 

        # check file already exists 
        if os.path.isfile (self.input_file.pathFileName):
            text   = f"Input file <b>{self.input_file.fileName}</b> already exists.<br><br>The file will be overwritten."
            button = MessageBox.confirm (self, title="Create Input file", text=text)
            if button == QMessageBox.StandardButton.Cancel:
                return
            
            # remove existing result directory
            self.case.clear_results()

        self.input_file.save_nml ()

        super().accept()


    @override
    def done(self, result):
        """ called by both accept() and reject() before closing"""

        self._watchdog.sig_new_polars.disconnect (self.refresh)
        self._watchdog = None

        super().done(result)



class Xo2_Run_Dialog (Dialog):
    """ Dialog to run/watch Xoptfoil2"""

    _width  = (350, None)
    _height = (330, None)

    name = "Run"


    # -------------------------------------------------------------------------

    def __init__ (self, parent : QWidget, 
                  app_model : App_Model,
                  **kwargs): 

        self._app_model = app_model

        # init layout etc 

        self._last_improvement  = 0
        self._improved          = False
        self._about_to_run      = False                             # additional state 

        self._panel_about_to_run : Edit_Panel = None
        self._panel_running      : Edit_Panel = None
        self._panel_ready        : Edit_Panel = None
        self._panel_stopping     : Edit_Panel = None
        self._panel_finished     : Edit_Panel = None
        self._panel_error        : Edit_Panel = None

        self._diagram : Diagram_Xo2_Airfoil_and_Polar = None
        
        self._btn_stop   : QPushButton = None
        self._btn_close  : QPushButton = None 
        self._btn_run    : QPushButton = None 

        super().__init__ (parent, title=f"{self.name}   [{self.case.input_file.fileName}]", **kwargs)  

        #self.setWindowFlags (self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint,)
        self.setWindowFlags (Qt.WindowType.CustomizeWindowHint | Qt.WindowType.Window | Qt.WindowType.WindowTitleHint)

        # no border for panel layout 

        self._panel.layout().setContentsMargins (QMargins(0, 0, 0, 0))              # no margin for main panel
        self.layout().setContentsMargins        (QMargins(5, 0, 5, 15))             # no top margin for self

        # handle button (signals) 

        self._btn_stop.pressed.connect   (self._stop_optimize)
        self._btn_close.clicked.connect  (self.close)
        self._btn_run.clicked.connect    (self._run_xo2)

        # switch panel and buttons on/off

        self._set_buttons ()

        # connect to xo2 signals

        self.app_model.sig_xo2_new_state.connect        (self.on_new_state)
        self.app_model.sig_xo2_new_step.connect         (self.on_new_step)
        self.app_model.sig_xo2_still_running.connect    (self.panel_running.refresh)

        # run immediately if ready and no previous run result

        if self.case.xo2.state == xo2_state.READY and not self.case.isFinished:        
            QTimer.singleShot(0, self._run_xo2)                                     # run xo2 



    @override
    def show (self):
        """ show this dialog and return """
        super().show()

        # overridden to ensure the actual panel according to state when open 
        self.refresh()

    @property
    def app_model (self) -> App_Model:
        """ application model"""
        return self._app_model

    @property
    def case(self) -> Case_Optimize:
        return self._app_model.case

    @property
    def xo2(self) -> Xo2_Controller:
        return self.case.xo2

    @property
    def results(self) -> Xo2_Results:
        return self.case.results

    @property
    def steps (self) -> list ['Optimization_History_Entry']:
        """ optimization steps imported (up to now)""" 
        if self._about_to_run:                                      # for responsive UI
            return []
        return self.results.steps


    @property
    def nxfoil_calcs (self) -> int:
        """ no of xfoil calculation"""

        nxfoil_per_step = self.case.input_file.nxfoil_per_step
        if self.case.xo2.state == xo2_state.RUNNING:
            return self.xo2.nSteps * nxfoil_per_step
        else: 
            return self.results.nSteps * nxfoil_per_step

    def _set_improved (self): 
        """ set internal improved flag if step made an improvement"""

        if self.xo2.improvement > self._last_improvement:
            self._improved = True
            self._last_improvement = self.xo2.improvement
        else:
            self._improved = False


    def on_new_state (self):
        """ slot to receive new results from running thread"""

        self._about_to_run = False 

        self.refresh ()

        # and the diagram 
        self._diagram.refresh()


    def on_new_step (self):
        """ slot new step """

        self._about_to_run = False 

        self._set_improved ()
        self.panel_about_to_run.refresh() 
        self.panel_running.refresh() 

        self._diagram.refresh()


    @property
    def panels_state (self) -> str:
        """ state string to select the right panel dependent on xo2 state"""

        if self._about_to_run:
            state = "about to run"
        elif self.case.xo2.state == xo2_state.RUNNING and self.xo2.nSteps == 0:
            state = "about to run"
        elif self.case.xo2.state == xo2_state.RUNNING and self.xo2.nSteps > 0:
            state = "running"
        elif self._about_to_run:
            state = "about to run"
        elif self.case.xo2.state == xo2_state.STOPPING:
            state = "stopping"
        elif self.case.xo2.state == xo2_state.RUN_ERROR:
            state = "error"
        elif self.case.xo2.state == xo2_state.READY and not self.case.isFinished:
            state = "ready"
        elif self.case.xo2.state == xo2_state.READY and self.case.isFinished:
            state = "finished"
        else: 
            state = "ready"
        return state 


    @property
    def panel_running (self) -> Edit_Panel:
        """ shows info during Xo2 run"""

        if self._panel_running is None: 

            l = QGridLayout()
            r,c = 0, 0 
            Label  (l,r,c,   get="Iterations / Designs")
            Label  (l,r,c+1, get=lambda: f" {self.xo2.nSteps}/{self.xo2.nDesigns} ", fontSize=size.HEADER)
            Label  (l,r,c+2, get=lambda: f"xfoil calculations {self.nxfoil_calcs}", 
                             style=style.COMMENT, fontSize=size.SMALL)
            r += 1
            Label  (l,r,c,   get="Time elapsed")
            Label  (l,r,c+1, get=lambda: f" {self.xo2.time_running()} ", fontSize=size.HEADER)
            r += 1
            Label  (l,r,c,   get="Improvement")
            Label  (l,r,c+1, get=lambda: f" {self.xo2.improvement:.5%} ", fontSize=size.HEADER,
                             style=lambda: style.GOOD if self._improved else style.NORMAL, 
                             styleRole=QPalette.ColorRole.Window) # background
            r += 1
            l.setRowStretch (r,1)

            l.setColumnMinimumWidth (0,110)
            l.setColumnMinimumWidth (1,60)
            l.setColumnStretch (2,2)

            self._panel_running = Edit_Panel (title="Running", layout=l, height=(None,None),
                                              hide=lambda: self.panels_state != "running") 
            self._panel_running.set_background_color (color='magenta', alpha=0.2)        

        return self._panel_running


    @property
    def panel_about_to_run (self) -> Edit_Panel:
        """ shows info during Xo2 short before run"""

        if self._panel_about_to_run is None: 

            l = QGridLayout()
            r,c = 0, 0 
            Label  (l,r,c,   get="... preparing and evaluating seed airfoil ...")
            r += 1
            SpaceR (l, r) 

            self._panel_about_to_run = Edit_Panel (title="Running", layout=l, height=(None,None),
                                              hide=lambda: self.panels_state != "about to run") 
            self._panel_about_to_run.set_background_color (color='magenta', alpha=0.15)        

        return self._panel_about_to_run


    @property
    def panel_ready (self) -> Edit_Panel:
        """ default panel for being idle"""

        if self._panel_ready is None: 

            l = QGridLayout()
            r = 0
            Label  (l,r,0, colSpan=5, height=40, get="Ready for Optimization")
            r += 1
            l.setRowStretch (r,1)

            self._panel_ready = Edit_Panel (title="Ready", layout=l, height=(None,None),
                        hide=lambda: self.panels_state != "ready") 
    
        return self._panel_ready


    @property
    def panel_stopping (self) -> Edit_Panel:
        """ stop requested """

        if self._panel_stopping is None: 

            l = QGridLayout()
            r = 0
            Label  (l,r,0,  get="Graceful stop request to Xoptfoil2.")
            r += 1
            Label  (l,r,0,  get=lambda: f"Final airfoil {self.case.outName} will be created ...")
            r += 1
            l.setRowStretch (r,1)

            self._panel_stopping = Edit_Panel (title="Stopping", layout=l, height=(None,None),
                                            hide=lambda: self.panels_state != "stopping") 
            self._panel_stopping.set_background_color (color='darkorange', alpha=0.3)

        return self._panel_stopping


    @property
    def panel_error (self) -> Edit_Panel:
        """ error occurred """

        if self._panel_error is None: 

            l = QGridLayout()
            r = 0
            Label  (l,r,0,  get=lambda: f"{self.case.xo2.run_errortext}", height=(60,None), wordWrap=True)
            r += 1
            l.setRowStretch (r,1)

            self._panel_error = Edit_Panel (title="Error occurred", layout=l, height=(None,None),
                                            hide=lambda: self.panels_state != "error") 
            self._panel_error.set_background_color (color='red', alpha=0.3)

        return self._panel_error


    @property
    def panel_finished (self) -> Edit_Panel:
        """ shows info during Xo2 run"""

        if self._panel_finished is None: 

            l = QGridLayout()
            r,c = 0, 0 
            Label  (l,r,c,   get="Iterations / Designs")
            Label  (l,r,c+1, get=lambda: f" {self.results.nSteps}/{self.results.nDesigns} ", fontSize=size.HEADER)
            Label  (l,r,c+2, get=lambda: f"xfoil calculations {self.nxfoil_calcs}", 
                             style=style.COMMENT, fontSize=size.SMALL)
            r += 1
            Label  (l,r,c,   get="Time elapsed")
            Label  (l,r,c+1, get=lambda: f" {self.results.time_elapsed()} ", fontSize=size.HEADER)
            r += 1
            Label  (l,r,c,   get="Improvement")
            Label  (l,r,c+1, get=lambda: f" {self.results.improvement:.5%} ", fontSize=size.HEADER)
            r += 1
            l.setRowStretch (r,1)

            l.setColumnMinimumWidth (0,110)
            l.setColumnMinimumWidth (1,60)
            l.setColumnStretch (2,2)

            self._panel_finished = Edit_Panel (title="Finished - Final Results", layout=l, height=(None,None),
                        hide=lambda: self.panels_state != "finished") 
            self._panel_finished.set_background_color (**mode_color.OPTIMIZE)

        return self._panel_finished



    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        l.addWidget (self.panel_ready, 0,0,1,1)
        l.addWidget (self.panel_about_to_run, 0,0,1,1)
        l.addWidget (self.panel_running, 0,0,1,1)
        l.addWidget (self.panel_stopping, 0,0,1,1)
        l.addWidget (self.panel_finished, 0,0,1,1)
        l.addWidget (self.panel_error, 0,0,1,1)

        self._diagram = Diagram_Xo2_Progress (self, lambda: self.steps)

        l.addWidget (self._diagram, 1,0,1,1) 

        l.setRowMinimumHeight (0,125)  
        l.setRowStretch (1,1)  
        l.setContentsMargins (QMargins(0, 0, 0, 0))

        return l


    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)

        self._btn_close  = buttonBox.button(QDialogButtonBox.StandardButton.Close)

        self._btn_stop = QPushButton ("Stop", parent=self)
        self._btn_stop.setFixedWidth (100)

        self._btn_run = QPushButton ("Run", parent=self)
        self._btn_run.setFixedWidth (100)

        buttonBox.addButton (self._btn_run, QDialogButtonBox.ButtonRole.ActionRole)
        buttonBox.addButton (self._btn_stop, QDialogButtonBox.ButtonRole.RejectRole)

        return buttonBox 


    def _set_buttons (self):
        """ depending on xo2 state, set panel and button visibility """

        state = self.case.xo2.state

        self._btn_stop.setVisible (False) 
        self._btn_stop.setDisabled (False)
        self._btn_run.setVisible (False) 
        self._btn_close.setVisible (False) 


        if state == xo2_state.RUNNING:

            self._btn_stop.setVisible (True) 
            self._btn_stop.setFocus ()

        elif state == xo2_state.READY and self.case.isFinished:

            self._btn_close.setVisible (True) 
            self._btn_run.setVisible (True) 
            self._btn_run.setFocus ()

        elif state == xo2_state.READY:

            self._btn_close.setVisible (True) 
            self._btn_run.setVisible (True) 
            self._btn_run.setFocus ()

        elif state == xo2_state.STOPPING:

            self._btn_stop.setVisible (True) 
            self._btn_stop.setDisabled (True)

        elif state == xo2_state.RUN_ERROR:

            self._btn_close.setVisible (True) 
            self._btn_run.setVisible (True) 
            self._btn_run.setFocus ()

        else: 

            self._btn_close.setVisible (True) 
            self._btn_close.setFocus ()


    def _run_xo2 (self):
        """ start xo2 run"""

        self._last_improvement = 0.0
        self._improved = False 
        self._about_to_run = True 

        self.refresh ()                             # fast, responsive refresh when Button clicked
        self._diagram.refresh()

        self.app_model.run_xo2()


    def _stop_optimize (self):
        """ request thread termination"""
    
        self.case.xo2.stop()

        self.refresh()


    @override
    def refresh (self, disable=None):
        """ overridden to set panel view according to state """

        self._set_buttons ()

        for panel in self.findChildren (Edit_Panel):
            panel.refresh()


    @override
    def reject(self): 
        """ close or x-Button pressed"""

        # stop running matcher if x-Button pressed
        if self.case.xo2.isRunning:
            self._stop_optimize()

        # disconnect to xo2 signals
        self.app_model.sig_xo2_new_state.disconnect        (self.on_new_state)
        self.app_model.sig_xo2_new_step.disconnect         (self.on_new_step)
        self.app_model.sig_xo2_still_running.disconnect    (self.panel_running.refresh)

        # normal close 
        super().reject()



class Xo2_Input_File_Dialog (Dialog):

    """ Text edit of Xoptfoil2 input file  """

    _width  = (800,1400)
    _height = (800,1600)

    name = "Edit Input file"

    def __init__ (self, parent, input_file : Input_File,  **kwargs): 

        self._input_file  = input_file
        self.name = f"{self.name} [{input_file.fileName}]"

        super().__init__ ( parent, **kwargs)

        self.setSizeGripEnabled (True)
        self._panel.layout().setContentsMargins (QMargins(0, 0, 0, 0))  # no borders in central panel 


    @property
    def new_text (self) -> str:
        """ the edited text when Ok was pressed"""
        return self._new_text
    
    def set_new_text (self, aStr : str):
        self._new_text = aStr

    # -------------------------------------------------------------------

    def _init_layout(self) -> QLayout:

        l = QGridLayout()

        self._qtextEdit = QTextEdit () 

        self._qtextEdit.setStyleSheet("font: 10pt 'Courier New';")
        self._qtextEdit.setPlaceholderText ("Enter text ...")  
        self._qtextEdit.setPlainText (self._input_file.as_text())  
        self._qtextEdit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap) 

        tabStop = 4
        metrics = QFontMetrics (self._qtextEdit.currentFont())
        self._qtextEdit.setTabStopDistance (tabStop * metrics.horizontalAdvance ('1'))

        l.addWidget (self._qtextEdit, 0,0)

        l.setRowStretch (0,1)    
        l.setColumnStretch (0,1)    

        return l

    def _highlight_error (self, error_text : str):
        """ highlight e.g. namelist of the error"""

        words = error_text.split() 

        if "namelist" in words:
            namelist_name = "&" + words [words.index ("namelist") + 1]

            document = self._qtextEdit.document()
            cursor = document.find (namelist_name, position=0)                      # cursor will have start-end
            self._qtextEdit.setTextCursor (cursor)                                  # select the text


    @override
    def accept(self):
        """ Qt overloaded - ok - check for errors"""

        if self._qtextEdit.document().isModified():

            text = self._qtextEdit.toPlainText ()
            rc, error_text = self._input_file.check_content (text)

            if rc == 0: 
                self._input_file.text_save (text, pathFileName=self._input_file.pathFileName)
                super().accept() 
            else: 
                self._highlight_error (error_text)
                MessageBox.error   (self,'Check Input File', f"{error_text}", min_height= 80)
                self._qtextEdit.setFocus ()

        else: 
            # no changes made - ok is like cancel 
            super().reject() 


class Xo2_Description_Dialog (Dialog):

    """ a small text editor to edit the &info description"""

    _width  = 300
    _height = 110

    name = "Description"

    def __init__ (self, *args, title : str= None, **kwargs): 

        self._close_btn  : QPushButton = None 
        self._new_text  = None

        super().__init__ ( *args, **kwargs)

        title = title if title is not None else self.name
        self.setWindowTitle (f"{title}")
        self._panel.layout().setContentsMargins (QMargins(0, 0, 0, 0))  # no borders in central panel 

        # connect dialog buttons
        self._close_btn.clicked.connect  (self.close)


    @property
    def text (self) -> str:
        return self.dataObject

    @property
    def new_text (self) -> str:
        """ the edited text when Ok was pressed"""
        return self._new_text
    
    def set_new_text (self, aStr : str):
        self._new_text = aStr

    # -------------------------------------------------------------------

    def _init_layout(self) -> QLayout:

        l = QGridLayout()

        self._qtextEdit = QTextEdit () 
        self._qtextEdit.setPlaceholderText ("Enter a description ...")  
        self._qtextEdit.setPlainText (self.text)  

        l.addWidget (self._qtextEdit, 0,0)
        l.setRowStretch (0,1)    
        l.setColumnStretch (0,1)    

        return l


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttonBox = QDialogButtonBox (QDialogButtonBox.StandardButton.Close) #  | QDialogButtonBox.StandardButton.Cancel)
        self._close_btn  = buttonBox.button(QDialogButtonBox.StandardButton.Close)
        return buttonBox 


    @override 
    def close (self): 
        """ close button clicked """

        self.set_new_text (self._qtextEdit.toPlainText ()) 

        super().close ()

        self.setResult (QDialog.DialogCode.Accepted)



class Xo2_OpPoint_Def_Dialog (Dialog):
    """ Dialog to view / edit current opPoint definition """

    _width  = (330, None)
    _height = (210, 210)

    name = "Operating Point Definition"

    def __init__ (self, parent : QWidget, 
                  app_model : App_Model,
                  **kwargs): 

        self._app_model = app_model

        self._individual_flap       = False if self.cur_opPoint_def.has_default_flap      else True 

        # init layout etc 

        self._btn_close  : QPushButton = None 

        super().__init__ (parent, title=self._titletext(), **kwargs)  

        #self.setWindowFlags (self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint,)
        self.setWindowFlags (Qt.WindowType.CustomizeWindowHint | Qt.WindowType.Window | 
                             Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint) #

        # no border for main layout 

        self._panel.layout().setContentsMargins (QMargins(10, 5, 10, 5))

        if Widget.light_mode:
            set_background (self._panel, darker_factor=30)
            set_background (self       , darker_factor=30)
        else: 
            set_background (self._panel, darker_factor=110)
            set_background (self       , darker_factor=110)

        # connect to changes of input file

        self.app_model.sig_xo2_input_changed.connect (self.refresh_current)
        self.app_model.sig_xo2_opPoint_def_selected.connect (self.refresh_current)
        self.app_model.sig_xo2_run_started.connect (self.close)


    @property
    def app_model (self) -> App_Model:
        return self._app_model

    @property
    def case (self) -> Case_Optimize:
        return self.app_model.case

    @property
    def opPoint_defs (self) -> OpPoint_Definitions:
        return self.case.input_file.opPoint_defs

    @property
    def cur_opPoint_def (self) ->OpPoint_Definition:
        return self.app_model.cur_opPoint_def

    @property
    def polar_defs_without_default (self) -> list [Polar_Definition]:
        """ current polar definitions without default polar of opPoints"""
        polar_defs = self.opPoint_defs.polar_defs[:]
        polar_def_default = self.opPoint_defs.polar_def_default
        for polar_def in polar_defs:
            if polar_def.re == polar_def_default.re and polar_def.ma == polar_def_default.ma and \
               polar_def.ncrit == polar_def_default.ncrit:

                polar_defs.remove (polar_def)    
        return polar_defs


    def refresh_current (self):
        """ slot for refresh opPoint def"""

        # update local settings 
        self.set_individual_flap      (not self.cur_opPoint_def.has_default_flap) 

        self.refresh()
 

    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0
        ComboBox (l,r,c, lab="Spec", width=90, 
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.specVar,
                    options=SPEC_TYPES,
                    toolTip="Specification of this Operating Point is either based on cl or alpha")
        FieldF   (l,r,c+2, width=70, dec=2, lim=(-20,20), step=0.01,
                    get=lambda: self.cur_opPoint_def.specValue, 
                    set=lambda aVal: self.cur_opPoint_def.set_specValue_limited(aVal),
                    toolTip="Specification of this Operating Point is on the polar")
        r += 1
        ComboBox (l,r,c, lab="Type", width=90, 
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.opt_asString,
                    options=lambda:self.cur_opPoint_def.opt_allowed_asString(),
                    toolTip="Type of optimization for this Operating Point")
        
        # target value cd       0.001 .. 0.1 step 0.00001
        FieldF   (l,r,c+2, width=70, dec=5, lim=(0.001,0.1), step=0.00001, 
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.optValue,
                    hide=lambda: not (self.cur_opPoint_def.isTarget_type and \
                                      self.cur_opPoint_def.optVar==var.CD and \
                                      not self.cur_opPoint_def.optValue_isFactor),
                    toolTip=f"{self.cur_opPoint_def.optVar} target value to achieve")

        # target value cl/cd    0 .. 200     step 0.01
        FieldF   (l,r,c+2, width=70, dec=2, lim=(0,200), step=0.01, 
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.optValue,
                    hide=lambda: not (self.cur_opPoint_def.isTarget_type and \
                                      self.cur_opPoint_def.optVar==var.GLIDE and \
                                      not self.cur_opPoint_def.optValue_isFactor),
                    toolTip=f"{self.cur_opPoint_def.optVar} target value to achieve")
        
        # target value cl       0.001 .. 5   step 0.001
        FieldF   (l,r,c+2, width=70, dec=3, lim=(0.001,5), step=0.001, 
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.optValue,
                    hide=lambda: not (self.cur_opPoint_def.isTarget_type and \
                                      self.cur_opPoint_def.optVar==var.CL and \
                                      not self.cur_opPoint_def.optValue_isFactor),
                    toolTip=f"{self.cur_opPoint_def.optVar} target value to achieve")

        # target value cm       -0.5 .. 0.5  step 0.001
        FieldF   (l,r,c+2, width=70, dec=4, lim=(-0.5,0.5), step=0.001, 
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.optValue,
                    hide=lambda: not (self.cur_opPoint_def.isTarget_type and \
                                      self.cur_opPoint_def.optVar==var.CM and \
                                      not self.cur_opPoint_def.optValue_isFactor),
                    toolTip=f"{self.cur_opPoint_def.optVar} target value to achieve")

        # target factor         0.5 .. 2  step 0.001
        FieldF   (l,r,c+2, width=70, dec=3, lim=(0.5,2), step=0.001, 
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.optValue,
                    hide=lambda: not (self.cur_opPoint_def.isTarget_type and \
                                      self.cur_opPoint_def.optValue_isFactor),
                    toolTip="Factor on the value of the seed airfoil to achieve")

        CheckBox (l,r,c+4, text="Factor",
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.optValue_isFactor,
                    hide=lambda: not self.cur_opPoint_def.isTarget_type or \
                                  self.cur_opPoint_def.optVar == var.CM,                # cm does not make sense as factor
                    toolTip="Target value should be a factor to value of seed airfoil")
        r += 1
        SpaceR   (l,r, stretch=0)
        r += 1
        CheckBox (l,r,c, text="Individual Weighting", colSpan=2, 
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.has_individual_weighting,
                    toolTip="Set an individual weighting for this Operating Point")
        FieldF   (l,r,c+2, width=70, step=0.1, lim=(0,10), dec=1,
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.weighting_abs,
                    hide=lambda: not self.cur_opPoint_def.has_individual_weighting,
                    toolTip="An individual weighting for this Operating Point")
        CheckBox (l,r,c+4, text="Fixed",
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.weighting_fixed,
                    hide=lambda: not self.cur_opPoint_def.has_individual_weighting or not self.opPoint_defs.dynamic_weighting,
                    toolTip="Fix this weighting during Dynamic Weighting")

        r += 1
        CheckBox (l,r,c, text="Individual Polar", colSpan=2,
                    get=lambda: self.individual_polar, set=self.set_individual_polar,
                    toolTip="Set an individual polar for this Operating Point")
        ToolButton (l,r,c+1, icon=Icon.EDIT, align=ALIGN_RIGHT,  set=self.new_polar_def,
                    hide=lambda: not self.individual_polar,
                    toolTip="Edit the individual polar definition")

        ComboBox (l,r,c+2, colSpan=3,
                    get=lambda: self.cur_opPoint_def.polar_def.name if self.cur_opPoint_def.polar_def else None,
                    set=self.set_polar_def_by_name,
                    options=lambda: [polar_def.name for polar_def in self.polar_defs_without_default],
                    hide=lambda: not self.individual_polar,
                    toolTip="Select individual polar for this Operating Point")

        r += 1
        CheckBox (l,r,c, text="Individual Flap Angle", colSpan=2,
                    get=lambda: self.individual_flap, set=self.set_individual_flap,
                    disable=lambda: not self.opPoint_defs.use_flap,
                    toolTip="Set an individual flap angle for this Operating Point")
        FieldF   (l,r,c+2, width=70, step=0.2, lim=(-15,15), dec=1, unit='°', colSpan=2,
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.flap_angle,
                    hide=lambda: not self.individual_flap,
                    toolTip="An individual flap angle of this Operating Point. <br>" + \
                            "When the flap angle is optimized, this will be the start value.")
        r += 1
        CheckBox (l,r,c, text="Flap Optimize", colSpan=3,
                    obj=lambda: self.cur_opPoint_def, prop=OpPoint_Definition.flap_optimize,
                    disable=lambda: not self.opPoint_defs.use_flap,
                    toolTip="Optimize flap angle at this Operating Point")
        r += 1
        l.setRowStretch (r,5)
        l.setColumnMinimumWidth (0,40)
        l.setColumnMinimumWidth (3,5)
        l.setColumnStretch (4,3)

        return l


    def _titletext (self) -> str: 
        return f"Operating Point {self.cur_opPoint_def.iPoint}"


    @override
    def _button_box(self):
        """ no buttons - floating window"""
        return None


    @override
    def _on_widget_changed (self,*_):
        """ slot for change of widgets"""
        # checkbox show handling                                     
        for w in self.widgets:
            w.refresh()

        # inform model about changes
        self.app_model.notify_xo2_input_changed()


    @property
    def individual_polar (self) -> bool:
        """ checkBox - opPoint def has individual polar """
        return self.cur_opPoint_def.has_individual_polar 

    def set_individual_polar (self, aBool : bool):
        if not aBool:
            self.cur_opPoint_def.set_has_individual_polar(False)
        elif aBool and not self.individual_polar:    
            # switch on
            if not self.polar_defs_without_default:
                # if there are no other polar defs open dialog directly 
                self.new_polar_def ()   
            else: 
                # take the first individual polar 
                self.cur_opPoint_def.set_polar_def (self.polar_defs_without_default[0])          


    def set_polar_def_by_name (self, aStr : str):
        """ for Combobox - set new polar_def by name string """
        for polar_def in self.polar_defs_without_default:
            if polar_def.name == aStr: 
                self.cur_opPoint_def.set_polar_def (polar_def)


    def new_polar_def (self):
        """ create new polar definition"""

        if self.cur_opPoint_def.has_individual_polar:
            new_polar_def = self.cur_opPoint_def.polar_def
        else:
            new_polar_def  = copy (self.opPoint_defs.polar_def_default)
            new_polar_def.set_re (new_polar_def.re + 100000)
            new_polar_def.set_active(True)
        
        diag = Polar_Definition_Dialog (self, new_polar_def, small_mode=True, polar_type_fixed=True, 
                                        parentPos=(0.9, 0.5), dialogPos=(0, 0.5))
        diag.setWindowTitle (f"Individual Polar of Op Point {self.cur_opPoint_def.iPoint}")
        diag.exec()

        self.cur_opPoint_def.set_polar_def (new_polar_def)
        self.refresh()

        # inform model about changes
        self.app_model.notify_xo2_input_changed()


    @property
    def individual_flap (self) -> bool:
        """ checkbox - opPoint def has individual flap angle"""
        return self._individual_flap

    def set_individual_flap (self, aBool : bool):
        self._individual_flap = aBool 
        if not aBool:
            self.cur_opPoint_def.set_flap_angle (None)                    # will set to default 


    @override
    def refresh (self): 
        """ refresh self"""
        self.setWindowTitle (self._titletext())

        super().refresh() 


    @override
    def close (self):
        """ close dialog - inform model about changes"""

        # disconnect from changes of input file
        self.app_model.sig_xo2_input_changed.disconnect (self.refresh_current)
        self.app_model.sig_xo2_opPoint_def_selected.disconnect (self.refresh_current)

        super().close ()



class Xo2_Abstract_Options_Dialog (Dialog):
    """ Super class dialog to edit options of namelist group """

    _width  = (300, None)
    _height = (320, None)

    name = "my xo2 Options"

    def __init__ (self, *args, **kwargs): 

        self._btn_default : QPushButton = None 
        self._btn_close   : QPushButton = None 

        super().__init__ (*args, **kwargs)  

    @override
    def _button_box (self) -> QDialogButtonBox:

        buttonBox = QDialogButtonBox (QDialogButtonBox.StandardButton.Close) #  | QDialogButtonBox.StandardButton.Cancel)

        self._close_btn   = buttonBox.button(QDialogButtonBox.StandardButton.Close)

        self._default_btn = QPushButton ("Default", parent=self)
        self._default_btn.setFixedWidth (80)
        self._default_btn.setToolTip    ("Reset to default values")
        buttonBox.addButton (self._default_btn, QDialogButtonBox.ButtonRole.ActionRole)

        # connect dialog buttons
        self._close_btn.clicked.connect  (self.close)
        self._default_btn.clicked.connect  (self.set_default_values)

        return buttonBox 


    def set_default_values (self):
        """ reset self to default values"""
        nml : Nml_Abstract = self.dataObject
        nml.set_to_default ()

        self.refresh()



class Xo2_Particle_Swarm_Dialog (Xo2_Abstract_Options_Dialog):
    """ Dialog to edit namelist Particle_Swarm_Options"""

    _width  = (300, None)
    _height = (320, None)

    name = "Particle Swarm Options"

    @property
    def particle_swarm_options (self) -> Nml_particle_swarm_options:
        return self.dataObject


    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0
        r += 1
        SpaceR      (l,r, height=5)
        r += 1
        ComboBox    (l,r,c, lab="Convergence", width=120,
                    obj=self.particle_swarm_options, prop=Nml_particle_swarm_options.convergence_profile, 
                    options=Nml_particle_swarm_options.POSSIBLE_PROFILES,
                    toolTip="Determines how quickly the swarm attempts to converge")
        r += 1
        SpaceR      (l,r)
        r += 1
        FieldI      (l,r,c, lab="Population", width=70, lim=(5,100), step=5,
                    obj=self.particle_swarm_options, prop=Nml_particle_swarm_options.pop,
                    toolTip="swarm population - number of particles") 
        r += 1
        FieldI      (l,r,c, lab="Max. Iterations", width=70, lim=(1,9999), step=100,
                    obj=self.particle_swarm_options, prop=Nml_particle_swarm_options.max_iterations, 
                    toolTip="max number of iterations") 
        r += 1
        FieldI      (l,r,c, lab="Max. Retries", width=70, lim=(0,5), step=1,
                    obj=self.particle_swarm_options, prop=Nml_particle_swarm_options.max_retries, 
                    toolTip="number of retries of a particle when it violates the geometry") 
        r += 1
        FieldI      (l,r,c, lab="Init. Attempts", width=70, lim=(10,9999), step=1000,
                    obj=self.particle_swarm_options, prop=Nml_particle_swarm_options.init_attempts, 
                    toolTip="number of trials to get an initial, valid design") 
        r += 1
        FieldF      (l,r,c, lab="Min. Radius", width=70, dec=4, lim=(0.00001,0.1), step=0.01,
                    obj=self.particle_swarm_options, prop=Nml_particle_swarm_options.min_radius, 
                    toolTip="design radius when optimization shall be finished") 
        r += 1
        FieldF      (l,r,c, lab="Max. Speed", width=70, dec=2, lim=(0.01,0.7), step=0.1,
                    obj=self.particle_swarm_options, prop=Nml_particle_swarm_options.max_speed, 
                    toolTip="max speed of a particle in solution space 0..1") 

        r += 1
        l.setRowStretch (r,5)
        l.setColumnMinimumWidth (0,100)
        l.setColumnStretch (5,2)

        return l



class Xo2_Xfoil_Run_Dialog (Xo2_Abstract_Options_Dialog):
    """ Dialog to edit namelist Xfoil_Run_Options"""

    _width  = (280, None)
    _height = (320, None)

    name = "Xfoil Options"

    @property
    def xfoil_run_options (self) -> Nml_xfoil_run_options:
        return self.dataObject


    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0
        r += 1
        SpaceR      (l,r, height=5)
        r += 1
        FieldF      (l,r,c, lab="Ncrit", width=70, dec=1, lim=(1,20), step=1,
                    obj=self.xfoil_run_options, prop=Nml_xfoil_run_options.ncrit,
                    toolTip="ncrit default value to control laminar-turbulent transition") 
        r += 1
        FieldF      (l,r,c, lab="xtrip top", width=70, dec=2, lim=(0,1), step=0.02,
                    obj=self.xfoil_run_options, prop=Nml_xfoil_run_options.xtript,
                    toolTip="forced transition point 0..1 - top side") 
        r += 1
        FieldF      (l,r,c, lab="xtrip bottom", width=70, dec=2, lim=(0,1), step=0.02,
                    obj=self.xfoil_run_options, prop=Nml_xfoil_run_options.xtripb,
                    toolTip="forced transition point 0..1 - bottom side") 
        r += 1
        FieldI      (l,r,c, lab="bl max iterations", width=70, lim=(1,100), step=10,
                    obj=self.xfoil_run_options, prop=Nml_xfoil_run_options.bl_maxit,
                    toolTip="max viscous iterations to achieve convergence") 
        r += 1
        FieldF      (l,r,c, lab="vaccel", width=70, dec=3, lim=(0,0.1), step=0.001,
                    obj=self.xfoil_run_options, prop=Nml_xfoil_run_options.vaccel,
                    toolTip="xfoil vaccel parameter to influence convergence of the viscous loop") 
        r += 1
        CheckBox   (l,r,c, text="Fix unconverged Op Point", colSpan=3,  
                    obj=self.xfoil_run_options, prop=Nml_xfoil_run_options.fix_unconverged,
                    toolTip="Retry an unconverged Op Point with bl initialization and slightly different Re number") 
        r += 1
        CheckBox   (l,r,c, text="Reinitialize boundary layer", colSpan=3, 
                    obj=self.xfoil_run_options, prop=Nml_xfoil_run_options.reinitialize,
                    toolTip="re-init boundary layer for each Op Point") 

        r += 1
        l.setRowStretch (r,5)
        l.setColumnMinimumWidth (0,100)
        l.setColumnStretch (5,2)

        return l



class Xo2_Paneling_Dialog (Xo2_Abstract_Options_Dialog):
    """ Dialog to edit namelist paneling_options"""

    _width  = (280, None)
    _height = (320, None)

    name = "Paneling Options"

    @property
    def xfoil_run_options (self) -> Nml_paneling_options:
        return self.dataObject


    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0
        r += 1
        SpaceR      (l,r, height=5)
        r += 1
        FieldI      (l,r,c, lab="No of panels", width=70, lim=(10,400), step=10,
                    obj=self.xfoil_run_options, prop=Nml_paneling_options.npan,
                    toolTip="Number of panels of airfoil designs and final airfoil") 
        r += 1
        FieldF      (l,r,c, lab="LE bunch", width=70, dec=2, lim=(0,1), step=0.02,
                    obj=self.xfoil_run_options, prop=Nml_paneling_options.le_bunch,
                    toolTip="panel bunch at leading edge") 
        r += 1
        FieldF      (l,r,c, lab="TE bunch", width=70, dec=2, lim=(0,1), step=0.02,
                    obj=self.xfoil_run_options, prop=Nml_paneling_options.te_bunch,
                    toolTip="panel bunch at trailing edge") 
        r += 1
        l.setRowStretch (r,5)
        l.setColumnMinimumWidth (0,100)
        l.setColumnStretch (5,2)

        return l



class Xo2_Hicks_Henne_Dialog (Xo2_Abstract_Options_Dialog):
    """ Dialog to edit namelist hicks_henne_options"""

    _width  = 260
    _height = 280

    name = "Hicks-Henne Options"

    @property
    def hicks_henne_options (self) -> Nml_hicks_henne_options:
        return self.dataObject


    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0
        Label       (l,r,c, get="Hicks-Henne Functions on ...", style=style.COMMENT, colSpan=4)
        r += 1
        FieldI      (l,r,c, lab='Top side', width=50, step=1, lim=(0, 8),
                     obj=lambda: self.hicks_henne_options, prop=Nml_hicks_henne_options.nfunctions_top,
                     toolTip="Number of Hicks-Henne functions") 
        r += 1
        FieldI      (l,r,c, lab='Bottom side', width=50, step=1, lim=(0, 8),
                     obj=lambda: self.hicks_henne_options, prop=Nml_hicks_henne_options.nfunctions_bot,
                     toolTip="Number of Hicks-Henne functions") 
        r += 1
        Label       (l,r,c, colSpan=4, style=style.COMMENT,
                     get=lambda: f"... will be {self.hicks_henne_options.ndesign_var} design variables")        
        r += 1
        SpaceR      (l,r)
        r += 1
        FieldF      (l,r,c, lab='Initial perturb', width=50, step=0.05, lim=(0.01,1),
                     obj=lambda: self.hicks_henne_options, prop=Nml_hicks_henne_options.initial_perturb,
                    toolTip="Measure of how much initial solutions may deviate from seed") 
        r += 1
        CheckBox    (l,r,c, text="Smooth Seed",
                     obj=lambda: self.hicks_henne_options, prop=Nml_hicks_henne_options.smooth_seed,
                     disable=lambda: self.hicks_henne_options._input_file.airfoil_seed.isBezierBased,
                     toolTip="Create a Bezier based airfoil from seed airfoil prior to optimization")                        
        r += 1
        l.setRowStretch (r,2)
        l.setColumnMinimumWidth (0,70)
        l.setColumnStretch (4,2)

        return l


    @override
    def _on_widget_changed (self,*_):
        """ slot for change of widgets"""
        # refresh design variables
        self.refresh()



class Xo2_Bezier_Dialog (Xo2_Abstract_Options_Dialog):
    """ Dialog to edit namelist bezier_options"""

    _width  = 260
    _height = 250

    name = "Bezier Options"

    @property
    def bezier_options (self) -> Nml_bezier_options:
        return self.dataObject

    @property
    def input_file (self) -> Input_File:
        return self.bezier_options._input_file


    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0
        Label (l,r,c, get="Bezier control points on ...", style=style.COMMENT, colSpan=4)
        r += 1
        FieldI     (l,r,c, lab='Top side', width=50, step=1, lim=(3,10),
                    obj=lambda: self.bezier_options, prop=Nml_bezier_options.ncp_top,
                    disable=self.input_file.airfoil_seed.isBezierBased,
                    toolTip="Number of Bezier control points") 
        r += 1
        FieldI     (l,r,c, lab='Bottom side', width=50, step=1, lim=(3,10),
                    obj=lambda: self.bezier_options, prop=Nml_bezier_options.ncp_bot,
                    disable=self.input_file.airfoil_seed.isBezierBased,
                    toolTip="Number of Bezier control points") 
        r += 1
        Label      (l,r,c, colSpan=4, style=style.COMMENT,
                    get=lambda: f"... will be {self.bezier_options.ndesign_var} design variables")        
        r += 1
        FieldF     (l,r,c, lab='Initial perturb', width=50, step=0.05, lim=(0.01,1),
                    obj=lambda: self.bezier_options, prop=Nml_bezier_options.initial_perturb,
                    toolTip="Measure of how much initial solutions may deviate from seed") 
        r += 1
        l.setRowStretch (r,2)
        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (4,2)

        return l

    @override
    def _on_widget_changed (self,*_):
        """ slot for change of widgets"""
        # refresh design variables
        self.refresh()



class Xo2_Camb_Thick_Dialog (Xo2_Abstract_Options_Dialog):
    """ Dialog to edit namelist camb_thick_options"""

    _width  = (260, None)
    _height = (240, None)

    name = "Camb-Thick Options"

    @property
    def camb_thick_options (self) -> Nml_camb_thick_options:
        return self.dataObject


    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0
        Label (l,r,c, get="Geometry parameters to optimize", style=style.COMMENT, colSpan=4)
        r += 1
        CheckBox (l,r,c, text="Thickness",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.thickness,
                    toolTip="Maximum thickness of the airfoil") 
        CheckBox (l,r,c+1, text="... position",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.thickness_pos,
                    toolTip="Position of maximum thickness of the airfoil") 
        r += 1
        CheckBox (l,r,c, text="Camber",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.camber,
                    toolTip="Maximum camber of the airfoil") 
        CheckBox (l,r,c+1, text="... position",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.camber_pos,
                    toolTip="Position of maximum camber of the airfoil") 
        r += 1
        CheckBox (l,r,c, text="LE radius",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.le_radius,
                    toolTip="Leading edge radius of the airfoil") 
        CheckBox (l,r,c+1, text="... blend distance",
                    obj=lambda: self.camb_thick_options, prop=Nml_camb_thick_options.le_radius_blend,
                    toolTip="How much will a change of the radius influence the whole airfoil") 
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Label (l,r,c, colSpan=4, style=style.COMMENT,
               get=lambda: f"Will be {self.camb_thick_options.ndesign_var} design variables")        
        l.setColumnMinimumWidth (0,110)
        l.setColumnStretch (4,2)

        return l

    @override
    def _on_widget_changed (self,*_):
        """ slot for change of widgets"""
        # refresh design variables
        self.refresh()


class Xo2_Constraints_Dialog (Xo2_Abstract_Options_Dialog):
    """ Dialog to edit namelist constraints"""

    _width  = (280, None)
    _height = (200, None)

    name = "Constraints"

    @property
    def constraints (self) -> Nml_constraints:
        return self.dataObject


    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0
        r += 1
        SpaceR      (l,r, height=5)
        r += 1
        CheckBox    (l,r,c, text="Check Geometry", colSpan=2, 
                     obj=lambda: self.constraints, prop=Nml_constraints.check_geometry,
                     toolTip="Check geometry constraints during optimization")                        
        r += 1
        SpaceR      (l,r, height=10)
        r += 1
        CheckBox    (l,r,c, text="Symmetrical Airfoil", colSpan=2,
                     obj=lambda: self.constraints, prop=Nml_constraints.symmetrical,
                     disable=lambda: not self.constraints.check_geometry,
                     toolTip="Airfoil is forced to be symmetrical")                        
        r += 1
        FieldF      (l,r,c, lab="Min TE angle", width=70, dec=1, lim=(0.1,20), step=0.02, unit='°',
                     obj=self.constraints, prop=Nml_constraints.min_te_angle, lab_disable=True,
                     disable=lambda: not self.constraints.check_geometry,
                     toolTip="Minimum opening angle at trailing edge ") 
        r += 1
        l.setRowStretch (r,5)
        l.setColumnMinimumWidth (0,100)
        l.setColumnStretch (5,2)

        return l

    @override
    def _on_widget_changed (self,*_):
        """ slot for change of widgets"""
        self.refresh()




class Xo2_Curvature_Dialog (Xo2_Abstract_Options_Dialog):
    """ Dialog to edit namelist curvature"""

    _width  = (370, None)
    _height = (390, None)

    name = "Curvature"

    def __init__ (self, *args, shape_functions=None, **kwargs): 

        self._shape_functions = shape_functions

        if shape_functions != Nml_optimization_options.HICKS_HENNE and \
           shape_functions != Nml_optimization_options.BEZIER:
            raise ValueError (f"shape function {shape_functions} not supported")

        s = "Bezier" if shape_functions == Nml_optimization_options.BEZIER else "Hicks-Henne"
        self.name = f"{self.name} options for {s}"

        super().__init__ (*args, **kwargs)  


    @property
    def curvature (self) -> Nml_curvature:
        return self.dataObject

    @property 
    def shape_functions (self) -> str:
        return self._shape_functions


    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0
        r += 1
        SpaceR      (l,r, height=5, stretch=0)
        r += 1
        CheckBox    (l,r,c, text="Auto Curvature", colSpan=4, 
                     obj=self.curvature, prop=Nml_curvature.auto_curvature,
                     toolTip="Try to set best curvature specifications based on seed airfoil")                        
        r += 1
        SpaceR      (l,r, height=5, stretch=0)

        r += 1
        Label       (l,r,c, get="Maximum number of reversals on ...", style=style.COMMENT, colSpan=4)
        r += 1
        FieldI      (l,r,c, lab='Top side', width=50, step=1, lim=(0,10),
                     obj=self.curvature, prop=Nml_curvature.max_curv_reverse_top,
                     toolTip="Maximum number of curvature reversals") 
        FieldF      (l,r,c+2, lab=" ... using Threshold  ", width=60, dec=2, lim=(0.01,1), step=0.01, rowSpan=2,
                     align=Qt.AlignmentFlag.AlignVCenter,
                     obj=self.curvature, prop=Nml_curvature.curv_threshold,
                     disable=lambda: self.curvature.auto_curvature,
                     toolTip="Threshold to detect reversals") 
        r += 1
        FieldI      (l,r,c, lab='Bottom side', width=50, step=1, lim=(0,10),
                     obj=self.curvature, prop=Nml_curvature.max_curv_reverse_bot,
                     toolTip="Maximum number of curvature reversals") 

        r += 1
        SpaceR      (l,r, height=5, stretch=0)

        if self.shape_functions == Nml_optimization_options.HICKS_HENNE:
            r += 1
            Label       (l,r,c, get="Maximum number of spikes on ...", style=style.COMMENT, colSpan=4)
            r += 1
            FieldI      (l,r,c, lab='Top side', width=50, step=1, lim=(0,10),
                         obj=self.curvature, prop=Nml_curvature.max_spikes_top,
                         disable=lambda: self.curvature.auto_curvature,
                         toolTip="Maximum number of curvature spikes") 
            FieldF      (l,r,c+2, lab=" ... using Threshold  ", width=60, dec=2, lim=(0.01,1), step=0.01, rowSpan=2,
                         align=Qt.AlignmentFlag.AlignVCenter,
                         obj=self.curvature, prop=Nml_curvature.spike_threshold,
                         disable=lambda: self.curvature.auto_curvature,
                         toolTip="Threshold to detect spikes") 
            r += 1
            FieldI      (l,r,c, lab='Bottom side', width=50, step=1, lim=(0,10),
                         obj=self.curvature, prop=Nml_curvature.max_spikes_bot,
                         disable=lambda: self.curvature.auto_curvature,
                         toolTip="Maximum number of curvature spikes") 
        r += 1
        SpaceR      (l,r, height=5, stretch=0)
        r += 1
        Label       (l,r,c, get="Curvature control at LE and TE  ...", style=style.COMMENT, colSpan=4)
        r += 1
        FieldF      (l,r,c, lab="Max at TE", width=60, dec=2, lim=(0.01,50), step=0.1, 
                     obj=self.curvature, prop=Nml_curvature.max_te_curvature,
                     disable=lambda: self.curvature.auto_curvature,
                     toolTip="Maximum curvature at trailing edge") 

        if self.shape_functions == Nml_optimization_options.BEZIER:
            r += 1
            FieldF      (l,r,c, lab='Max diff at LE', width=60, step=1, lim=(0.1,50), dec=1, 
                         obj=self.curvature, prop=Nml_curvature.max_le_curvature_diff,
                         toolTip="Maximum difference of curvature of top and bottom side at leading edge") 

        r += 1
        l.setRowStretch (r,5)
        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (5,2)

        return l

    @override
    def _on_widget_changed (self):
        self.refresh(9)




class Xo2_Flap_Definition_Dialog (Xo2_Abstract_Options_Dialog):
    """ Dialog to edit flap definition"""

    _width  = 280
    _height = 170

    name = "Flap Definition"

    @property
    def operating_conditions (self) -> Nml_operating_conditions:
        return self.dataObject


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r,c = 0,0 
        SpaceR (l, r, stretch=0, height=5) 
        r += 1
        FieldF  (l,r,c, lab="Hinge x", width=60, step=1, lim=(1, 98), dec=1, unit="%",
                        obj=self.operating_conditions, prop=Nml_operating_conditions.x_flap)
        r += 1
        FieldF  (l,r,c, lab="Hinge y", width=60, step=1, lim=(0, 100), dec=0, unit='%',
                        obj=self.operating_conditions, prop=Nml_operating_conditions.y_flap)
        Label   (l,r,c+3, get="of thickness", style=style.COMMENT)
        r += 1
        FieldF  (l,r,c, lab="Default angle", width=60, step=1, lim=(-30, 30), dec=1, unit='°',
                        obj=self.operating_conditions, prop=Nml_operating_conditions.flap_angle_default)
        r += 1
        SpaceR  (l, r, stretch=3) 

        l.setColumnMinimumWidth (0,80)
        l.setColumnMinimumWidth (2,10)
        l.setColumnStretch (3,2)   

        return l

