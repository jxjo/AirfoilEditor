#!/usr/bin/env pythonupper
# -*- coding: utf-8 -*-

"""  

The "Artists" to plot a airfoil object on a pg.PlotItem 

"""
import numpy as np

from base.artist                  import *
from base.common_utils               import *

from model.airfoil              import Airfoil, Airfoil_Bezier, usedAs, Geometry, Geometry_Bezier
from model.airfoil_geometry     import Line, Side_Airfoil_Bezier, Side_Airfoil_HicksHenne

from model.airfoil_geometry     import Curvature_Abstract, linetype
from base.spline                import HicksHenne, Bezier

from PyQt6.QtGui                import QColor, QBrush, QPen
from PyQt6.QtCore               import pyqtSignal, QObject



# -------- helper functions ------------------------

def _color_airfoil_of (airfoil_type : usedAs) -> QColor:
    """ returns QColor for airfoil depending on its type """

    alpha = 1.0

    if airfoil_type == usedAs.DESIGN:
        color = 'deeppink'
    elif airfoil_type == usedAs.NORMAL:
        color = 'springgreen' # 'aquamarine'
        alpha = 0.9
    elif airfoil_type == usedAs.FINAL:
        color = 'springgreen'
    elif airfoil_type == usedAs.SEED:
        color = 'dodgerblue'
    elif airfoil_type == usedAs.SEED_DESIGN:
        color = 'cornflowerblue'
    elif airfoil_type == usedAs.REF1:                          # used also in 'blend' 
        color = 'lightskyblue'  
        alpha = 0.9
    elif airfoil_type == usedAs.REF2:
        color = 'orange'
        alpha = 0.9
    else:
        color = 'gray'
    qcolor =  QColor (color) 

    if alpha != 1.0:
        qcolor.setAlphaF (alpha) 
    return qcolor


def _linestyle_of (aType : linetype) -> QColor:
    """ returns PenStyle for line depending on its type """

    if aType == linetype.CAMBER:
        style = style=Qt.PenStyle.DashDotLine
    elif aType == linetype.THICKNESS:
        style = style=Qt.PenStyle.DashLine
    elif aType == linetype.UPPER:
        style = style=Qt.PenStyle.DotLine
    elif aType == linetype.LOWER:
        style = style=Qt.PenStyle.DotLine
    else:
        style = style=Qt.PenStyle.SolidLine

    return style


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




class Movable_Highpoint (Movable_Point):
    """ 
    Represents the highpoint of an airfoil Line object,
    which can be moved to change the highpoint 
    """

    def __init__ (self, 
                  geo : Geometry, 
                  line : Line, 
                  line_plot_item : pg.PlotDataItem, *args, 
                  movable : bool = False,
                  color : QColor|str, 
                  **kwargs):

        # symmetrical and camber? 
        if line.type == linetype.CAMBER and geo.isSymmetrical: 
            movable = False 
        # Bezier is changed via control points ? 
        elif geo.isBezier:
            movable = False 

        self.name = 'max '+ line.name
        self._geo = geo
        self._line = line
        self._line_type = line.type
        self._line_plot_item = line_plot_item

        super().__init__(line.highpoint.xy, 
                         color = color, 
                         movable = movable, 
                         show_label_static = movable,
                         **kwargs)


    def label_static (self):

        if self._line.type == linetype.CAMBER and self._geo.isSymmetrical: 
            return  "No camber - symmetrical" 
        else:  
            return super().label_static()

    def label_moving (self):

        if self._line.type == linetype.CAMBER and self._geo.isSymmetrical: 
            return  "No camber - symmetrical" 
        else:  
            return f"{self.y:.2%} @ {self.x:.2%}"


    def _moving (self, _):
        """ slot - point is moved by mouse """
        # overlaoded to update airfoil geo 
        # update highpoint coordinates
        self._geo.set_highpoint_of (self._line, (self.x, self.y), moving=True)

        # update self xy if we run against limits 
        self.setPos(self._line.highpoint.xy)

        # update line plot item 
        self._line_plot_item.setData (self._line.x, self._line.y)


    def _finished (self, _):
        """ slot - point is move finished """
        # overlaoded to update airfoil geo 
        self._geo.set_highpoint_of (self._line, (self.x, self.y), moving=False)

        # update parent plot item 
        self._changed()




class Movable_TE_Point (Movable_Point):
    """ 
    Represents the upper TE point. 
    When moved the upper and lower plot item will be updated
    When finished final TE gap will be set 
    """

    name = "TE gap"

    def __init__ (self, 
                  geo : Geometry, 
                  upper_plot_item : pg.PlotDataItem, 
                  lower_plot_item : pg.PlotDataItem, 
                  movable = False, 
                  **kwargs):

        # Bezier is changed via control points ? 
        if geo.isBezier:
            movable = False 

        self._geo = geo
        self._upper_plot_item = upper_plot_item
        self._lower_plot_item = lower_plot_item

        xy = self._te_point_xy()

        super().__init__(xy, movable=movable, show_label_static = movable,**kwargs)

    
    def _te_point_xy (self): 
        return self._geo.upper.x[-1], self._geo.upper.y[-1]
    

    def _moving (self, _):
        """ slot -point is moved"""

        # update highpoint coordinates
        self._geo.set_te_gap (self.y * 2 , moving=True)

        # update self xy if we run against limits 
        self.setPos(self._te_point_xy())

        # update line plot item 
        self._upper_plot_item.setData (self._geo.upper.x, self._geo.upper.y)
        self._lower_plot_item.setData (self._geo.lower.x, self._geo.lower.y)


    def _finished (self, _):
        """ slot - point moving is finished"""

        # final highpoint coordinates
        self._geo.set_te_gap (self.y * 2, moving=False)
        self._changed()


    def label_moving (self):

        return f"{self.name}  {self.y*2:.2%} "

    def _label_opts (self, moving=False, hover=False) -> dict:
        """ returns the label options as dict """

        # overloaded to align right 
        if moving or hover:
            labelOpts = {'color': QColor(Artist.COLOR_NORMAL),
                        'anchor': (1,1),
                        'offset': (10, 10)}
        else: 
            labelOpts = {'color': QColor(Artist.COLOR_LEGEND),
                        'anchor': (1,1),
                        'offset': (10, 10)}
        return labelOpts




class Movable_LE_Point (Movable_Point):
    """ 
    Represents the LE radius . 
    When moved the LE radius will be updated
    When finished final LE radius will be set 
    """
    name =  "LE radius"

    def __init__ (self, 
                  geo : Geometry, 
                  circle : pg.ScatterPlotItem, 
                  movable = False, 
                  **kwargs):

        # Bezier is changed via control points ? 
        if geo.isBezier:
            movable = False 

        self._geo = geo
        self._circle_item = circle
        xy = 2 * self._geo.le_radius , 0

        super().__init__(xy, movable=movable, show_label_static = movable, **kwargs)
  

    def _moving (self, _):
        """ slot - when point is moved"""

        # update radius 
        new_radius = self.x / 2
        new_radius = min(0.05,  new_radius)
        new_radius = max(0.002, new_radius)

        # update self xy if we run against limits 
        self.setPos(2 * new_radius,0)

        # update line plot item 
        self._circle_item.setData ([new_radius], [0])
        self._circle_item.setSize (2 * new_radius)


    def _finished (self, _):
        """ slot - point moving is finished"""

        # final highpoint coordinates
        new_radius = self.x / 2
        self._geo.set_le_radius (new_radius)
        self._changed()


    def label_moving (self):

        return f"{self.name}  {self.x/2:.2%} "





class Movable_Side_Bezier (Movable_Bezier):
    """
    pg.PlotCurveItem/UIGraphicsItem which represents 
    an airfoil Side_Bezier. 
    The Bezier curve which can be changed by the controllpoints
    
    Points are implemented with Moveable_Points
    A Moveable_Point can also be fixed ( movable=False).
    See pg.TargetItem for all arguments 

    Callback 'on_changed' will return the (new) list of 'points'

    """
    def __init__ (self, 
                  airfoil : Airfoil_Bezier,
                  side : Side_Airfoil_Bezier,
                  **kwargs):

        self._airfoil = airfoil
        self._side = side 
        points = side.controlPoints_as_points

        if side.isUpper:
            label_anchor = (0,1) 
        else: 
            label_anchor = (0,0)

        super().__init__(points, label_anchor=label_anchor, **kwargs)


    def scene_clicked (self, ev : MouseClickEvent):
        """ 
        slot - mouse click in scene of self 
            - handle add Bezier point with crtl-click either on upper or lower side
        """ 

        # handle on ctrl-click
        if not (ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier): return  
       
        # get scene coordinates of click pos and map to view box 
        vb : pg.ViewBox = self.getViewBox()
        pos : pg.Point = vb.mapSceneToView(ev.scenePos())
        pos_x = pos.x()
        pos_y = pos.y()

        # typically there are 2 instances of self - upper and lower Bezier 
        if pos_y < 0.0 and self._side.isLower:
            self._add_point (pos_x, pos_y)
        elif pos_y >= 0.0 and self._side.isUpper:
            self._add_point (pos_x, pos_y)


    def _add_point (self, pos_x, pos_y):
       """ slot -""" 

       index, point = self._side.check_new_controlPoint_at (pos_x, pos_y)
       
       if index is not None: 

            self._points.insert (index, point)

            # _finished will do the rest - and init complete refresh
            self._finished_point()
 

    def _delete_point (self, aPoint : Movable_Point):
        """ slot - point is should be deleted """
        # overloaded - don't delete point 1 
        if aPoint.id == 1: return
        super()._delete_point (aPoint)        


    def _finished_point (self, aPoint = None):
        """ slot - point move is finished """

        # overloaded - update airfoil geometry 
        px, py = self.points_xy()
        self._airfoil.geo.set_controlPoints_of (self._side, px, py)      

        if callable(self._callback_changed):
            timer = QTimer()   
            # delayed emit to leave scope of mouse event handling 
            timer.singleShot(10, self._callback_changed)




# -------- concrete sub classes ------------------------


class Airfoil_Artist (Artist):
    """Plot the airfoils contour  """

    sig_airfoil_changed     = pyqtSignal()          # airfoil data changed 


    def __init__ (self, *args, **kwargs):

        self._show_panels = False                       # show ony panels 
        self._label_with_airfoil_type = False           # include airfoil type in label 

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


    def set_show_points (self, aBool):
        """ user switch to show point (marker ) """

        # overloaded to show leading edge of spline 
        super().set_show_points (aBool)
        self.plot()             # do refresh will show leading edge of spline 


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
            if len(self.airfoils) > 1 and (airfoil.usedAsDesign or airfoil.usedAs == usedAs.NORMAL):
                airfoils_with_design = True 

        for iair, airfoil in enumerate (self.airfoils):
            if (airfoil.isLoaded):

                # the first airfoil get's in the title 

                if iair == 0:
                    mods = None 
                    if airfoil.usedAsDesign:
                        mods = self._get_modifications (airfoil)
                    if mods:
                        subTitle = "Mods: " + mods
                    elif not mods and airfoil.isBezierBased:
                        subTitle = 'Based on 2 Bezier curves'
                    else: 
                        subTitle = None 
                    self._plot_title (airfoil.name, subTitle=subTitle )

                    label = None                                # suppress legend 

                # ... the others in the legand 
                else: 
                    if self.label_with_airfoil_type:
                        label = f"{airfoil.usedAs}: {airfoil.name}"
                    else: 
                        label = f"{airfoil.name}"

                # set color and symbol style 

                width = 2
                antialias = True
                color = _color_airfoil_of (airfoil.usedAs)
                if color is not None: 
                    if airfoils_with_design and not (airfoil.usedAsDesign or airfoil.usedAs == usedAs.NORMAL):
                        width = 1
                        antialias = False
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
                                          fillLevel=0.0, fillBrush=brush, antialias = antialias)
                else: 
                    p = self._plot_dataItem  (airfoil.x, airfoil.y, name=label, pen = pen, 
                                          symbol=s, symbolSize=sSize, symbolPen=sPen, symbolBrush=sBrush,
                                          antialias = antialias)

                # optional plot of real LE defined by spline 

                if self.show_points and airfoil.geo.isSplined:
                    if airfoil.isNormalized:
                        brushcolor = color
                        text = None
                    else: 
                        brushcolor = "yellow"
                        text="LE spline"
                    self._plot_point (airfoil.geo.le_real, color=color, brushColor=brushcolor,
                                      text=text,anchor=(0.5,1) )



    def _get_modifications (self, airfoil : Airfoil) -> str: 
        """ returns the modifications made to the airfoil as long string"""

        return ', '.join(airfoil.geo.modifications)

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



class Bezier_Artist (Artist):
    """Plot and edit airfoils Bezier control points """

    sig_airfoil_changed     = pyqtSignal()          # airfoil data changed 

    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list


    def _plot (self): 
    
        airfoil: Airfoil

        for airfoil in self.airfoils:
            if airfoil.isBezierBased and airfoil.isLoaded:

                color = _color_airfoil_of (airfoil.usedAs)
                movable = airfoil.usedAsDesign

                side : Side_Airfoil_Bezier
                for side in [airfoil.geo.lower, airfoil.geo.upper]:     # paint upper on top 

                    p = Movable_Side_Bezier (airfoil, side, color=color, movable=movable,
                                              on_changed=self.sig_airfoil_changed.emit) 
                    self._add(p)
 
                    # connect to mouse click in scene to add a new Bezier control point 

                    if movable:
                        sc : pg.GraphicsScene = p.scene()
                        sc.sigMouseClicked.connect (p.scene_clicked)



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

        from base.math_util    import derivative1

        nairfoils = len(self.airfoils)
        
        airfoil: Airfoil

        for airfoil in self.airfoils:
            if (airfoil.isLoaded):

                color = _color_airfoil_of (airfoil.usedAs)

                sides = []
                if self.show_upper: sides.append (airfoil.geo.curvature.upper)
                if self.show_lower: sides.append (airfoil.geo.curvature.lower)

                side : Line
                for side in sides:
                    x = side.x
                    y = side.y      
                    if side.type == linetype.UPPER:
                        pen = pg.mkPen(color, width=1, style=Qt.PenStyle.SolidLine)
                    else: 
                        pen = pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)

                    label = f"{side.name} - {airfoil.name}"
                    self._plot_dataItem (x, y, name=label, pen=pen)

                    # self._plot_reversals (side, color)

                    # plot derivative1 of curvature ('spikes') 

                    if self.show_derivative and (nairfoils == 1 or airfoil.usedAsDesign):
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



class Airfoil_Line_Artist (Artist, QObject):
    """
    Plot thickness, camber line of an airfoil, print max values 
    """

    sig_airfoil_changed     = pyqtSignal()          # airfoil data changed 

    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list


    def _plot (self): 

        airfoil: Airfoil

        for airfoil in self.airfoils:
            if (airfoil.isLoaded ):

                color = _color_airfoil_of (airfoil.usedAs)
                color.setAlphaF (0.8)

                # plot all 'lines' of airfoil 

                for line in airfoil.geo.lines_dict.values():
                  
                    style = _linestyle_of (line._type)
                    pen = pg.mkPen(color, width=1, style=style)
                    p = self._plot_dataItem (line.x, line.y, pen = pen, name = line.name)

                    # plot its highpoint 

                    ph = Movable_Highpoint (airfoil.geo, line, p, 
                                             movable=airfoil.usedAsDesign, color=color,
                                             on_changed=self.sig_airfoil_changed.emit )
                    self._add (ph) 

                # te gap point for DESIGN 

                if airfoil.usedAsDesign:
                    upper_item = self._get_plot_item (airfoil.geo.upper.name)
                    lower_item = self._get_plot_item (airfoil.geo.lower.name)
                    pt = Movable_TE_Point (airfoil.geo, upper_item, lower_item, 
                                            movable=airfoil.usedAsDesign, color=color,
                                            on_changed=self.sig_airfoil_changed.emit )
                    self._add (pt) 


                # plot le circle 

                radius = airfoil.geo.le_radius
                circle_item = self._plot_point (radius, 0, color=color, size=2*radius, pxMode=False, 
                                                style=Qt.PenStyle.DotLine, brushAlpha=0.3, brushColor='black')
                pl = Movable_LE_Point (airfoil.geo, circle_item, 
                                        movable=airfoil.usedAsDesign, color=color,
                                        on_changed=self.sig_airfoil_changed.emit )
                self._add(pl) 
