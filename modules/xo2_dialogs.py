#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

Extra functions (dialogs) to optimize airfoil  

"""

from copy                   import copy 
from shutil                 import copyfile

import pyqtgraph as pg

from PyQt6.QtWidgets        import QLayout, QDialogButtonBox, QPushButton, QDialogButtonBox
from PyQt6.QtWidgets        import QWidget, QTextEdit, QDialog, QFileDialog
from PyQt6.QtGui            import QFontMetrics, QCloseEvent

from base.widgets           import * 
from base.panels            import Dialog, Edit_Panel, MessageBox, Container_Panel, Panel_Abstract
from base.diagram           import Diagram, Diagram_Item
from base.artist            import Artist

from airfoil_dialogs        import Polar_Definition_Dialog
from airfoil_widgets        import Airfoil_Select_Open_Widget

from model.airfoil          import Airfoil
from model.polar_set        import Polar_Definition
from model.case             import Case_Optimize
from model.xo2_controller   import xo2_state, Xo2_Controller
from model.xo2_results      import Xo2_Results

from model.xo2_input        import *

from model.xo2_input        import SPEC_TYPES, SPEC_ALLOWED, OPT_ALLOWED, var
from xo2_artists            import Xo2_Design_Radius_Artist, Xo2_Improvement_Artist


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)



class Xo2_Optimize_Select_Dialog (Dialog):
    """ Dialog to choose what should be done"""

    _width  = (480, None)
    _height = (200, None)

    name = "Airfoil Optimization"

    EXAMPLE_DIR = "examples_optimize"


    def __init__ (self, parent, input_fileName : str,  current_airfoil : Airfoil, **kwargs): 

        self._input_fileName  = input_fileName
        self._current_airfoil = current_airfoil
        self._workingDir      = None 

        self._info_panel = None

        # is there an existung input file for airfoil

        if self._input_fileName is None and self._current_airfoil is not None:
            self._input_fileName = Input_File.fileName_of (self._current_airfoil)
            self._workingDir     = self._current_airfoil.pathName 

        super().__init__ ( parent, **kwargs)


    @property 
    def input_fileName (self) -> str:
        return self._input_fileName
    
    @property 
    def workingDir (self) -> str:
        return self._workingDir
    
    @property
    def current_airfoil (self) -> Airfoil:
        return self._current_airfoil
    

    
    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0
        if self.input_fileName:
            Button   (l,r,c, width=120, text="Open Case", set=self._open_case)
            Label    (l,r,c+2, wordWrap=True,
                      get=lambda: f"Open input file <b>{self.input_fileName}</b> of airfoil {self.current_airfoil.fileName}" )
            r += 1
            Button   (l,r,c, width=120, text="New Version", set=self._new_version)
            Label    (l,r,c+2, wordWrap=True,
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
        SpaceR   (l,r,stretch=1, height=10)
        r += 1
        l.addWidget (self.info_panel, r,c, 1, 3)  
        l.setRowStretch (r,1)

        # r +=1
        # l.setRowStretch (r,2)
        l.setColumnMinimumWidth (1,20)
        l.setColumnStretch (2,2)

        return l 


    @property
    def info_panel (self) -> Edit_Panel:
        """ return info panel holding additional user info"""

        if self._info_panel is None:    
            l = QGridLayout()
            r,c = 0, 0 
            lab = Label    (l,r,c, height=170, colSpan=3, style=style.COMMENT, wordWrap=True,
                    get="Airfoil optimization is based on <a href='https://github.com/jxjo/Xoptfoil2'>Xoptfoil2</a>, which will run in the background.<br><br>" +
                        "Xoptfoil2 is controlled via the Input file, whose paramters can be edited subsequently. "
                        "The Input file is equivalent to an Optimization Case in the AirfoilEditor." +
                        "<br><br>" +
                        "If you have no experience with airfoil optimization, please read the " + 
                        "<a href='https://jxjo.github.io/Xoptfoil2/'>description of Xoptfoil2</a> first and then run the examples:")
            lab.setOpenExternalLinks(True)

            r += 1
            for example_file, example_path in self._get_example_files (self.EXAMPLE_DIR).items():
                #https://docs.python.org/3.4/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result
                Button   (l,r,c,   width=100, text=Path(example_file).stem, 
                          set=lambda p=example_path: self._open_example_case (p))
                c += 1 
                if c > 2: break
            c = 0
            r += 1
            SpaceR   (l,r,height=10, stretch=0)
            r += 1
            Label    (l,r,c, colSpan=3, style=style.COMMENT, 
                        get="After that you are ready for your own projects!")
            r += 1
            SpaceR   (l,r,height=10, stretch=0)

            l.setColumnMinimumWidth (0,120)
            l.setColumnMinimumWidth (1,120)

            self._info_panel = Edit_Panel (title="Info and Examples", layout=l, height=(100,None), 
                                              switchable=True, switched_on=False, on_switched=lambda x: self.adjustSize())
            
            self._info_panel.set_background_color (color='darkturquoise', alpha=0.2)

        return self._info_panel 



    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""
        buttonBox = QDialogButtonBox ( QDialogButtonBox.StandardButton.Cancel)

        buttonBox.rejected.connect  (self.close)

        return buttonBox 


    def _select_open_open_case (self): 
        """ file select of an input file and close self with input_fileName"""

        # build somethinglike "*.inp *.xo2" as filter for the dialog
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

        new_fileName = Input_File.new_input_fileName_version (self.input_fileName, self.workingDir)

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


    def _get_example_files (self, example_dir : str ) -> dict: 
        """ 
        Returns dict of example input files in example dir and below 
        All .inp, .xo2 are collected 
        """

        examples_dict = {}
        if not os.path.isdir (example_dir): return examples_dict

        for sub_dir, _, _ in os.walk(example_dir):
            for input_file in Input_File.files_in_dir (sub_dir):
                examples_dict [input_file] = os.path.join (sub_dir, input_file)
        return examples_dict




class Xo2_Optimize_New_Dialog (Dialog):
    """ Dialog to create a new input file """

    _width  = (1000, None)
    _height = (800, None)

    name = "New Optimization Case"


    class Diagram_Airfoil_and_Polar (Diagram):
        """ Diagram with design radus and improvement development  """

        width  = (None, None)               # (min,max) 
        height = (400, None)                # (min,max)


        def __init__(self, *args, **kwargs):

            super().__init__(*args, **kwargs)

            self.graph_layout.setContentsMargins (5,10,5,5)  # default margins


        @property
        def airfoil_seed (self) -> Airfoil:
            return self._getter ()


        def airfoils (self) -> list[Airfoil]: 
            return [self.airfoil_seed] if self.airfoil_seed else []


        @override
        def create_diagram_items (self):
            """ create all plot Items and add them to the layout """

            from airfoil_diagrams       import Diagram_Item_Airfoil, Diagram_Item_Polars

            r = 0
            item = Diagram_Item_Airfoil (self, getter=self.airfoils)
            item.setMinimumSize (300, 200)
            self._add_item (item, r, 0, colspan=2)
    
            r += 1
            for iItem, xyVars in enumerate ([(var.CD,var.CL), (var.CL,var.GLIDE)]):
                item = Diagram_Item_Polars (self, getter=self.airfoils, xyVars=xyVars, show=True)
                item.setMinimumSize (200, 200)
                self._add_item (item, r, iItem)


        @override
        def create_view_panel (self):
            """ no view_panel"""
            pass


    # -------------------------------------------------------------------------

    def __init__ (self, parent, workingDir : str,  current_airfoil : Airfoil, **kwargs): 

        self._case            = Case_Optimize ('New',workingDir=workingDir, is_new=True)  

        # init empty input file with current seed airfoil

        self.input_file.set_airfoil_seed (current_airfoil)

        polar_defs = self.case.polar_definitions_of_input ()
        self.airfoil_seed.set_polarSet (Polar_Set (self.airfoil_seed, polar_def=polar_defs))

        #  main panels 

        self._edit_panel      = None  
        self._diagram         = None

        super().__init__ ( parent, **kwargs)

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
        return self._case

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
    def opPoint_defs (self) -> OpPoint_Definitions:
        return self.input_file.opPoint_defs

    @property
    def optimization_options (self) -> Nml_optimization_options:
        return self.input_file.nml_optimization_options

    @property
    def geometry_targets (self) -> Nml_geometry_targets:
        return self.case.input_file.nml_geometry_targets

    @property
    def thickness (self) -> GeoTarget_Definition | None: 
        return self.geometry_targets.thickness


    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0
        Field       (l,r,c, lab="Outname",  
                    get=lambda: self.input_file.outName, set=self.input_file.set_outName)
        r += 1
        Label       (l,r,c, get="Seed Airfoil")
        Airfoil_Select_Open_Widget (l,r,c+1, colSpan=2, width=180,
                                    textOpen="&Open", widthOpen=90, 
                                    obj=lambda: self.input_file, prop=Input_File.airfoil_seed)

        r += 1
        Field       (l,r,c, lab="Default Polar",  
                    get=lambda: self.opPoint_defs.polar_def_default.name)
        ToolButton  (l,r,c+2, icon=Icon.EDIT,   set=self._edit_polar_def)

        r += 1
        ComboBox    (l,r,c, lab="Shape functions", lab_disable=True,
                     get=lambda: self.optimization_options.shape_functions_label_long, 
                     set=self.optimization_options.set_shape_functions_label_long,
                     options=lambda: self.optimization_options.shape_functions_list)     

        r += 1
        CheckBox    (l,r,c, text="Thickness", colSpan=2, 
                     get=lambda: self.thickness is not None, 
                     set=lambda x: self.geometry_targets.activate_thickness(x))
        FieldF      (l,r,c+2, width=70, unit="%", step=0.2,
                     obj=lambda: self.thickness, prop=GeoTarget_Definition.optValue,
                     hide=lambda: not self.thickness)
        r += 1

        l.setRowStretch (r,1)
        l.setColumnMinimumWidth (0,110)
        l.setColumnMinimumWidth (1,140)
        l.setColumnMinimumWidth (2,50)
        l.setColumnStretch (3,2)

        self._edit_panel      = Edit_Panel (self, layout=l, width=400) 

        self._diagram         = self.Diagram_Airfoil_and_Polar (self, lambda: self.airfoil_seed)
        
        l =  QHBoxLayout()
        l.addWidget (self._edit_panel)
        l.addWidget (self._diagram, stretch=2)   
        l.setContentsMargins (QMargins(0, 0, 0, 0))

        return l 


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

        return buttonBox 


    def _open_case (self): 
        """ open existing case self.input_file"""
        self.accept ()




class Xo2_Run_Dialog (Dialog):
    """ Dialog to run/watch Xoptfoil2"""

    _width  = (330, None)
    _height = (340, None)

    name = "Run Control"

    sig_finished          = pyqtSignal()       


    class Diagram_Item_Design_Radius (Diagram_Item):
        """ 
        Diagram (Plot) Item to plot design radius during optimization
        """

        title       = "Design Radius"
        subtitle    = None                

        min_width   = 100                                       # min size needed - see below 
        min_height  = 100 

        def __init__(self, *args, **kwargs):

            super().__init__(*args, **kwargs)

            self.buttonsHidden = True                           # hide resize buttons
            self.setContentsMargins ( 0,10,5,0)

        def results (self) -> Xo2_Results: 
            return self._getter ()


        @override
        def plot_title(self):
            super().plot_title (title=self.title, title_size=8, title_color=Artist.COLOR_LEGEND,offset= (10,-10))


        @override
        def setup_artists (self):
            """ create and setup the artists of self"""
            self._add_artist (Xo2_Design_Radius_Artist (self, self.results))
    

        @override
        def setup_viewRange (self):
            """ define view range of this plotItem"""
            axis : pg.AxisItem = self.getAxis ('left')
            axis.setWidth (5)
            axis : pg.AxisItem = self.getAxis ('bottom')
            axis.setHeight (5)
            self.viewBox.enableAutoRange (axis == 'xy')
            self.viewBox.setDefaultPadding (0.0)



    class Diagram_Item_Improvement (Diagram_Item):
        """ 
        Diagram (Plot) Item to plot improvement during optimization
        """

        title       = "Improvement"
        subtitle    = None                

        min_width   = 100                                    # min size needed - see below 
        min_height  = 100 

        def __init__(self, *args, **kwargs):

            super().__init__(*args, **kwargs)

            self.buttonsHidden = True                           # hide resize buttons
            self.setContentsMargins ( 0,10,5,0)

        def results (self) -> Xo2_Results: 
            return self._getter ()


        @override
        def plot_title(self):
            super().plot_title (title=self.title, title_size=8, title_color=Artist.COLOR_LEGEND,offset= (10,-10))


        @override
        def setup_artists (self):
            """ create and setup the artists of self"""
            self._add_artist (Xo2_Improvement_Artist (self, self.results))
    

        @override
        def setup_viewRange (self):
            """ define view range of this plotItem"""
            axis : pg.AxisItem = self.getAxis ('left')
            axis.setWidth (5)
            axis : pg.AxisItem = self.getAxis ('bottom')
            axis.setHeight (5)
            self.viewBox.enableAutoRange (axis == 'xy')
            self.viewBox.setDefaultPadding (0.0)



    class Diagram_Progress (Diagram):
        """ Diagram with design radus and improvement development  """

        width  = (None, None)               # (min,max) 
        height = (400, None)                # (min,max)


        def __init__(self, *args, **kwargs):


            super().__init__(*args, **kwargs)

            self.graph_layout.setContentsMargins (5,10,5,5)  # default margins


        def results (self) -> Xo2_Results:
            return self._getter ()

        def create_diagram_items (self):
            """ create all plot Items and add them to the layout """
            item = Xo2_Run_Dialog.Diagram_Item_Design_Radius (self, getter=self.results)
            self._add_item (item, 0, 0)
            item = Xo2_Run_Dialog.Diagram_Item_Improvement   (self, getter=self.results)
            self._add_item (item, 0, 1)


        @override
        def create_view_panel (self):
            """ no view_panel"""
            pass


    # -------------------------------------------------------------------------

    def __init__ (self, parent : QWidget, 
                  case,
                  **kwargs): 

        if not isinstance (case, Case_Optimize):
            raise ValueError ("case isn't a Case_Optimize")
        
        self._case = case

        # init layout etc 

        self._last_improvement = 0
        self._improved = False

        self._panel_container = Container_Panel  (height=150)

        self._panel_running  : Edit_Panel = None
        self._panel_ready    : Edit_Panel = None
        self._panel_stopping : Edit_Panel = None
        self._panel_finished : Edit_Panel = None
        self._panel_error    : Edit_Panel = None
        self._diagram        : Diagram    = None
        
        self._btn_stop   : QPushButton = None
        self._btn_close  : QPushButton = None 
        self._btn_run    : QPushButton = None 

        super().__init__ (parent, title=self._titletext(), **kwargs)  

        #self.setWindowFlags (self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint,)
        self.setWindowFlags (Qt.WindowType.CustomizeWindowHint | Qt.WindowType.Window | Qt.WindowType.WindowTitleHint)
        # no border for main layout 

        self._panel.layout().setContentsMargins (QMargins(0, 0, 0, 0))

        # handle button (signals) 

        self._btn_stop.pressed.connect   (self._stop_optimize)
        self._btn_close.clicked.connect  (self.close)
        self._btn_run.clicked.connect    (self.run_optimize)

        # switch panel and buttons on/off

        self._set_buttons ()


    @property
    def case(self) -> Case_Optimize:
        return self._case

    @property
    def xo2(self) -> Xo2_Controller:
        return self.case.xo2

    @property
    def results(self) -> Xo2_Results:
        return self.case.results

    @property
    def nxfoil_calcs (self) -> int:
        """ no of xfoil calculation"""

        nxfoil_per_step = self.case.input_file.nxfoil_per_step
        if self.case.xo2.state == xo2_state.RUNNING:
            return self.xo2.nSteps * nxfoil_per_step
        else: 
            return self.results.nSteps * nxfoil_per_step


    def run_optimize (self): 
        """ run optimizer"""

        # reset current xo2 controller if there was an error 
        if self.case.xo2.isRun_failed:
            self.case.xo2_reset()

        # now run if ready

        if self.case.xo2.isReady:

            self._last_improvement = 0.0
            self._improved = False 

            self.case.run()

        self.refresh ()              # after to get running state 


    def on_results (self):
        """ slot to receice new results from running thread"""

        if self.xo2.improvement > self._last_improvement:
            self._improved = True
            self._last_improvement = self.xo2.improvement
        else:
            self._improved = False

        self.refresh ()

        # and the diagram 
        self._diagram.refresh()

        self.setWindowTitle (self._titletext())


    @property
    def panel_running (self) -> Edit_Panel:
        """ shows info during Xo2 run"""

        if self._panel_running is None: 

            l = QGridLayout()
            r,c = 0, 0 
            SpaceR (l, r, stretch=0, height=5) 
            r += 1
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
            SpaceR (l, r, stretch=0, height=5) 

            l.setColumnMinimumWidth (0,110)
            l.setColumnMinimumWidth (1,60)
            l.setColumnStretch (2,2)

            self._panel_running = Edit_Panel (title="Running", layout=l, height=(None,None),
                                              hide=lambda: not self.case.xo2.state == xo2_state.RUNNING) 
            self._panel_running.set_background_color (color='magenta', alpha=0.2)        

        return self._panel_running


    @property
    def panel_ready (self) -> Edit_Panel:
        """ default panel for being idle"""

        if self._panel_ready is None: 

            l = QGridLayout()
            r = 0
            Label  (l,r,0, colSpan=5, height=40, get="Ready for Optimization")
            r += 1
            SpaceR (l, r, stretch=0, height=5) 
            r += 1
            SpaceR (l, r) 

            self._panel_ready = Edit_Panel (title="Ready", layout=l, height=(None,None),
                        hide=lambda: not (self.case.xo2.state == xo2_state.READY and not self.case.isFinished)) 
    
        return self._panel_ready


    @property
    def panel_stopping (self) -> Edit_Panel:
        """ stop requested """

        if self._panel_stopping is None: 

            l = QGridLayout()
            r = 0
            SpaceR (l, r, stretch=0, height=5) 
            r += 1
            Label  (l,r,0,  get="Graceful stop request to Xoptfoil2.")
            r += 1
            Label  (l,r,0,  get=lambda: f"Final airfoil {self.case.outName} will be created ...")
            r += 1
            SpaceR (l, r) 

            self._panel_stopping = Edit_Panel (title="Stopping", layout=l, height=(None,None),
                                            hide=lambda: not self.case.xo2.state == xo2_state.STOPPING) 
            self._panel_stopping.set_background_color (color='darkorange', alpha=0.3)

        return self._panel_stopping


    @property
    def panel_error (self) -> Edit_Panel:
        """ error occured """

        if self._panel_error is None: 

            l = QGridLayout()
            r = 0
            SpaceR (l, r, stretch=0, height=5) 
            r += 1
            Label  (l,r,0,  get=lambda: f"{self.case.xo2.run_errortext}", height=(60,None), wordWrap=True)
            r += 1
            SpaceR (l, r) 

            self._panel_error = Edit_Panel (title="Error occured", layout=l, height=(None,None),
                                            hide=lambda: not self.case.xo2.state == xo2_state.RUN_ERROR) 
            self._panel_error.set_background_color (color='red', alpha=0.3)

        return self._panel_error


    @property
    def panel_finished (self) -> Edit_Panel:
        """ shows info during Xo2 run"""

        if self._panel_finished is None: 

            l = QGridLayout()
            r,c = 0, 0 
            SpaceR (l, r, stretch=0, height=5) 
            r += 1
            Label  (l,r,c,   get="Iterations / Designs")
            Label  (l,r,c+1, get=lambda: f" {self.results.nSteps}/{self.results.nDesigns} ", fontSize=size.HEADER)
            Label  (l,r,c+2, get=lambda: f"xfoil calculations {self.nxfoil_calcs}", 
                             style=style.COMMENT, fontSize=size.SMALL)
            r += 1
            Label  (l,r,c,   get="Time elapsed")
            Label  (l,r,c+1, get=lambda: f" {self.results.time_running()} ", fontSize=size.HEADER)
            r += 1
            Label  (l,r,c,   get="Improvement")
            Label  (l,r,c+1, get=lambda: f" {self.results.improvement:.5%} ", fontSize=size.HEADER)
            r += 1
            SpaceR (l, r, stretch=0, height=5) 

            l.setColumnMinimumWidth (0,110)
            l.setColumnMinimumWidth (1,60)
            l.setColumnStretch (2,2)

            self._panel_finished = Edit_Panel (title="Finished - Final Results", layout=l, height=(None,None),
                        hide=lambda: not (self.case.xo2.state == xo2_state.READY and self.case.isFinished)) 
            self._panel_finished.set_background_color (color='darkturquoise', alpha=0.2)

        return self._panel_finished



    def _init_layout(self) -> QLayout:

        # container panel with different state panels 

        l_cont = QVBoxLayout()
        l_cont.addWidget (self.panel_ready)
        l_cont.addWidget (self.panel_running)
        l_cont.addWidget (self.panel_stopping)
        l_cont.addWidget (self.panel_finished)
        l_cont.addWidget (self.panel_error)
        l_cont.setContentsMargins (QMargins(0, 0, 0, 0))
        self._panel_container.setLayout (l_cont) 

        # main layout with diagram 

        self._diagram = self.Diagram_Progress (self, lambda: self.case.results)

        l =  QVBoxLayout()
        l.addWidget (self._panel_container)
        l.addWidget (self._diagram, stretch=5)   
        l.setContentsMargins (QMargins(0, 0, 0, 0))

        return l


    def _titletext (self) -> str: 
        """ headertext depending on state """
        if self.case.xo2.state == xo2_state.RUNNING:
            return f"Xoptfoil2 running ..."
        else: 
            return self.name


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

        self.setWindowTitle (self._titletext())



    def _stop_optimize (self):
        """ request thread termination"""
    
        self.case.xo2.stop()

        self.refresh()


    @override
    def refresh (self, disable=None):
        """ overidden to set panel view according to state """

        self._set_buttons ()

        # refresh only the visible widgets 
        w : QWidget
        for w in self.widgets:
            if w.isVisible() or isinstance (w, Edit_Panel):
                w.refresh(disable=disable)

        # and the various Panels 
        for panel in self.findChildren (Edit_Panel):
            panel.refresh()


    @override
    def reject(self): 
        """ close or x-Button pressed"""

        # stop running matcher if x-Button pressed
        if self.case.xo2.isRunning:
            self._stop_optimize()
        
        # tell parent including self
        self.sig_finished.emit () 

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
            # no chnages made - ok is like cancel 
            super().reject() 


class Xo2_Description_Dialog (Dialog):

    """ a small text editor to edit the &info description"""

    _width  = 320
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
    """ Dialog to view / edit a single opPoint definition """

    _width  = (320, None)
    _height = (210, 210)

    name = "OpPoint Deinition"

    sig_finished            = pyqtSignal(object)          # self finished 
    sig_opPoint_def_changed = pyqtSignal()

    # -------------------------------------------------------------------------

    def __init__ (self, parent : QWidget, 
                  case_fn,
                  opPoint_def : OpPoint_Definition,
                  **kwargs): 

        self._opPoint_def = opPoint_def
        self._case_fn = case_fn

        self._show_weighting = False if self.opPoint_def.has_default_weighting else True 
        self._show_polar     = False if self.opPoint_def.has_default_polar     else True 
        self._show_flap      = False if self.opPoint_def.has_default_flap      else True 

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

    @property
    def opPoint_def (self) ->OpPoint_Definition:
        return self._opPoint_def

    def set_opPoint_def (self, opPoint_def : OpPoint_Definition):
        """ slot for new opPoint def"""
        if isinstance (opPoint_def, OpPoint_Definition):
            self._opPoint_def = opPoint_def

            # update local settings 
            self.set_show_weighting (not self.opPoint_def.has_default_weighting) 
            self.set_show_polar     (not self.opPoint_def.has_default_polar) 
            self.set_show_flap      (not self.opPoint_def.has_default_flap) 

            self.refresh()
 
 
    @property
    def case (self) -> Case_Optimize:
        return self._case_fn()

    @property
    def opPoint_defs (self) -> OpPoint_Definitions:
        return self.case.input_file.opPoint_defs

    @property
    def polar_defs_without_default (self) -> list [Polar_Definition]:
        """ current polar definitions without default polar of opPoints"""
        polar_defs = self.opPoint_defs.polar_defs()[:]
        polar_def_default = self.opPoint_defs.polar_def_default
        for polar_def in polar_defs:
            if polar_def.re == polar_def_default.re and polar_def.ma == polar_def_default.ma and \
               polar_def.ncrit == polar_def_default.ncrit:

                polar_defs.remove (polar_def)    
        return polar_defs

    @override
    def _button_box(self):
        return None

    def _init_layout(self) -> QLayout:

        l =  QGridLayout()
        r,c, = 0,0
        ComboBox (l,r,c, lab="Spec", width=90, 
                    get=lambda: self.opPoint_def.specVar, set=self.opPoint_def.set_specVar,
                    options=SPEC_TYPES)
        FieldF   (l,r,c+2, width=70, dec=2, lim=(-20,20), step=0.1,
                    get=lambda: self.opPoint_def.specValue, set=lambda aVal: self.opPoint_def.set_specValue_limited(aVal))
        r += 1
        ComboBox (l,r,c, lab="Type", width=90, 
                    get=lambda: self.opPoint_def.opt_asString, set=self.opPoint_def.set_opt_asString,
                    options=lambda:self.opPoint_def.opt_allowed_asString())
        FieldF   (l,r,c+2, width=70, dec=5, lim=(0.001,0.1), step=0.0001, 
                    obj=lambda: self.opPoint_def, prop=OpPoint_Definition.optValue,
                    hide=lambda: not (self.opPoint_def.isTarget_type and self.opPoint_def.optVar==var.CD))
        FieldF   (l,r,c+2, width=70, dec=2, lim=(0.0,200), step=0.1, 
                    obj=lambda: self.opPoint_def, prop=OpPoint_Definition.optValue,
                    hide=lambda: not (self.opPoint_def.isTarget_type and self.opPoint_def.optVar!=var.CD))
        r += 1
        SpaceR   (l,r, stretch=0)
        r += 1
        CheckBox (l,r,c, text="Individual Weighting", colSpan=2,
                    get=lambda: self.show_weighting, set=self.set_show_weighting)
        FieldF   (l,r,c+2, width=70, step=0.2, lim=(-10,10), dec=2,
                    obj=lambda: self.opPoint_def, prop=OpPoint_Definition.weighting,
                    hide=lambda: not self.show_weighting)
        Label    (l,r,c+3, style=style.COMMENT, 
                    get=lambda: self.opPoint_def.weighting_fixed_label)
        r += 1
        CheckBox (l,r,c, text="Individual Polar", colSpan=2,
                    get=lambda: self.show_polar, set=self.set_show_polar)
        ToolButton (l,r,c+1, icon=Icon.EDIT, align=ALIGN_RIGHT,  set=self.new_polar_def,
                    hide=lambda: not self.show_polar)

        ComboBox (l,r,c+2, colSpan=2, # width=130,
                    get=lambda: self.opPoint_def.polar_def.name if self.opPoint_def.polar_def else None,
                    set=self.set_polar_def_by_name,
                    options=lambda: [polar_def.name for polar_def in self.polar_defs_without_default],
                    hide=lambda: not self.show_polar)

        r += 1
        CheckBox (l,r,c, text="Individual Flap Angle", colSpan=2,
                    get=lambda: self.show_flap, set=self.set_show_flap,
                    disable=lambda: not self.opPoint_defs.use_flap)
        FieldF   (l,r,c+2, width=70, step=0.2, lim=(-15,15), dec=1, unit='°',
                    obj=lambda: self.opPoint_def, prop=OpPoint_Definition.flap_angle,
                    hide=lambda: not self.show_flap)
        r += 1
        CheckBox (l,r,c, text="Flap Optimize", colSpan=2,
                    obj=lambda: self.opPoint_def, prop=OpPoint_Definition.flap_optimize,
                    disable=lambda: not self.opPoint_defs.use_flap)
        r += 1
        l.setRowStretch (r,5)
        l.setColumnMinimumWidth (0,40)
        l.setColumnStretch (3,2)

        return l


    def _titletext (self) -> str: 
        """ headertext depending on state """
        return f"Op Point Definition {self.opPoint_def.iPoint}"


    @override
    def _on_widget_changed (self,*_):
        """ slot for change of widgets"""
        # checkbox show handling                                     
        for w in self.widgets:
            w.refresh()

        # inform parent
        self.sig_opPoint_def_changed.emit()


    # @override
    # def set_background_color (self, **_):
    #     """ do not change background """
    #     if Widget.light_mode:
    #         self.set_background_color (darker_factor = 80)                  # make it lighter 
    #     else: 
    #         self.set_background_color (darker_factor = 110)                 # make it darker

    @property
    def show_weighting (self) -> bool:
        """ show weighting entry field"""
        return self._show_weighting 

    def set_show_weighting (self, aBool : bool):
        self._show_weighting = aBool 
        if not aBool:
            self.opPoint_def.set_weighting (1.0)                    # will set to default 


    @property
    def show_polar (self) -> bool:
        """ show polar entry field"""
        return self._show_polar 

    def set_show_polar (self, aBool : bool):
        self._show_polar = aBool 
        if not aBool:
            # remove individual polar definition
            self.opPoint_def.set_re(None)                    # will set to default 
            self.opPoint_def.set_ma(None)                    
            self.opPoint_def.set_ncrit(None)     
        elif not self.polar_defs_without_default:
            # if there are now other polar defs open dialog directly 
            self.new_polar_def ()             


    def set_polar_def_by_name (self, aStr : str):
        """ for Combobox - set new polar_def by name string """
        for polar_def in self.polar_defs_without_default:
            if polar_def.name == aStr: 
                self.opPoint_def.set_polar_def (polar_def)


    def new_polar_def (self):
        """ create new polar definition"""

        if self.opPoint_def.has_default_polar:
            new_polar_def  = copy (self.opPoint_defs.polar_def_default)
            new_polar_def.set_re (new_polar_def.re + 100000)
            new_polar_def.set_active(True)
        else:
            new_polar_def = self.opPoint_def.polar_def
        
        diag = Polar_Definition_Dialog (self, new_polar_def, small_mode=True, parentPos=(0.9, 0.5), dialogPos=(0, 0.5))
        diag.setWindowTitle (f"Individual Polar of Op Point {self.opPoint_def.iPoint}")
        diag.exec()

        self.opPoint_def.set_polar_def (new_polar_def)
        self.refresh()

        self.sig_opPoint_def_changed.emit()


    @property
    def show_flap (self) -> bool:
        """ show flap entry field"""
        return self._show_flap

    def set_show_flap (self, aBool : bool):
        self._show_flap = aBool 
        if not aBool:
            self.opPoint_def.set_flap_angle (None)                    # will set to default 
            self.opPoint_def.set_flap_optimize (None)                    


    @override
    def refresh (self): 
        """ refresh self"""
        self.setWindowTitle (self._titletext())

        super().refresh() 


    @override
    def closeEvent  (self, event: QCloseEvent ):
        """ window is closed - inform parent """

        self.sig_finished.emit (self)

        event.accept ()



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
                    toolTip="Retry an unconverged Op Point with bl initialization and slightly differen Re number") 
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

    _width  = (260, None)
    _height = (260, None)

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
        SpaceR      (l,r)
        r += 1
        CheckBox    (l,r,c, text="Smooth Seed",
                     obj=lambda: self.hicks_henne_options, prop=Nml_hicks_henne_options.smooth_seed,
                     disable=lambda: self.hicks_henne_options._input_file.airfoil_seed.isBezierBased,
                     toolTip="Create a Bezier based airfoil from seed airfoil prior to optimization")                        
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Label (l,r,c, colSpan=4, style=style.COMMENT,
               get=lambda: f"Will be {self.hicks_henne_options.ndesign_var} design variables")        
        l.setColumnMinimumWidth (0,70)
        l.setColumnStretch (4,2)

        return l



class Xo2_Bezier_Dialog (Xo2_Abstract_Options_Dialog):
    """ Dialog to edit namelist bezier_options"""

    _width  = (260, None)
    _height = (220, None)

    name = "Bezier Options"

    @property
    def bezier_options (self) -> Nml_bezier_options:
        return self.dataObject


    def _init_layout (self) -> QGridLayout:

        l = QGridLayout()
        r,c = 0, 0
        Label (l,r,c, get="Bezier control points on ...", style=style.COMMENT, colSpan=4)
        r += 1
        FieldI (l,r,c, lab='Top side', width=50, step=1, lim=(3,10),
                obj=lambda: self.bezier_options, prop=Nml_bezier_options.ncp_top,
                toolTip="Number of Bezier control points") 
        r += 1
        FieldI (l,r,c, lab='Bottom side', width=50, step=1, lim=(3,10),
                obj=lambda: self.bezier_options, prop=Nml_bezier_options.ncp_bot,
                toolTip="Number of Bezier control points") 
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Label (l,r,c, colSpan=4, style=style.COMMENT,
               get=lambda: f"Will be {self.bezier_options.ndesign_var} design variables")        
        l.setColumnMinimumWidth (0,70)
        l.setColumnStretch (4,2)

        return l


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
                    toolTip="How much will a change of the rdius influence the whole airfoil") 
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Label (l,r,c, colSpan=4, style=style.COMMENT,
               get=lambda: f"Will be {self.camb_thick_options.ndesign_var} design variables")        
        l.setColumnMinimumWidth (0,110)
        l.setColumnStretch (4,2)

        return l



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
