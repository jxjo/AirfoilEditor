#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Geometry of a Spline based airfoil  

    Implements a kind of 'strategy pattern' for the different approaches how 
    the geometry of an airfoil is determined and modified.

    This module contains cubic spline interpolation based geometry classes.
"""

import numpy as np
from typing                 import override

from ..base.math_util       import * 
from ..base.spline          import Spline1D, Spline2D

from .geometry      import (Line, Geometry, Curvature_Abstract, 
                                    Panelling, GeometryException)

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# -----------------------------------------------------------------------------
#  Panel Distribution  
# -----------------------------------------------------------------------------

class Panelling_Spline (Panelling):
    """
    Helper class which represents the target panel distribution of an airfoil 

    Calculates new panel distribution u for an airfoil spline (repanel) to 
    achieve the leading edge of the spline (uLe) being leading edge of coordinates (iLe)
    """ 

    @classmethod    
    def to_dict (cls, d:dict) :
        """ save current values of panelling parameters to dict"""

        # save panelling values 
        if cls._nPanels != cls.N_PANELS_DEFAULT:
            d["spline_nPanels"] = cls._nPanels
        else: 
            d.pop ("spline_nPanels", None)

        if cls._le_bunch != cls.LE_BUNCH_DEFAULT:
            d["spline_le_bunch"] = cls._le_bunch
        else:
            d.pop ("spline_le_bunch", None) 

        if cls._te_bunch != cls.TE_BUNCH_DEFAULT:
            d["spline_te_bunch"] = cls._te_bunch
        else:
            d.pop ("spline_te_bunch", None)


    @classmethod
    def from_dict (cls, d:dict) :
        """ load panelling parameters from dict and set them as class variables"""

        # load panelling values 
        if "spline_nPanels" in d:
            cls._nPanels = d["spline_nPanels"]
        if "spline_le_bunch" in d:
            cls._le_bunch = d["spline_le_bunch"]
        if "spline_te_bunch" in d:
            cls._te_bunch = d["spline_te_bunch"]


    @override
    def _get_u (self, nPanels_per_side) -> np.ndarray:
        """ 
        returns numpy array of u having cosinus similar distribution for one side 
            - running from 0..1
            - having nPanels+1 points 
        """
        return Panelling._cosine_distribution(nPanels_per_side + 1, self.le_bunch, self.te_bunch)


    def new_u (self, 
                   u_current : np.ndarray|None, 
                   iLe : int,
                   uLe_target : float,
                   retain : bool = False, 
                   nPanels : int|None = None ):
        """ 
        Returns a new panel distribution u of an airfoil spline 
            - leading edge point (iLe) will be at uLe_target 
            - 'nPanels' will overwrite the default self.nPanels    
            - running from 0..1
            - if 'retain', the current distribution 'u_current' is scaled to uLe_target
        """

        if not retain: 

            nPanels = nPanels if nPanels is not None else self._nPanels
            # overwrite number of panels of self 
 
            nPan_upper = Panelling.nPanels_for(Line.Type.UPPER, nPanels)
            nPan_lower = Panelling.nPanels_for(Line.Type.LOWER, nPanels)
           
            # new distribution for upper and lower - points = +1 
            # ensuring LE is at uLe_target 
            u_cos_upper = self._get_u (nPan_upper)
            u_new_upper = np.abs (np.flip(u_cos_upper) -1) * uLe_target

            u_cos_lower = self._get_u (nPan_lower)
            u_new_lower = u_cos_lower * (1- uLe_target) + uLe_target

        else: 
            # get distribution from current 

            uLe_current =  u_current [iLe]     
            u_upper = u_current [:iLe+1]
            u_lower = u_current [iLe:]

            # stretch current distribution to fit to new uLe_target 
            stretch = uLe_target / uLe_current
            u_new_upper = u_upper * stretch                     # 0.0 ... uLe_target 
            u_lower_0   = u_lower - uLe_current
            u_new_lower = uLe_target + u_lower_0 / stretch      # uLe_target ... 1.0

            u_new_lower [-1] = 1.0
            nPan_upper = iLe
            nPan_lower = self.nPanels - nPan_upper

        # add new upper and lower 

        logger.debug (f"{self} _repanel {nPan_upper} {nPan_lower}")

        u_new = np.concatenate ((u_new_upper, u_new_lower[1:]))

        return u_new


# -----------------------------------------------------------------------------
#  Curvature  
# -----------------------------------------------------------------------------

class Curvature_of_Spline (Curvature_Abstract):
    """
    Curvature of geometry spline - - using existing spline for evaluation
    """

    def __init__ (self, spline: Spline2D, uLe: float):
        super().__init__()

        # high res repanelling for curvature evaluation

        # u = Panelling_Spline(nPanels=400, le_bunch=0.98).new_u (spline.u, 0, uLe_target=uLe)
        u = spline.u

        iLe = int(np.argmin(np.abs(u - uLe)))
        self._iLe = iLe
        self._values = spline.curvature (u) 

        # split curvature spline in upper and lower 
        x, y    = spline.eval (u)

        self._upper = Line (np.flip(x[: iLe+1]), np.flip(self._values [: iLe+1]), 
                            linetype=Line.Type.UPPER )
        self._lower = Line (x[iLe: ], self._values [iLe: ],                       
                            linetype=Line.Type.LOWER )

        # for curvature comb
        self._upper_side = Line (np.flip(x[: iLe+1]), np.flip(y [: iLe+1]), linetype=Line.Type.UPPER )
        self._lower_side = Line (x[iLe: ], y [iLe: ], linetype=Line.Type.LOWER )

        dx, dy  = spline.eval (u, der=1)
        self._upper_dx = -np.flip(dx[: iLe+1])
        self._upper_dy = -np.flip(dy[: iLe+1])
        self._lower_dx = dx[iLe: ]
        self._lower_dy = dy[iLe: ]


# -----------------------------------------------------------------------------
#  Side of an Airfoil   
# -----------------------------------------------------------------------------

class Side_Airfoil_Splined (Line): 
    """ 
    1D line of an airfoil like upper, lower side, camber line, curvature etc...
    with x 0..1

    Represented by a 1D spline

    """

    def __init__ (self, *args, **kwargs):

        self._spline    = None                  # 1D Spline to get max values of line
        super().__init__ (*args, **kwargs) 

  
    @property 
    def spline (self) -> Spline1D:
        """ spline representation of self """
        if self._spline is None: 
            self._spline = Spline1D (self.x, self.y)
        return self._spline


    def yFn (self,x):
        """ returns interpolated y values based on a x-value
        """
        return self.spline.eval (x)


    # ------------------ private ---------------------------


    def _reset (self):
        """ reinit self if x,y has changed""" 

        super()._reset()
        self._spline     = None


# -----------------------------------------------------------------------------
#  Geometry Classes 
# -----------------------------------------------------------------------------

class Geometry_Splined (Geometry): 
    """ 
    Geometry with a 2D cubic spline representation of airfoil all around the contour
    
    The 2D spline is used to get the best approximation of the airfoil e.g. for re-paneling
    """

    isBasic         = False
    isSplined       = True 


    description     = "based on spline interpolation"

    side_class      = Side_Airfoil_Splined
    line_class      = Side_Airfoil_Splined

    CURVE_NAME      = "Cubic Spline"            


    def __init__ (self, *args, **kwargs):
        super().__init__( *args, **kwargs)        


        self._spline : Spline2D          = None   # 2 D cubic spline representation of self
        self._uLe = None                          # leading edge  - u value 


    @property 
    def spline (self) -> Spline2D:
        """ spline representation of self """

        if self._spline is None: 
            self._spline = Spline2D (self.x, self.y)
            logger.debug (f"{self} New Spline ")
        return self._spline

    @property 
    def panelling (self) -> Panelling_Spline:
        """ returns the target panel distribution / helper """
        if self._panelling is None:
            self._panelling = Panelling_Spline()   # (self.nPanels)
        return self._panelling


    @property
    def isNormalized (self):
        """ true if coordinates AND spline is normalized"""
        return self._isNormalized_spline()


    def _isNormalized_spline (self):
        """ true if coordinates AND spline is normalized"""
        return super()._isNormalized () and self.isLe_closeTo_le_real


    @property
    def le_real (self): 
        """ le calculated based on spline """
        #overloadded
        xLe, yLe = self.xyFn (self.uLe)   
        # + 0.0 ensures not to have -0.0 
        return round(xLe,7) + 0.0, round(yLe,7) + 0.0 
    
    @property
    def uLe (self): 
        """ u (arc) value of the leading edge """
        if self._uLe is None: 
            try: 
                self._uLe = self._le_find()
            except: 
                self._uLe = self.spline.u[self.iLe] 
                logger.warning (f"{self} le_find failed - taking geometric uLe:{self._uLe:.7f}")
        return self._uLe


    @property
    def curvature (self) -> Curvature_of_Spline: 
        " return the curvature object"
        if self._curvature is None: 
            self._curvature = Curvature_of_Spline (self.spline, self.uLe)  
        return self._curvature 

    @property
    def angle (self): 
        """ return the angle in degrees at knots"""
        return np.arctan (self.spline.deriv1(self.spline.u)) * 180 / np.pi
    

    #-----------


    def upper_new_x (self, new_x) -> np.ndarray: 
        """
        returns y coordinates for new_x
        
        Using spline interpolation  
        """
        # evaluate the corresponding y-values on lower side 
        upper_y = np.zeros (len(new_x))
 
        for i, x in enumerate (new_x):
 
            # nelder mead find min boundaries 
            uStart = 0.0
            uEnd   = self.uLe 
            uGuess = interpolate (0.0, 1.0, uStart, uEnd, x)   # best guess as start value

            u = findMin (lambda xlow: abs(self.spline.evalx(xlow) - x), uGuess, 
                        bounds=(uStart, uEnd), no_improve_thr=1e-8) 

            # with the new u-value we get the y value on lower side 
            upper_y[i] = self.spline.evaly (u)

        upper_y = np.round(upper_y, 10)

        return upper_y



    def lower_new_x (self, new_x) -> np.ndarray: 
        """
        returns lower new y coordinates for new_x
        
        Using spline interpolation  
        """
        # evaluate the corresponding y-values on lower side 
        n = len(new_x)
        lower_y = np.zeros (n)
 
        for i, x in enumerate (new_x):

            # first and last point from current lower to avoid numerical issues 
            if i == 0: 
                lower_y[i] = self.lower.y[0]
            elif i == (n - 1):
                lower_y[i] = self.lower.y[-1]
            else:
 
                # nelder mead find min boundaries 
                uStart = self.uLe
                uEnd   = 1.0 
                uGuess = interpolate (new_x[0], new_x[-1], uStart, 1.0, x)   # best guess as start value

                umin = max (uStart, uGuess - 0.1 )
                umax = min (uEnd, uGuess + 0.1 )

                # find min using Secant - fast but not for LE with high curvature 
                if i > n/10: 
                    max_iter = 4 
                    u, niter  = secant_fn (lambda u: self.spline.evalx(u) - x,
                                            umin, umax, max_iter)
                else: 
                # find u value for x using Nelder Mead 
                    u = findMin (lambda u: abs(self.spline.evalx(u) - x), uGuess, 
                                bounds=(uStart, uEnd), no_improve_thr=1e-10) 

                # with the new u-value we get the y value on lower side 
                # print (i, u, uGuess)
                lower_y[i] = self.spline.evaly (u)

        lower_y = np.round(lower_y, 12)

        return lower_y


    def _normalize (self):
        """Shift, rotate, scale airfoil so LE is at 0,0 and TE is symmetric at 1,y"""

        if self._isNormalized_spline():
            return False

        # the exact determination of the splined LE is quite "sensibel"
        # on numeric issues (decimals) 
        # there try to iterate to a good result 

        isNormalized = False
        n = 0

        while not isNormalized and n < 10:

            n += 1

            if n > 1:
                self._reset_spline ()
                self._repanel (retain=True)   

            super()._normalize()                # normalize based on coordinates

            # is real and splined le close enough
            norm2 = self._le_real_norm2()

            logger.debug (f"{self} normalize spline iteration #{n} - norm2: {norm2:.7f}")

            if norm2 <= self.EPSILON_LE_CLOSE:
                isNormalized = True


        return isNormalized


    def xyFn (self,u): 
        " return x,y at spline arc u"
        return  self.spline.eval (u)


    def scalarProductFn (self,u): 
        """ return the scalar product of a vector from TE to u and the tangent at u
        Used for finding LE where this value is 0.0at u"""

        # exact trailing edge point 
        xTe = (self.x[0] + self.x[-1]) / 2
        yTe = (self.y[0] + self.y[-1]) / 2

        x,y = self.xyFn(u) 

        # vector 1 from te to point 
        dxTe = x - xTe
        dyTe = y - yTe
        # vector2 tangent at point 
        dx, dy = self.spline.eval(u, der=1) 

        dot = dx * dxTe + dy * dyTe

        return dot 


    def repanel (self,  nPanels : int = None, just_finalize = False):
        """
        Repanel self with a new cosinus distribution.

        If no new panel numbers are defined, the current numbers for upper and lower side remain. 
        """

        try: 

            if not just_finalize:
                self._repanel (nPanels = nPanels)
            
            # repanel could lead to a slightly different le 
            super()._normalize()               # do not do iteration in self.normalize       

            # save the actual panelling options as class variables
            self._panelling.save() 

            self._reset()
            self._changed (Geometry.MOD_REPANEL)
            self._set_xy (self._x, self._y)

        except GeometryException: 
            logger.error ("Error during repanel")
            self._clear_xy()       


    def _repanel (self, retain : bool = False, 
                        nPanels : int = None,
                        based_on_org = False):
        """ 
        Inner repanel without normalization and change handling
            - retain = True keeps the current distribution for the new calculated LE 
            - nPanels = new total number of panels (optional)
            - based_on_org = True will use original x,y coordinates to build spline (if available
        """

        # for repeated repanelling use the original x,y coordinates to repanel to avoid numerical issues
        if based_on_org and self._x_org is not None and self._y_org is not None:
            
            self._x, self._y = None, None                       # will use original x,y coordinates to build spline 
            self._reset_spline()
            logger.debug (f"{self} repanel based on org x,y")

        # sanity
        if len(self.spline.u) != len(self.x):
            raise ValueError (f"{self} - repanel: u and x don't fit")

        # re(calculate) panel distribution of spline so LE will be at uLe and iLe  
        u_new = self.panelling.new_u (self.spline.u, self.iLe, self.uLe,
                                          retain=retain, nPanels=nPanels)

        # new calculated x,y coordinates  
        x, y = self.xyFn(u_new)

        self._x = np.round (x, 10)
        self._y = np.round (y, 10)

        self._reset_spline()

        return True


    # ------------------ private ---------------------------


    def _reset_spline (self):
        """ reinit self spline data if x,y has changed""" 
        self._curvature  = None                 # curvature 
        self._spline     = None
        self._uLe        = None                 # u value at LE 


    def _rebuild_from_camb_thick(self):
        """ rebuilds self out of thickness and camber distribution """
        # overloaded to reset spline

        # keep current panel numbers of self 

        nPan_upper = self.iLe
        nPan_lower = self.nPanels - nPan_upper

        super()._rebuild_from_camb_thick()

        # dummy to build spline now 

        a = self.spline

        # when panel number changed with rebuild do repanel to get original number again 

        # nPan_upper_new = self.iLe
        # nPan_lower_new = self.nPanels - nPan_upper_new

        # if (nPan_upper != nPan_upper_new) or (nPan_lower != nPan_lower_new):

        #     self.repanel (nPan_upper=nPan_upper,nPan_lower=nPan_lower)

            # repanel could lead to a slightly different le 
            # self.normalize()


    def _le_find (self):
        """ returns u (arc) value of leading edge based on scalar product tangent and te vector = 0"""

        iLe_guess = np.argmin (self.x)              # first guess for Le point 
        uLe_guess = self.spline.u[iLe_guess-1]      # '-1'  a little aside 

        umin = max (0.4, uLe_guess-0.1)
        umax = min (0.6, uLe_guess+0.1)
 
        # exact determination of root  = scalar product = 0.0 
        uLe = findRoot (self.scalarProductFn, uLe_guess , bounds=(umin, umax)) 
        logger.debug (f"{self} le_find u_guess:{uLe_guess:.7f} u:{uLe:.7f}")

        return uLe


    def get_y_on (self, side : Line.Type, xIn): 
        """
        Evalutes y values right on 'side' having x-values xIn.
        Note: if self isn't normalized, it will be normalized prior to evaluation

        Parameters
        ----------
        side : either UPPER or LOWER
        xIn : x-coordinates on 'side' to evaluate y
             
        Returns
        -------
        yOut : np array - evaluated y values 
        """

        iLe = np.argmin (self.x)

        if side == Line.Type.LOWER: 
            uStart = self.spline.u[iLe] 
            uEnd   = self.spline.u[-1]  
            uGuess = 0.75          
        elif side == Line.Type.UPPER:
            uStart = self.spline.u[0] 
            # uEnd   = self.spline.u[iLe-1]   
            uEnd   = self.spline.u[iLe]   
            uGuess = 0.25         
        else:
            raise ValueError ("'%s' not supported" % side.value[0])

        ux = np.zeros (len(xIn))
        for i, xi in enumerate (xIn): 

            # find matching u to x-value 
            #   no_improve_thr= 10e-6 is sufficient to get average 10e-10  tolerance
            ux[i] = findMin (lambda u: abs(self.spline.evalx(u) - xi), uGuess, bounds=(uStart, uEnd), 
                             no_improve_thr= 10e-6) 
            uGuess = ux[i]

        # get y coordinate from u          
        yOut = self.spline.evaly (ux)

        # ensure Le is 0,0 and Te is at 1
        if   xIn[0]  == self.x[iLe]:                    yOut[0]  = self.y[iLe]
        elif xIn[-1] == self.x[0]  and side == Line.Type.UPPER:   yOut[-1] = self.y[0]
        elif xIn[-1] == self.x[-1] and side == Line.Type.LOWER:   yOut[-1] = self.y[-1]

        return yOut 
