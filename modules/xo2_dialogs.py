#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

Extra functions (dialogs) to optimize airfoil  

"""

from copy                   import copy 
from shutil                 import copyfile

import pyqtgraph as pg

from PyQt6.QtWidgets        import QLayout, QDialogButtonBox, QPushButton, QDialogButtonBox
from PyQt6.QtWidgets        import QWidget, QTextEdit, QDialog
from PyQt6.QtGui            import QFontMetrics, QCloseEvent

from base.widgets           import * 
from base.panels            import Dialog, Edit_Panel, MessageBox, Container_Panel
from base.diagram           import Diagram, Diagram_Item
from base.artist            import Artist

from airfoil_dialogs        import Polar_Definition_Dialog
from model.airfoil          import Airfoil
from model.polar_set        import Polar_Definition
from model.case             import Case_Optimize
from model.xo2_controller   import xo2_state, Xo2_Controller
from model.xo2_results      import Xo2_Results
from model.xo2_input        import Input_File, OpPoint_Definition, OpPoint_Definitions
from model.xo2_input        import SPEC_TYPES, SPEC_ALLOWED, OPT_ALLOWED, var
from xo2_artists            import Xo2_Design_Radius_Artist, Xo2_Improvement_Artist

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)



class Xo2_Choose_Optimize_Dialog (Dialog):
    """ Dialog to choose what should be done"""

    _width  = (300, None)
    _height = (500, None)

    name = "What You want to optimize"

    def __init__ (self, parent, input_fileName : str,  current_airfoil : Airfoil, **kwargs): 

        self._input_fileName  = input_fileName
        self._current_airfoil = current_airfoil
        self._workingDir      = None 

        # is there an existung input file for airfoil

        if self._input_fileName is None and self._current_airfoil is not None:
            self._input_fileName = Case_Optimize.input_fileName_of (self._current_airfoil)
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
        Label    (l,r,c, height=70, colSpan=3, style=style.COMMENT,
                  get= "Airfoil optimization is based on <b>Xoptfoil2</b>, which will run in the background.<br>" +
                       "Xoptfoil2 is controlled via the input file, whoose paramters you may edit subsequently.<br>"
                       "The input file equals to an optimization Case in the AirfoilEditor.")
        r += 1
        Button   (l,r,c, width=100, text="Open Case", set=self.open_case,
                  hide=lambda: self.input_fileName is None)
        Label    (l,r,c+2, height=50, 
                  get=lambda: f"Open input file <b>{self.input_fileName}</b> of airfoil {self.current_airfoil.fileName}" + 
                              f"<br>change options and run optimization",
                  hide=lambda: self.input_fileName is None and self.current_airfoil is None )
        # r +=1
        # SpaceR   (l,r,stretch=0)
        r += 1
        Button   (l,r,c, width=100, text="New Version", set=self.new_version,
                  hide=lambda: self.input_fileName is None)
        Label    (l,r,c+2,  height=50, 
                  get=lambda: f"Create new Version of input file <b>{self.input_fileName}</b>,<br>open it, change options and run optimization",
                  hide=lambda: self.input_fileName is None)
        
        r += 1
        l.setRowStretch (r,2)
        l.setColumnMinimumWidth (1,20)
        l.setColumnStretch (2,2)

        return l 


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""
        buttonBox = QDialogButtonBox ( QDialogButtonBox.StandardButton.Cancel)

        buttonBox.rejected.connect  (self.close)

        return buttonBox 


    def open_case (self): 
        """ open existing case self.input_file"""
        self.accept ()


    def new_version (self): 
        """ create new version of an existing case self.input_file"""

        new_fileName = Case_Optimize.new_input_fileName_version (self.input_fileName, self.workingDir)

        if new_fileName:
            copyfile (os.path.join (self.workingDir,self.input_fileName), os.path.join (self.workingDir,new_fileName))
            self._input_fileName = new_fileName
            self.accept ()
        else: 
            MessageBox.error   (self,'Create new version', f"New Version of {self.input_fileName} could not be created.",
                                min_width=350)



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


    # --------------------------------------------------------


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

        if self.case.xo2.isReady:

            self._last_improvement = 0.0
            self._improved = False 

            self.case.run()

            self._set_buttons ()              # after to get running state 


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

    _width  = (300, None)
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

        ComboBox (l,r,c+2, width=130, 
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
        l.setColumnStretch (5,2)

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
            self.opPoint_def.set_re(None)                    # will set to default 
            self.opPoint_def.set_ma(None)                    
            self.opPoint_def.set_ncrit(None)                    

    def set_polar_def_by_name (self, aStr : str):
        """ for Combox - set new polar_def by name string """
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
        
        diag = Polar_Definition_Dialog (self, new_polar_def, parentPos=(0,0.5), dialogPos=(1,0.5))
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



