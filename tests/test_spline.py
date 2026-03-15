#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""

    Spline pytest classes

"""

import numpy as np 

# -> pyproject.toml

from airfoileditor.base.spline import *


class Test_Spline:

    def test_bspline_polynomial_eval (self):

        spl = BSpline([0.0, 0.2, 0.65, 1.0], [0.0, 0.18, 0.08, 0.0], degree=3)

        x_mid, y_mid = spl.eval(0.5)
        x_mid_poly, y_mid_poly = spl._eval_polynomials(0.5)

        np.testing.assert_allclose([x_mid_poly, y_mid_poly], [x_mid, y_mid], atol=1e-12)

        u = np.linspace(0.0, 1.0, 21)
        x, y = spl.eval(u, update_cache=False)
        x_poly, y_poly = spl._eval_polynomials(u)

        np.testing.assert_allclose(x_poly, x, atol=1e-12)
        np.testing.assert_allclose(y_poly, y, atol=1e-12)

        dx_ref, dy_ref = spl.eval(u, der=1, update_cache=False)
        dx_poly, dy_poly = spl._eval_polynomials(u, der=1)
        ddx_ref, ddy_ref = spl.eval(u, der=2, update_cache=False)
        ddx_poly, ddy_poly = spl._eval_polynomials(u, der=2)

        np.testing.assert_allclose(dx_poly, dx_ref, atol=1e-12)
        np.testing.assert_allclose(dy_poly, dy_ref, atol=1e-12)
        np.testing.assert_allclose(ddx_poly, ddx_ref, atol=1e-12)
        np.testing.assert_allclose(ddy_poly, ddy_ref, atol=1e-12)

        spl.set_cpoint(1, (0.25, 0.22))
        x_updated, y_updated = spl.eval(u, update_cache=False)
        x_poly_updated, y_poly_updated = spl._eval_polynomials(u)

        np.testing.assert_allclose(x_poly_updated, x_updated, atol=1e-12)
        np.testing.assert_allclose(y_poly_updated, y_updated, atol=1e-12)

    def test_spline_1D (self): 

        x = [  0, 0.5,  2,  3,  4,  5,  7]  
        y = [  0,  3,  0,  2,  0,  2,  0]  

        # scalar 
        spl = Spline1D (x,y, boundary="natural")
        xnew = 1.0
        ynew = spl.eval(xnew, der=0) 
        assert ynew == 2.9546299523643555

        # scalar 

        spl = Spline1D (x,y, boundary="notaknot")
        xnew = 1.0
        ynew = spl.eval(xnew, der=0) 
        assert ynew == 2.642301710730949

        # array

        xnew = np.linspace( x[0], x[-1] , 10)
        ynew = spl.eval(xnew, der=0) 
        sum = round(np.sum (ynew),10)
        assert sum == 15.4634525661

        ynew = spl.eval(xnew, der=1) 
        sum = round(np.sum (ynew),10)
        assert sum == 0.0739588733

        ynew = spl.eval(xnew, der=2) 
        sum = round(np.sum (ynew),10)
        assert sum == -49.1819595645

        c  = spl.curvature(xnew) 
        sum = round(np.sum (c),10)
        assert sum == -6.7610052324

        pass



    def test_spline_2D (self): 

        x = [  0, 0.5,  2,  3,  4,  5,  7]  
        y = [  0,  3,  0,  2,  0,  2,  0]  

        # array 
        spl = Spline2D (x,y, boundary="notaknot")

        u = np.linspace( 0, 1 , 10)

        xnew, ynew = spl.eval (u)
        sum_xnew = round(np.sum (xnew),10)
        sum_ynew = round(np.sum (ynew),10)
        assert sum_xnew == 28.8656256356
        assert sum_ynew == 12.8493867404
        # print ("2D notaknot", np.sum(xnew), np.sum(ynew))

        curv = spl.curvature (u)
        sum_curv = round(np.sum(curv),10)
        assert sum_curv == -10.2688794746

        # print ("2D notaknot curvature", np.sum(curv), curv)

        # xnew = np.linspace( x[0], x[-1] , 10)
        # ynew = spl.eval(xnew, der=0) 
        # print ("notaknot der=0", np.sum (ynew), "   x sum", np.sum(xnew))
        # assert np.sum (ynew) == 15.463452566096425

        # ynew = spl.eval(xnew, der=1) 
        # print ("notaknot der=1", np.sum (ynew))
        # assert np.sum (ynew) == 0.07395887333679596

        # ynew = spl.eval(xnew, der=2) 
        # print ("notaknot der=2", np.sum (ynew))
        # assert np.sum (ynew) == -49.18195956454122

        # c  = spl.curvature(xnew) 
        # print ("notaknot curv", np.sum (c))
        # assert np.sum (c) == -6.761005232410417

        pass


# Main program for testing 
if __name__ == "__main__":

    test = Test_Spline()
    test.test_spline_1D()
    test.test_spline_2D()
