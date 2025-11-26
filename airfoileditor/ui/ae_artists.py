#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

The "Artists" to plot a airfoil object on a pg.PlotItem 

"""
import html 

from ..base.math_util           import derivative1
from ..base.artist              import *
from ..base.spline              import Bezier, HicksHenne

from ..model.airfoil            import Airfoil, Airfoil_Bezier, usedAs, Geometry, Flap_Setter
from ..model.airfoil_geometry   import Line, Side_Airfoil_Bezier, Side_Airfoil_HicksHenne
from ..model.polar_set          import * 

from PyQt6.QtGui                import QColor, QBrush, QPen
from PyQt6.QtCore               import pyqtSignal, QObject


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# -------- helper functions ------------------------

def _color_airfoil (airfoils : list[Airfoil], airfoil: Airfoil) -> QColor:
    """ returns QColor for airfoil depending on its type """

    alpha = 1.0
    airfoil_type = airfoil.usedAs

    if airfoil_type == usedAs.DESIGN:
        color = 'deeppink'
    elif airfoil_type == usedAs.NORMAL:
        color = 'springgreen'  
    elif airfoil_type == usedAs.FINAL:
        # color = QColor('turquoise').lighter (120)
        color = 'springgreen'  
    elif airfoil_type == usedAs.SEED:
        color = 'dodgerblue'
    elif airfoil_type == usedAs.SEED_DESIGN:
        color = 'cornflowerblue'
    elif airfoil_type == usedAs.REF: 
        i, n = airfoil.usedAs_i_Ref (airfoils)  
        color = color_in_series ('lightskyblue', i, n, delta_hue=0.4)                      
    elif airfoil_type == usedAs.TARGET:
        color = 'cornflowerblue'
    elif airfoil_type == usedAs.SECOND:
        color = 'cornflowerblue'
    else:
        color = 'gray'
    qcolor =  QColor (color) 

    if alpha != 1.0:
        qcolor.setAlphaF (alpha) 
    return qcolor


def _label_airfoil (airfoils : list[Airfoil], airfoil: Airfoil) -> str:
    """ nice label including usedAs for airfoil"""

    if airfoil.usedAs == usedAs.REF:
        i, n = airfoil.usedAs_i_Ref (airfoils)  
        use = f"Ref {i+1}: "
    elif airfoil.usedAs in [usedAs.DESIGN, usedAs.NORMAL] or airfoil.usedAs is None: # no prefix 
        use = ""
    else: 
        use = f"{airfoil.usedAs}: " 

    label = f"{use}{airfoil.name_to_show}"
    return label 


def _linestyle_of (aType : Line.Type) -> QColor:
    """ returns PenStyle for line depending on its type """

    if aType == Line.Type.CAMBER:
        style = Qt.PenStyle.DashDotLine
    elif aType == Line.Type.THICKNESS:
        style = Qt.PenStyle.DashLine
    elif aType == Line.Type.UPPER:
        style = Qt.PenStyle.DotLine
    elif aType == Line.Type.LOWER:
        style = Qt.PenStyle.DotLine
    else:
        style = Qt.PenStyle.SolidLine

    return style


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
        if line.type == Line.Type.CAMBER and geo.isSymmetrical: 
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


    def label_static (self, *_):

        if self._line.type == Line.Type.CAMBER and self._geo.isSymmetrical: 
            return  "No camber - symmetrical" 
        else:  
            return super().label_static()

    def label_moving (self, *_):

        if self._line.type == Line.Type.CAMBER and self._geo.isSymmetrical: 
            return  "No camber - symmetrical" 
        else:  
            return f"{self.y:.2%} @ {self.x:.2%}"


    def _moving (self, _):
        """ slot - point is moved by mouse """
        # overlaoded to update airfoil geo 
        # update highpoint coordinates
        self._geo.set_highpoint_of (self._line, (self.x, self.y), finished=False)

        # update self xy if we run against limits 
        self.setPos(self._line.highpoint.xy)

        # update line plot item 
        self._line_plot_item.setData (self._line.x, self._line.y)


    def _finished (self, _):
        """ slot - point is move finished """
        # overlaoded to update airfoil geo 
        self._geo.finished_change_of (self._line)

        # update parent plot item 
        self._changed()




class Movable_TE_Point (Movable_Point):
    """ 
    Represents the upper TE point. 
    When moved the upper plot item will be updated
    When finished final TE gap will be set 
    """

    name = "TE gap"

    def __init__ (self, 
                  geo : Geometry, 
                  upper_plot_item : pg.PlotDataItem, 
                  show_label_static_with_value = False, 
                  movable = False, 
                  **kwargs):

        # Bezier is changed via control points ? 
        if geo.isBezier:
            movable = False 

        self._geo = geo
        self._upper_plot_item = upper_plot_item
        self._show_label_static_with_value = show_label_static_with_value

        xy = self._te_point_xy()

        super().__init__(xy, movable=movable, **kwargs)

    
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


    def _finished (self, _):
        """ slot - point moving is finished"""
        # final highpoint coordinates
        self._geo.set_te_gap (self.y * 2, moving=False)
        self._changed()


    @override
    def label_static (self, *_):
        """label static"""
        if self._show_label_static_with_value:
            return f"{self.name}  {self.y*2:.2%}"
        else: 
            return super().label_static() 


    @override
    def label_hover (self, *_):
        """label when hovered"""
        return f"{self.name}  {self.y*2:.2%}"


    @override
    def label_moving (self, *_):
        """label when moving"""
        return f"{self.name}  {self.y*2:.2%} with {Geometry.TE_GAP_XBLEND:.0%} blend range"

    @override
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
                  show_label_static_with_value = False, 
                  movable = False, 
                  **kwargs):

        # Bezier is changed via control points ? 
        if geo.isBezier:
            movable = False 

        self._show_label_static_with_value = show_label_static_with_value
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


    @override
    def label_static (self, *_):
        """label static"""
        if self._show_label_static_with_value:
            return f"{self.name}  {self.x/2:.2%}"
        else: 
            return super().label_static() 


    @override
    def label_hover (self, *_):
        """label when hovered"""
        return f"{self.name}  {self.x/2:.2%}"


    @override
    def label_moving (self, *_):
        """label when moving"""
        return f"{self.name}  {self.x/2:.2%} with {Geometry.LE_RADIUS_XBLEND:.0%} blend range"





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

    @property
    def bezier (self) -> Bezier:
        """ the Bezier  self is working with """
        # here - take Bezier of the 'side' 
        return self._side.bezier

    @property
    def u (self) -> list:
        """ the Bezier parameter  """
        # here - take Bezier of the 'side' 
        return self._side._u


    def refresh (self):
        """ refresh control points from side control points """

        # update all my movable points at once 
        movable_point : Movable_Bezier_Point
        for i, point_xy in enumerate(self._side.controlPoints): 
            movable_point = self._movable_points[i]
            movable_point.setPos_silent (point_xy)              # silent - no change signal 

        self.setData(*self.points_xy())                         # update self (polyline) 

        # if self._bezier_item is not None:   	                # update bezier item to be dispalyed
        #     x,y = self.bezier.eval (self.u) 
        #     self._bezier_item.setData (x, y)
        #     self._bezier_item.show()



    def _add_point (self, pos_x, pos_y):
       """ add controlpoint to Bezier curve - called by mouse ctrl_click on Bezier line """ 

       index, point = self._side.check_new_controlPoint_at (pos_x, pos_y)
       
       if index is not None: 

            self._side.add_controlPoint (index, point)
            # _finished will do the rest - and init complete refresh
            self._finished_point()
 

    def _delete_point (self, aPoint : Movable_Point):
        """ slot - point is should be deleted """
        # overloaded - don't delete point 1 
        if aPoint.id == 1: return
        super()._delete_point (aPoint)    

        px, py = self.jpoints_xy()
        self._side.set_controlPoints (px, py)   

        # _finished will do the rest - and init complete refresh
        self._finished_point()


    def _finished_point (self, aPoint = None):
        """ slot - point move is finished """

        # overloaded - update airfoil geometry 
        self._airfoil.geo.finished_change_of (self._side)      

        super()._finished_point(aPoint)



# -------- concrete sub classes ------------------------


class Airfoil_Artist (Artist):
    """Plot the airfoils contour  """


    def __init__ (self, *args, 
                  show_points = False,
                  **kwargs):

        self._show_panels = False                       # show ony panels 
        self._show_points = show_points is True         # show coordinate points
        self._show_airfoils_refs_scaled = True          # show reference airfoils scaled 

        super().__init__ (*args, **kwargs)


    @property
    def show_panels(self): return self._show_panels
    def set_show_panels (self, aBool): 
        self._show_panels = aBool 
        if self._show_panels: 
            self.set_show_points (False)


    @property
    def show_points (self): return self._show_points
    def set_show_points (self, aBool):
        """ user switch to show point (marker )
        """
        self._show_points = aBool is True 

        p : pg.PlotDataItem
        for p in self._plots:
            if isinstance (p, pg.PlotDataItem):
                if self.show_points:
                    p.setSymbol('o')
                else: 
                    p.setSymbol(None)
        self.plot()             # do refresh will show leading edge of spline 


    @property
    def show_airfoils_refs_scaled (self) -> bool:
        """ True if ref airfoils will be scaled """
        return self._show_airfoils_refs_scaled 
    
    def set_show_airfoils_refs_scaled (self, aBool):
        self._show_airfoils_refs_scaled = aBool
        self.refresh()


    def set_current (self, aLineLabel):
        # tries to set a highlighted airfoil to section with name ''aLineLabel' 
        if (not aLineLabel is None and aLineLabel != self._curLineLabel):    # only when changed do something
            self._curLineLabel = aLineLabel
            if self.show:                       # view is switched on by user? 
                self.plot ()


    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list


    def _plot (self): 
    
        color_palette = random_colors (len(self.airfoils))

        # are there many airfoils - one of them is DESIGN? 

        airfoils_with_design = False 
        for airfoil in self.airfoils:
            if airfoil.usedAsDesign:
                airfoils_with_design = True 
                break

        for iair, airfoil in enumerate (self.airfoils):
            if (airfoil.isLoaded):

                # no legend if it is only one airfoil 

                if len(self.airfoils) == 1:
                    label = None                                    # suppress legend 
                else: 
                    label = _label_airfoil (self.airfoils, airfoil)

                # set color, width, ZValue, symbol style depending on airfoil usage and no of airfoils  

                color = _color_airfoil (self.airfoils, airfoil)
                if color is None: color = color_palette [iair]

                # default 
                width = 1
                antialias = False
                zValue = 1
                scale = 1.0 

                if airfoil.usedAs == usedAs.FINAL:
                    width = 2
                    antialias = True
                    zValue = 5                                      # final top most 
                elif airfoils_with_design:
                    if airfoil.usedAsDesign:
                        width = 2
                        antialias = True
                        zValue = 3
                    elif airfoil.usedAs != usedAs.NORMAL:
                        color = QColor (color).darker (110)
                elif airfoil.usedAs == usedAs.NORMAL:
                    width = 2
                    antialias = True

                pen = pg.mkPen(color, width=width)

                sPen, sBrush, sSize = pg.mkPen(color, width=1), 'black', 7
                s = 'o' if self.show_points else None 

                x,y = airfoil.geo.x, airfoil.geo.y 

                # apply optional scale value for reference airfoils 

                if self.show_airfoils_refs_scaled and airfoil.usedAs == usedAs.REF:
                    scale = airfoil.scale_factor
                    x,y = x * scale, y * scale

                # plot contour and fill airfoil if it's only one 
                #   use geometry.xy to refelect changes in diesign airfoil

                if len(self.airfoils) == 1: 

                    # if there is only one airfoil, fill the airfoil contour with a soft color tone  
                    brush = pg.mkBrush (color.darker (600))
                    self._plot_dataItem  (x, y, name=label, pen = pen, symbol=s, symbolSize=sSize, symbolPen=sPen, 
                                          symbolBrush=sBrush, fillLevel=0.0, fillBrush=brush, antialias = antialias,
                                          zValue=zValue)
                    
                    # plot note if reflexed or rearloaded
                    self._plot_reflexed_rearloaded (airfoil, color)

                else: 
                    self._plot_dataItem  (x, y, name=label, pen = pen, symbol=s, symbolSize=sSize, symbolPen=sPen, 
                                          symbolBrush=sBrush, antialias = antialias, zValue=zValue)

                # optional plot of real LE defined by spline 

                if self.show_points and airfoil.geo.isSplined:
                    textColor = None
                    if airfoil.isNormalized:
                        brushcolor = COLOR_GOOD
                        text = None
                    else: 
                        brushcolor = COLOR_WARNING
                        text="LE spline"

                    self._plot_point (airfoil.geo.le_real, color=brushcolor, brush=brushcolor,
                                      text=text, textColor=textColor, anchor=(1.1,0.5) )
                    
                # optional plot of LE angle lines
                if self.show_points and airfoil.usedAsDesign:
                    self._plot_le_angle_lines (airfoil, color)


    def _plot_reflexed_rearloaded (self, airfoil : Airfoil, color : QColor): 
        """ plot note if reflexed or rearloaded"""

        textColor = color.darker (130)  
        
        if airfoil.isReflexed: 
            x = 0.8
            y = airfoil.geo.upper.yFn (x) 
            self._plot_point ((x,y), size=0, text="Reflexed", anchor=(0.5,2.0), textColor=textColor) 

        elif airfoil.isRearLoaded: 
            x = 0.8
            y = airfoil.geo.lower.yFn (x) 
            self._plot_point ((x,y), size=0, text="Rearloaded", anchor=(0.5,-1.0), textColor=textColor)


    def _plot_le_angle_lines (self, airfoil : Airfoil, color : QColor): 
        """ plot helper lines showing le panel angle"""

        iLe = airfoil.geo.iLe

        xLe, yLe = airfoil.geo.x[iLe], airfoil.geo.y[iLe]

        # upper line
        x2, y2   = airfoil.geo.x[iLe-1], airfoil.geo.y[iLe-1]
        yEnd   = 0.08
        xEnd   = interpolate (yLe, y2, xLe, x2, yEnd)

        self._plot_dataItem ([xLe, xEnd], [yLe, yEnd], pen=pg.mkPen(color, style=Qt.PenStyle.DotLine))

        # lower line
        x2, y2   = airfoil.geo.x[iLe+1], airfoil.geo.y[iLe+1]
        yEnd   = -0.08
        xEnd   = interpolate (yLe, y2, xLe, x2, yEnd)

        self._plot_dataItem ([xLe, xEnd], [yLe, yEnd], pen=pg.mkPen(color, style=Qt.PenStyle.DotLine))

        # text LE angle

        angle = airfoil.geo.panelAngle_le
        text  = f"LE angle {angle:.1f}°"
        if angle >  Geometry.LE_PANEL_ANGLE_TOO_BLUNT:
            text += " (too blunt)"
        elif angle < Geometry.PANEL_ANGLE_TOO_SHARP:    
            text += " (too sharp)"
        self._plot_point ((xEnd,yEnd), size=0, text=text, textColor=None, anchor=(-0.05, 1))  



class Flap_Artist (Artist):
    """Plot the flapped airfoil based on Flapper data  """

    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list

    @property
    def design_airfoil (self) -> Airfoil:
        for airfoil in self.airfoils:
            if airfoil.usedAsDesign:
                return airfoil 
    
    @property
    def flap_setter (self) -> Flap_Setter:
        return self.design_airfoil.flap_setter if self.design_airfoil else None 


    def _plot (self): 
    
        if self.flap_setter is None: return 

        flapped_airfoil = self.flap_setter.airfoil_flapped
        color = _color_airfoil ([], self.design_airfoil)

        if flapped_airfoil is not None:

            # plot flapped airfoil 

            pen   = pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)
            label = f"{self.design_airfoil.name_to_show} flapped"

            self._plot_dataItem  (flapped_airfoil.x, flapped_airfoil.y, name=label, pen = pen, 
                                    antialias = False, zValue=5)

            # plot flap angle 

            x = (1.0 + flapped_airfoil.x[0]) / 2
            y = flapped_airfoil.y[0] / 2

            self._plot_point ((x,y), size=0,text=f"{self.flap_setter.flap_angle:.1f}°", anchor=(-0.1, 0.5))

        # plot hinge point at the initial, unflapped airfoil

        x = self.flap_setter.x_flap
        airfoil_base = self.flap_setter.airfoil_base

        y_base = airfoil_base.geo.lower.yFn(x)
        thick  = airfoil_base.geo.thickness.yFn(x)
        y = y_base + self.flap_setter.y_flap * thick 

        self._plot_point ((x,y), color=color, size=10,text=f"Hinge {self.flap_setter.x_flap:.1%}" )



class TE_Gap_Artist (Artist):
    """Plot airfoil based on current TE gap"""

    def __init__ (self, *args, **kwargs):

        self._xBlend = None                             # blend range
        super().__init__ (*args, **kwargs)


    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list

    @property
    def design_airfoil (self) -> Airfoil:
        for airfoil in self.airfoils:
            if airfoil.usedAsDesign:
                return airfoil 

    @property
    def xBlend (self): return self._xBlend

    def set_xBlend (self, xBlend):
        """ set blend range for LE circle """
        self._xBlend = xBlend 
        self.set_show (xBlend is not None)


    def _plot (self): 
    
        if not self.design_airfoil: return

        color = _color_airfoil (self.airfoils, self.design_airfoil)
        color.setAlphaF (0.8)

        for line in [self.design_airfoil.geo.upper, 
                     self.design_airfoil.geo.lower]:
            
            style = _linestyle_of (line._type)
            pen   = pg.mkPen(color, width=1, style=style)

            p = self._plot_dataItem (line.x, line.y, pen = pen, zValue=5)

            # te gap point for upper line 

            if line.type == Line.Type.UPPER:
                pt = Movable_TE_Point (self.design_airfoil.geo, p, show_label_static_with_value=True,
                                       movable=False, color=color)
                self._add (pt) 

        # plot blending range

        if self.xBlend is not None:

            pen = pg.mkPen("dimgray", width=1)
            lr  = pg.LinearRegionItem (values=[1.0-self.xBlend, 1.0], pen=pen, movable=False, span=(0.2, 0.8))

            lab = pg.InfLineLabel(lr.lines[0], f"Blending Range {self.xBlend:.0%}", position=0.95, 
                                  color=Artist.COLOR_LEGEND)

            self._add(lr)




class LE_Radius_Artist (Artist):
    """Plot airfoil based on current LE radius"""

    def __init__ (self, *args, **kwargs):

        self._xBlend = None                             # blend range
        super().__init__ (*args, **kwargs)


    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list

    @property
    def design_airfoil (self) -> Airfoil:
        for airfoil in self.airfoils:
            if airfoil.usedAsDesign:
                return airfoil 

    @property
    def xBlend (self): return self._xBlend

    def set_xBlend (self, xBlend):
        """ set blend range for LE circle """
        self._xBlend = xBlend 
        self.set_show (xBlend is not None)


    def _plot (self): 
    
        if not self.design_airfoil: return

        color = _color_airfoil (self.airfoils, self.design_airfoil)
        color.setAlphaF (0.8)
            
        for line in [self.design_airfoil.geo.upper, 
                     self.design_airfoil.geo.lower]:
            
            style = _linestyle_of (line._type)
            pen   = pg.mkPen(color, width=1, style=style)

            p = self._plot_dataItem (line.x, line.y, pen = pen, zValue=5)

        # plot le circle 

        radius = self.design_airfoil.geo.le_radius
        circle_item = self._plot_circle (radius, 0, color=color, size=2*radius, 
                                        style=Qt.PenStyle.DotLine)
        pl = Movable_LE_Point (self.design_airfoil.geo, circle_item, 
                               show_label_static_with_value=True, movable=False, color=color)
        self._add(pl) 

        # plot blending range

        if self.xBlend is not None:

            pen = pg.mkPen("dimgray", width=1)
            lr  = pg.LinearRegionItem (values=[0, self.xBlend], pen=pen, movable=False, span=(0.2, 0.8))

            lab = pg.InfLineLabel(lr.lines[1], f"Blending Range {self.xBlend:.0%}", position=0.95,  
                                  color=Artist.COLOR_LEGEND) 

            self._add(lr)



class Bezier_Artist (Artist):
    """Plot and edit airfoils Bezier control points """

    sig_bezier_changed     = pyqtSignal()           # bezier curve changed 


    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list

    def refresh_from_side (self, aLinetype):

        p : Movable_Side_Bezier
        for p in self._plots: 
            if p._side.type == aLinetype:
                p.refresh()

    def _plot (self): 
    
        airfoil: Airfoil

        for airfoil in self.airfoils:
            if airfoil.isBezierBased and airfoil.isLoaded:

                color = _color_airfoil (self.airfoils, airfoil)
                movable = airfoil.isEdited and self.show_mouse_helper

                side : Side_Airfoil_Bezier
                for side in [airfoil.geo.lower, airfoil.geo.upper]:     # paint upper on top 

                    p = Movable_Side_Bezier (airfoil, side, color=color, movable=movable,
                                              on_changed=self.sig_bezier_changed.emit) 
                    self._add(p)
 



class Bezier_Deviation_Artist (Artist):
    """Plot deviation of Bezier curves to target airfoil """

    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list


    def _plot (self): 
    
        # check - is there a design airfoil and a target (normal) airfoil 

        geo_from   : Geometry = None 
        geo_target : Geometry = None 

        for airfoil in self.airfoils:
            if airfoil.usedAsDesign:
                geo_from = airfoil.geo 
            elif airfoil.usedAs == usedAs.NORMAL:
                geo_target = airfoil.geo

        if not geo_from or not geo_target: return 

        # plot difference as thick lines at deviation check coordinates 

        label = "Deviation x 10"
        color = COLOR_WARNING  
        color.setAlphaF (0.6)

        for side in [Line.Type.UPPER, Line.Type.LOWER]:     

            if side == Line.Type.UPPER:
                from_line   = geo_from.upper  
                target_line = geo_target.upper
            else:
                from_line   = geo_from.lower  
                target_line = geo_target.lower

            # get deviation from Matcher 

            x, y, devi = Line.deviation_to (from_line, target_line, reduce_points=False, fast=True)

            # build array of coordinate pairs for fast plot -> connect='pairs'

            x_dbl = np.zeros ((len(x)-2)*2)
            y_dbl = np.zeros ((len(x)-2)*2)

            j = 0 
            for i in range (1, len(x)-1):
                if abs(devi[i]) > 1e-6:                     # avoid pyqtgraph artefacts
                    x_dbl[j] = x[i]
                    y_dbl[j] = y[i]
                    j += 1
                    x_dbl[j] = x[i]
                    y_dbl[j] = y[i] - (devi[i] * 10) 
                    j += 1

            x_dbl = x_dbl [:j]
            y_dbl = y_dbl [:j]

            if len(x_dbl):
                self._plot_dataItem  (x_dbl, y_dbl, pen=pg.mkPen(color, width=3), name=label, 
                                        antialias=False, zValue=1, connect='pairs')    




class Hicks_Henne_Artist (Artist):
    """Plot and edit airfoils Hicks Henne functions of airfoils  """

    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list

    def _plot (self): 
    
        y_factor = 20 

        for airfoil in self.airfoils:
            if airfoil.isHicksHenneBased and airfoil.isLoaded:

                color_airfoil = _color_airfoil (self.airfoils, airfoil)

                side : Side_Airfoil_HicksHenne
                for side in [airfoil.geo.upper, airfoil.geo.lower]:     # paint upper on top 

                    hh : HicksHenne
                    for ih, hh in enumerate(side.hhs):

                        color = color_in_series (color_airfoil,ih, len(side.hhs), delta_hue=0.2)    
                        style = Qt.PenStyle.DashDotDotLine if side.isUpper else Qt.PenStyle.DashLine
                        pen   = pg.mkPen(color, width=0.7, style=style)

                        if ih == 0:
                            label = f"Hicks Henne upper x {y_factor}" if side.isUpper else f"Hicks Henne lower x {y_factor}"
                        else: 
                            label = None 

                        # plot hh function 
                        x = side.x 
                        y = hh.eval (x) * y_factor # + delta_y

                        self._plot_dataItem  (x, y,pen = pen, antialias = False, zValue=4, name=label)

                        # plot maximum marker 

                        x = hh.location
                        y = hh.strength  * y_factor   

                        text = f"HH{ih+1}"
                        anchor = (-0.05,1.05) if side.isUpper else (-0.05,-0.05)

                        self._plot_point ((x, y), symbol = '+', color=color, text=text, textColor=color, anchor=anchor,
                                          zValue=4)

 



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

        nairfoils = len(self.airfoils)
        
        airfoil: Airfoil

        for airfoil in self.airfoils:

            color = _color_airfoil (self.airfoils, airfoil)

            sides = []
            if self.show_upper: sides.append (airfoil.geo.curvature.upper)
            if self.show_lower: sides.append (airfoil.geo.curvature.lower)

            side : Line
            for side in sides:
                x = side.x
                y = side.y      
                if side.type == Line.Type.UPPER:
                    pen = pg.mkPen(color, width=1, style=Qt.PenStyle.SolidLine)
                else: 
                    pen = pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)

                label   = f"{side.name} - {_label_airfoil (self.airfoils, airfoil)}"
                zValue = 3 if airfoil.usedAsDesign else 1

                self._plot_dataItem (x, y, name=label, pen=pen, zValue=zValue)

                # plot derivative1 of curvature ('spikes') 

                if self.show_derivative and (nairfoils == 1 or airfoil.usedAsDesign):
                    pen = QPen (pen)
                    pen.setColor (QColor('red'))
                    name = f"{side.name} - Derivative"
                    self._plot_dataItem (x, -derivative1(x,y), name=name, pen=pen)

                # plot max points at le and te and reversals

                self._plot_le_te_max_point (side, color, airfoil.usedAsDesign)
                self._plot_reversals       (side, color, airfoil.usedAsDesign)



    def _plot_le_te_max_point (self, aSide : Line, color, usedAsDesign : bool ):
        """ plot the max values at LE and te"""

        color   = QColor (color).darker (130)
        zValue  = 5 if usedAsDesign else 3

        # le 
        anchor = (0,1) if aSide.isUpper else (0,0)
        text   = f"max {aSide.name} {aSide.max_xy[1]:.0f}"

        self._plot_point (aSide.max_xy, color=color, text=text, anchor=anchor, zValue=zValue,
                          textColor=color)

        # te 
        anchor = (1,1) if aSide.isUpper else (1,0)
        text   = f"max {aSide.name} {aSide.te[1]:.1f}"

        self._plot_point (aSide.te, color=color, text=text, anchor=anchor, zValue=zValue,
                          textColor=color)


    def _plot_reversals (self, side : Line, color, usedAsDesign : bool):
        """ annotate reversals of curvature """

        color   = QColor (color).darker (130)
        zValue  = 5 if usedAsDesign else 3

        reversals = side.reversals()
        if reversals:
            for reversal_xy in reversals: 
                anchor = (1,1.2) if side.isUpper else (1,-0.2)

                self._plot_point (reversal_xy, color=color, size=2, text="R", anchor=anchor,
                                  zValue=zValue, textColor=color)




class Airfoil_Line_Artist (Artist, QObject):
    """
    Plot thickness, camber line of an airfoil, print max values 
    """

    sig_geometry_changed     = pyqtSignal()          # airfoil data changed 

    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list


    def _plot (self): 

        airfoil: Airfoil

        for iair, airfoil in enumerate (self.airfoils):

            color = _color_airfoil (self.airfoils, airfoil)
            color.setAlphaF (0.8)

            # plot all 'lines' of airfoil 

            for line in airfoil.geo.lines_dict.values():
                
                style = _linestyle_of (line._type)
                if airfoil.usedAsDesign:
                    zValue = 5                                  # plot design on top 
                else:
                    zValue = 4 

                is_upper = line.type == Line.Type.UPPER
                is_lower = line.type == Line.Type.LOWER
                is_upper_lower = is_upper or is_lower

                if iair == 0 and not is_upper_lower:            # line legend only for the first airfoil 
                    name = line.name
                else: 
                    name = None 

                # plot upper and lower only for design (to visualize move highpoint)

                if airfoil.usedAsDesign or not is_upper_lower:
                    pen = pg.mkPen(color, width=1, style=style)
                    p = self._plot_dataItem (line.x, line.y, pen = pen, name = name, zValue=zValue)
                else: 
                    p = None

                # plot its highpoint 

                ph = Movable_Highpoint (airfoil.geo, line, p, 
                                            movable=airfoil.isEdited, color=color,
                                            on_changed=self.sig_geometry_changed.emit )
                self._add (ph) 


                # te gap point for DESIGN 

                if airfoil.usedAsDesign and is_upper:
                    pt = Movable_TE_Point (airfoil.geo, p, 
                                            movable=airfoil.usedAsDesign, color=color,
                                            on_changed=self.sig_geometry_changed.emit )
                    self._add (pt) 


            # plot le circle 

            radius = airfoil.geo.le_radius
            
            circle_item = self._plot_circle (radius, 0, color=color, size=2*radius, 
                                            style=Qt.PenStyle.DotLine)
            pl = Movable_LE_Point (airfoil.geo, circle_item, 
                                    movable=airfoil.usedAsDesign, color=color,
                                    on_changed=self.sig_geometry_changed.emit )
            self._add(pl) 



class Polar_Artist (Artist):
    """Plot the polars of airfoils """


    def __init__ (self, axes, modelFn, 
                  xyVars = (var.CD, var.CL), 
                  **kwargs):
        super().__init__ (axes, modelFn, **kwargs)

        self._show_points = False                       # show point marker 
        self._show_bubbles = False                      # show bubble info
        self._xyVars = xyVars                           # definition of x,y axis


    @property
    def show_points(self): return self._show_points
    def set_show_points (self, aBool): 
        self._show_points = aBool 
        self.refresh()


    @property
    def show_bubbles (self): return self._show_bubbles
    def set_show_bubbles (self, aBool): 
        self._show_bubbles = aBool 
        self.refresh()


    @property
    def xyVars(self): return self._xyVars
    def set_xyVars (self, xyVars: Tuple[var, var]): 
        """ set new x, y variables for polar """
        self._xyVars = xyVars 
        self.refresh()


    @property
    def airfoils (self) -> list [Airfoil]: return self.data_list


    def _plot (self): 
        """ do plot of airfoil polars in the prepared axes  """

        if not self.airfoils : return 

        # cancel all polar generations which are not for this current set of airfoils 
        #   to avoid to many os worker threads 

        Polar_Task.terminate_instances_except_for (self.airfoils)

        # load or generate polars which are not loaded up to now

        for airfoil in self.airfoils: 
            polarSet = airfoil.polarSet
            if polarSet:
                polarSet.load_or_generate_polars ()
            else:
                logger.debug (f"{airfoil} has no polarSet to plot")

        # plot polars of airfoils

        nPolar_plotted    = 0 
        nPolar_generating = 0                     # is there a polar in calculation 
        error_msg         = []  

        airfoil: Airfoil
        for airfoil in self.airfoils:

            if airfoil.polarSet:
 
                color_airfoil = _color_airfoil (self.airfoils, airfoil)

                # first filter only visible polars to get number of polars and plot 

                polarSet : Polar_Set = airfoil.polarSet
                polars =  [p for p in polarSet.polars if p.active] 

                for iPolar, polar in enumerate(polars [::-1]): 

                    if polar.error_occurred:
                        # in error_msg could be e.g. '<' 
                        error_msg.append (f"'{airfoil.name_to_show} - {polar.name}': {html.escape(polar.error_reason)}")
                    elif not polar.isLoaded: 
                        nPolar_generating += 1
                    else: 
                        nPolar_plotted    += 1
                        # generate increasing color hue value for the polars of an airfoil 
                        color = color_in_series (color_airfoil, iPolar, len(polars), delta_hue=0.1)

                        self._plot_polar (self.airfoils, airfoil, polar, color)

                        # plot bubble info if available
                        if self.show_bubbles:
                            self._plot_bubble_info (polar, color)
                            

        logger.debug (f"{self} {nPolar_plotted} polars plotted, {nPolar_generating} generating ")
        
        # show error messages 

        if error_msg:
            text = '<br>'.join (error_msg)          
            self._plot_text (text, color=COLOR_ERROR, itemPos=(0.5,0.5))

        # show generating message 

        if nPolar_generating > 0: 
            if nPolar_generating == 1:
                text = f"Generating polar"
            else: 
                text = f"Generating {nPolar_generating} polars"
            self._plot_text (text, color= "dimgray", fontSize=self.SIZE_HEADER, itemPos=(0.5, 1))

            # refresh for new polars 
            # QTimer().singleShot(1000, self.check_for_new_polars)     # delayed emit 



    def _plot_polar (self, airfoils: list[Airfoil], airfoil : Airfoil, polar: Polar, color): 
        """ plot a single polar"""

        airfoils_with_design = False 
        for a in airfoils:
            if a.usedAsDesign: airfoils_with_design = True 

        # build nice label 

        label = f"{_label_airfoil (airfoils, airfoil)} - {polar.name}" 

        if not polar.isLoaded:
            label = label + ' generating'                       # async polar generation  

        # set linewidth 

        antialias = True

        if self._show_points:
            linewidth=0.5
        elif airfoil.usedAs == usedAs.FINAL:  
            linewidth=1.5
            antialias = True
        elif airfoil.usedAs == usedAs.DESIGN:  
            linewidth=1.5
            antialias = True
        elif airfoil.usedAs == usedAs.NORMAL and not airfoils_with_design:  
            linewidth=1.5
            antialias = True
        else:
            linewidth=1.0

        # NORMAl and DESIGN polar above other polars 

        if airfoil.usedAs == usedAs.FINAL:
            zValue = 5
        elif airfoil.usedAs == usedAs.DESIGN:
            zValue = 3
        elif airfoil.usedAs == usedAs.NORMAL:
            zValue = 2
        else: 
            zValue = 1

        # finally plot 

        pen = pg.mkPen(color, width=linewidth)
        sPen, sBrush, sSize = pg.mkPen(color, width=1), 'black', 7
        s = 'o' if self.show_points else None 

        x,y = polar.ofVars (self.xyVars)

        self._plot_dataItem  (x, y, name=label, pen = pen, 
                                symbol=s, symbolSize=sSize, symbolPen=sPen, symbolBrush=sBrush,
                                antialias = antialias, zValue=zValue)


    def _plot_bubble_info (self, polar: Polar, color : QColor):
        """ plot bubble info of polar """

        is_xtr_plot = var.XTRB in self.xyVars or var.XTRT in self.xyVars

        # bubble symbol style and color
        color_symbol =  QColor (color) 
        color_symbol.setAlphaF (0.7) 
        brush_color_symbol =  QColor ('black') 
        brush_color_symbol.setAlphaF (0.6) 
        brush_symbol = pg.mkBrush(brush_color_symbol)

        # bubble line in xtr style and color        
        color_line   =  QColor (color) 
        color_line.setAlphaF (0.4) 
        pen_line     = pg.mkPen(color_line, width=3)  
        
        x,y = polar.ofVars (self.xyVars)

        if polar.has_bubble_top:
            name = 'bubble upper side'
            for i, bubble in enumerate(polar.bubble_top):
                if bubble:
                    if is_xtr_plot:
                        if var.XTRT in self.xyVars:
                            self._plot_bubble_in_xtr (bubble, x[i], y[i], name, pen_line)
                    else:
                        self._plot_point ((x[i], y[i]), name=name, color=color_symbol, symbol='t1', size=9, brush=brush_symbol)

        if polar.has_bubble_bot:
            # plot bubble on lower side
            name = 'bubble lower side'
            for i, bubble in enumerate(polar.bubble_bot):
                if bubble:
                    if is_xtr_plot:
                        if var.XTRB in self.xyVars:
                            self._plot_bubble_in_xtr (bubble, x[i], y[i], name, pen_line)
                    else:
                        self._plot_point ((x[i], y[i]), name=name, color=color_symbol, symbol='t', size=9, brush=brush_symbol)


    def _plot_bubble_in_xtr (self, bubble :tuple, x, y, name, pen_line):
        """ plot bubble in xtr diagram as a line """

        if self.xyVars[0] == var.XTRT or self.xyVars[0] == var.XTRB:        # horizontal xtr plot
            x = list(bubble)
            y = [y,y]
        else:                                                               # vertical xtr plot
            x = [x,x]
            y = list(bubble)  
        self._plot_dataItem  (x, y, name=name, pen = pen_line, zValue=5)
