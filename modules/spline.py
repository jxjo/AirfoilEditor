#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""

    Cubic Spline 1D and 2D  

"""
import bisect
import numpy as np
from math_util import findMin 



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
            
        if arccos:           # test of a arccos distribution to avoid oscillation at LE          
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
        for i in range(n-1):                  
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
        y : ndarray or list of ndarrays
            An array of values representing the spline function evaluated at
            the points in ``x``.  .
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
            # copy x???        

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
        Evaluate the curvature of self.

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
           
            'quadratic'  - the first and last segement ist parabolic 
            'notaknot'   - at the first and last interior break, 
                           even the third derivative is continuous - defalt 
            'natural'    - the second derivate at start and end is zero 

        Returns
        -------
        """
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




#------------ Bezier -----------------------------------


class BezierCubic: 
    """Build a cubic Bezier curve defined by 4 points """


    def __init__ (self, px, py):
        """
        Build a cubic Bezier curve defined by 4 points.

        Parameters
        ----------
        x,y : array_like - coordinates of the 4 points 
             
        """
        self._px = None                         # definition points
        self._py = None

        self._x  = None                         # cached x,y results
        self._y  = None
        self._u  = None                         # cached parameter u 

        self.set_points(px, py)

        return

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

        if not np.array_equal (u, self._u): 
            self._u = u 
            self._x = self._eval (self._px, u, der)
            self._y = self._eval (self._py, u, der)
        return self._x, self._y
    

    def eval_y_on_x (self, x, fast=True):
        """
        Evaluate the y value based on x 

        A interpolation is made to find u(x) - either linear (fast=True) or based on the curve

        Parameters
        ----------
        x :   Scalar - x-value 
        fast : bool, optional - only a linear interpolation of u is made .

        Returns
        -------
        y : Scalar - y evaluated at x 
        """

        if fast and (not self._x is None) and (x >= self._x[0] and x <= self._x[-1]):
            i = min(bisect.bisect(self._x, x)-1, len(self._x) -2)
            # interpolate u 
            u = ((self._u[i+1]-self._u[i])/(self._x[i+1]-self._x[i])) * (x - self._x[i]) + self._u[i]
            # evaluate y from u 
            return self._eval (self._py, u)
        else: 
            u = findMin (lambda u: abs(self._eval(self._px,u) - x), 0.5, bounds=(0, 1)) 
            y =  self._eval (self._py, u)
            # print ("x: ",x, "  y evaluated ", y)
            return y
            # raise ValueError ("Bezier: evaluation of y from x = %f not implemented" %x)
        


    def eval_x_on_y (self, y, fast=True):
        """
        Evaluate the x value based on y 

        A interpolation is made to find u(y) - either linear (fast=True) or based on the curve

        Parameters
        ----------
        y :   Scalar - y-value 
        fast : bool, optional - only a linear interpolation of u is made .

        Returns
        -------
        x : Scalar - x evaluated at y 
        """

        if fast and (not self._y is None) and (y <= self._y[0] and y >= self._y[-1]):
            i = min(bisect.bisect(self._y, y)-1, len(self._y) -2)
            # interpolate u 
            u = ((self._u[i+1]-self._u[i])/(self._y[i+1]-self._y[i])) * (y - self._y[i]) + self._u[i]
            # evaluate y from u 
            return self._eval (self._px, u)
        else: 
            u = findMin (lambda u: abs(self._eval(self._py,u) - y), 0.5, bounds=(0, 1)) 
            x =  self._eval (self._px, u)
            # print ("y: ",y, "  x evaluated ", x)
            return x
        

    def set_points(self, px, py):
        """ (re) sets the definition points of the Bezier curve"""

        n = len(px)
        if n != 4:
            raise ValueError('Cubic Bezier: Must have 4 points')
        elif n != len(py): 
            raise ValueError('Spline: Length of x,y is different')

        self._px = np.copy(px)
        self._py = np.copy(py)

        # reset already evaluated values 
        self._x  = None
        self._y  = None
        self._u =  None


    def _eval (self, pxy, u, der=0):
        """ evaluates self at u for coordinate xory

        Parameters
        ----------
        xy:   either x or y coordinates of the bezier definition points
        u :   Scalar or an array of normed arc length 0..1 at which to return 
              the value of the spline or its derivatives. 
        der : int, optional - The order of derivative of the spline to compute.
        """
        if der == 0: 
            f =   (1-u)**3       *pxy[0] + \
                3*(1-u)**2 *u    *pxy[1] + \
                3*(1-u)    *u**2 *pxy[2] + \
                            u**3 *pxy[3]
        else:
            raise ValueError('Cubic Bezier: Derivatives currently not implemented')

        return f 



class BezierQuadratic: 
    """Build a quadratic Bezier curve defined by 3 points """


    def __init__ (self, px, py):
        """
        Build a quadratic Bezier curve defined by 3 points.

        Parameters
        ----------
        x,y : array_like - coordinates of the 3 points 
             
        """
        self._px = None                         # definition points
        self._py = None

        self._x  = None                         # cached x,y results
        self._y  = None
        self._u  = None                         # cached parameter u 

        self.set_points(px, py)

        return

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

        if not np.array_equal (u, self._u):         #  u array in cache? 
            x = self._eval (self._px, u, der)
            y = self._eval (self._py, u, der)
            if len(u) >= 50:                        # refill cache
                self._u = u 
                self._x = x
                self._y = y
        else:                                       # get cached values 
            x = self._x
            y = self._y 
        return self._x, self._y
    

    def eval_y_on_x (self, x, fast=True):
        """
        Evaluate the y value based on x 

        A interpolation is made to find u(x) - either linear (fast=True) or based on the curve

        Parameters
        ----------
        x :   Scalar - x-value 
        fast : bool, optional - only a linear interpolation of u is made .

        Returns
        -------
        y : Scalar - y evaluated at x 
        """

        if fast and (not self._x is None) and (x >= self._x[0] and x <= self._x[-1]):
            i = min(bisect.bisect(self._x, x)-1, len(self._x) -2)
            # interpolate u 
            u = ((self._u[i+1]-self._u[i])/(self._x[i+1]-self._x[i])) * (x - self._x[i]) + self._u[i]
            # evaluate y from u 
            return self._eval (self._py, u)
        else: 
            raise ValueError ("Bezier: evaluation of y from x = %f not implemented" %x)
        

    def set_points(self, px, py):
        """ (re) sets the definition points of the Bezier curve"""

        n = len(px)
        if n != 3:
            raise ValueError('Quadratic Bezier: Must have 3 points')
        elif n != len(py): 
            raise ValueError('Spline: Length of x,y is different')

        self._px = np.copy(px)
        self._py = np.copy(py)

        # reset already evaluated values 
        self._x  = None
        self._y  = None
        self._u =  None


    def _eval (self, pxy, u, der=0):
        """ evaluates self at u for coordinate xory

        Parameters
        ----------
        xy:   either x or y coordinates of the bezier definition points
        u :   Scalar or an array of normed arc length 0..1 at which to return 
              the value of the spline or its derivatives. 
        der : int, optional - The order of derivative of the spline to compute.
        """
        if der == 0: 
            f =   (1-u)**2    *pxy[0] + \
                2*(1-u)    *u *pxy[1] + \
                         u**2 *pxy[2]
        else:
            raise ValueError('Quadratic Bezier: Derivatives currently not implemented')

        return f 


# ------------ test functions - to activate  -----------------------------------


# def test_BezierQuadratic (): 
    
#     import matplotlib.pyplot as plt

#     px = [  0,  0.95,  1.0]  
#     py = [  0,  0.5,  0.0]  

#     u = np.linspace( 0, 1 , 200)

#     bez = BezierQuadratic (px, py)
#     x,y = bez.eval(u)
    
#     plt.plot(px, py, "or", label="Points")    
#     plt.plot(x, y, label="Bezier Quad")

#     plt.plot(u, x, "b", label="x(u)")
#     plt.plot(u, y, "g", label="y(u)")

#     # try to simulate with cubic spline
#     # unew = np.linspace( 0, 1 , 10)
#     # px,py = bez.eval(unew)

#     # spl = Spline1D (px, py, boundary='notaknot')
#     # x = np.linspace( 0, 1 , 200)
#     # y = spl.eval(x)
#     # plt.plot(px, py, "og", label="Points Spline")    
#     # plt.plot(x, y, "g", label="Cubic Spline")


#     plt.grid(True)

#     plt.legend()
#     plt.show()


# def test_BezierCubic (): 
    
#     import matplotlib.pyplot as plt

#     px = [  0,  0.8,  1.0,  1.0]  
#     py = [  1,  1.0,  0.5,  0.0]  

#     u = np.linspace( 0, 1 , 200)

#     bez = BezierCubic (px, py)
#     x,y = bez.eval(u)
    
#     plt.plot(px, py, "or", label="Points")    
#     plt.plot(x, y, label="Bezier")

#     plt.plot(u, x, "b", label="x(u)")
#     plt.plot(u, y, "g", label="y(u)")



#     # px = [  0,  0.9,  1.0]  
#     # py = [  0,  0.1,  0.0]  
#     # spl = Spline1D (px, py, boundary='natural')
#     # x = np.linspace( 0, 1 , 200)
#     # y = spl.eval(x)
#     # plt.plot(px, py, "og", label="Points Spline")    
#     # plt.plot(x, y, "g", label="Spline")


#     plt.grid(True)

#     plt.legend()
#     plt.show()


# def test_spline1D (): 
    
#     import matplotlib.pyplot as plt

#     x = [  0, 0.5,  2,  3,  4,  5,  7]  
#     y = [  0,  3,  0,  2,  0,  2,  0]  

#     xnew = np.linspace( x[0], x[-1] , 200)
#     plt.plot(x, y, "xb")
#     plt.grid(True)


#     spl = Spline1D (x,y, boundary="notaknot")
#     ynew = spl.eval(xnew, der=0) 
#     plt.plot(xnew, ynew, "r-", label="notaknot")
#     c  = spl.curvature(xnew) 
#     ynew = spl.eval(xnew, der=1) 
#     plt.plot(xnew, ynew, "r:", label="notaknot deriv1")
#     ynew = spl.eval(xnew, der=2) 
#     plt.plot(xnew, ynew, "r--", label="notaknot deriv2")

#     plt.legend()
#     plt.show()


# def test_spline2D (): 
    
#     import matplotlib.pyplot as plt

#     print("Spline 2D test")

#     input_x = [-2.5, -1.5,  0.0, 2.5, 5.0, 6.5, 3.0, 0.0, -0.5]
#     input_y = [ 0.7,  0.0, -0.1,   5, 6.5, 4.0, 4.5, 2.0, -2.0]

#     unew = np.linspace(0, 1 , 500)

#     spl = Spline2D (input_x, input_y, boundary='notaknot')
#     x, y = spl.eval (unew)

#     plt.subplots(1)
#     plt.plot(input_x, input_y, "xb", label="input")
#     plt.plot(x, y,   "-r", label="Spline2D")

#     # curvature 
#     plt.subplots(1)
#     curv = spl.curvature (unew)
#     plt.plot(unew, curv,  "-r", label="curvature")


#     # scipy 
#     # from scipy.interpolate import splprep, splev
#     # tck, u = splprep([input_x, input_y], s=0.0, k=3)
#     # x2, y2 = splev(unew, tck, der=0)
#     # plt.plot(x2, y2, "-b", label="SciPy")
#     # plt.grid(True)
#     # plt.axis("equal")
#     # plt.legend()


#     # dx, dy   = splev(unew, tck, der=1)
#     # ddx, ddy = splev(unew, tck, der=2)

#     # deriv2 = dx * ddy - dy * ddx
#     # # get curvature from derivative 2
#     # n = dx**2 + dy**2
#     # curv2 = deriv2 / n**(3./2.)
#     # plt.plot(unew, curv2, "-g", label="scipy curvature")

#     plt.grid(True)
#     plt.legend()


if __name__ == '__main__':
    
    # test_BezierQuadratic ()
    # test_BezierCubic () 
    # test_spline1D ()
    # test_spline2D ()
    pass

