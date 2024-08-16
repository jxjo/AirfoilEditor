#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Match a Bezier curve to a Side of an airfoil 

"""

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

import numpy as np
import time 

from PyQt6.QtCore           import QThread, QDeadlineTimer, Qt
from PyQt6.QtWidgets        import QLayout, QDialogButtonBox

from base.math_util         import nelder_mead, find_closest_index, derivative1
from base.widgets           import * 
from base.panels            import Dialog 
from base.spline            import Bezier 

from model.airfoil_geometry import Side_Airfoil_Bezier, Line


# ----- common methods -----------

class Match_Bezier (Dialog):
    """ Main handler represented as little tool window"""

    _width  = 300
    _height = 300

    name = "Match Bezier"

    sig_new_bezier = pyqtSignal ()
    sig_match_finished = pyqtSignal ()

    def __init__ (self, parent, 
                  side_bezier : Side_Airfoil_Bezier, target_line: Line,
                  target_curv_le : float = None, target_curv_le_weighting : float = None,
                  max_te_curv : float = None): 

        # init matcher thread 

        self._matcher = Match_Thread ()

        self._side_bezier = side_bezier
        self._nevals = 0
        self._norm2 = 0 
        self._matcher.set_match (side_bezier, target_line,
                                target_curv_le, target_curv_le_weighting,
                                max_te_curv)

        self._matcher.finished.connect (self._on_finished)
        self._matcher.sig_new_results [int, float].connect (self._on_results)

        # init layout etc 

        self._cancel_btn : QPushButton = None
        self._close_btn  : QPushButton = None 

        title = f"Match Bezier of {side_bezier.name} side"
        super().__init__ (parent=parent, title=title)

        # enable custom window hint, disable (but not hide) close button
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.CustomizeWindowHint)
        # self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._cancel_btn.clicked.connect (self._cancel_thread)
        self._close_btn.clicked.connect  (self.close)

        # auto start of thread 

        timer = QTimer()   
        # delayed emit to leave scope of init
        timer.singleShot(10, self._matcher.start)

 


    def _on_results (self, nevals, norm2):
        """ slot to receice new results from running thread"""
        self._nevals = nevals
        self._norm2 = norm2 
        self.refresh ()
        self.sig_new_bezier.emit()


    def _on_finished(self):
        """ slot to for thread finished """

        print ("finished")
        self.refresh ()
        self.sig_match_finished.emit()


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0 
        Label (l,r,0, fontSize=size.HEADER, get=self._headertext)
        r += 1
        Field  (l,r,0, lab="Type", width=80, obj= self._side_bezier, prop=Side_Airfoil_Bezier.name, disable=True)
        r += 1
        FieldI (l,r,0, lab="No. Control Points", width=80, obj= self._side_bezier, prop=Side_Airfoil_Bezier.nControlPoints)
        r += 1
        Button (l,r,1, text="Sync", set=self.run_match, width=80)
        r += 1
        SpaceR (l, r, stretch=1) 
        r += 1
        FieldI (l,r,0, lab="Evals", width=80, get=lambda: self._nevals)
        r += 1
        FieldF (l,r,0, lab="Norm2", width=80, dec=8, get=lambda: self._norm2)
 
        l.setColumnStretch (2,1)
        # l.setColumnMinimumWidth (0,80)
        return l

    def _headertext (self) -> str: 

        if self._matcher.isRunning():
            return "Match is running ..."
        else: 
            return "Match finished"


    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Cancel | \
                  QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)

        self._cancel_btn = buttonBox.button(QDialogButtonBox.StandardButton.Cancel)
        self._close_btn  = buttonBox.button(QDialogButtonBox.StandardButton.Close)

        return buttonBox 


    def _cancel_thread (self):
        """ request thread termination"""
    
        print ("cancel clicked")
        self._matcher.requestInterruption()


    def run_match (self): 
        """ start match thread"""
        self._nevals = 0
        self._norm2 = 0 
        self._matcher.start() 


    
# -----------------------------------------------------------------------------
# Match Bezier Thread  
# -----------------------------------------------------------------------------


class Match_Thread (QThread):
    """ 
    Controller for matching a single Side_Airfoil with Bezier

    Optimizes self to best fit to target line
    uses nelder meat root finding

    """

    sig_new_results = pyqtSignal (int, float)

    def __init__ (self, parent = None):
        """ use .set_initial(...) to put data into thread 
        """
        super().__init__(parent)

        self._exiting = False 

        # nelder mead results 
        self._niter      = 0                        # number of iterations needed
        self._nevals     = 0                        # current number of objective function evals

        # match data - see match ()
        # self._side          = None
        # self._isLower       = False 
        # self._bezier        = None

        # self._targets_xy    = None

        # self._target_y_te   = None 
        # self._max_te_curv    = None          

        # self._target_curv_le = None   
        # self._target_curv_le_weighting = None     


    def __del__(self):  
        """ ensure that self stops processing before destroyed"""  
        self._exiting = True
        self.wait()     


    def set_match (self,  side : Side_Airfoil_Bezier, 
                            target_line: Line,
                            target_curv_le : float = None,
                            target_curv_le_weighting : float = 1.0,
                            max_te_curv : float = 10.0):
        """ set initial data for match"""

        self._side    = side 
        self._bezier  = side.bezier
        self._ncp     = self._bezier.npoints
        self._nvar    =  (self._ncp - 2) * 2 - 1    #  number of design variables
        self._isLower = target_line.isLower         # lower side? - dv will be inverted
        self._max_iter = self._nvar * 250           # max number of interations - depending on number of control points

        # selected target points for objective function

        self._target_line  = self._reduce_target_points (target_line)
        self._targets_xy   = self._define_targets(target_line)  
        self._target_y_te = target_line.y[-1]        

        # curvature targets  

        self._target_curv_le = target_curv_le       # also take curvature at le into account
        if target_curv_le_weighting is None: target_curv_le_weighting = 1.0
        self._target_curv_le_weighting = target_curv_le_weighting   
        if max_te_curv is None: max_te_curv = 1.0
        self._max_te_curv    = max_te_curv          # also take curvature at te into account


        # re-arrange initial Bezier as start bezier 
        #    ensure a standard (start) position of control points 

        controlPoints = Side_Airfoil_Bezier.estimated_controlPoints (target_line, self._ncp) 
        self._bezier.set_points (controlPoints)      # a new Bezier curve 
 

    # --------------------


    def run (self) :
        # Note: This is never called directly. It is called by Qt once the
        # thread environment has been set up.s

        self._niter      = 0                        # number of iterations needed
        self._nevals     = 0                        # current number of objective function evals

        #-- map control point x,y to optimization variable 

        variables_start, bounds = self._map_bezier_to_variables ()

        # ----- objective function

        f = lambda variables : self._objectiveFn (variables) 


        # -- initial step size 

        step = 0.16                      # big enough to explore solution space 
                                         #  ... but not too much ... 

        # ----- nelder mead find minimum --------

        res, niter = nelder_mead (f, variables_start,
                    step=step, no_improve_thr=1e-5,             
                    no_improv_break=50, max_iter=self._max_iter,
                    bounds = bounds)

        variables = res[0]

        #-- evaluate the new y values on Bezier for the target x-coordinate

        self._map_variables_to_bezier (variables)

        self._niter      = niter
        self._evals      = 0 

        return 


    # --------------------


    def _reduce_target_points (self, target_line: Line) -> Line:
        """ 
        Returns a new target Line with a reduced number of points 
        to increase speed of deviation evaluation

        The reduction tries to get best points which represent an aifoil side 
        """
        # based on delta x
        # we do not take every coordinate point - define different areas of point intensity 
        x1  = 0.02 # 0.03                               # a le le curvature is master 
        dx1 = 0.04 # 0.025                              # now lower density at nose area
        x2  = 0.25 
        dx2 = 0.04
        x3  = 0.8                                       # no higher density at te
        dx3 = 0.03 # 0.03                               # to handle reflexed or rear loading

        targ_x = []
        targ_y = []
        x = x1
        while x < 1.0: 
            i = find_closest_index (target_line.x, x)
            targ_x.append(float(target_line.x[i]))
            targ_y.append(float(target_line.y[i]))
            if x > x3:
                x += dx3
            elif x > x2:                             
                x += dx2
            else: 
                x += dx1

        return Line(targ_x, targ_y)




    def _define_targets (self, target_side: Line) -> list[tuple]:
        """ 
        returns target points xy where deviation is evaluated during optimization 
        """
        # based on delta x
        # we do not take every coordinate point - define different areas of point intensity 
        x1  = 0.02 # 0.03                               # a le le curvature is master 
        dx1 = 0.04 # 0.025                              # now lower density at nose area
        x2  = 0.25 
        dx2 = 0.04
        x3  = 0.8                                       # no higher density at te
        dx3 = 0.03 # 0.03                               # to handle reflexed or rear loading

        targ_x = []
        targ_y = []
        x = x1
        while x < 1.0: 
            i = find_closest_index (target_side.x, x)
            targ_x.append(target_side.x[i])
            targ_y.append(target_side.y[i])
            if x > x3:
                x += dx3
            elif x > x2:                             
                x += dx2
            else: 
                x += dx1

        return list(zip(np.array(targ_x), np.array(targ_y)))


    def _map_bezier_to_variables (self): 
        """ 
        Maps bezier control points to design variables of objective function

        Returns: 
            list of design variables  
            bounds: list of bound tuples of variables """

        vars   = [None] * self._nvar
        bounds = [None] * self._nvar
        cp_x, cp_y = self._bezier.points_x, self._bezier.points_y
        ncp = self._bezier.npoints

        ivar = 0
        for icp in range (ncp): 
            if icp == 0: 
                pass                                    # skip leading edge
            elif icp == ncp-1:                      
                pass                                    # skip trailing edge
            elif icp == 1: 
                if self._isLower:
                    y = -cp_y[icp]             # - >pos. solution space
                else:
                    y = cp_y[icp] 
                vars[ivar] = y                
                ivar += 1                  
            else:                                       
                vars[ivar] = cp_x[icp]                  # x value of control point
                bounds[ivar] = (0.01, 0.95)             # right bound not too close to TE
                ivar += 1                               #    to avoid curvature peaks 
                if self._isLower:
                    y = -cp_y[icp]             # - >pos. solution space
                else:
                    y = cp_y[icp]   
                vars[ivar] = y           
                ivar += 1                  
        return vars, bounds 


    def _map_variables_to_bezier (self, vars: list): 
        """ maps design variables to bezier (control points)"""

        cp_x, cp_y = self._bezier.points_x, self._bezier.points_y
        ncp = self._bezier.npoints
        ivar = 0
        for icp in range (ncp): 
            if icp == 0: 
                pass                                    # skip leading edge
            elif icp == ncp-1:                      
                pass                                    # skip trailing edge
            elif icp == 1:    
                if self._isLower:
                    y = - vars[ivar]            # solution space was y inverted 
                else:
                    y = vars[ivar] 
                cp_y[icp] = y       
                ivar += 1                  
            else:                                       
                cp_x[icp] = vars[ivar]
                ivar += 1                  
                if self._isLower:
                    y = - vars[ivar]            # solution space was y inverted 
                else:
                    y = vars[ivar] 
                cp_y[icp] = y               
                ivar += 1                  
        self._bezier.set_points (cp_x, cp_y)



    def _objectiveFn (self, variables : list ):  
        """ returns norm2 value of y deviations of self to target y at x """
        
        # is termination requested?
        if self.isInterruptionRequested(): 
            # todo callback in nelder_mead to get stop flag 
            print ("requested")
          

        # rebuild Bezier 

        self._map_variables_to_bezier (variables)
        # print (' '.join(f'{p:8.4f}' for p in self._bezier.points_y))   
          
        # norm2 of deviations to target
        norm2 = self._side.norm2_deviation_to (self._target_line)
        obj_norm2 = norm2 * 1000                                # 1.0   is ok, 0.2 is good 

        # difference to target le curvature 

        obj_le = 0.0 
        diff = 0 
        if self._target_curv_le:
            target  = abs(self._target_curv_le)
            current = abs(self._bezier.curvature(0.0))
            diff = abs(target - current)                        # 1% is like 1 
        obj_le = (diff  / 40) * self._target_curv_le_weighting  # apply optional weighting      

        # limit max te curvature 

        obj_te = 0  
        if self._isLower:                                       # ! curvature on bezier side_upper is negative !
            cur_curv_te   =  self._bezier.curvature(1.0)
        else:
            cur_curv_te   = -self._bezier.curvature(1.0)

        # current should be between 0.0 and target te curvature 
        if self._max_te_curv >= 0.0: 
            if cur_curv_te >= 0.0: 
                delta = cur_curv_te - self._max_te_curv
            else:
                delta = - cur_curv_te * 3.0                 # te curvature shouldn't result in reversal
        else: 
            if cur_curv_te < 0.0:  
                delta = - (cur_curv_te - self._max_te_curv)
            else:
                delta = cur_curv_te * 3.0                   # te curvature shouldn't result in reversal
        if delta > 0.1:                                     # delta < 0.3 is ok,  0
            obj_te = delta - 0.1   

        # calculate derivative of curvature for detection of curvature artefacts 

        u = np.concatenate ((np.linspace (0.2, 0.95, 15, endpoint=False),
                             np.linspace (0.95, 1.0, 10)))          # higher density at te     
        x,_    = self._bezier.eval(u)
        curv   = self._bezier.curvature(u)
        deriv1 = derivative1 (x, curv)

        # derivative of curvature at te 
    	    # try to avoid that curvature slips away at TE when control point 
            # is getting closer to TE 

        obj_te_deriv = 0 

        max_curv_deriv_te = np.max (abs(deriv1[-10:]))              # check the last 10 points                   
        lim_curv_deriv_te = 10 * (abs(self._max_te_curv) if self._max_te_curv else 0.1)
        lim_curv_deriv_te = max (lim_curv_deriv_te, 1)             # derivative limit depending on curv at te

        if max_curv_deriv_te > lim_curv_deriv_te: 
            obj_te_deriv = (max_curv_deriv_te - lim_curv_deriv_te) / 20  # 0 is good, > 0 ..50 is bad 

        # penalty for reversals in derivative of curvature - avoid bumps 

        obj_revers = 0 
        nrevers = 0 
        yold    = deriv1[0]
        for i in range(len(x)):
            if abs(deriv1[i]) >= 0.02:                              #  threshold for reversal detetction
                if (deriv1[i] * yold < 0.0):                        # yes - changed + - 
                    nrevers += 1                             
                yold = deriv1[i]
        obj_revers = nrevers ** 2 * 0.4                             #  2+ reversals are really bad


        # objective function is sum of single objectives 

        # take norm2 of deviation an le curvature to get balanced result 
        obj = np.linalg.norm ([obj_norm2, obj_le]) + obj_te + obj_revers + obj_te_deriv

        # counter of objective evaluations (for entertainment)
        self._nevals += 1

        if self._nevals%100 == 0:           
            logger.debug (f"{self._nevals:4} " +
                           f" obj:{obj:5.2f}   norm2:{obj_norm2:5.2f}" +
                           f"  le:{obj_le:5.2f}   te:{obj_te:4.1f}" +
                           f"  rev:{obj_revers:4.1f}  te_der:{obj_te_deriv:4.1f}")

        if self._nevals%20 == 0:  
            # print ("emit", self._nevals)         
            self.sig_new_results.emit (self._nevals, norm2)

            self.msleep(10)                      # give parent some time to do updates

        return obj 

