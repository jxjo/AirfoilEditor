#!/usr/bin/env pythonupper
# -*- coding: utf-8 -*-

"""  

The "Artists" to plot a airfoil object on a matplotlib axes

"""
import numpy as np

from ui.artist                  import *
from common_utils               import *

from model.airfoil              import Airfoil, Airfoil_Bezier
from model.airfoil              import NORMAL, SEED,SEED_DESIGN, REF1, REF2, DESIGN, FINAL
from model.airfoil_geometry     import Side_Airfoil, Side_Airfoil_Bezier, Side_Airfoil_HicksHenne
from model.airfoil_geometry     import Curvature_Abstract, UPPER, LOWER, THICKNESS, CAMBER
from model.spline               import HicksHenne

from PyQt6.QtGui    import QColor, QBrush, QPen

cl_fill             = 'whitesmoke'
cl_editing          = 'deeppink'
cl_editing_lower    = 'orchid'
cl_helperLine       = 'orange'
ls_curvature        = '-'
ls_curvature_lower  = '--'
ls_difference       = '-.'
ls_camber           = '--'
ls_thickness        = ':'



# -------- helper functions ------------------------

def _color_airfoil_of (airfoil_type) -> QColor:
    """ returns QColor for airfoil depending on its type """

    alpha = 1.0

    if airfoil_type == DESIGN:
        color = 'deeppink'
    elif airfoil_type == NORMAL:
        color = 'springgreen' # 'aquamarine'
        alpha = 0.9
    elif airfoil_type == FINAL:
        color = 'springgreen'
    elif airfoil_type == SEED:
        color = 'dodgerblue'
    elif airfoil_type == SEED_DESIGN:
        color = 'cornflowerblue'
    elif airfoil_type == REF1:                          # used also in 'blend' 
        color = 'lightskyblue'  
        alpha = 0.9
    elif airfoil_type == REF2:
        color = 'orange'
        alpha = 0.9
    else:
        color = 'gray'
    qcolor =  QColor (color) 

    if alpha != 1.0:
        qcolor.setAlphaF (alpha) 
    return qcolor



# def _plot_bezier_point_marker (ax, side : Side_Airfoil_Bezier, ipoint, color, animated=False):
#     """
#     Plot a single marker for a bezier control point
#     returns: plt marker artist  
#     """

#     markersize = 7
#     if ipoint == 0 or ipoint == (len(side.controlPoints)-1):
#         markerstyle = '.'
#         markersize = 3
#     elif side.name == UPPER:
#         markerstyle = 6
#     else: 
#         markerstyle = 7

#     x,y = side.controlPoints[ipoint]

#     if animated: 
#         alpha = 1
#     else: 
#         alpha = 0.5

#     p =  ax.plot (x,y , marker=markerstyle, markersize=markersize, 
#                  color=color, alpha=alpha, animated=animated) 
#     return p



# def _plot_bezier_point_number (ax, side : Side_Airfoil_Bezier, ipoint, color, animated=False):
#     """
#     Plot a single marker for a bezier control point
#     returns: plt text artist  
#     """

#     if side.name == UPPER:
#         va = 'bottom'
#         yn = 8
#     else:
#         va = 'top'
#         yn = -8

#     x,y = side.controlPoints[ipoint]

#     p = None 

#     if ipoint == 0 :                            # point 0 draw to the left 
#         p = ax.annotate(f'{ipoint+1}', (x,y) , va='center', ha='right', fontsize='small',
#             xytext=(-10, 0), textcoords='offset points', 
#             color = color, backgroundcolor= cl_background, animated=animated)
#     elif ipoint > 0: 
#         p = ax.annotate(f'{ipoint+1}', (x,y), va=va, ha='center', fontsize='small',
#             xytext=(0, yn), textcoords='offset points', 
#             color = color, backgroundcolor= cl_background, animated=animated)
#     return p


# def _plot_side_title (ax : plt.Axes, side : Side_Airfoil):
#     """
#     Plot info text about bezier curve of one side 
#     returns: plt text artist  
#     """

#     if side.name == UPPER:
#         y = 0.88
#         va = 'top'
#     else:
#         y = 0.12
#         va = 'bottom'
#     x = 0.05 

#     if side.isBezier:
#         text = f'{side.nPoints} control points'
#     elif side.isHicksHenne:
#         text = f'{side.nhhs} functions'

#     p = ax.text(x,y, text, va=va, ha='left',
#                 transform= ax.transAxes,  fontsize='small',
#                 color = cl_textHeader, alpha=1)
#     return p 



# -------- concrete sub classes ------------------------


class Airfoil_Artist (Artist):
    """Plot the airfoils contour  """


    def __init__ (self, *args, **kwargs):

        self._show_panels = False                       # show ony panels 
        self._label_with_airfoil_type = False           # include airfoil type in label 
        self._show_shape_function = True                # show Bezier or Hicks Henne shape functions

        super().__init__ (*args, **kwargs)

 
    @property
    def label_with_airfoil_type(self): return self._label_with_airfoil_type
    def set_label_with_airfoil_type (self, aBool): self._label_with_airfoil_type = aBool 


    @property
    def show_panels(self): return self._show_panels
    def set_show_panels (self, aBool): 
        self._show_panels = aBool 
        if self._show_panels: 
            self.set_show_points (False)

    @property
    def show_shape_function(self): return self._show_shape_function
    def set_show_shape_function (self, aBool): self._show_shape_function = aBool 


    def set_current (self, aLineLabel):
        # tries to set a highlighted airfoil to section with name ''aLineLabel' 
        if (not aLineLabel is None and aLineLabel != self._curLineLabel):    # only when changed do something
            self._curLineLabel = aLineLabel
            if self.show:                       # view is switched on by user? 
                self.plot ()


    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list


    def _refresh_plots (self):
        # overloaded for high speed refresh 

        #todo optimization doesn't work if new airfoils are in refresh 
        super()._refresh_plots ()
        # for iair, airfoil in enumerate (self.airfoils):

        #     plot : pg.PlotDataItem = self._plots[iair]
        #     plot.setData (airfoil.x, airfoil.y, name=airfoil.name)


    def _plot (self): 
    
        color_palette = random_colors (len(self.airfoils))

        # are there many airfoils - one of them is DESIGN? 

        airfoil: Airfoil
        airfoils_with_design = False 
        for airfoil in self.airfoils:
            if len(self.airfoils) > 1 and (airfoil.usedAs == DESIGN or airfoil.usedAs == NORMAL):
                airfoils_with_design = True 

        for iair, airfoil in enumerate (self.airfoils):
            if (airfoil.isLoaded):

                # the first airfoil get's in the title 
                if iair == 0:
                    self._plot_title (airfoil.name)
                    label = None
                # ... the others in the legand 
                else: 
                    if self.label_with_airfoil_type:
                        label = f"{airfoil.usedAs}: {airfoil.name}"
                    else: 
                        label = f"{airfoil.name}"

                # set color and symbol style 

                width = 2
                color = _color_airfoil_of (airfoil.usedAs)
                if color is not None: 
                    if airfoils_with_design and not (airfoil.usedAs == DESIGN or airfoil.usedAs == NORMAL):
                        width = 1
                else: 
                    color = color_palette [iair]
                pen = pg.mkPen(color, width=width)

                sPen, sBrush, sSize = pg.mkPen(color, width=1), 'black', 7
                s = 'o' if self.show_points else None 

                # plot contour and fill airfoil if it's only one 

                if len(self.airfoils) == 1: 

                    # if there is only one airfoil, fill the airfoil contour with a soft color tone  
                    brush = pg.mkBrush (color.darker (600))
                    p = self._plot_dataItem  (airfoil.x, airfoil.y, name=label, pen = pen, 
                                          symbol=s, symbolSize=sSize, symbolPen=sPen, symbolBrush=sBrush, 
                                          fillLevel=0.0, fillBrush=brush)
                else: 
                    p = self._plot_dataItem  (airfoil.x, airfoil.y, name=label, pen = pen, 
                                          symbol=s, symbolSize=sSize, symbolPen=sPen, symbolBrush=sBrush)

                # plot real le - airfoil must be loaded as GEO_SPLINE!
                # p = self.ax.plot (airfoil.geo.le, linestyle='None', 
                #                   marker='o', fillstyle='full', markersize=6, 
                #                   mfc='red', mec='red')
                # self._add (p)

                # show Bezier or Hicks Henne shape function
                # if self.show_shape_function:
                #     if airfoil.isBezierBased: 
                #         self.draw_bezier (airfoil, color)
                #         if self.show_title: 
                #             self._plot_title ('Bezier based', va='top', ha='left', wspace=0.05, hspace=0.05)

                #     if airfoil.isHicksHenneBased: 
                #         self.draw_hicksHenne (airfoil)
                #         if self.show_title: 
                #             self._plot_title ('Hicks Henne based', va='top', ha='left', wspace=0.05, hspace=0.05)


                # print a table for the max values 
                # if self.showLegend == 'extended':
                #     self._print_values (iair, airfoil, color)
                # elif self.showLegend == 'normal':
                #     self._print_name (iair, airfoil, color)



    # def draw_bezier(self, airfoil: Airfoil_Bezier, color):
    #     """ draw Bezier control Points of airfoil """

    #     linewidth   = 1
    #     linestyle   = ':'

    #     for side in [airfoil.geo.upper, airfoil.geo.lower]:

    #         # print info text about bezier curve 

    #         if self.show_title:
    #             p = _plot_side_title (self.ax, side)
    #             self._add(p)

    #         # plot bezier control points with connecting line 

    #         x = side.bezier.points_x
    #         y = side.bezier.points_y
    #         p = self.ax.plot (x,y, linestyle, linewidth=linewidth, color=color, alpha=0.7) 
    #         self._add(p)

    #         for ipoint in range (side.nPoints):

    #             # plot bezier control point marker 

    #             p = _plot_bezier_point_marker(self.ax, side, ipoint, color)
    #             self._add(p)

    #             # print point number  

    #             p = _plot_bezier_point_number (self.ax, side, ipoint, color)
    #             self._add(p)

            


    # def draw_hicksHenne (self, airfoil: Airfoil_Bezier):
    #     """ draw hicks henne functions of airfoil """

    #     linewidth   = 1
    #     linestyle   = ':'

    #     side : Side_Airfoil_HicksHenne

    #     for side in [airfoil.geo.upper, airfoil.geo.lower]:
    #     # side = airfoil.geo.upper

    #         if side.name == UPPER:
    #             delta_y =  0.1
    #         else:
    #             delta_y = -0.1

    #         hh : HicksHenne
    #         for ih, hh in enumerate(side.hhs):

    #             # plot hh function 
    #             x = side.x 
    #             y = hh.eval (x) 
    #             p = self.ax.plot (x,y * 10 + delta_y, linestyle, linewidth=linewidth , alpha=1) 
    #             self._add(p)

    #             # plot maximum marker 
    #             x = hh.location
    #             y = hh.strength  * 10 + delta_y
    #             color =self._get_color (p) 
    #             p = self.ax.plot (x, y, color=color, **ms_point)
    #             self._add(p)

    #             p = self.ax.annotate(f'{ih+1}  w{hh.width:.2f}', (x, y), fontsize='small',
    #                 xytext=(3, 3), textcoords='offset points', color = color)
    #             self._add(p)

    #         # print info text 

    #         if self.show_title:    
    #             p = _plot_side_title (self.ax, side)
    #             self._add(p)



    # def _print_name (self, iair, airfoil: Airfoil, color):
    #     # print airfoil name in upper left corner , position relative in pixel 

    #     xa = 0.96
    #     ya = 0.96 
    #     sc = get_font_size() / 10                    # scale pos depending on font size 

    #     yoff = - iair * (12*sc) - 12
    #     if self.label_with_airfoil_type:
    #         name = f"{airfoil.usedAs}: {airfoil.name}" if airfoil.usedAs else f"{airfoil.name}" 
    #     else:  
    #         name = f"{airfoil.name}"

    #     self._add (print_text   (self.ax, name, 'right', (xa,ya), (0, yoff), color, xycoords='axes fraction'))


    # def _print_values (self, iair, airfoil: Airfoil, color):
    #      # print thickness, camber in a little table in upper left corner , position relative in pixel 
 
    #     xa = 0.98
    #     ya = 0.96 

    #     sc = get_font_size() / 10                    # scale pos depending on font size 

    #     # header 
    #     if iair == 0: 
    #         self._add (print_text (self.ax, 'Thickness', 'right', (xa,ya), (-85*sc, 0), cl_textHeader, xycoords='axes fraction'))
    #         self._add (print_text (self.ax, 'Camber'   , 'right', (xa,ya), (-25*sc, 0), cl_textHeader, xycoords='axes fraction'))

    #     # airfoil data 
    #     if self.label_with_airfoil_type:  
    #         name = f"{airfoil.usedAs}: {airfoil.name}" if airfoil.usedAs else f"{airfoil.name}" 
    #     else:  
    #         name = f"{airfoil.name}"

    #     geo = airfoil.geo
    #     xt, t = geo.maxThickX, geo.maxThick 
    #     xc, c = geo.maxCambX,  geo.maxCamb

    #     yoff = - iair * (12*sc) - (12*sc)
    #     self._add (print_text   (self.ax, name, 'right', (xa,ya), (-135*sc, yoff), color, xycoords='axes fraction'))
    #     self._add (print_number (self.ax,  t, 2, (xa,ya), (-100*sc, yoff), cl_text, asPercent=True))
    #     self._add (print_number (self.ax, xt, 1, (xa,ya), ( -70*sc, yoff), cl_text, asPercent=True))
    #     self._add (print_number (self.ax,  c, 2, (xa,ya), ( -30*sc, yoff), cl_text, asPercent=True))
    #     self._add (print_number (self.ax, xc, 1, (xa,ya), (   0*sc, yoff), cl_text, asPercent=True))



# class Airfoil_Line_Artist (Artist):
#     """Superclass for plotting a line like curvature of upper and lower side of an airfoil
#     """
#     def __init__ (self, axes, modelFn, **kwargs):
#         super().__init__ (axes, modelFn, **kwargs)

#         self._upper  = True                     # including upper and lower lines 
#         self._lower  = True
#         self._points = False                    # show point marker 

#     def refresh(self, figureUpdate=False, upper=None, lower=None):
#         """ overloaded to switch upper/lower on/off"""
#         if upper is not None: self._upper = upper
#         if lower is not None: self._lower = lower
#         super().refresh (figureUpdate=figureUpdate)

#     @property
#     def upper(self): return self._upper
#     def set_upper (self, aBool): self._upper = aBool 

#     @property
#     def lower(self): return self._lower
#     def set_lower (self, aBool): self._lower = aBool 
    
#     @property
#     def points(self): return self._points
#     def set_points (self, aBool): self._points = aBool 

#     @property
#     def _marker_style (self):
#         """ the marker style to show points"""
#         if self._points: return ms_points
#         else:            return dict()

    
#     @property
#     def airfoils (self): 
#         return self.model
    
#     def _plot (self): 
#         # to be overloaded
#         pass


class Curvature_Artist (Artist):
    """
    Plot curvature (top or bottom) of an airfoil
    """
    name = 'Curvature' 

    def __init__ (self, *args, show_derivative=False, **kwargs):

        self._show_upper = True                     # show upper side 
        self._show_lower = True                     # show lower side 
        self._show_derivative = show_derivative     # show derivative of curvature 
 
        super().__init__ (*args, **kwargs)

    @property
    def show_upper(self): return self._show_upper
    def set_show_upper (self, aBool): 
        self._show_upper = aBool
        self.plot() 

    @property
    def show_lower(self): return self._show_lower
    def set_show_lower (self, aBool): 
        self._show_lower = aBool 
        self.plot()

    @property
    def show_derivative(self): return self._show_derivative
    def set_show_derivative (self, aBool): 
        self._show_derivative = aBool 
        self.plot()

    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list


    def _plot (self): 

        from model.math_util    import derivative1

        nairfoils = len(self.airfoils)
        
        airfoil: Airfoil

        for airfoil in self.airfoils:
            if (airfoil.isLoaded):

                color = _color_airfoil_of (airfoil.usedAs)

                sides = []
                if self.show_upper: sides.append (airfoil.geo.curvature.upper)
                if self.show_lower: sides.append (airfoil.geo.curvature.lower)

                side : Side_Airfoil
                for side in sides:
                    x = side.x
                    y = side.y      
                    if side.name == UPPER:
                        pen = pg.mkPen(color, width=1, style=Qt.PenStyle.SolidLine)
                    else: 
                        pen = pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)

                    label = f"{side.name} - {airfoil.name}"
                    self._plot_dataItem (x, y, name=label, pen=pen)

                    # self._plot_reversals (side, color)

                    # plot derivative1 of curvature ('spikes') 

                    if self.show_derivative and (nairfoils == 1 or airfoil.usedAs == DESIGN):
                        pen = QPen (pen)
                        pen.setColor (QColor('red'))
                        name = f"{side.name} - Derivative"
                        self._plot_dataItem (x, -derivative1(x,y), name=name, pen=pen)

                    # print a table for the max values 
                    # if self.showLegend == 'extended':
                    #     self._print_values (iair, nairfoils, airfoil.name, side, side.name==UPPER, color)


        # self._plot_title (self.name, va='top', ha='center', wspace=0.1, hspace=0.05)



    # def _plot_reversals (self, line : Side_Airfoil, color):
    #     # annotate reversals of curvature  - return number of reversals 

    #     reversals = line.reversals()
    #     if reversals:
    #         for i, point in enumerate(reversals): 
    #             text = "R"
    #             marker_x = point[0]
    #             if point[1] < 0.0:
    #                 marker_y = point[1] - 0.5
    #                 va = 'bottom'
    #             else: 
    #                 marker_y = point[1] + 0.5
    #                 va = 'top'

    #             p = self.ax.text (marker_x, marker_y, text, va=va, ha='center', color = color )
    #             self._add (p) 


    # def _print_values (self, iair, nair, name, curvature: Side_Airfoil, upper: bool, color):
    #     # print curvature values 

    #     # print in upper left corner , position relative in pixel 
    #     xa = 0.87
    #     if upper: 
    #         ya = 0.96 
    #         ypos = 0
    #     else: 
    #         ya = 0.04 
    #         ypos = 12 * nair + 6

    #     sc = get_font_size() / 10                    # scale pos depending on font size 

    #     # header 
    #     if iair == 0: 
    #         self._add (print_text (self.ax, 'LE'    , 'right', (xa,ya), (  2*sc, ypos), cl_textHeader, xycoords='axes fraction'))
    #         self._add (print_text (self.ax, 'TE'    , 'right', (xa,ya), ( 38*sc, ypos), cl_textHeader, xycoords='axes fraction'))
    #         self._add (print_text (self.ax, 'Revers', 'right', (xa,ya), ( 80*sc, ypos), cl_textHeader, xycoords='axes fraction'))

    #     # airfoil data + name 
    #     le_curv = curvature.y[0]
    #     te_curv = curvature.y[-1]
    #     nr     = len(curvature.reversals())
    #     yoff = ypos - iair * 12 - 12

    #     if nair > 1:                                # airfoil name only if there are several
    #         self._add (print_text   (self.ax, name, 'right', (xa,ya), (-35*sc, yoff), color, alpha=0.8, xycoords='axes fraction'))
    #     self._add (print_number (self.ax, le_curv, 0, (xa,ya), (  5*sc, yoff), cl_text))
    #     self._add (print_number (self.ax, te_curv, 1, (xa,ya), ( 40*sc, yoff), cl_text))
    #     self._add (print_number (self.ax,      nr, 0, (xa,ya), ( 68*sc, yoff), cl_text))


                

# class Difference_Artist (Airfoil_Line_Artist):
#     """Plot the y-difference of two airfoils 

#         2nd airfoil is Bezier based airfoil 
#         1st is reference or original airfoil from where x-stations are taken  
#     """

#     @property
#     def airfoil (self) -> Airfoil_Bezier: 
#         return self.airfoils[1] 
    
#     @property
#     def ref_airfoil (self) -> Airfoil : 
#         return self.airfoils[0] 
    

#     def _get_difference (self, side_ref: Side_Airfoil, side_actual: Side_Airfoil_Bezier):
#         # calculate difference at y-stations of reference airfoil 
#         diff  = np.zeros (len(side_ref.x))
#         for i, x in enumerate(side_ref.x):
#             diff [i] = side_actual.bezier.eval_y_on_x (x, fast=True) - side_ref.y[i]
#         return diff 


#     def _plot (self): 

#         if len(self.airfoils) != 2 : return 

#         self.set_showLegend (False)                             # no legend 
#         color = _color_airfoil_of (self.airfoil.usedAs)
#         linewidth=0.8

#         if self.upper:
#             x = self.ref_airfoil.geo.upper.x
#             y = 10 * self._get_difference (self.ref_airfoil.geo.upper, self.airfoil.geo.upper )
#             p = self.ax.plot (x, y, ls_difference, color = color, 
#                             linewidth= linewidth, **self._marker_style)
#             self._add(p)

#         if self.lower:
#             x = self.ref_airfoil.geo.lower.x
#             y = 10 * self._get_difference (self.ref_airfoil.geo.lower, self.airfoil.geo.lower ) 
#             p = self.ax.plot (x, y, ls_difference, color = color, 
#                             linewidth= linewidth, **self._marker_style)
#             self._add(p)



# class Le_Artist (Artist):
#     """Plot the airfoils leading edge areacontour  """

#     def __init__ (self, axes, modelFn, show=False, showMarker=True):
#         super().__init__ (axes, modelFn, show=show, showMarker=showMarker)

#         self._points = True                     # show point marker 
#         self.set_showLegend (False)             # no legend 


#     @property
#     def points(self): return self._points
#     def set_points (self, aBool): self._points = aBool 

#     @property
#     def _marker_style (self):
#         """ the marker style to show points"""
#         if self._points: return ms_points
#         else:            return dict()

#     @property
#     def airfoils (self): 
#         return self.model
    
#     def _plot (self): 
#         """ do plot of airfoils in the prepared axes   
#         """

#         # create cycled colors 
#         self._set_colorcycle (10, colormap="Paired")          # no of cycle colors - extra color for each airfoil

#         airfoil : Airfoil

#         for airfoil in self.airfoils:
#             if (airfoil.isLoaded):

#                 color = _color_airfoil_of (airfoil.usedAs)

#                 linewidth = 0.5
                
#                 self._plot_le_angle (airfoil)
#                 self._plot_le_coordinates (airfoil)

#                 p = self.ax.plot (airfoil.x, airfoil.y, '-', color = color, 
#                                   linewidth= linewidth, **self._marker_style)
#                 self._add(p)

#                 self._plot_le (airfoil.geo.le, color)


#     def _plot_le (self, le, color):

#         # highlight leading edge based on coordinates
#         if self.points:
#             p = self.ax.plot (le[0], le[1], color=color, **ms_le)
#             self._add(p)


#     def _plot_le_angle (self, airfoil: Airfoil):

#         yLim1, yLim2 = self.ax.get_ylim()

#         xLe, yLe = airfoil.geo.le
#         iLe = airfoil.geo.iLe
 
#         # plot two lines from LE to upper and lower neighbour points 
#         xLe_before = airfoil.x [iLe-1]
#         yLe_before = airfoil.y [iLe-1]

#         # length of lines about 3/4 of axes height
#         dy_line = (yLim2 - yLim1)/ 3 

#         dx = xLe_before - xLe
#         dy = yLe_before - yLe
#         x = [xLe, xLe_before + dy_line * dx/dy]
#         y = [yLe, yLe_before + dy_line]
#         p = self.ax.plot (x,y, color = cl_helperLine, lw=0.7)
#         self._add(p)

#         # plot angle text 
#         text = "%.1f °" % (airfoil.geo.panelAngle_le)

#         p = self.ax.annotate(text, (x[1], y[1]), fontsize = 'small',
#                              xytext=(-15, 5), textcoords='offset points', color = cl_helperLine)
#         self._add (p)   

#         # lower line
#         xLe_after = airfoil.x [iLe+1]
#         yLe_after = airfoil.y [iLe+1]
#         dx = xLe_after - xLe
#         dy = yLe_after - yLe
#         x = [xLe, xLe_after - dy_line * dx/dy]
#         y = [yLe, yLe_after - dy_line]
#         p = self.ax.plot (x,y, color = cl_helperLine, lw=0.7)
#         self._add(p)



#     def _plot_le_coordinates (self, airfoil: Airfoil):

#         xLe, yLe = airfoil.geo.le
#         if airfoil.isEdited:
#             text = "New "
#         else:
#             text = ""

#         text = text + "LE at %.7f, %.7f" % (xLe, yLe)
#         p = self.ax.annotate(text, (xLe, yLe), fontsize = 'small',
#                              xytext=(20, -4), textcoords='offset points', color = cl_helperLine)
#         self._add (p)   



class Thickness_Artist (Artist):
    """
    Plot thickness, camber line of an airfoil, print max values 
    """

    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list


    def _plot (self): 

        airfoil: Airfoil

        for airfoil in self.airfoils:
            if (airfoil.isLoaded ):
                  
                color = _color_airfoil_of (airfoil.usedAs)

                # plot camber line

                camber = airfoil.camber
                pen = pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)
                self._plot_dataItem (camber.x, camber.y, pen = pen, name = 'Camber')

                # plot thickness distribution line

                thickness = airfoil.thickness
                pen = pg.mkPen(color, width=1, style=Qt.PenStyle.DotLine)
                self._plot_dataItem (thickness.x, thickness.y, pen = pen, name = 'Thickness')

                # plot marker for the max values 
                self._plot_max_val (airfoil, thickness, color)
                self._plot_max_val (airfoil, camber,    color)

                # plot le circle 

                radius = airfoil.geo.le_radius
                # self._plot_point (radius,0, color=color, symbolSize=radius*100, pxMode=False, text="Hallo")



    def _plot_max_val (self, airfoil: Airfoil, airfoilLine: Side_Airfoil, color):
        """ indicate max. value of camber or thickness line """

        if airfoil.usedAs == DESIGN:
            color = cl_helperLine
        else:
            color = color

        # symmetrical and camber? 
        if airfoilLine.name == CAMBER and airfoil.isSymmetrical: 
            x, y = 0.3, 0
            text =  "No camber - symmetrical" 
        # normal 
        else:  
            x, y = airfoilLine.highpoint.xy
            x, y = airfoilLine.highpoint.xy
            text = "%.2f%% at %.1f%%" % (y * 100, x *100)

        self._plot_point (x, y, color=color, symbol='+', text=text)   

