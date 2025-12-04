#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Xoptfoil2 controler for run state  

"""
import os

from enum                   import StrEnum
from datetime               import datetime

from .xo2_driver            import Xoptfoil2

#-------------------------------------------------------------------------------
# enums   
#-------------------------------------------------------------------------------

class StrEnum_Extended (StrEnum):
    """ enum extension to get a list of all enum values"""
    @classmethod
    def values (cls):
        return [c.value for c in cls]


class xo2_state (StrEnum_Extended):
    """ xoptfoil2 run states """

    RUNNING     = 'running'
    RUN_ERROR   = 'run error'
    READY       = 'ready'
    NOT_READY   = 'not_ready'
    STOPPING    = 'waiting for stop'


#-------------------------------------------------------------------------------
# Model   
#-------------------------------------------------------------------------------

class Xo2_Controller:
    """ 
    Proxy to Xoptfoil2, manage results of a optimization run     
    """

    def __init__(self, workingDir: str):
        """
        """
        self._workingDir = workingDir               # working dir of optimizer
        self._xoptfoil   = None                     # proxy of Xoptfoil2

        self._isStop_requested    = False           # is there request to stop
        self._time_started        = None            # started date time  

        self._nSteps     = 0                        # no of steps up to now when running
        self._nDesigns   = 0                        # no of designs up to now when running
        self._objective  = 1.0                      # objective function when running

        self._state = None                         # lazy state 


    # ---- Properties -------------------------------------------


    @property
    def workingDir (self): 
        """ working dir of optimizer - absolut"""
        return self._workingDir
    
    @property
    def xoptfoil2 (self) -> Xoptfoil2: 
        """ Xoptfoil2 proxy object"""
        if self._xoptfoil is None: 
            self._xoptfoil = Xoptfoil2(self.workingDir)
        return self._xoptfoil


    @property 
    def isRunning (self) -> bool:
        """ is Xoptfoil running"""
        running = self.xoptfoil2.isRunning()
        return running 


    @property 
    def isReady (self) -> bool:
        """ is Xoptfoil2 ready for optimization"""
        return self.state == xo2_state.READY and Xoptfoil2.ready


    @property
    def isRun_failed (self) -> bool: 
        """ true if a run failed"""
        return not self.run_errortext is None

    @property
    def run_errortext (self): 
        """ errortext from Xoptfoil when run ended """
        return self.xoptfoil2.finished_errortext

    @property 
    def isStop_requested (self) -> bool:
        """ is there a pending request to stop Xoptfoil"""
        if self._isStop_requested and not self.isRunning:
            self._isStop_requested = False
        return self._isStop_requested

    @property 
    def state (self) -> xo2_state:
        """ returns the run state of Xoptfoil of last state evaluation 
            either: RUNNING, READY, NOT_READY, STOPPING  """     

     
        if self.isStop_requested:
            state = xo2_state.STOPPING
        elif self.isRunning:
            state = xo2_state.RUNNING
        elif self.isRun_failed:
            state = xo2_state.RUN_ERROR
        elif not self.xoptfoil2.ready:
            state = xo2_state.NOT_READY
        else:
            state = xo2_state.READY

        self._state = state 

        return self._state


    def refresh_progress (self) -> bool:
        """ refresh progress data from Xoptfoil2. Returns True if there is a change in progress"""

        if self.isRunning:
            new_nSteps, new_nDesigns, new_objective = self.xoptfoil2.get_progress()
            if new_nSteps != self._nSteps or new_nDesigns != self._nDesigns or new_objective != self._objective:
                self._nSteps    = new_nSteps
                self._nDesigns  = new_nDesigns
                self._objective = new_objective
                return True
        else: 
            self._nSteps = 0                             # no of steps up to now when running
            self._nDesigns = 0                           # no of designs up to now when running
            self._objective = 1.0                        # objective function when running
        return False


    @property 
    def time_started (self) -> datetime:
        """ returns dateTime when Xoptfoil2 started"""

        if self._time_started is None:                          # in case already running optimizer 
           self._time_started = datetime.now()
        return self._time_started
    

    def time_running (self) -> str:
        """ returns hours, minutes, seconds how long self is (or was) running as string hh:mm:ss"""

        if not self.isRunning: return ""

        delta = datetime.now() - self.time_started
        hours, remainder = divmod(delta.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{int(hours)}:{int(minutes)}:{int(seconds):02d}"
        else: 
            return f"{int(minutes)}:{int(seconds):02d}"


    @property
    def nDesigns (self) -> int:
        """ no of designs while running""" 
        return self._nDesigns 


    @property
    def nSteps (self) -> int:
        """ no of steps while running """ 
        return self._nSteps 


    @property 
    def improvement (self) -> float:
        """ improvement in fraction of 1.0 reached up to now while running - else 0.0 """
        
        return 1.0 - self._objective
    

    def run (self, outName, input_file : str) -> int:
        """ 
        start a new optimization run - returns rc 
        """

        rc = self.xoptfoil2.run (outName, input_file=input_file)

        if rc == 0: 
            self._state = None                      # will re-eval state 
            self._time_started = datetime.now()

        return rc 


    def stop (self):
        """ stop optimization run """

        self._isStop_requested = True
        self.xoptfoil2.stop()
