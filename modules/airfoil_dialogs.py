#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Extra functions (dialogs) to modify airfoil  

"""

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

import numpy as np
import time 

from PyQt6.QtCore           import QThread, QDeadlineTimer, Qt
from PyQt6.QtWidgets        import QLayout, QDialogButtonBox, QPushButton, QDialogButtonBox

from base.math_util         import nelder_mead, find_closest_index, derivative1
from base.widgets           import * 
from base.panels            import Dialog 
from base.spline            import Bezier 

from model.airfoil          import Airfoil
from model.airfoil_geometry import Side_Airfoil_Bezier, Line
from model.airfoil_geometry import Geometry_Splined, Panelling_Spline
from airfoil_widgets        import Airfoil_Select_Open_Widget



# ----- Blend two airfoils   -----------

class Blend (Dialog):
    """ Dialog to two airfoils into a new one"""

    _width  = 550
    _height = 240

    name = "Repanel Airfoil"

    sig_airfoil_changed    = pyqtSignal ()
    sig_airfoil2_changed   = pyqtSignal (Airfoil)

    # ---- static members for external use 


    def __init__ (self, parent : QWidget, 
                  airfoil1 : Airfoil,
                  airfoil2 : Airfoil = None): 

        self._airfoil1 = airfoil1
        self._airfoil2 = airfoil2
        self._blendby  = 0.5                            # initial blend value 

        # init layout etc 

        super().__init__ (parent=parent)

        # enable custom window hint, disable (but not hide) close button
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        # move window a little to the side 
        p_center = parent.rect().center()               # parent should be main window
        pos_x = p_center.x() + 200
        pos_y = p_center.y() + 250            
        self.move(pos_x, pos_y)


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0 
        SpaceR (l, r, stretch=0, height=5) 
        r += 1
        Label  (l,r,0, colSpan=5, get="Select airfoil to blend with and adjust blending value")
        r += 1
        SpaceR (l, r, stretch=0, height=10) 
        r += 1 
        Field  (l,r,1, get=self._airfoil1.name, width = 120)
        SpaceC (l,2,stretch=0)
        Slider (l,r,3, width=120, lim=(0,1), get=lambda: self._blendby,
                       set=self._set_blendBy)
        FieldF (l,r,4, width=60,  lim=(0, 1),get=lambda: self._blendby, step=0.1,
                       set=self._set_blendBy)
        SpaceC (l,5, stretch=0)
        Airfoil_Select_Open_Widget (l,r,6, withOpen=True, asSpin=False, signal=True, width=140, 
                                    get=lambda: self._airfoil2, set=self._set_airfoil2)

        SpaceC (l,7, width=5)
        r += 1
        SpaceR (l, r, height=5) 

        return l

    def _set_blendBy (self, aVal : float):
        """ set new value - do strak - signal change"""
        self._blendby = aVal
        self.refresh()


    def _set_airfoil2 (self, aAirfoil : Airfoil):
        """ set new 2nd airfoil - do strak - signal change"""
        self._airfoil2 = aAirfoil
        self.refresh()

        self.sig_airfoil2_changed.emit (aAirfoil)


    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.rejected.connect(self.close)

        return buttonBox 



# ----- repanel dialog helper window  -----------


class Repanel (Dialog):
    """ Dialog to repanel an airfoil"""

    _width  = 460
    _height = 240

    name = "Repanel Airfoil"

    sig_new_panelling    = pyqtSignal ()

    # ---- static members for external use 


    def __init__ (self, parent : QWidget, 
                  geo : Geometry_Splined): 

        self._geo = geo

        # init layout etc 

        super().__init__ (parent=parent)

        # enable custom window hint, disable (but not hide) close button
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        # move window a little to the side 
        p_center = parent.rect().center()               # parent should be main window
        pos_x = p_center.x() + 400
        pos_y = p_center.y() + 250            
        self.move(pos_x, pos_y)


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0 
        SpaceR (l, r, stretch=0, height=5) 
        r += 1
        Label  (l,r,0, colSpan=5, get="Adjust No of Panels and the extra density at leading and trailing edge")
        r += 1
        SpaceR (l, r, stretch=0, height=10) 
        r += 1 
        Label  (l,r,1, get="Panels", align=Qt.AlignmentFlag.AlignRight)
        FieldI (l,r,2, width=60, step=10, lim=(40, 400),
                        obj=self._geo.panelling, prop=Panelling_Spline.nPanels,
                        style=self._le_bunch_style)
        r += 1 
        Slider (l,r,1, colSpan=3, width=150, align=Qt.AlignmentFlag.AlignHCenter,
                        lim=(40, 400), dec=0, # step=10,
                        obj=self._geo.panelling, prop=Panelling_Spline.nPanels)
        # r += 1
        Label  (l,r,0, get="LE bunch")
        Label  (l,r,4, get="TE bunch")

        r += 1
        FieldF (l,r,0, width=60, step=0.02, lim=(0, 1),
                        obj=self._geo.panelling, prop=Panelling_Spline.le_bunch,
                        style=self._le_bunch_style)
        Slider (l,r,1, width=100, lim=(0, 1),
                        obj=self._geo.panelling, prop=Panelling_Spline.le_bunch)

        Slider (l,r,3, width=100, lim=(0, 1),
                        obj=self._geo.panelling, prop=Panelling_Spline.te_bunch)
        FieldF (l,r,4, width=60, step=0.02, lim=(0, 1),
                        obj=self._geo.panelling, prop=Panelling_Spline.te_bunch)
        r += 1
        Label  (l,r,0, colSpan=4, get=self._le_bunch_message, style=style.COMMENT)        
        SpaceC (l,5, width=5)
        r += 1
        SpaceR (l, r, height=5) 

        return l

    def _le_bunch_message (self): 
        angle = self._geo.panelAngle_le
        if angle > 175.0: 
            text = "Panel angle at LE is too blunt. Decrease panels or LE bunch" 
        elif angle < 150.0: 
            text = "Panel angle at LE is too sharp. Increase panels or LE bunch"
        else:
            text = ""
        return text 
    

    def _le_bunch_style (self): 
        angle = self._geo.panelAngle_le
        if angle > 175.0 or angle < 150.0: 
            return style.WARNING
        else: 
            return style.NORMAL


    @override
    def _on_widget_changed (self):
        """ slot a input field changed - repanel and refresh"""

        self.refresh()
        self._geo._repanel ()

        self.sig_new_panelling.emit()               # inform parent -> diagram update

    @override
    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.rejected.connect(self.close)

        return buttonBox 


# ----- Match a Bezier curve to a Side of an airfoil  -----------

class Match_Bezier (Dialog):
    """ Main handler represented as little tool window"""

    _width  = 350
    _height = 270

    name = "Match Bezier"

    sig_new_bezier = pyqtSignal (Line.Type)
    sig_match_finished = pyqtSignal (Side_Airfoil_Bezier)

    # ---- static members for external use 

    @staticmethod
    def style_deviation (norm2 : float) -> style:
        """ returns color style depending of deviation"""
        if norm2 < 0.001:
            st = style.GOOD
        elif norm2 < 0.005:
            st = style.NORMAL
        else:
            st = style.WARNING
        return st 

    @staticmethod
    def style_curv_le (target_curv_le: float, aCurv: Line | float) -> style:
        """ returns color style depending if curvature at LE is too different from target"""
        if isinstance (aCurv, float):
            delta = abs(target_curv_le - abs(aCurv))
        else: 
            delta = abs(target_curv_le - abs(aCurv.y[0]))
        if delta > 10: 
            return style.WARNING
        elif delta > 2: 
            return style.NORMAL
        else: 
            return style.GOOD

    @staticmethod
    def style_curv_te (aCurv: Line | float)  -> style:
        """ returns color style depending if curvature at TE is to high"""
        if isinstance (aCurv, float):
            curv_te = abs(aCurv)
        else: 
            curv_te = abs(aCurv.y[-1])
        if curv_te > 10: 
            return style.WARNING
        elif curv_te > 0.5: 
            return style.NORMAL
        else: 
            return style.GOOD




    def __init__ (self, parent : QWidget, 
                  side_bezier : Side_Airfoil_Bezier, target_line: Line,
                  target_curv_le : float,
                  max_curv_te : float): 

        self._side_bezier = side_bezier
        self._target_line = target_line
        self._curv_le = abs(side_bezier.curvature.max_xy[1]) 
        self._curv_te = side_bezier.curvature.te[1] 

        self._target_curv_le = target_curv_le
        self._target_curv_le_weighting = 1
        self._max_curv_te = max_curv_te

        self._norm2 = Matcher.norm2_deviation_to (side_bezier.bezier, target_line) 
        self._nevals = 0

        # init matcher thread 

        self._matcher = Matcher ()
        self._matcher.finished.connect (self._on_finished)
        self._matcher.sig_new_results [int, float, float, float].connect (self._on_results)

        # init layout etc 

        self._stop_btn : QPushButton = None
        self._close_btn  : QPushButton = None 
        self._match_btn  : QPushButton = None 

        super().__init__ (parent=parent)

        # enable custom window hint, disable (but not hide) close button
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setWindowTitle (self._titletext())

        # move window a little to the side 
        p_center = parent.rect().center()               # parent should be main window
        pos_x = p_center.x() + 600
        pos_y = p_center.y() + 200            
        self.move(pos_x, pos_y)

        # handle button (signals) 
        self._stop_btn.clicked.connect (self._cancel_thread)
        self._close_btn.clicked.connect  (self.close)
        self._match_btn.clicked.connect  (self._start_matcher)

        self._stop_btn.setVisible (False) 
        self._close_btn.setVisible (True) 

        # save current background color for state dependand backgrounds
        self._palette_normal = self._panel.palette()


    def _start_matcher (self): 
        """ start matcher thread"""

        self._nevals = 0
        self._norm2 = 0 

        self._panel.setDisabled (True)
        self.set_background_color (color='lightskyblue', alpha=0.3)        

        self._matcher.set_match (self._side_bezier, self._target_line,
                                self._target_curv_le, self._target_curv_le_weighting,
                                self._max_curv_te)
        self._matcher.start()

        self._set_button_visibility ()              # after to get running state 
        self.setWindowTitle (self._titletext())


    def _on_results (self, nevals, norm2, curv_le, curv_te):
        """ slot to receice new results from running thread"""

        self._nevals = nevals
        self._norm2 = norm2         # self._side_bezier.norm2_deviation_to (self._target_line)  
        self._curv_le = curv_le     # abs(self._side_bezier.curvature.max_xy[1]) 
        self._curv_te = curv_te     # self._side_bezier.curvature.te[1] 
        self.refresh ()
        self.setWindowTitle (self._titletext())

        self.sig_new_bezier.emit (self._side_bezier.type)


    def _on_finished(self):
        """ slot for thread finished """

        self._set_button_visibility ()

        # restore old background color 
        self._panel.setPalette(self._palette_normal)
        self.set_background_color (color=None)    
        self._panel.setDisabled (False)
        self.setWindowTitle (self._titletext())

        self.refresh ()

        self.sig_match_finished.emit(self._side_bezier)


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0
        # SpaceR (l, r, stretch=0, height=5) 
        # r += 1 
        # Label (l,r,c, colSpan=6, fontSize=size.HEADER, get=self._headertext)
        # r += 1
        Label  (l,r,0, colSpan=5, height=40, get="Run an optimization for a best fit of the Bezier curve."+
                                      "\nUse 'Weight' to balance deviation and LE curvature.")
        r += 1
        SpaceR (l, r, stretch=0, height=5) 
        r += 1
        Label  (l,r,1, get="Deviation")
        SpaceC (l,2, width=15)
        Label  (l,r,3, get="LE   curvature   TE", colSpan=2)
        SpaceC (l,5, width=5, stretch=2)

        r += 1
        Label  (l,r,0, get="Target side")
        FieldF (l,r,3, width=50,  dec=0, step=10.0, lim=(10, 1000),
                        get=lambda: self._target_curv_le, set=self.set_target_curv_le )
        FieldF (l,r,4, width=50,  dec=1, step=0.1, lim=(-9.9, 9.9),
                        get=lambda: self._max_curv_te, set=self.set_max_curv_te )

        r += 1
        Label  (l,r,0, get="Weight")
        FieldF (l,r,3, width=50,  dec=1, step=0.5, lim=(0.1,10),
                        get=lambda: self._target_curv_le_weighting, set=self.set_target_curv_le_weighting )

        r += 1
        Label  (l,r,0, get=f"{self._side_bezier.name} side", width=80)
        FieldF (l,r,1, width=60, dec=3, unit='%', get=lambda: self._norm2, 
                       style=lambda: Match_Bezier.style_deviation (self._norm2 ))
        FieldF (l,r,3, width=50, dec=0, get=lambda: self._curv_le,
                       style=lambda: Match_Bezier.style_curv_le(self._target_curv_le, self._curv_le))
        FieldF (l,r,4, width=50, dec=1, get=lambda: self._curv_te,
                       style=lambda: Match_Bezier.style_curv_te(self._curv_te))
        r += 1
        SpaceR (l, r) 

        return l


    def set_target_curv_le (self, aVal : float):
        self._target_curv_le = aVal

    def set_target_curv_le_weighting (self, aVal : float):
        self._target_curv_le_weighting = aVal

    def set_max_curv_te (self, aVal : float):
        self._max_curv_te = aVal


    def _titletext (self) -> str: 
        """ headertext dpending on state """
        if self._matcher.isRunning():
            return f"Match running ... Iterations: {self._nevals}"
        elif self._matcher.isFinished():
            return f"Match {self._side_bezier.name} side finished"
        else: 
            return f"Match {self._side_bezier.name} side"


    def _button_box (self):
        """ returns the QButtonBox with the buttons of self"""

        buttons = QDialogButtonBox.StandardButton.Close
        buttonBox = QDialogButtonBox(buttons)

        self._close_btn  = buttonBox.button(QDialogButtonBox.StandardButton.Close)

        self._stop_btn = QPushButton ("Stop", parent=self)
        self._stop_btn.setFixedWidth (100)

        self._match_btn = QPushButton ("Match Target", parent=self)
        self._match_btn.setFixedWidth (100)

        buttonBox.addButton (self._match_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttonBox.addButton (self._stop_btn, QDialogButtonBox.ButtonRole.RejectRole)

        return buttonBox 


    def _set_button_visibility (self):
        """ depending on matcher state, set button visibility """

        if self._matcher.isRunning():
            self._stop_btn.setVisible (True) 
            self._match_btn.setVisible (False) 
            self._close_btn.setVisible (False) 
            self._stop_btn.setFocus ()
        else: 
            self._stop_btn.setVisible (False) 
            self._match_btn.setVisible (True) 
            self._close_btn.setVisible (True) 
            self._match_btn.setFocus ()

    def _cancel_thread (self):
        """ request thread termination"""
    
        self._matcher.requestInterruption()


    
# -----------------------------------------------------------------------------
# Match Bezier Thread  
# -----------------------------------------------------------------------------


class Matcher (QThread):
    """ 
    Worker Thread for matching a single Side_Airfoil with Bezier

    Optimizes self to best fit to target line
    uses nelder meat root finding

    """

    sig_new_results = pyqtSignal (int, float, float, float)


    # ------ static methods also for external use 

    @staticmethod
    def _reduce_target_points (target_line: Line) -> Line:
        """ 
        Returns a new target Line with a reduced number of points 
        to increase speed of deviation evaluation

        The reduction tries to get best points which represent an aifoil side 
        """
        # based on delta x
        # we do not take every coordinate point - define different areas of point intensity 
        x1  = 0.02 # 0.03                               # a le le curvature is master 
        dx1 = 0.020 # 0.025                              # now lower density at nose area
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


    @staticmethod
    def norm2_deviation_to (bezier : Bezier, target_line : 'Line', isReduced=False)  -> float:
        """returns norm2 deviation of self to a target_line"""

        if not isinstance (target_line, Line): return 0.0 

        # reduce no of coordinates to speed up evaluation 
        if not isReduced:
            reduced_target = Matcher._reduce_target_points (target_line)
        else: 
            reduced_target = target_line 

        # evaluate the new y values on Bezier for the target x-coordinate   
        y_new = np.zeros (len(reduced_target.y))
        for i, x in enumerate(reduced_target.x) :
            y_new[i] = bezier.eval_y_on_x (x, fast=True, epsilon=1e-7)

        # calculate abs difference between bezier y and target y
        devi = np.abs((y_new - reduced_target.y))
        return np.linalg.norm (devi)

    # ------------------

    def __init__ (self, parent = None):
        """ use .set_initial(...) to put data into thread 
        """
        super().__init__(parent)

        self._exiting = False 

        # nelder mead results 
        self._niter      = 0                        # number of iterations needed
        self._nevals     = 0                        # current number of objective function evals


    def __del__(self):  
        """ ensure that self stops processing before destroyed"""  
        self._exiting = True
        self.wait()     


    def set_match (self,  side : Side_Airfoil_Bezier, 
                            target_line: Line,
                            target_curv_le : float = None,
                            target_curv_le_weighting : float = 1.0,
                            max_curv_te : float = 10.0):
        """ set initial data for match"""

        self._side    = side 
        self._bezier  = side.bezier
        self._ncp     = self._bezier.npoints
        self._nvar    =  (self._ncp - 2) * 2 - 1    #  number of design variables
        self._isLower = target_line.isLower         # lower side? - dv will be inverted
        self._max_iter = self._nvar * 250           # max number of interations - depending on number of control points

        # selected target points for objective function

        self._target_line  = Matcher._reduce_target_points (target_line)
        self._target_y_te = target_line.y[-1]        

        # curvature targets  

        self._target_curv_le = target_curv_le       # also take curvature at le into account
        if target_curv_le_weighting is None: target_curv_le_weighting = 1.0
        self._target_curv_le_weighting = target_curv_le_weighting   
        if max_curv_te is None: max_curv_te = 1.0
        self._max_curv_te    = max_curv_te          # also take curvature at te into account


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
                    bounds = bounds,
                    stop_callback=self.isInterruptionRequested)     # Qthread method 

        variables = res[0]

        #-- evaluate the new y values on Bezier for the target x-coordinate

        self._map_variables_to_bezier (variables)

        self._niter      = niter
        self._evals      = 0 

        return 


    # --------------------



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
        
        # rebuild Bezier 

        self._map_variables_to_bezier (variables)
        # print (' '.join(f'{p:8.4f}' for p in self._bezier.points_y))   
          
        # norm2 of deviations to target
        norm2 = Matcher.norm2_deviation_to (self._bezier, self._target_line, isReduced=True)
        obj_norm2 = norm2 * 1000                                # 1.0   is ok, 0.2 is good 

        # --- LE curvature 

        curv_le = abs(self._bezier.curvature(0.0)) 
         
        # highpoint of curvature muste be at LE

        obj_le_hp = 0.0 
        curv_after_le = abs(self._bezier.curvature(0.005)) 
        if (curv_le - curv_after_le) < 0: 
            # print ("ohooo", self._nevals, curv_le, curv_after_le)
            obj_le_hp = abs( (curv_le - curv_after_le))  / 4

        # difference to target le curvature 

        obj_le = 0.0 
        diff = 0 
        if self._target_curv_le:
            target  = abs(self._target_curv_le)
            diff = abs(target - curv_le)                         # 1% is like 1 
        obj_le += (diff / 80) * self._target_curv_le_weighting  # #40 apply optional weighting      

        # --- TE curvature 
        # limit max te curvature 

        obj_te = 0  
        if self._isLower:                                       # ! curvature on bezier side_upper is negative !
            curv_te   =  self._bezier.curvature(1.0)
        else:
            curv_te   = -self._bezier.curvature(1.0)

        # current should be between 0.0 and target te curvature 
        if self._max_curv_te >= 0.0: 
            if curv_te >= 0.0: 
                delta = curv_te - self._max_curv_te
            else:
                delta = - curv_te * 3.0                 # te curvature shouldn't result in reversal
        else: 
            if curv_te < 0.0:  
                delta = - (curv_te - self._max_curv_te)
            else:
                delta = curv_te * 3.0                   # te curvature shouldn't result in reversal
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
        lim_curv_deriv_te = 10 * (abs(self._max_curv_te) if self._max_curv_te else 0.1)
        lim_curv_deriv_te = max (lim_curv_deriv_te, 1)             # derivative limit depending on curv at te

        if max_curv_deriv_te > lim_curv_deriv_te: 
            obj_te_deriv = (max_curv_deriv_te - lim_curv_deriv_te) / 20  # 0 is good, > 0 ..50 is bad 

        # ---- penalty for reversals in derivative of curvature - avoid bumps 

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

        # take norm2 of deviation and le curvature to get balanced result 
        # obj = np.linalg.norm ([obj_norm2, obj_le]) + obj_le_hp + obj_te + obj_revers + obj_te_deriv
        obj = obj_norm2 + obj_le + obj_le_hp + obj_te + obj_revers + obj_te_deriv

        # counter of objective evaluations (for entertainment)
        self._nevals += 1

        if self._nevals%100 == 0:           
            print (f"{self._nevals:4} " +
                           f" obj:{obj:5.2f}   norm2:{obj_norm2:5.2f}" +
                           f"  le:{obj_le:5.2f}   le_hp:{obj_le_hp:4.1f}   te:{obj_te:4.1f}" +
                           f"  rev:{obj_revers:4.1f}  te_der:{obj_te_deriv:4.1f}")

        # signal parent with new results 
        if self._nevals%10 == 0:  

            # print ("ohooo", self._nevals, curv_le, curv_after_le)
            # print ("     ", abs(self._bezier.curvature(0.00)) , abs(self._bezier.curvature(0.001)) , abs(self._bezier.curvature(0.01)) )

            self.sig_new_results.emit (self._nevals, norm2, curv_le, curv_te)
            self.msleep(2)                      # give parent some time to do updates

        return obj 

