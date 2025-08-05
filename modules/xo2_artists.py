#!/usr/bin/env pythonupper
# -*- coding: utf-8 -*-

"""  

The "Artists" to plot a airfoil object on a pg.PlotItem 

"""
import html 

from typing                     import Callable

from base.artist                import *
from base.common_utils          import *

from model.airfoil              import Line
from model.polar_set            import * 
from model.xo2_input            import OpPoint_Definition, OpPoint_Definitions, OPT_TARGET, OPT_MAX, OPT_MIN, GeoTarget_Definitions
from model.xo2_results          import OpPoint_Result, Xo2_Results, Optimization_History_Entry, GeoTarget_Result

from airfoil_artists            import _color_airfoil

from PyQt6.QtGui                import QColor, QBrush, QPen, QPainterPath, QTransform
from PyQt6.QtCore               import pyqtSignal


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# -------- helper functions ------------------------

def _size_opPoint (weighting : float, normal_size = 13) -> float:
    """ returns plot size of an opPoint (def) depending on weighting"""

    # weighting can be negative (meaning fixed weighting - no dynamic)
    return abs(weighting) ** 0.7 * normal_size 



# -------- Movable Points  ------------------------


class Movable_Xo2_OpPoint_Def (Movable_Point):
    """ 
    Movable opPoint definition
    """

    name = "OpPoint Def"

    COLOR = QColor ("darkturquoise")

    # -- special symbols for min/max optTypes 
    #
    #               .--x
    #               |
    #               y
    #

    @staticmethod
    def _symbol_opt_up (width=1.0, height1=0.3, height2=0.5):
        path = QPainterPath()

        path.addRect(QtCore.QRectF(-width / 2, -height1 / 2, width, height1))
        # vertcial line
        path.moveTo(0.0, -height1 / 2)
        path.lineTo(0.0, -height2 * 2)
        #triangle
        path.moveTo(-width / 2, -height2 * 2)
        path.lineTo( width / 2, -height2 * 2)
        path.lineTo(       0.0, -height2 * 2 - height2)
        path.lineTo(-width / 2, -height2 * 2)

        return path

    tr : QTransform = QTransform()
    tr.rotate(-90)                                  # because y is downward

    SYMBOL_OPT_UP    = _symbol_opt_up ()                       
    SYMBOL_OPT_LEFT  = tr.map (SYMBOL_OPT_UP)                         
    SYMBOL_OPT_DOWN  = tr.map (SYMBOL_OPT_LEFT)                        
    SYMBOL_OPT_RIGHT = tr.map (SYMBOL_OPT_DOWN)                        


    def __init__ (self, pi : pg.PlotItem, 
                    opPoint_def : OpPoint_Definition,
                    xyVars : Tuple[var, var], 
                    movable = True, 
                    on_selected = None,
                    on_dblClick = None,
                    on_delete   = None,
                    **kwargs):

        self._pi = pi
        self._opPoint_def = opPoint_def
        self._xyVars = xyVars

        self._callback_selected = on_selected
        self._callback_dblClick = on_dblClick
        self._callback_delete   = on_delete
        self._highlight_item    = None                       

        brush = QColor ("black")
        brush.setAlphaF (0.3) 

        size = _size_opPoint (opPoint_def.weighting)

        super().__init__(self._point_xy(), movable=movable, label_anchor = (0, 0.5),
                            color=QColor(self.COLOR), brush=brush,
                            symbol=self._symbol(), size=size, show_label_static = True, **kwargs)

        self.sigShiftClick.connect  (self._delete_opPoint_def)


    def _symbol (self) -> QPainterPath | str:
        """ returns the symbol for self depending on optType"""

        xVar, yVar = self._xyVars

        optVar, optType = self._opPoint_def.optVar_type_for_xyVars (self._xyVars)

        if optType == OPT_TARGET:
            s = 's'
        elif optType == OPT_MAX:
            if optVar == yVar:
                s = self.SYMBOL_OPT_UP
            else:
                s = self.SYMBOL_OPT_RIGHT
        elif optType == OPT_MIN:
            if optVar == yVar:
                s = self.SYMBOL_OPT_DOWN
            else:
                s = self.SYMBOL_OPT_LEFT
        else: 
            s = 'star'
        
        return s


    def _delete_opPoint_def (self, _):
        """ shift-click - delete me opPoint_dev"""

        if callable(self._callback_delete):
            # callback / emit signal delayed so we leave the scope of Graphics 
            QTimer() .singleShot(10, lambda: self._callback_delete (self._opPoint_def))   


    def _point_xy (self) -> tuple:  
        return self._opPoint_def.xyValues_for_xyVars (self._xyVars)     


    @override
    def mouseClickEvent(self, ev):
        """ handle callback to parent when clicked with left button to select self """

        if not self.moving and ev.button() == QtCore.Qt.MouseButton.LeftButton  \
                           and not (ev.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier): # shift is handled in super
            if callable(self._callback_selected):
                ev.accept()

                self._opPoint_def.set_as_current()

                # callback / emit signal delayed so we leave the scope of Graphics 
                QTimer() .singleShot(10, lambda: self._callback_selected ())   
        else:
            super().mouseClickEvent (ev)


    @override
    def mouseDoubleClickEvent(self, ev):
        """ handle callback to parent when double clicked """
        if callable(self._callback_dblClick):
            ev.accept()

            self._opPoint_def.set_as_current()

            # callback / emit signal delayed so we leave the scope of Graphics 
            QTimer() .singleShot(10, lambda: self._callback_dblClick ())   
        else:
            super().mouseDoubleClickEvent (ev)


    @override
    def _moving (self, _):
        """ slot -point is moved"""
        self._opPoint_def.set_xyValues_for_xyVars (self._xyVars, (self.x,self.y))

        self.setPos (self._point_xy())                      # ... if we run against limits 

        # also refresh pos of highlight item 
        if isinstance (self._highlight_item, pg.TargetItem):
            self._highlight_item.setPos (self.pos())


    @override
    def label_static (self, *_) -> str:
        """ the static label - can be overloaded """
        return f"{self._opPoint_def.iPoint}" 

    @override
    def label_moving (self, *_):
        """ label for hovering or moving"""
        return f"{self._opPoint_def.labelLong_for (self._xyVars, fix=False)}"

    @override
    def _finished (self, _):
        """ slot - point moving is finished"""

        self._opPoint_def.set_as_current()

        # callback / emit signal delayed so we leave the scope of Graphics 
        QTimer() .singleShot(10, lambda: self._callback_changed ())   


    def set_highlight_item (self, aItem: pg.TargetItem):
        """ a point item used to highlight current"""

        self._highlight_item = aItem
        if self._highlight_item:
            self._highlight_item.setPos (self.pos())




# -------- Artists ------------------------


class Xo2_OpPoint_Defs_Artist (Artist):
    """ Plot / Modify Xoptfoil2 operating point defin itions """

    sig_opPoint_def_changed     = pyqtSignal ()             # opPoint_def changed changed 
    sig_opPoint_def_selected    = pyqtSignal ()
    sig_opPoint_def_dblClick    = pyqtSignal ()

    def __init__ (self, *args, 
                  isRunning_fn = None, 
                  xyVars = (var.CD, var.CL), 
                  **kwargs):
        super().__init__ (*args, **kwargs)

        self._xyVars = xyVars                               # definition of x,y axis
        self._isRunning_fn = isRunning_fn


    @property
    def xyVars(self): return self._xyVars
    def set_xyVars (self, xyVars: Tuple[var, var]): 
        """ set new x, y variables for polar """
        self._xyVars = xyVars 
        self.refresh()


    @property
    def opPoint_defs (self) -> OpPoint_Definitions: 
        return self.data_list

    @property
    def opPoint_def_are_editable (self) -> bool:
        """ True if optimier is ready - definitions can be changed"""
        return not self._isRunning_fn() if callable (self._isRunning_fn) else True


    def _plot (self): 

        legend_name = "Op Point Definition" 

        for opPoint_def in self.opPoint_defs:

            x, y = opPoint_def.xyValues_for_xyVars (self.xyVars)

            # does it fit into this x,y polar view

            if x is not None and y is not None: 

                pt = Movable_Xo2_OpPoint_Def  (self._pi, opPoint_def, self.xyVars, 
                                                movable=self.opPoint_def_are_editable and self.show_mouse_helper,
                                                on_changed =self.sig_opPoint_def_changed.emit,
                                                on_delete  =self._on_delete,
                                                on_dblClick=self.sig_opPoint_def_dblClick.emit,
                                                on_selected=self.sig_opPoint_def_selected.emit)
                self._add (pt, name = legend_name) 

                legend_name = None                                  # legend only once 

                # highlight current opPoint def for edit with a big circle 

                if opPoint_def == self.opPoint_defs.current_opPoint_def and self.opPoint_def_are_editable:

                    brush = QColor (Movable_Xo2_OpPoint_Def.COLOR)
                    brush.setAlphaF (0.3)
                    highlight_item = self._plot_point (0.02,0.2, color="black", size=60, brush=brush)

                    pt.set_highlight_item (highlight_item)


        # make scene clickable to add wing section - delayed as during init scene is not yet available

        QTimer().singleShot (10, self._connect_scene_mouseClick)

        self.show_help_message ()


    def show_help_message (self):
        """ show mouse helper message"""
        msg = "OpPoint: click to select,  double-click to edit,  shift-click to remove,  ctrl-click to add"
        self.set_help_message (msg)


    def _connect_scene_mouseClick (self): 
        """ connect mouse click in scene to slot"""           

        scene : pg.GraphicsScene = self._pi.scene()
        if scene:  scene.sigMouseClicked.connect (self._scene_clicked)


    @override
    def _remove_plots(self):
        """ overloaded to disconnect older slot when doing refresh"""

        super()._remove_plots()

        scene : pg.GraphicsScene = self._pi.scene()

        try:                            # slot could be not connected up to now
            scene.sigMouseClicked.disconnect (self._scene_clicked)
        except:
            pass


    def _scene_clicked (self, ev : MouseClickEvent):
        """ 
        slot - mouse click in scene of self - handle add wing section with crtl-click 
        """ 

        # handle only ctrl-click
        if not (ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier): return  
       
        # was the scene click in my viewbox?
        if isinstance(ev.currentItem, pg.ViewBox):
            viewbox : pg.ViewBox = ev.currentItem
        else:
            viewbox : pg.ViewBox = ev.currentItem.getViewBox()

        if viewbox == self._pi.vb:                     # is this my view box (or of another plot item)? 
            
            # get scene coordinates of click pos and map to view box 
            ev.accept()
            pos : pg.Point = viewbox.mapSceneToView(ev.scenePos())

            # create new opPoint_def in the list of opPoint_defs 
            self.opPoint_defs.create_in_xyVars (self.xyVars, pos.x(), pos.y())

            self.sig_opPoint_def_changed.emit()


    def _on_delete (self, opPoint_def : OpPoint_Definition):
        """ callback of Movable Point to delete opPoint_def"""

        self.opPoint_defs.delete (opPoint_def)

        self.sig_opPoint_def_changed.emit ()


class Xo2_OpPoint_Artist (Artist):
    """ Plot Xoptfoil2 operating point results """

    def __init__ (self, *args, 
                  opPoint_defs_fn : Callable = None,
                  opPoint_results_fn : Callable = None,
                  prev_opPoint_results_fn : Callable = None,
                  xyVars = (var.CD, var.CL), 
                  **kwargs):

        self._xyVars = xyVars                                       # definition of x,y axis
        self._opPoint_defs_fn = opPoint_defs_fn                     # method to get opPoint definitions
        self._opPoint_results_fn = opPoint_results_fn               # method to get opPoint results
        self._prev_opPoint_results_fn = prev_opPoint_results_fn     # method to get previous opPoint results 

        super().__init__ (*args, **kwargs)

    @property
    def xyVars(self): return self._xyVars
    def set_xyVars (self, xyVars: Tuple[var, var]): 
        """ set new x, y variables for polar """
        self._xyVars = xyVars 
        self.refresh()


    def _plot (self): 
        """ plot all opPoints"""

        opPoints :      list[OpPoint_Result] = self._opPoint_results_fn() 
        if not opPoints: return 

        opPoint_defs :  list[OpPoint_Definition] = self._opPoint_defs_fn() 
        prev_opPoints : list[OpPoint_Result] = self._prev_opPoint_results_fn() [:] 

        legend_name = f"Op Point Result - Design {opPoints[0].idesign}"

        textFill = QColor ("black")
        textFill.setAlphaF (0.5)
       
        for iop, opPoint in enumerate (opPoints):

            prev_opPoint = prev_opPoints[iop] if prev_opPoints else None
            x = opPoint.get_value (self.xyVars[0])
            y = opPoint.get_value (self.xyVars[1])

            # sanity - opPoint def could be deleted in the meantime 
            opPoint_def = opPoint_defs[iop] if len(opPoint_defs) == len (opPoints) else None

            color  = self._opPoint_color  (opPoint, opPoint_def)
            symbol = self._opPoint_symbol (opPoint, prev_opPoint)
            label  = self._opPoint_label  (opPoint, opPoint_def, self.xyVars)
            size   = _size_opPoint (opPoint.weighting)

            textColor = QColor (color).darker(130)

            self._plot_point ((x,y), color=color, size=size, symbol=symbol, zValue=20, name=legend_name,
                              text=label, anchor=(0, 0.5), textOffset = (8,0), textColor=textColor, textFill=textFill)

            legend_name = None 

        # message if dynamic weighting of opPoints occured 

        if prev_opPoints:
            weightings      = [op.weighting for op in opPoints]
            prev_weightings = [op.weighting for op in prev_opPoints]
            if sum(weightings) != sum (prev_weightings):
                self._plot_text ('New weightings applied', color= "dimgray", fontSize=self.SIZE_HEADER, itemPos=(0.5, 1))

        
    def _opPoint_color (self, opPoint : OpPoint_Result, opPoint_def : OpPoint_Definition | None) -> QColor:
        """ color of opPoint depending on % deviation """

        # sanity 
        if opPoint_def is None: 
            return COLOR_OK

        deviation = opPoint.deviation

        optType = opPoint_def.optType
        optVar  = opPoint_def.optVar
        allow_improved = opPoint_def._myList.allow_improved_target

        if optType == OPT_TARGET:                            # targets - take deviation to target
            # Xoptfoil2 - colors for deviation 
            #
            #   if (op_spec%allow_improved_target .and. opt_type == 'target-drag' .and. dev < 0d0) then 
            #     how_good = Q_GOOD
            #   else if (op_spec%allow_improved_target .and. opt_type /= 'target-drag' .and. dev > 0d0) then 
            #     how_good = Q_GOOD
            #   else
            #     how_good = r_quality (abs(dev), 0.1d0, 2d0, 10d0)      ! in percent
            #   end if
            if allow_improved   and optVar == var.CD and deviation < 0.0:
                color = COLOR_GOOD
            elif allow_improved and optVar != var.CD and deviation > 0.0:
                color = COLOR_GOOD
            else:
                deviation = abs(deviation)
                if deviation < 0.1:
                    color = COLOR_GOOD
                elif deviation >= 10:
                    color = COLOR_ERROR
                elif deviation >= 2.0:
                    color = COLOR_WARNING
                elif deviation >= 0.1:
                    color = COLOR_OK
                else:
                    color = COLOR_OK
        else:                                               # min/max - deviation is improvement 
            # Xoptfoil2 - colors for improvement 
            #
            # if (improv <= 0d0) then 
            #     how_good = Q_BAD
            # elseif (improv < 5d0) then 
            #     how_good = Q_OK
            # elseif (improv >= 5d0) then 
            #     how_good = Q_GOOD
            # else
            #     how_good = Q_BAD
            # end if 
            if optType == OPT_MAX:                          # eg. OPT_MAX of 'glide' - more is better 
                improv = deviation
            else:                                           # eg OPT_MIN of 'cd' - less is better
                improv = deviation

            if improv <= -0.1:
                color = COLOR_WARNING
            elif improv < 2.0:
                color = COLOR_OK
            elif improv >= 2.0:
                color = COLOR_GOOD
            else:
                color = COLOR_ERROR
        return color 


    def _opPoint_symbol (self, opPoint : OpPoint_Result, prev_opPoint : OpPoint_Result | None ):
        """ a triangle in the direction of value change """

        if prev_opPoint is None: return 'o'

        x = opPoint.get_value (self.xyVars[0])
        y = opPoint.get_value (self.xyVars[1])
        prev_x = prev_opPoint.get_value (self.xyVars[0])
        prev_y = prev_opPoint.get_value (self.xyVars[1])

        if prev_x > x:
            symbol = 't3'               # triangle to left
        elif prev_x < x:
            symbol = 't2'               # triangle to right
        elif prev_y > y:
            symbol = 't'                # triangle to down
        elif prev_y < y:
            symbol = 't1'               # triangle to up
        else: 
            symbol = 'o'
        return symbol

        
    def _opPoint_label (self, opPoint : OpPoint_Result, opPoint_def : OpPoint_Definition | None, xyVars: tuple) -> str:
        """ label of opPoint depending on % deviation """

        # sanity 
        if opPoint_def is None: return None

        optVar  = opPoint_def.optVar
        optType = opPoint_def.optType
        allow_improved = opPoint_def._myList.allow_improved_target

        # optVar must be in diagram to show distanc 

        if not (optVar in xyVars): return None 

        # set distance = 0 if 'allow_improved_target' and result (distance) is better

        distance = opPoint.distance

        if optType == OPT_TARGET:                            # targets - take deviation to target

            if allow_improved   and optVar == var.CD and distance < 0.0:
                distance = 0.0
            elif allow_improved and optVar != var.CD and distance > 0.0:
                distance = 0.0
            else:
                distance = abs(distance)

        # format value for label 

        label = None 

        if  optType == OPT_TARGET:                              # targets - take deviation to target

            if optVar == var.CD and round_down (distance,5):
                label = f"delta {optVar}: {distance:.5f}"
            elif optVar != var.CD and round_up (distance,2):
                label = f"delta {optVar}: {distance:.2f}"        
            else: 
                label = f"hit"        

        else:                                               # min/max - deviation is improvement 

            if  opPoint_def.optType == OPT_MAX:             # eg. OPT_MAX of 'glide' - more is better 
                improv = distance
            else:                                           # eg OPT_MIN of 'cd' - less is better
                improv = distance

            if improv: 
                if optVar == var.CD:
                    label = f"d{var.CD} {improv:.5f}"
                else:
                    label = f"d{optVar} {improv:.2f}"
        return label 
        



class Xo2_Design_Radius_Artist (Artist):
    """ Plot Xoptfoil2 design radius during optimization """

    @property
    def results (self) -> Xo2_Results: 
        return self.data_object
    
    @property
    def steps (self) -> list[Optimization_History_Entry]: 
        """ optimization step entries up to now """
        return self.results.steps  

    def _plot (self): 

        radius_list = [entry.design_radius for entry in self.steps]

        if radius_list:
            p = pg.PlotDataItem  (radius_list)
            self._add (p)

            # plot last as point 
            x = len(radius_list) - 1
            y = radius_list[-1]
            back_color = QColor ("black")
            back_color.setAlphaF (0.5)

            self._plot_point (x,y, size=5, color=COLOR_OK, text = f"{y:.3f}", textFill=back_color, anchor= (1.1, 0.9))



class Xo2_Improvement_Artist (Artist):
    """ Plot Xoptfoil2 improvement during optimization """

    @property
    def results (self) -> Xo2_Results: 
        return self.data_object
    
    @property
    def steps (self) -> list[Optimization_History_Entry]: 
        """ optimization step entries up to now """
        return self.results.steps  

    def _plot (self): 

        improvement_list = [entry.improvement for entry in self.steps]

        if improvement_list:

            p = pg.PlotDataItem  (improvement_list)
            self._add (p)

            # plot last as point 
            x = len(improvement_list) - 1
            y = improvement_list[-1]
            back_color = QColor ("black")
            back_color.setAlphaF (0.5)
            
            self._plot_point (x,y, size=5, color=COLOR_GOOD, text = f"{y:.2f}%", textFill=back_color, 
                              textOffset=(-5,0), anchor= (0.8, -0.1))




class Xo2_Transition_Artist (Artist):
    """ Plot Xoptfoil2 point of transition on design airfoil """

    # ----------  Symbol transition - create an arrow up and rotate to right 
    #
    #               .--x
    #               |
    #               y

    @staticmethod
    def _symbol_transition_right ():
        path = QPainterPath()
        # coords = [(-0.125, 0.125), (0, 0), (0.125, 0.125),
        #             (0.05, 0.125), (0.05, 0.5), (-0.05, 0.5), (-0.05, 0.125)]
        coords = [
                (0,0),
                (0,0.125),
                (-0.04, 0.125),
                (-0.04, -0.125),
                (0, -0.125),
                (0,0),
                (0.05, 0.075),
                (0.15, -0.075),
                (0.25, 0.075),
                (0.35, -0.075),
                (0.4, 0)]
        path.moveTo(*coords[0])
        for x,y in coords[1:]:
            path.lineTo(x, y)
        # path.closeSubpath()
        return path
    # tr : QTransform = QTransform()
    # tr.rotate(90)                                   # because y is downward
    # tr.translate (0,-0.5)                          # translate is after rotation ...

    # SYMBOL_TRANSITION_RIGHT  = tr.map (_symbol_transition_up())                         
    SYMBOL_TRANSITION_RIGHT  = _symbol_transition_right()                         

    # ----------------

    def __init__ (self, *args, 
                  opPoints_result_fn : Callable = None,
                  **kwargs):

        self._opPoints_result_fn = opPoints_result_fn                  # method to get opPoints of designs

        super().__init__ (*args, **kwargs)


    def _plot (self): 
        """ plot all opPoints"""

        airfoil : Airfoil = self.data_object
        opPoints_result : list[OpPoint_Result ]= self._opPoints_result_fn() 

        if not opPoints_result or not airfoil: return 

        legend_name = "Point of Transition xtr"

        color  = _color_airfoil ([], airfoil).darker (120) 
        symbol = self.SYMBOL_TRANSITION_RIGHT
        size   = 40
        brush  = QColor ("black")
        fill   = QColor ("black")
        fill.setAlphaF (0.5) 

        for side in [airfoil.geo.lower, airfoil.geo.upper]:     

            for iop, opPoint in enumerate (opPoints_result):

                x = opPoint.xtrt if side.isUpper else opPoint.xtrb
                y = side.yFn (x) 
                y = y + 0.008 if side.isUpper else y - 0.008

                text   = f"{iop+1}"
                anchor = (0.5, 1.2) if side.isUpper else (0.5, -0.2)

                self._plot_point (x,y, color=color, symbol=symbol, size=size, brush=brush, 
                                  text=text, textColor=color, anchor=anchor, textFill=fill, name=legend_name)

                legend_name = None                                      # only once for legend 


    @override
    def _add_legend_item (self, plot_item, name : str = None):
        """ add legend item having 'name'"""

        # non standard legend size of transition symbol 
        if self._pi.legend is not None and self.show_legend and name:

            if isinstance (plot_item,  pg.TargetItem):

                # create a dummy PlotItem as TargetItem won't appear in legend 
                size_legend = 30    
                pen    = plot_item.pen
                symbol = plot_item._path 
                brush  = plot_item.brush
                p = pg.ScatterPlotItem ([], [], pen= pen, brush=brush, symbol=symbol, size=size_legend, pxMode=True)
                self._add (p, name=name) 

            else: 

                super()._add_legend_item (plot_item, name=name)
     

class Xo2_GeoTarget_Artist (Artist):
    """ Plot Xoptfoil2 geometry target results """

    def __init__ (self, *args, 
                  geoTarget_defs_fn : Callable = None,
                  geoTarget_results_fn : Callable = None,
                  **kwargs):

        self._geoTarget_defs_fn    = geoTarget_defs_fn                     # method to get geo target definitions
        self._geoTarget_results_fn = geoTarget_results_fn                  # method to get geo target results

        super().__init__ (*args, **kwargs)


    def _plot (self): 
        """ plot all geo target results"""

        geoTargets :      list[GeoTarget_Result] = self._geoTarget_results_fn() 
        if not geoTargets: return 

        geoTarget_defs :  GeoTarget_Definitions = self._geoTarget_defs_fn() 
       
        for igeo, geoTarget_def in enumerate (geoTarget_defs):

            for geoTarget in geoTargets:                                    # get both definition and result
                if geoTarget_def.optVar == geoTarget.optVar:

                    target_text = f"Target {geoTarget_def.optVar}: {geoTarget_def.optValue:.2%}"

                    if round (geoTarget.deviation,1) != 0.0:
                        result_text = f"delta: {geoTarget.distance:.2%}"
                    else: 
                        result_text = f"hit"        

                    deviation = abs (round (geoTarget.deviation,1))
                    if deviation < 0.1:
                        result_color = COLOR_GOOD
                    elif deviation >= 10:
                        result_color = COLOR_ERROR
                    elif deviation >= 2.0:
                        result_color = COLOR_WARNING
                    elif deviation >= 0.1:
                        result_color = COLOR_OK
                    else:
                        result_color = COLOR_OK

                    self._plot_text (target_text, parentPos=(0.5,0.1), itemPos=(1.0, 0.5), offset=(0, igeo*20))
                    self._plot_text (result_text, parentPos=(0.5,0.1), itemPos=(0.0, 0.5), offset=(5, igeo*20), color=result_color)
