#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""

    Cubic Spline 1D and 2D  

"""
import bisect
import math
import numpy as np
from copy                   import deepcopy
from timeit                 import default_timer as timer

from .math_util             import findMin, newton

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


#------------ Helper -----------------------------------


def rref(B, tol=1e-8):
    """Compute the Reduced Row Echelon Form (RREF)"""
    # from https://gist.github.com/sgsfak/77a1c08ac8a9b0af77393b24e44c9547

    A = np.copy(B)
    rows, cols = A.shape
    r = 0
    pivots_pos = []
    row_exchanges = np.arange(rows)
    for c in range(cols):

        ## Find the pivot row:
        pivot = np.argmax (np.abs (A[r:rows,c])) + r
        m = np.abs(A[pivot, c])
        if m <= tol:
            ## Skip column c, making sure the approximately zero terms are
            ## actually zero.
            A[r:rows, c] = np.zeros(rows-r)
        else:
            ## keep track of bound variables
            pivots_pos.append((r,c))

            if pivot != r:
                ## Swap current row and pivot row
                A[[pivot, r], c:cols] = A[[r, pivot], c:cols]
                row_exchanges[[pivot,r]] = row_exchanges[[r,pivot]]

            ## Normalize pivot row
            A[r, c:cols] = A[r, c:cols] / A[r, c]

            ## Eliminate the current column
            v = A[r, c:cols]
            ## Above (before row r):
            if r > 0:
                ridx_above = np.arange(r)
                A[ridx_above, c:cols] = A[ridx_above, c:cols] - np.outer(v, A[ridx_above, c]).T
            ## Below (after row r):
            if r < rows-1:
                ridx_below = np.arange(r+1,rows)
                A[ridx_below, c:cols] = A[ridx_below, c:cols] - np.outer(v, A[ridx_below, c]).T
            r += 1
        ## Check if done
        if r == rows:
            break
    return A


def print_array2D (aArr):

    for i, row in enumerate (aArr):
        print ("%4d: " %i, end=" ")
        for j in row:
            print("%6.2f" % j, end=" ")
        print()
    print()


def print_array1D (aArr,header=None):

    if not header is None: 
        print (header)
    for i, val in enumerate (aArr):
        print ("%4d: " %i, end=" ")
        print ("%6.2f" % val)
    print()

def print_array_compact (aArr,header=None):

    if not header is None: 
        print (header,": ", end=" ")
    for i, val in enumerate (aArr):
        #print ("%8.4f" % val, end=" ")
        print ("%8.5f" % val, end=",")
    print()



#------------ Spline 1D -----------------------------------

class Spline1D: 
    """Cubic 1D Spline"""


    def __init__ (self, x, y, boundary="notaknot", arccos=False):
        """
        Build cubic spline based on x,y. x must be strongly ascending.

        Parameters
        ----------
        x,y : array_like
             
        boundary : Type of boundary condition  - either 
           
            'notaknot'   - at the first and last interior break, 
                           even the third derivative is continuous - default 
            'natural'    - the second derivate at start and end is zero 

        Returns
        -------
        """
        
        # based on https://en.wikiversity.org/wiki/Cubic_Spline_Interpolation
        # and      https://blog.scottlogic.com/2020/05/18/cubic-spline-in-python-and-alteryx.html

        # Info     https://sepwww.stanford.edu/sep/sergey/128A/answers6.pdf for boundary conditions
        #          https://documents.uow.edu.au/~/greg/math321/Lec3.pdf 

        if not (boundary == 'natural' or 'notaknot'): 
            boundary = 'notaknot'

        n = len(x)

        if boundary == 'notaknot' and n < 4:
            raise ValueError("Spline: 'notaknot' must have at least 4 points")
        elif n < 3:
            raise ValueError('Spline: Must have at least 3 points')
        if n != len(y): 
            raise ValueError('Spline: Length of x,y is different')
            
        if arccos:           # arccos distribution to avoid oscillation at LE          
            self.x = np.arccos(1.0 - x) * 2.0 / np.pi     
            self._arccos = True 
        else:
            self.x = x
            self._arccos = False 

        # keep for later evaluation 
        self.y = y

        # only delta x will be relevant 
        h = np.diff(self.x,1)                        # the differences hi = xi+1 - xi  (length n-1)
        if np.amin(h) <= 0.0: 
            raise ValueError('Spline: x is not strictly increasing')

        # build the tridiagonal matrix with simple, natural boundary condition
        A, B, C = self._build_tridiagonalArrays (n, h)

        # build the right hand side 
        D = self._build_targetArray (n, h, y)

        # boundary conditions - overwrite boundaries of A, B, C, D

        if boundary == 'natural':

            # 1. der2(x0) and der2(xn) is known 
            #    special case: 'Natural' or 'Simple'   der2(x0) = der2(xn) = 0 
            #    Di = 2 * der2i
            C[0]  = 0.0
            A[-1] = 0.0 
            D[0]  = 0.0     # 2 * 5.0     # 2nd derivative test
            D[-1] = 0.0     # 2 * 3.0     # 2nd derivative test

            # solve tridiagonal system 
            M = self._solve_tridiagonalsystem(A, B, C, D)

        elif boundary == 'notaknot':

            # 2. not a knot  ( knot (x1) and (xn-1) is not a knot)
            #    der3(x0) = der3(x1)  and der3[xn-1] = der[xn]
            #    According to
            #    https://documents.uow.edu.au/~/greg/math321/Lec3.pdf
            #    
            #  in this case only a (n-2) x (n-2) matrix has be solved
            B[1]  = (2*h[1]  + h[0])  / h[1]                            # diagonal - upper-left corner 
            B[-2] = (2*h[-2] + h[-1]) / h[-2]                           # diagonal - lower-right corner 
            C[1]  = (h[1]**2  - h[0]**2)  / ( h[1] * (h[0]  + h[1]))    # super diagonal 
            A[-2] = (h[-2]**2 - h[-1]**2) / (h[-2] * (h[-2] + h[-1]))   # sub diagonal 

            M = self._solve_tridiagonalsystem (A, B, C, D, reduced=True)

            # evaluate the missing M0 and M-1 (eqauls derivate2 at x0 and xn) 
            M[0]  = ((h[0]  + h[1])  * M[1]  - h[0]  * M[2])  / h[1]
            M[-1] = ((h[-2] + h[-1]) * M[-2] - h[-1] * M[-3]) / h[-2]
            # print_array1D (M,"M") 
            
        # print_array1D (h,"h") ; 
        # print_array1D (A,"A"); print_array1D (B,"B"); print_array1D (C, "C"); print_array1D (D, "D") 

        # extract coefficients of polynoms
        self.a = np.zeros (n-1)
        self.b = np.zeros (n-1)
        self.c = np.zeros (n-1)
        self.d = np.zeros (n-1)
        for i in range(n-1):

            #  a1 = y1
            #  b1 = b(0) = C'(0) = -M0*h1/2 + (y1-y0)/h1 - (M1-M0)*h1/6 
            #  c1 = M-1 / 2     
            #  d1 = (M1 - M1) / (6 * h1)    
             
            self.a[i] = y[i]
            self.b[i] = (y[i+1] - y[i]) / h[i]  - h[i] * (3 * M[i] +  (M[i+1] - M[i])) / 6 
            self.c[i] = M[i] / 2
            self.d[i] = (M[i+1]-M[i]) / (6 * h[i])

            # print ("i:%d  a=%6.2f  b=%6.2f  c=%6.2f  d=%6.2f " % (i, self.a[i] , self.b[i] , self.c[i] , self.d[i] ))


    def _build_tridiagonalArrays (self, n: int, h ):

        # returns the tridiagonal arrays A, B, C 
        #   with B[i] = 2
        #
        #   b0   c0    0    0             B - diagonal elements length n       
        #   a0   b1   c1    0             A - below length n-1
        #    0   a1   b2   c2             C - above length n-1 
        #    0    0   a2   b3

        B = np.empty(n); B.fill(2.0)

        A = np.zeros (n-1) 
        for i in range(n-2):                    
            A[i] = h[i]  / (h[i] + h[i+1])

        C = np.zeros (n-1) 
        for i in range(1, n-1):                  
            C[i] = h[i]  / (h[i-1] + h[i])

        return A, B, C


    def _build_targetArray(self, n: int, h, y):
        # returns the right hand side (rhs) array D 
        #   which is the "divided difference" f[xi-1, xi, xi+1]
        #   https://en.wikipedia.org/wiki/Divided_differences
        
        #   d0                            D - rhs array length n
        #   d1
        #   d2 

        D = np.zeros(n)
        for i in range(1, n - 1): 
            D[i] = 6.0 * ((y[i + 1] - y[i]) / (h[i]) - (y[i] - y[i-1]) / (h[i-1])) / \
                         (h[i] + h[i-1])        
        return D


    def _solve_tridiagonalsystem (self, A, B, C, D, reduced=False):
        # solves the tridiagonal system ABC * M = D  
        #
        # when reduced the inner (n-2) x (n-2) matrix is solved (need for not a knot)
        ''''
        TDMA solver, a b c d can be NumPy array type or Python list type.
        refer to http://en.wikipedia.org/wiki/Tridiagonal_matrix_algorithm
        and to http://www.cfd-online.com/Wiki/Tridiagonal_matrix_algorithm_-_TDMA_(Thomas_algorithm)
        '''
        if reduced: 
            di = 1
        else:
            di = 0 

        # https://gist.github.com/cbellei/8ab3ab8551b8dfc8b081c518ccd9ada9

        iEnd = len(D) - di  # number of equations

        ac, bc, cc, dc = map(np.array, (A, B, C, D)) # copy arrays
        for it in range(1+di, iEnd):
            mc = ac[it-1]/bc[it-1]
            bc[it] = bc[it] - mc*cc[it-1] 
            dc[it] = dc[it] - mc*dc[it-1]
                    
        M = bc
        M[-1-di] = dc[-1-di]/bc[-1-di]

        for il in range(iEnd-2, -1+di, -1):
            M[il] = (dc[il]-cc[il]*M[il+1])/bc[il]

        return M


    def _solve_tridiagonalsystem2 (self, A, B, C, D):
        # solves the tridiagonal system ABC * M = D  
        ''''
        TDMA solver, a b c d can be NumPy array type or Python list type.
        refer to http://en.wikipedia.org/wiki/Tridiagonal_matrix_algorithm
        and to http://www.cfd-online.com/Wiki/Tridiagonal_matrix_algorithm_-_TDMA_(Thomas_algorithm)
        '''
        nf = len(D) # number of equations
        ac, bc, cc, dc = map(np.array, (A, B, C, D)) # copy arrays
        for it in range(1+1, nf-1):
            mc = ac[it-1]/bc[it-1]
            bc[it] = bc[it] - mc*cc[it-1] 
            dc[it] = dc[it] - mc*dc[it-1]
                    
        M = bc
        M[-2] = dc[-2]/bc[-2]

        for il in range(nf-3, -1+1, -1):
            M[il] = (dc[il]-cc[il]*M[il+1])/bc[il]

        return M



    def eval (self, x, der=0):
        """
        Evaluate self or its derivatives.

        Parameters
        ----------
        x : Scalar or an array of points at which to return the value of the 
            spline or its derivatives. 
        der : int, optional - The order of derivative of the spline to compute 

        Returns
        -------
        y : scalar or ndarray representing the spline function evaluated at x.
        """

        if isinstance(x, float): 
            return self._eval (x, der=der) 
        else: 
            f = np.zeros (np.size(x))
            for i, xi in enumerate (x): f[i] = self._eval (xi, der=der) 
            return f 


    def _eval (self, x, der=0):
        """
        Evaluate self or its derivatives.

        Parameters
        ----------
        x : Scalar to return the value of the spline or its derivatives. 
        der : int, optional - The order of derivative of the spline to compute 

        Returns
        -------
        y : scalar representing the spline function evaluated at  ``x``.  .
        """

        if x < self.x[0]:  x = self.x[0]
        if x > self.x[-1]: x = self.x[-1]

        if self._arccos: 
            x = np.arccos(1.0 - x) * 2.0 / np.pi                   # acos(1.d0 - x(i)) * 2.d0 / pi 

        # get the index j of x in the function intervals of self 
        j = min(bisect.bisect(self.x, x)-1, len(self.x) -2)
        z = (x - self.x[j])                # relative coordinate within interval 

        if   der == 0: f = self.a[j] + self.b[j] * z + self.c[j] * z**2 + self.d[j] * z**3
        elif der == 1: f = self.b[j] + 2 * self.c[j] * z + 3 * self.d[j] * z**2
        elif der == 2: f = 2 * self.c[j] + 6 * self.d[j] * z
        else:          f = 0 

        return f 



    def curvature (self, xin):
        """
        Eval
        uate the curvature of self.

        Parameters
        ----------
        x : Scalar or an array

        Returns
        -------
        c : Scalar or an array of values representing the curvature evaluated at
            the points in ``x``.  
        """

        df  = self.eval(xin, der=1)
        ddf = self.eval(xin, der=2)
        return ddf / ((1 + df**2) ** 1.5)




#------------ Spline 2D -----------------------------------

class Spline2D: 
    """Cubic 2D Spline"""

    def __init__ (self, x, y, boundary="notaknot"):
        """
        Build cubic 2D spline based on x,y. 

        Parameters
        ----------
        x,y : array_like
             
        boundary : Type of boundary condition  - either 
           
            'notaknot'   - at the first and last interior break, 
                           even the third derivative is continuous - default 
            'natural'    - the second derivate at start and end is zero 

        Returns
        -------
        """
        self.x = x
        self.y = y
        self.s = self._calc_s(x, y)
        # print_array1D (self.s)

        # 'normalize' to have u = 0..1
        self.u = self.s - self.s[0]
        self.u = (self.u / self.u[-1]) 
        
        # ensure 0.0 and 1.0 
        self.u[0]  = self.u[0].round(10)
        self.u[-1] = self.u[-1].round(10)
        
        self.splx = Spline1D(self.s, x, boundary=boundary)
        self.sply = Spline1D(self.s, y, boundary=boundary)


    def _calc_s(self, x, y):
        """ returns the arc length of x,y curve """
        dx = np.diff(x)
        dy = np.diff(y)
        # self.ds = [math.sqrt(idx ** 2 + idy ** 2)
        #            for (idx, idy) in zip(dx, dy)]
        ds = np.sqrt (dx**2 + dy**2)
        ds = np.insert (ds,0, 0.0)
        s  = np.cumsum(ds)
        return s


    def eval (self, u, der=0):
        """
        Evaluate self or its derivatives.

        Parameters
        ----------
        u :   Scalar or an array of normed arc length 0..1 at which to return 
              the value of the spline or its derivatives. 
        der : int, optional - The order of derivative of the spline to compute.

        Returns
        -------
        x,y : Scalar or an array representing the spline function evaluated at
              the points in ``s``.  .  eg. x,y  or  dx,dy  or  ddx, ddy
        """

        # denormalize u to original arc length s
        s = self.s[0] + u * (self.s[-1] - self.s[0])

        fx = self.splx.eval (s, der=der)
        fy = self.sply.eval (s, der=der)

        return fx, fy 


    def evalx (self, u, der=0):
        """
        Evaluate self or its derivatives and returns just x - for optimization - 

        Parameters  - see eval()
        ----------
        Returns
        -------
        x  : ndarray representing the spline function evaluated a
        """
        # denormalize u to original arc length s
        s = self.s[0] + u * (self.s[-1] - self.s[0])

        return self.splx.eval (s, der=der)


    def evaly (self, u, der=0):
        """
        Evaluate self or its derivatives and returns just y - for optimization - 

        Parameters  - see eval()
        ----------
        Returns
        -------
        y : Scalar or an array representing the spline function evaluated a
        """
        # denormalize u to original arc length s
        s = self.s[0] + u * (self.s[-1] - self.s[0])

        return self.sply.eval (s, der=der)


    def curvature (self, u):
        """
        Evaluate the curvature of self at u 0..1

        Parameters
        ----------
        u :   Scalar or an array of arc length at which to return 
              the value of the spline or its derivatives. 
        Returns
        -------
        c : An array of values representing the curvature evaluated at the points u.  
        """

        dx,  dy  = self.eval (u, der=1)
        ddx, ddy = self.eval (u, der=2)

        c = (ddy * dx - ddx * dy) / (dx ** 2 + dy ** 2) ** 1.5
        return c


    def deriv1 (self, u):
        """
        Evaluate first derivative dy/du / dx/du of self at u 0..1

        Parameters
        ----------
        u :   Scalar or an array of arc length at which to return 
              the value of the spline or its derivatives. 
        Returns
        -------
        c : An array of values representing the 2nd derivative evaluated at the points u.  
        """

        dx,  dy  = self.eval (u, der=1)

        deriv1 = dy/dx
        return deriv1


    def deriv2 (self, u):
        """
        Evaluate second derivative ddy * dx - ddx * dy of self at u 0..1

        Parameters
        ----------
        u :   Scalar or an array of arc length at which to return 
              the value of the spline or its derivatives. 
        Returns
        -------
        c : An array of values representing the 2nd derivative evaluated at the points u.  
        """

        dx,  dy  = self.eval (u, der=1)
        ddx, ddy = self.eval (u, der=2)

        deriv2 = ddy * dx - ddx * dy
        return deriv2


#------------ Bezier -----------------------------------


class Bezier: 
    """
    Bézier curve defined by its control points.

    - ``n = 2``: straight line
    - ``n = 3``: quadratic
    - ``n = 4``: cubic
    - ``n > 4``: higher order
    """
    #todo rename points -> cpoints, take care of Artists

    def __init__ (self, cpx_or_cp : list, cpy : list|None =None):
        """
        Initialize a Bézier curve from control points.

        Args:
            cpx_or_cp: x coordinates or an iterable of ``(x, y)`` control points.
            cpy: y coordinates when ``cpx_or_cp`` contains only x values.
        """

        self._cpx = None                        # definition points
        self._cpy = None

        self.basisFn = None                     # stored Bezier basis function for test 

        self._clear_cache()                          # cache for evaluated values

        self.set_cpoints(cpx_or_cp, cpy)
        return

    def _clear_cache(self):
        """Reset cached curve evaluations and inverse lookups."""
        self._x,   self._y    = None, None                          # cached evaluation results
        self._dx,  self._dy   = None, None
        self._ddx, self._ddy  = None, None
        self._u     = None                           
        self._y_on_x_cache = {}
        self._x_on_y_cache = {}


    @property
    def cpoints (self) -> list[tuple]: 
        """Control points as a list of ``(x, y)`` tuples."""
        if not (self._cpx is None or self._cpy is None):
            return list(zip(self._cpx,self._cpy))   
        else:
            return []
        
    @property
    def ncp (self) -> int:
        """Number of control points."""
        return len (self._cpx) 

    @property
    def degree(self) -> int:
        """Curve degree."""
        return self.ncp - 1


    @property
    def cpoints_x (self) -> list[float]:  
        """x coordinates of the control points."""
        return list(self._cpx)

    @property
    def cpoints_y (self) -> list[float]:  
        """y coordinates of the control points."""
        return list(self._cpy)


    def set_cpoints (self, cpx_or_cp : list, cpy :list|None =None):
        """  
        Set or replace all control points.

        Args:
            cpx_or_cp: x coordinates or an iterable of ``(x, y)`` control points.
            cpy: y coordinates when ``cpx_or_cp`` contains only x values.
        """
        
        if cpy is None:                          # point tuples as argument? 
            cpx, cpy = zip(*cpx_or_cp)
        else: 
            cpx = cpx_or_cp

        n = len(cpx)
        if n < 2:
            raise ValueError('Bezier: Must have at least 2 control points')
        elif n != len(cpy): 
            raise ValueError('Bezier: Length of x,y is different')

        self._cpx = np.copy(cpx)
        self._cpy = np.copy(cpy)

        self._clear_cache()


    def set_cpoint (self, iPoint : int , cpx_or_cp : tuple|float, cpy : float|None=None):
        """  
        Update one control point in place.

        Args:
            iPoint: Index of the control point to update.
            cpx_or_cp: Either an ``(x, y)`` tuple or the x value.
            cpy: y value when ``cpx_or_cp`` contains only x.
        """

        if cpy is None:                          # point tuple as argument? 
            (cpx, cpy) = cpx_or_cp
        else: 
            cpx = cpx_or_cp

        if self._cpx is None: 
            raise ValueError("Bezier: No points defined up to now - can't set Point %d " % iPoint)

        n = len(self._cpx)
        if iPoint > n-1:
            raise ValueError('Bezier: Point %d is outside of control point array' % iPoint)

        if self._cpx[iPoint] != cpx or self._cpy[iPoint] != cpy:

            self._cpx[iPoint] = cpx
            self._cpy[iPoint] = cpy
                
            self._clear_cache()


    def elevate_degree(self):
        """
        Raise the degree of the Bezier curve by one while preserving its shape exactly.
        
        Uses the degree elevation algorithm which adds one control point and increases
        the degree by 1. The curve geometry remains identical.
        
        This is the Bezier equivalent of knot insertion for B-splines - it adds control
        points without changing the curve shape.
        
        Note: For airfoils with vertical tangent at LE (cpx[0] = cpx[1] = 0.0),
        this constraint is automatically preserved by the elevation formula.
        """
        n = self.ncp  # current number of control points
        degree = n - 1  # current degree
        
        # Check if vertical tangent constraint exists
        has_vertical_tangent = np.isclose(self._cpx[0], self._cpx[1])
        
        # New control points (n+1 points for degree+1)
        new_cpx = np.zeros(n + 1)
        new_cpy = np.zeros(n + 1)
        
        # Degree elevation formula:
        # Q_i = (i/(degree+1)) * P_{i-1} + (1 - i/(degree+1)) * P_i
        # where Q_i are the new control points and P_i are the old ones
        
        for i in range(n + 1):
            if i == 0:
                # First control point stays the same
                new_cpx[i] = self._cpx[0]
                new_cpy[i] = self._cpy[0]
            elif i == n:
                # Last control point stays the same
                new_cpx[i] = self._cpx[n - 1]
                new_cpy[i] = self._cpy[n - 1]
            else:
                # Interior control points are weighted averages
                alpha = i / (degree + 1)
                new_cpx[i] = alpha * self._cpx[i - 1] + (1 - alpha) * self._cpx[i]
                new_cpy[i] = alpha * self._cpy[i - 1] + (1 - alpha) * self._cpy[i]
        
        # Ensure vertical tangent constraint is preserved (enforce exactly to avoid floating point drift)
        if has_vertical_tangent:
            new_cpx[1] = new_cpx[0]
        
        # Update control points
        self.set_cpoints(new_cpx, new_cpy)


    @staticmethod
    def _basisFunction (n, i, u):
        """Bernstein basis polynomial."""
        return np.array (math.comb(n, i) * (u ** i) * (1 - u) ** (n - i))


    @property
    def has_u (self) -> bool: 
        """Whether cached evaluations exist for parameter values ``u``."""
        return self._u is not None 


    def eval (self, u, der=0):
        """
        Evaluate the curve or one of its derivatives.

        Args:
            u: Scalar or array of parameter values in ``[0, 1]``.
            der: Derivative order ``0``, ``1``, or ``2``.

        Returns:
            tuple[float, float] | tuple[np.ndarray, np.ndarray]: Evaluated x and y values.
        """
        x, y = None, None

        # use cache if available

        if np.array_equal (u, self._u):
            if der == 0 and self._x is not None and self._y is not None:
                x, y = self._x, self._y
            elif der == 1 and self._dx is not None and self._dy is not None:
                x, y = self._dx, self._dy
            elif der == 2 and self._ddx is not None and self._ddy is not None:
                x, y = self._ddx, self._ddy

        # evaluate if not cached

        if x is None or y is None:
            x = self._eval_1D (self._cpx, u, der=der)   # recalc 
            y = self._eval_1D (self._cpy, u, der=der)

            if not np.isscalar(u):
                self._clear_cache()  # clear cache if u is array and thus not reusable for other calls
                self._u = u 
                if der == 0:         # cache result for der=0 if u is array
                    self._x, self._y = x, y
                elif der == 1:       # cache result for der=1 if u is array
                    self._dx, self._dy = x, y
                elif der == 2:       # cache result for der=2 if u is array
                    self._ddx, self._ddy = x, y
        return x, y


    def eval_y (self, u, der=0):
        """
        Evaluate only the y component.

        Args:
            u: Scalar or array of parameter values in ``[0, 1]``.
            der: Derivative order ``0``, ``1``, or ``2``.

        Returns:
            float | np.ndarray: Evaluated y values.
        """

        return self._eval_1D (self._cpy, u, der=der)


    def eval_y_on_x (self, x, fast=True, epsilon=10e-10):
        """
        Evaluate ``y`` for a given x coordinate on the curve.

        Use either a cached linearized lookup or a Newton solve for ``u(x)``.

        Args:
            x: Target x coordinate.
            fast: Use cached linear interpolation when possible.
            epsilon: Convergence tolerance passed to ``newton``.

        Returns:
            float: y coordinate at the requested x location.
        """

        # check for cached value 
        y = self._y_on_x_cache.get(x)
        if y is not None:
            return y


        if fast and (not self._x is None) and (x >= self._x[0] and x <= self._x[-1]):

            # find closest index
            i = min(bisect.bisect(self._x, x)-1, len(self._x) -2)

            # interpolate u 
            u = ((self._u[i+1]-self._u[i])/(self._x[i+1]-self._x[i])) * (x - self._x[i]) + self._u[i]

            # evaluate y from u 
            y =  self._eval_1D (self._cpy, u)

        else: 

            if x == self._eval_1D(self._cpx,0.0):    # avoid numerical issues of Newton 
                u = 0.0
            else: 
                if x < 0.05:                        # good start value für newton iteration 
                    u0 = 0.05
                elif x > 0.95:
                    u0 = 0.95
                else: 
                    u0 = x                          # first estimation 

                # find u value for x
                u, niter  = newton (lambda u: self._eval_1D(self._cpx,u) - x,
                            lambda u: self._eval_1D(self._cpx,u, der=1) , u0, 
                            epsilon=epsilon, max_iter=20, bounds=(0.0,1.0))

            # eval y for u value
            y =  self._eval_1D (self._cpy, u)

            # cache value - only not fast
            self._y_on_x_cache [x] = y

        return y
        


    def eval_x_on_y (self, y, fast=True):
        """
        Evaluate ``x`` for a given y coordinate on the curve.

        Use either a cached linearized lookup or a scalar minimization for ``u(y)``.

        Args:
            y: Target y coordinate.
            fast: Use cached linear interpolation when possible.

        Returns:
            float: x coordinate at the requested y location.
        """

        # check for cached value 
        x = self._x_on_y_cache.get(y)
        if x is not None:
            return x

        if fast and (not self._y is None) and (y <= self._y[0] and y >= self._y[-1]):
            i = min(bisect.bisect(self._y, y)-1, len(self._y) -2)
            # interpolate u 
            u = ((self._u[i+1]-self._u[i])/(self._y[i+1]-self._y[i])) * (y - self._y[i]) + self._u[i]
            # evaluate y from u 
            x = self._eval_1D (self._cpx, u)
        else: 
            u = findMin (lambda u: abs(self._eval_1D(self._cpy,u) - y), 0.5, bounds=(0, 1)) 
            x =  self._eval_1D (self._cpx, u)
            # print ("y: ",y, "  x evaluated ", x)

            # cache value - only not fast
            self._x_on_y_cache [y] = x

        return x


    def curvature (self, u):
        """
        Compute curvature along the curve.

        Args:
            u: Scalar or array of parameter values in ``[0, 1]``.

        Returns:
            float | np.ndarray: Signed curvature values.
        """

        dx,  dy  = self.eval (u, der=1)
        ddx, ddy = self.eval (u, der=2)

        c = (ddy * dx - ddx * dy) / (dx ** 2 + dy ** 2) ** 1.5
        return c


    def curvature_at_0 (self) -> float:
        """Leading-edge curvature under the vertical-tangent assumption.

        Assumes ``cpx[0] == cpx[1]`` and at least three control points, so the
        closed-form expression for ``u = 0`` applies.
        """
        n    = self.ncp - 1                                         # degree
        h    = self._cpy[1] - self._cpy[0]
        curv = (n - 1) * self._cpx[2] / (n * h ** 2)
        return curv


    def deriv2 (self, u):
        """
        Compute the numerator term used in curvature-based penalties.

        Args:
            u: Scalar or array of parameter values in ``[0, 1]``.

        Returns:
            float | np.ndarray: ``ddy * dx - ddx * dy`` evaluated at ``u``.
        """

        dx,  dy  = self.eval (u, der=1)
        ddx, ddy = self.eval (u, der=2)

        deriv2 = ddy * dx - ddx * dy
        return deriv2  

    @staticmethod
    def _smooth_weight_function(x, a=3.0, b=0.2, mode='cosine'):
        """
        Smooth weighting function that transitions from weight 'a' at x=0 to 1.0 at x=b
        
        Args:
            x: array_like - x coordinates (normalized, typically 0..1)
            a: float - weight at x=0 (LE), should be > 1.0 (default: 3.0)
            b: float - x position where weight reaches 1.0 (default: 0.2)
            mode: str - interpolation type:
                'exponential' - smooth exponential decay
                'cosine' - cosine-based smooth transition (default)
                'polynomial' - cubic polynomial (smooth acceleration)
                'power' - power law decay
        
        Returns:
            weights: array_like - weight values, a at x=0, declining to 1.0 at x=b and beyond
        
        Examples:
            weights = _smooth_weight_function(x, a=3.0, b=0.2)  # 3x weight at LE, 1x at x>0.2
        """
        x = np.asarray(x)
        weights = np.ones_like(x, dtype=float)
        
        # Only apply weighting in region [0, b]
        mask = x <= b
        x_scaled = x[mask] / b  # Scale to [0, 1] in the weighted region
        
        if mode == 'exponential':
            # Exponential decay: w = 1 + (a-1) * exp(-k*x/b)
            # Solve for k so that w(b) ≈ 1.0
            k = -np.log(0.01) / 1.0  # At x/b=1, decay to ~1% of (a-1)
            weights[mask] = 1.0 + (a - 1.0) * np.exp(-k * x_scaled)
        
        elif mode == 'cosine':
            # Cosine transition: w = 1 + (a-1) * (1 + cos(π*x/b)) / 2
            weights[mask] = 1.0 + (a - 1.0) * (1.0 + np.cos(np.pi * x_scaled)) / 2.0
        
        elif mode == 'polynomial':
            # Smooth cubic polynomial: w = 1 + (a-1) * (1 - x/b)³
            weights[mask] = 1.0 + (a - 1.0) * (1.0 - x_scaled) ** 3
        
        elif mode == 'power':
            # Power law: w = 1 + (a-1) * (1 - x/b)^p
            p = 2.0  # Can be adjusted for steepness
            weights[mask] = 1.0 + (a - 1.0) * (1.0 - x_scaled) ** p
        
        else:
            raise ValueError(f"Unknown weight mode: {mode}")
        
        return weights

    @classmethod
    def fit_curve(cls, x_data, y_data, ncp=5, 
                  le_tangent_vertical=False,
                  le_weight=4.0,
                  le_weight_distance=0.15) -> list[tuple]:
        """
        Fit Bezier curve to data using least-squares
        
        Fits a Bezier curve with fixed endpoints using chord-length parameterization.
        Note: Bezier curves are global (moving one control point affects entire curve),
        so use fewer control points than B-splines (typically 4-6 for airfoils).
        
        Args:
            x_data, y_data: array_like - data points to fit
            ncp: int - number of control points (default: 5)
            le_tangent_vertical: bool - enforce vertical tangent at LE (default: False)
            le_weight: float - weight at LE (default: 4.0)
            le_weight_distance: float - x position where weight transitions to 1 (default: 0.15)
        Returns:
            Control points of fitted Bezier as list of tuples (x, y)
        """
        x_data = np.array(x_data)
        y_data = np.array(y_data)
        n_data = len(x_data)
        
        if n_data < 4:
            raise ValueError("Bezier.fit_curve: Need at least 4 data points")
        
        if ncp < 2:
            raise ValueError("Bezier.fit_curve: Need at least 2 control points")
        
        # Fixed endpoints
        x_le, y_le = x_data[0], y_data[0]
        x_te, y_te = x_data[-1], y_data[-1]

        # Compute chord-length distances
        distances = np.sqrt(np.diff(x_data)**2 + np.diff(y_data)**2)

        # Apply smooth weighting function
        weights = cls._smooth_weight_function(x_data, a=le_weight, b=le_weight_distance, mode='power')
        
        # Apply weights to distances (average weights at edges)
        weighted_distances = distances * (weights[:-1] + weights[1:]) / 2.0

        chord_lengths = np.concatenate(([0], np.cumsum(weighted_distances)))
        total_length = chord_lengths[-1]
        if total_length > 0:
            u_data = chord_lengths / total_length
        else:
            u_data = np.linspace(0, 1, n_data)
        
        u_data[0] = 0.0
        u_data[-1] = 1.0
        
        # Build Bernstein basis matrix
        degree = ncp - 1
        B = np.zeros((n_data, ncp))
        for i, u in enumerate(u_data):
            for j in range(ncp):
                B[i, j] = Bezier._basisFunction(degree, j, u)
        
        # Solve constrained least-squares for x control points
        if le_tangent_vertical and ncp > 2:
            # Fix P0, P1 at x_le, and P_last at x_te
            B_fixed = B[:, [0, 1, -1]]
            B_free = B[:, 2:-1]
            x_fixed = np.array([x_le, x_le, x_te])
            rhs_x = x_data - B_fixed @ x_fixed
            x_free = np.linalg.lstsq(B_free, rhs_x, rcond=None)[0]
            x_cp = np.concatenate([[x_le, x_le], x_free, [x_te]])
        else:
            # Fix only P0 and P_last
            B_fixed = B[:, [0, -1]]
            B_free = B[:, 1:-1]
            x_fixed = np.array([x_le, x_te])
            rhs_x = x_data - B_fixed @ x_fixed
            x_free = np.linalg.lstsq(B_free, rhs_x, rcond=None)[0]
            x_cp = np.concatenate([[x_le], x_free, [x_te]])
        
        # Solve constrained least-squares for y control points
        B_fixed_y = B[:, [0, -1]]
        B_free_y = B[:, 1:-1]
        y_fixed = np.array([y_le, y_te])
        rhs_y = y_data - B_fixed_y @ y_fixed
        y_free = np.linalg.lstsq(B_free_y, rhs_y, rcond=None)[0]
        y_cp = np.concatenate([[y_le], y_free, [y_te]])
        
        return list(zip(x_cp, y_cp))


    # -------------  end public --------------------


    def _eval_1D (self, pxy, u, der=0):
        #
        #                    Bezier Core
        #
        # evaluates self at u with control point coordinates x or y
        #   pxy:  either x or y coordinates of the bezier control points
        #   u:    Scalar or an array of normed arc length 0..1 at which to return bezier value
        #   der:  optional derivative - either 0,1 or 2 

        if u is None or (np.isscalar(u) and (u > 1.0 or u < 0.0)):
            raise ValueError ("Bezier: parameter u = %s not valid " %u)
        
        # init result (array)
        if np.isscalar(u):
            # optimize for end points 
            if u == 0.0 and der == 0:
                return pxy[0]
            elif u == 1.0 and der == 0:
                return pxy[-1]
            else:
                bezier = 0.0 
            
        else: 
            bezier = np.zeros (np.size(u))

        # http://math.aalto.fi/~ahniemi/hss2012/Notes06.pdf

        start = timer()

        n = np.size(pxy) - 1                            # n - degree of Bezier 
        weights = deepcopy(pxy)                         # der = 0: weights = points 
        if der > 0:                                     
            weights = np.ediff1d(weights) * n           # new weight = difference * n 
            n = n - 1                                   # lower 1 degree 
        if der > 1:                                     # derivative 2  
            weights = np.ediff1d(weights) * n           # new weight = difference * n                           
            n = n - 1                                   # lower 1 degree 
        if der > 2:                                     # derivative 3  
            weights = np.ediff1d(weights) * n           # new weight = difference * n                           
            n = n - 1                                   # lower 1 degree 

        # test self.basisFn = []   
    
        for i in range (len(weights)):
            
            # collect bernstein Polynomial self.basisFn.append (basisFunction(n, i, u))  

            bezier += Bezier._basisFunction(n, i, u) * weights[i] 

        n = len(u) if not np.isscalar(u) else 1
        logger.debug(f"Bezier eval 1D: nu={n}, der={der}, time={timer() - start:.6f}s")

        return bezier



#------------ Hicks Henne  -----------------------------------

# although Hicks Henne bump functions are no 'splines' it is implemented here for 
#    not to have an extra module   


# class for evaluating a single hicks henne function  

class HicksHenne: 
    """
    Hicks Henne function defined by strength, location and width  
    """

    def __init__ (self, strength : float, location : float, width : float):
        """
        Hicks Henne function defined by strength, location and width 
        """

        self._strength = strength                         
        self._location = location
        self._width    = width

        self._x  = None                         # cached x,y results
        self._y  = None


    @property
    def strength (self) -> float: 
        return self._strength 

    @property
    def location (self) -> float: 
        return self._location 

    @property
    def width (self) -> float: 
        return self._width 



    def eval (self, x):
        """
        Evaluate self. Results will be cached for same x  

        Parameters
        ----------
        x :   Scalar or an array of x 0..1 at which to return the value of hh

        Returns
        -------
        y : Scalar or an array representing the evaluated values
        """

        if np.array_equal (x, self._x) and (not self._x is None) :
            y = self._y 
        else: 
            y = self._eval_y (x)

        if not np.isscalar(x):      
            self._x = x
            self._y = y
        return y


    def _eval_y (self, x):
        #
        #                Hicks Henne Core
        #

        if x is None or (np.isscalar(x) and (x > 1.0 or x < 0.0)):
            raise ValueError ("Hicks Henne: x = %s not valid " %x)

        # init result (array)
        if np.isscalar(x):
            y = 0.0
        else: 
            y = np.zeros (np.size(x))

        t1 = self._location
        t2 = self._width
        st = self._strength

        t1 = min (t1, 0.999)
        t1 = max (t1, 0.001)
        t2 = max (t2, 0.01)
        power = math.log10 (0.5) / math.log10 (t1)

        # eval Hicks Henne - Fortran: y(i) = st * sin (pi * x(i) **power)**t2

        y = st * np.power (np.sin ( math.pi * np.power(x, power)), t2)
        y = np.round (y, 10)

        return y



# ------------ test functions - to activate  -----------------------------------


# def test_Bezier_for_Fortran (): 
    
#     # to compare with fortran bezier implementation 
#     px = [   0,  0.0, 0.3,   1]
#     py = [   0, 0.06, 0.12,  0]
#     u  = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    
#     # u = np.linspace( 0, 1 , 200)

#     bez = Bezier (px, py)
#     x,y = bez.eval(u)
#     checksum = np.sum(x) + np.sum(y) 
#     print_array_compact (u, header="u")
#     print_array_compact (x, header="x")
#     print_array_compact (y, header="y")
#     print ("checksum: %10.6f" %checksum)
#     print ()

#     print ("1st derivative")
#     dx,dy = bez.eval(u, der=1)
#     checksum = np.sum(dx) + np.sum(dy) 
#     print_array_compact (dx, header="dx")
#     print_array_compact (dy, header="dy")
#     print ("checksum: %10.6f" %checksum)

#     print ("eval_y_on_x")
#     x = np.linspace( 0, 1 , 10)
#     y = np.zeros (len(x))
#     for i,xi in enumerate (x):
#         y[i] = bez.eval_y_on_x (xi)
#     print_array_compact (x, header="x fast")
#     print_array_compact (y, header="y fast")
#     for i,xi in enumerate (x):
#         y[i] = bez.eval_y_on_x (xi, fast=False)
#     print_array_compact (x, header="x exct")
#     print_array_compact (y, header="y exct")
#     checksum = np.sum(x) + np.sum(y) 
#     print ("checksum: %10.6f" %checksum)

#     from timeit import default_timer as timer
#     start = timer()
#     x = np.linspace( 0, 1 , 1000)
#     y = np.zeros (len(x))
#     for i,xi in enumerate (x):
#         y[i] = bez.eval_y_on_x (xi)
#     end = timer()
#     print("Time ", end - start)  



#------------ B-Spline -----------------------------------

class BSpline:
    """
    B-Spline curve defined by control points
         - provides local control with smoothness
         - supports fitting airfoil coordinates with fewer points
    """

    def __init__(self, cpx_or_cp, cpy=None, degree=4, knots=None):
        """
        Initialize a B-spline from control-point coordinates.

        Args:
            cpx_or_cp: x coordinates or an iterable of ``(x, y)`` control points.
            cpy: y coordinates when ``cpx_or_cp`` contains only x values.
            degree: Spline degree. If ``None``, derive it from ``knots`` or default to 3.
            knots: Optional knot vector. If omitted, generate a uniform clamped vector.
        """
        self._cpx = None
        self._cpy = None
        self._degree = degree
        self._knots  = np.asarray(knots) if knots is not None else None

        self._seg_polynom    = None                     # cached polynomial coefficients for each segment
        self._seg_polynom_d1 = None
        self._seg_polynom_d2 = None
        self._seg_starts     = None

        self._clear_cache()

        self.set_cpoints(cpx_or_cp, cpy)


    def _clear_cache(self):
        """Reset cached curve evaluations and lookup helpers."""
        self._x,   self._y    = None, None                          # cached evaluation results
        self._dx,  self._dy   = None, None
        self._ddx, self._ddy  = None, None
        self._u     = None                           
        self._y_on_x_cache = {}


    def _generate_uniform_knots(self):
        """
        Generate a uniform clamped knot vector for the current control points.

        Returns:
            ndarray: Knot vector of length ``ncp + degree + 1``.
        """
        n = len(self._cpx)  # number of control points
        k = self._degree
        
        # Total number of knots: n + k + 1
        num_knots = n + k + 1
        
        # Create clamped knot vector: [0,0,0,...,1,2,3,...,1,1,1]
        knots = np.zeros(num_knots)
        
        # Repeat 0 at the beginning (k+1 times)
        # Repeat max value at the end (k+1 times)
        # Linear spacing in between
        
        if num_knots > 2 * (k + 1):
            # Interior knots
            num_interior = num_knots - 2 * (k + 1)
            knots[k+1:k+1+num_interior] = np.linspace(0, 1, num_interior + 2)[1:-1]
        
        # Last k+1 knots are 1
        knots[-(k+1):] = 1.0
        
        return np.round (knots,10)          # round to avoid numerical issues


    def _basis_function(self, i, k, u, der=0):
        """
        Evaluate a B-spline basis function or its derivative via Cox-de Boor recursion.

        Args:
            i: Basis-function index.
            k: Basis-function degree.
            u: Parameter value in ``[0, 1]``.
            der: Derivative order ``0``, ``1``, or ``2``.

        Returns:
            float: Basis-function value or derivative at ``u``.
        """
        knots = self._knots
        n = len(self._cpx)
        n_knots = len(knots)
        
        # Check if index is out of valid range for basis functions
        # Valid basis functions are N_{i,k} for i in [0, n-1]
        if i < 0 or i >= n:
            return 0.0
        
        # Check if required knot indices are valid
        # For basis function N_{i,k}, we need knots[i] through knots[i+k+1]
        if i + k + 1 >= n_knots:
            return 0.0
        
        # Base cases
        if k == 0:
            # Closed interval at the end: include u == last knot for last basis
            if u == knots[-1] and i == n - 1:
                return 1.0 if der == 0 else 0.0
            return 1.0 if knots[i] <= u < knots[i+1] else 0.0 if der == 0 else 0.0
        
        if der == 0:
            # Basis function value
            # Recursive case
            denom1 = knots[i+k] - knots[i]
            term1 = 0.0
            if denom1 != 0.0:
                term1 = ((u - knots[i]) / denom1) * self._basis_function(i, k-1, u, der=0)
            
            denom2 = knots[i+k+1] - knots[i+1]
            term2 = 0.0
            if denom2 != 0.0:
                term2 = ((knots[i+k+1] - u) / denom2) * self._basis_function(i+1, k-1, u, der=0)
            
            return term1 + term2
        
        elif der == 1:
            # First derivative: N'_{i,k}(u) = k * [N_{i,k-1}(u)/(t_{i+k}-t_i) - N_{i+1,k-1}(u)/(t_{i+k+1}-t_{i+1})]
            denom1 = knots[i+k] - knots[i]
            term1 = 0.0
            if denom1 != 0.0:
                term1 = k * self._basis_function(i, k-1, u, der=0) / denom1
            
            denom2 = knots[i+k+1] - knots[i+1]
            term2 = 0.0
            if denom2 != 0.0:
                term2 = k * self._basis_function(i+1, k-1, u, der=0) / denom2
            
            return term1 - term2
        
        elif der == 2:
            # Second derivative: N''_{i,k}(u) = k * [N'_{i,k-1}(u)/(t_{i+k}-t_i) - N'_{i+1,k-1}(u)/(t_{i+k+1}-t_{i+1})]
            if k < 2:
                return 0.0
            
            denom1 = knots[i+k] - knots[i]
            term1 = 0.0
            if denom1 != 0.0:
                term1 = k * self._basis_function(i, k-1, u, der=1) / denom1
            
            denom2 = knots[i+k+1] - knots[i+1]
            term2 = 0.0
            if denom2 != 0.0:
                term2 = k * self._basis_function(i+1, k-1, u, der=1) / denom2
            
            return term1 - term2
        
        else:
            return 0.0


    @staticmethod
    def _poly_add(a : np.ndarray, b : np.ndarray) -> np.ndarray:
        """Add two polynomials stored in descending-power coefficient order."""
        if len(a) < len(b):
            a, b = b, a
        out = a.copy()
        out[-len(b):] += b
        return out


    @staticmethod
    def _poly_mul(a : np.ndarray, b : np.ndarray) -> np.ndarray:
        """Multiply two polynomials stored in descending-power coefficient order."""
        out = np.zeros(len(a) + len(b) - 1)
        for i in range(len(a)):
            out[i:i+len(b)] += a[i] * b
        return out


    @staticmethod
    def _eval_horner(coeffs : np.ndarray, tau: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Evaluate vector-valued polynomials using Horner's method."""
        pxy = np.zeros((len(tau), coeffs.shape[2]))
        for i_coeff in range(coeffs.shape[1]):
            pxy = pxy * tau[:, None] + coeffs[:, i_coeff, :]
        return pxy[:, 0], pxy[:, 1]


    def _segment_basis_polynomials (self, seg : int) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute all non-zero basis polynomials on a knot span in normalized tau ∈ [0,1].

        Returns:
            active_indices: ndarray of active basis indices for the span
            basis_coeffs: ndarray with shape (degree + 1, degree + 1), one row per
                          active basis, coefficients in descending-power order
        """
        knots  = self.knots
        degree = self.degree
        t0 = knots[seg]
        t1 = knots[seg + 1]
        dt = t1 - t0

        if np.isclose(dt, 0.0):
            return np.array([], dtype=int), np.empty((0, degree + 1))

        # On span `seg`, the degree-0 basis is just 1 for the rightmost active basis.
        basis = {seg: np.array([1.0])}

        for current_degree in range(1, degree + 1):
            next_basis = {}
            for i in range(seg - current_degree, seg + 1):
                poly = np.array([0.0])

                # Lift the two contributing lower-degree basis polynomials to the next degree.
                left_basis = basis.get(i)
                denom1 = knots[i + current_degree] - knots[i]
                if left_basis is not None and denom1 != 0.0:
                    factor1 = np.array([
                        dt / denom1,
                        (t0 - knots[i]) / denom1,
                    ])
                    poly = self._poly_mul(factor1, left_basis)

                right_basis = basis.get(i + 1)
                denom2 = knots[i + current_degree + 1] - knots[i + 1]
                if right_basis is not None and denom2 != 0.0:
                    factor2 = np.array([
                        -dt / denom2,
                        (knots[i + current_degree + 1] - t0) / denom2,
                    ])
                    poly_right = self._poly_mul(factor2, right_basis)
                    poly = self._poly_add(poly, poly_right)

                next_basis[i] = poly

            basis = next_basis

        # Return the active basis functions on this span in control-point order.
        active_indices = np.arange(seg - degree, seg + 1, dtype=int)
        basis_coeffs = np.zeros((degree + 1, degree + 1))
        for row, i in enumerate(active_indices):
            coeff = basis.get(i, np.array([0.0]))
            basis_coeffs[row, -len(coeff):] = coeff

        return active_indices, basis_coeffs


    def _polynomial_deriv (self, coeffs : np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute first- and second-derivative coefficient arrays.

        Args:
            coeffs: Polynomial coefficients with shape ``(degree + 1, dim)`` in
                descending-power order.

        Returns:
            tuple[np.ndarray, np.ndarray]: First- and second-derivative coefficients.
        """
        degree = coeffs.shape[0] - 1

        if degree <= 0:
            d1 = np.zeros((1, coeffs.shape[1]))
            d2 = np.zeros((1, coeffs.shape[1]))
            return d1, d2

        powers = np.arange(degree, 0, -1)[:, None]
        d1 = coeffs[:-1] * powers

        if degree >= 2:
            powers2 = np.arange(degree - 1, 0, -1)[:, None]
            d2 = d1[:-1] * powers2
        else:
            d2 = np.zeros((1, coeffs.shape[1]))

        return d1, d2


    def _build_segments (self):
        """
        Build cached polynomial coefficients for each non-zero knot span.
        """

        cp     = np.column_stack((self._cpx, self._cpy)) if self._cpx is not None else np.empty((0, 2))
        knots  = self.knots
        degree = self.degree

        if cp.size == 0:
            empty = np.empty((0, degree + 1, 0))
            empty_d1 = np.empty((0, max(degree, 1), 0))
            empty_d2 = np.empty((0, max(degree - 1, 1), 0))
            return empty, empty_d1, empty_d2, np.array([], dtype=int)
        max_span = len(knots) - degree - 2

        segments = []
        segments_d1 = []
        segments_d2 = []
        segment_starts = []

        for seg in range(degree, max_span + 1):
            t0 = knots[seg]
            t1 = knots[seg+1]
            dt = t1 - t0
            if np.isclose(dt, 0.0):
                continue

            # First build the active basis polynomials on this span, then combine
            # them with the active control points to get x(tau), y(tau).
            active_indices, basis_coeffs = self._segment_basis_polynomials(seg)
            coeff = basis_coeffs.T @ cp[active_indices]
            d1, d2 = self._polynomial_deriv(coeff)

            segments.append(coeff)
            segments_d1.append(d1)
            segments_d2.append(d2)
            segment_starts.append(seg)

        if not segments:
            segments       = np.empty((0, degree + 1, cp.shape[1]))
            segments_d1    = np.empty((0, max(degree, 1), cp.shape[1]))
            segments_d2    = np.empty((0, max(degree - 1, 1), cp.shape[1]))
            segment_starts = np.array([], dtype=np.intp)

        self._seg_polynom    = np.array(segments)
        self._seg_polynom_d1 = np.array(segments_d1)
        self._seg_polynom_d2 = np.array(segments_d2)
        # Ensure _seg_starts is always a proper 1D array with platform integer type for indexing
        self._seg_starts     = np.asarray(segment_starts, dtype=np.intp).ravel()


    @property
    def cpoints(self) -> np.ndarray[tuple]:
        """Control points as an ``(n, 2)`` array."""
        if self._cpx is not None and self._cpy is not None:
            return np.array(list(zip(self._cpx, self._cpy)))
        return np.array([])
    
    @property
    def ncp(self) -> int:
        """Number of control points."""
        return len(self._cpx) if self._cpx is not None else 0
    
    @property
    def cpoints_x(self) -> list[float]:
        """x coordinates of the control points."""
        return list(self._cpx) if self._cpx is not None else []
    
    @property
    def cpoints_y(self) -> list[float]:
        """y coordinates of the control points."""
        return list(self._cpy) if self._cpy is not None else []
    
    @property
    def degree(self) -> int:
        """Spline degree."""
        return self._degree
    
    @property
    def knots(self) -> np.ndarray:
        """Knot vector."""
        return self._knots


    @property
    def is_uniform (self) -> bool:
        """Whether the knot vector matches the uniform clamped form."""
        if self._knots is None:
            return True
        expected_knots = self._generate_uniform_knots()
        return np.array_equal(self._knots, expected_knots)


    @property
    def has_u (self) -> bool:
        """Whether an evaluation cache exists for parameter values ``u``."""
        return  self._u is not None
    

    def set_cpoints(self, cpx_or_cp, cpy=None):
        """
        Set or replace all control points.

        Args:
            cpx_or_cp: x coordinates or an iterable of ``(x, y)`` control points.
            cpy: y coordinates when ``cpx_or_cp`` contains only x values.
        """
        if cpy is None:  # tuples provided
            cpx_or_cp = list(cpx_or_cp)
            self._cpx = np.array([p[0] for p in cpx_or_cp])
            self._cpy = np.array([p[1] for p in cpx_or_cp])
        else:
            self._cpx = np.array(cpx_or_cp)
            self._cpy = np.array(cpy)

        self._cpx = np.round(self._cpx, 10)  # round to avoid numerical issues
        self._cpy = np.round(self._cpy, 10)

        # Validate
        n = len(self._cpx)
        if n < 4:
            raise ValueError('BSpline: Must have at least 4 control points')
        if len(self._cpy) != n:
            raise ValueError('BSpline: Length of x,y coordinates must be equal')
        
        # Derive degree from knots if degree not specified
        # Relationship: m = n + k + 1  =>  k = m - n - 1
        knots_were_provided = self._knots is not None
        if knots_were_provided and self._degree is None:
            m = len(self._knots)
            self._degree = m - n - 1
        elif self._degree is None:
            self._degree = 3  # default degree
        
        # Validate and adjust degree
        original_degree = self._degree
        if self._degree >= n:
            self._degree = max(1, n - 1)
        
        # Generate or regenerate knot vector
        # Regenerate if: no knots provided, or degree was adjusted, or knots don't match expected length
        expected_knot_length = n + self._degree + 1
        needs_new_knots = (self._knots is None or 
                          original_degree != self._degree or 
                          len(self._knots) != expected_knot_length)
        
        if needs_new_knots:
            self._knots = self._generate_uniform_knots()
        
        self._clear_cache()
        self._build_segments()
    

    def set_cpoint (self, iPoint: int, cpx_or_cp: tuple|float, cpy: float|None=None):
        """
        Update one control point in place.

        Args:
            iPoint: Index of the control point to update.
            cpx_or_cp: Either an ``(x, y)`` tuple or the x value.
            cpy: y value when ``cpx_or_cp`` contains only x.
        """
        if self._cpx is None:
            raise ValueError("BSpline: No points defined - can't set point %d" % iPoint)
        
        n = len(self._cpx)
        if iPoint >= n or iPoint < -n:
            raise ValueError('BSpline: Point index %d is outside valid range [0, %d]' % (iPoint, n-1))
        
        # Extract coordinates
        if cpy is None:
            cpx, cpy = cpx_or_cp
        else:
            cpx = cpx_or_cp
        
        cpx = round(cpx, 10)  # round to avoid numerical issues
        cpy = round(cpy, 10)

        # Only update if changed
        if self._cpx[iPoint] != cpx or self._cpy[iPoint] != cpy:
            self._cpx[iPoint] = cpx
            self._cpy[iPoint] = cpy
            
            self._clear_cache()
            self._build_segments()


    def _eval_u_on_x(self, x, u0=None, epsilon=1e-10):
        """
        Find parameter u for a given x-coordinate using Newton iteration.
        
        Args:
            x: Target x-coordinate.
            u0: Optional initial guess for Newton iteration.
            epsilon: Convergence tolerance.
            
        Returns:
            float: Parameter value u in [0, 1] where the curve has x-coordinate x.
        """
        # Handle endpoints
        if x <= self._cpx[0]:
            return 0.0
        elif x >= self._cpx[-1]:
            return 1.0
        
        # Determine initial guess
        if u0 is None:
            u0 = x if 0.05 <= x <= 0.95 else (0.05 if x < 0.05 else 0.95)
        else:
            u0 = np.clip(u0, 0.0, 1.0)
        
        # Newton iteration to find u where curve x-coordinate equals target x
        try:
            u, _ = newton(lambda u: self.eval(u)[0] - x,
                         lambda u: self.eval(u, der=1)[0] + 1e-12, u0,
                         epsilon=epsilon, max_iter=20, bounds=(0.0, 1.0))
        except:
            raise ValueError(f"BSpline: Could not find parameter u for x={x}.")
        return u


    def insert_knot (self, x):
        """
        Insert a new knot at x-coordinate without changing the curve shape.
        
        Uses knot insertion (Boehm's algorithm) to add a new control point and knot
        while preserving the exact curve geometry.
        
        Args:
            x: x-coordinate where to insert the new knot.
        """
        # Find parameter u for the given x
        u = self._eval_u_on_x(x)
        
        # Find knot span that contains u
        knots = self._knots
        degree = self._degree
        k = degree  # default span
        for i in range(degree, len(knots) - degree - 1):
            if knots[i] <= u < knots[i + 1]:
                k = i
                break
        
        # Boehm's knot insertion algorithm
        # Insert u into knot vector
        new_knots = np.insert(knots, k + 1, u)
        
        # Calculate new control points
        n = len(self._cpx)
        new_cpx = np.zeros(n + 1)
        new_cpy = np.zeros(n + 1)
        
        for i in range(n + 1):
            if i <= k - degree:
                # Control points before affected region stay the same
                new_cpx[i] = self._cpx[i]
                new_cpy[i] = self._cpy[i]
            elif i > k:
                # Control points after affected region stay the same
                new_cpx[i] = self._cpx[i - 1]
                new_cpy[i] = self._cpy[i - 1]
            else:
                # Affected control points: blend between neighbors
                alpha_denom = knots[i + degree] - knots[i]
                if abs(alpha_denom) < 1e-10:
                    alpha = 0.0
                else:
                    alpha = (u - knots[i]) / alpha_denom
                
                new_cpx[i] = alpha * self._cpx[i] + (1.0 - alpha) * self._cpx[i - 1]
                new_cpy[i] = alpha * self._cpy[i] + (1.0 - alpha) * self._cpy[i - 1]
        
        # Update knots first, then use set_cpoints to update control points
        self._knots = np.round(new_knots, 10)
        self.set_cpoints(new_cpx, new_cpy)


    def remove_cpoint(self, index):
        """
        Remove a control point at the given index.
        
        Note: This will change the curve shape. The curve is approximated
        by the remaining control points.
        
        Args:
            index: Index of the control point to remove (0-based).
        """
        n = len(self._cpx)
        
        # Validate index
        if index < 0 or index >= n:
            raise ValueError(f"BSpline: Index {index} out of range [0, {n-1}]")
        
        # Need at least degree+1 control points
        if n <= self._degree + 1:
            raise ValueError(f"BSpline: Cannot remove control point. "
                           f"Need at least {self._degree + 1} control points for degree {self._degree}")
        
        # Remove control point
        new_cpx = np.delete(self._cpx, index)
        new_cpy = np.delete(self._cpy, index)
        
        # Remove corresponding knot (remove from the middle section, preserving clamped structure)
        # For a clamped B-spline, remove knot at position index + degree
        knot_index = min(index + self._degree, len(self._knots) - self._degree - 2)
        new_knots = np.delete(self._knots, knot_index)
        
        # Update knots first, then use set_cpoints
        self._knots = np.round(new_knots, 10)
        self.set_cpoints(new_cpx, new_cpy)


    def _eval_polynomials (self,u, der=0):
        """
        Evaluate the cached span polynomials or their derivatives.

        Args:
            u: Scalar or array of parameter values.
            der: Derivative order ``0``, ``1``, or ``2``.

        Returns:
            tuple[np.ndarray | float, np.ndarray | float]: x and y values for ``u``.
        """
        start = timer()

        scalar_input = np.isscalar(u)
        u = np.atleast_1d(np.asarray(u, dtype=float))

        knots  = self.knots
        segment_starts = self._seg_starts
        segments    = self._seg_polynom
        segments_d1 = self._seg_polynom_d1
        segments_d2 = self._seg_polynom_d2

        if len(segments) == 0 or len(segment_starts) == 0:
            dim = self.cpoints.shape[1] if self.cpoints.ndim == 2 else 0
            empty = np.empty((len(u), dim))
            if scalar_input:
                return empty[0, 0], empty[0, 1]
            return empty[:, 0], empty[:, 1]

        # Each u-value is mapped to its cached knot span and normalized to local tau.
        segment_knots = knots[segment_starts]
        
        # For each u, find which segment: count how many segment_knots are <= u
        segment_index = np.sum(segment_knots <= u[:, None], axis=1) - 1
        segment_index = np.clip(segment_index, 0, len(segment_starts) - 1)
        
        # Get the actual segment indices
        seg = segment_starts[segment_index]

        # Use array indexing for both t0 and t1
        t0 = knots[seg]
        t1 = knots[np.clip(seg + 1, 0, len(knots) - 1)]
        dt = t1 - t0
        tau = np.where(dt > 0, (u - t0) / dt, 0.0)
        tau = np.clip(tau, 0.0, 1.0)

        # Evaluate the cached polynomial (or derivative polynomial) on each span.
        if der == 0:
            coeffs = segments[segment_index]
            x,y =  self._eval_horner(coeffs, tau)
        elif der == 1:
            coeffs = segments_d1[segment_index]
            x,y = self._eval_horner(coeffs, tau)
            x /= dt
            y /= dt
        elif der == 2:
            coeffs = segments_d2[segment_index]
            x,y = self._eval_horner(coeffs, tau)
            x /= dt * dt
            y /= dt * dt
        else:
            raise ValueError("der must be 0, 1, or 2")
        
        logger.debug(f"B-Spline eval: der={der}, nu={len(u):3},  time={timer() - start:.6f}s")

        x,y = np.round(x, 10), np.round(y, 10)              # round to avoid numerical issues

        if scalar_input:
            return x[0], y[0]

        return x, y


    def eval(self, u, der=0, update_cache=True):
        """
        Evaluate the spline or one of its derivatives.

        Args:
            u: Scalar or array of parameter values in ``[0, 1]``.
            der: Derivative order ``0``, ``1``, or ``2``.
            update_cache: Cache array results for reuse.

        Returns:
            tuple[float, float] | tuple[np.ndarray, np.ndarray]: Evaluated x and y values.
        """
        x, y = None, None

        # use cache if available

        if np.array_equal (u, self._u):
            if der == 0 and self._x is not None and self._y is not None:
                x, y = self._x, self._y
            elif der == 1 and self._dx is not None and self._dy is not None:
                x, y = self._dx, self._dy
            elif der == 2 and self._ddx is not None and self._ddy is not None:
                x, y = self._ddx, self._ddy

        # evaluate if not cached

        if x is None or y is None:

            x,y = self._eval_polynomials(u, der=der)  

            if update_cache and not np.isscalar(u):
                self._clear_cache()  # clear any previous cache if u has changed
                self._u = u 
                if der == 0:         # cache result for der=0 if u is array
                    self._x, self._y = x, y
                elif der == 1:       # cache result for der=1 if u is array
                    self._dx, self._dy = x, y
                elif der == 2:       # cache result for der=2 if u is array
                    self._ddx, self._ddy = x, y
        
        return x, y


    def eval_y_on_x (self, x, u0=None, epsilon=10e-10, fast=False):
        """
        Evaluate ``y`` for a given x coordinate on the spline.

        Use Newton iteration to solve ``x(u) = x`` and then evaluate ``y(u)``.
        When ``fast=True`` and a cached curve sample is available, fall back to a
        linearized lookup based on that cache.

        Args:
            x: Target x coordinate.
            u0: Optional initial guess for Newton iteration.
            epsilon: Convergence tolerance passed to ``newton``.
            fast: Use cached linear interpolation when possible.

        Returns:
            float: y coordinate at the requested x location.
        """

        # check for cached value 
        try:
            y = self._y_on_x_cache [x]
            return y
        except: 
            pass

        if fast and (not self._x is None) and (x >= self._x[0] and x <= self._x[-1]):

            # find closest index
            i = min(bisect.bisect(self._x, x)-1, len(self._x) -2)

            if self._x[i] == x:                         # we have it already exactly 
                return self._y[i]

            # interpolate u 
            u = ((self._u[i+1]-self._u[i])/(self._x[i+1]-self._x[i])) * (x - self._x[i]) + self._u[i]

            # evaluate y from u 
            y =  self.eval (u)[1]

        else:
            if x == self.eval(0.0)[0]:    # avoid numerical issues of Newton 
                u = 0.0
            else: 

                # start value for newton iteration - either given or based on x value
                if u0 is not None:
                    u0 = max(0.0, min(1.0, u0))  # clamp to [0, 1]
                else:
                    if x < 0.05:                        # good start value für newton iteration 
                        u0 = 0.05
                    elif x > 0.95:
                        u0 = 0.95
                    else: 
                        u0 = x                          # first estimation 

                # find u value for x
                # Add small epsilon to derivative to avoid division by zero when curve is vertical
                u, niter  = newton (lambda u: self.eval(u)[0] - x,
                            lambda u: self.eval(u, der=1)[0] + 1e-12 , u0, 
                            epsilon=epsilon, max_iter=20, bounds=(0.0,1.0))

                # print iteration info if needed
                # print(f"Newton iteration: {niter}, u: {u:.6f}, x: {x_target:.6f}")

            # eval y for u value
            _, y =  self.eval(u)

            # cache value - only not fast
            self._y_on_x_cache [x] = y


        return y


    def curvature(self, u):
        """
        Compute curvature along the spline.

        Args:
            u: Scalar or array of parameter values in ``[0, 1]``.

        Returns:
            float | np.ndarray: Signed curvature values.
        """
        
        # Get first and second derivatives
        dx, dy   = self.eval(u, der=1)
        ddx, ddy = self.eval(u, der=2)
        
        # Curvature formula: κ = (x'y'' - y'x'') / (x'^2 + y'^2)^(3/2)
        numerator = dx * ddy - dy * ddx
        denominator = (dx**2 + dy**2)**1.5
        
        # Handle division by zero
        if np.isscalar(u):
            kappa = numerator / denominator if denominator > 1e-10 else 0.0
        else:
            kappa = np.where(denominator > 1e-10, numerator / denominator, 0.0)
        
        return kappa



    @staticmethod
    def _power_parameterization(x, y, le_exponent=0.5, te_exponent=1.0):
        """
        Build a power-law parameterization from the x distribution.

        This keeps a uniform clamped knot vector while concentrating parameter
        resolution near the leading or trailing edge.
        
        Args:
            x: x coordinates of the sample points.
            y: Unused placeholder kept for signature symmetry with callers.
            le_exponent: Leading-edge clustering exponent. Values below 1 cluster
                more strongly near the leading edge.
            te_exponent: Trailing-edge clustering exponent applied after the
                leading-edge transform.
            
        Returns:
            ndarray: Parameter values in ``[0, 1]`` with power-law clustering.
        """
        x = np.array(x)
        
        # Normalize x to [0, 1] based on range
        x_min, x_max = x[0], x[-1]
        if x_max > x_min:
            x_norm = (x - x_min) / (x_max - x_min)
        else:
            return np.linspace(0, 1, len(x))
        
        # Apply power law from LE
        if le_exponent != 1.0:
            u = x_norm ** le_exponent
        else:
            u = x_norm.copy()
        
        # Apply power law from TE if specified
        if te_exponent != 1.0:
            u = 1.0 - (1.0 - u) ** te_exponent
        
        # Ensure exact endpoints
        u[0] = 0.0
        u[-1] = 1.0
        
        return u


    @classmethod
    def fit_curve (cls, x_data, y_data, degree=3, ncp=10,
                   le_tangent_vertical=True, le_exponent=0.5, te_exponent=1.0) -> list[tuple]:
        """
        Fit a B-spline to sampled curve data with constrained least squares.

        The fit uses power-law parameterization to cluster resolution near the
        leading or trailing edge while keeping a uniform clamped knot vector.
        
        Args:
            x_data: x coordinates of the fit samples.
            y_data: y coordinates of the fit samples.
            degree: Spline degree.
            ncp: Number of control points.
            le_tangent_vertical: Keep the leading-edge tangent vertical by fixing
                the second x control point to the leading-edge x value.
            le_exponent: Leading-edge clustering exponent.
            te_exponent: Trailing-edge clustering exponent.
            
        Returns:
            list[tuple]: Fitted control points as ``(x, y)`` tuples.
        """
        # build mask where x is greater than epsilon or 0.0 
        # to avoid numerical issues of parameterization and fitting
        epsilon = 1e-4

        start = timer()

        mask = np.ones_like(x_data, dtype=bool)
        for i in range(1,len(x_data)-1):
            if abs(x_data[i]) < epsilon or abs(y_data[i]) < epsilon:
                mask[i] = False

        x_m = np.array(x_data)[mask]
        y_m = np.array(y_data)[mask]

        n_data = len(x_m)
        
        if n_data < ncp:
            raise ValueError(f"BSpline.fit_curve: Need at least {ncp} data points to fit {ncp} control points")
        
        if ncp <= degree:
            raise ValueError(f"BSpline.fit_curve: Need at least {degree + 1} control points for degree {degree}")

        # Fixed endpoints
        x_le, y_le = x_m[0], y_m[0]
        x_te, y_te = x_m[-1], y_m[-1]
        
        # Use power-law parameterization
        u_data = cls._power_parameterization(x_m, y_m, le_exponent=le_exponent, te_exponent=te_exponent)
        
        # Initialize control point positions using interpolation
        u_cp = np.linspace(0, 1, ncp)
        x_cp = np.interp(u_cp, u_data, x_m)
        y_cp = np.interp(u_cp, u_data, y_m)
        
        # Ensure endpoints are exact
        x_cp[0], x_cp[-1] = x_le, x_te
        y_cp[0], y_cp[-1] = y_le, y_te
        
        # Vertical tangent: fix second control point x at LE
        if le_tangent_vertical:
            x_cp[1] = x_le
        
        # Create B-spline to get basis function structure
        bspline_temp = cls(x_cp, y_cp, degree=degree)
        
        # Build basis matrix
        N = np.zeros((n_data, ncp))
        for i, u in enumerate(u_data):
            for j in range(ncp):
                N[i, j] = bspline_temp._basis_function(j, degree, u, der=0)
        
        # Fit x coordinates with constraints
        if le_tangent_vertical:
            fixed_indices = [0, 1, -1]
            fixed_values = [x_le, x_le, x_te]
            free_slice = slice(2, -1)
        else:
            fixed_indices = [0, -1]
            fixed_values = [x_le, x_te]
            free_slice = slice(1, -1)
        
        N_fixed_x = N[:, fixed_indices]
        N_free_x = N[:, free_slice]
        
        if N_free_x.shape[1] >= 2:
            rhs_x = x_m - N_fixed_x @ np.array(fixed_values)
            x_cp[free_slice] = np.linalg.lstsq(N_free_x, rhs_x, rcond=None)[0]
        
        # Fit y coordinates (always fix endpoints only)
        N_fixed_y = N[:, [0, -1]]
        N_free_y = N[:, 1:-1]
        
        if N_free_y.shape[1] >= 2:
            rhs_y = y_m - N_fixed_y @ np.array([y_le, y_te])
            y_cp[1:-1] = np.linalg.lstsq(N_free_y, rhs_y, rcond=None)[0]
        

        logger.debug(f"Fitting B-Spline: degree={degree}, ncp={ncp}, "
                     f"le_exp={le_exponent}, te_exp={te_exponent}, time={timer() - start:.6f}s")
        
        return list(zip(x_cp, y_cp))



