#!/usr/bin/env pythonupper
# -*- coding: utf-8 -*-

"""  

The "Artists" to plot a airfoil object on a pg.PlotItem 

"""
import html 

from typing                     import Callable

from base.artist                import *
from base.common_utils          import *

from model.polar_set            import * 
from model.xo2_input            import OpPoint_Definition, OpPoint_Definitions, OPT_TARGET, OPT_MAX, OPT_MIN
from model.xo2_results          import OpPoint_Result, Xo2_Results, Optimization_History_Entry

from PyQt6.QtGui                import QColor, QBrush, QPen, QPainterPath, QTransform
from PyQt6.QtCore               import pyqtSignal


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# -------- helper functions ------------------------

def _size_opPoint (weighting : float, normal_size = 8) -> float:
    """ returns plot size of an opPoint (def) depending on weighting"""

    # weighting can be negative (meaning fixed weighting - no dynamic)
    return abs(weighting) ** 0.5 * normal_size 



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
                    **kwargs):

        self._pi = pi
        self._opPoint_def = opPoint_def
        self._xyVars = xyVars

        self._callback_selected = on_selected
        self._callback_dblClick = on_dblClick

        brush = QColor ("black")
        brush.setAlphaF (0.3) 

        size = _size_opPoint (opPoint_def.weighting, normal_size = 9)

        super().__init__(self._point_xy(), movable=movable, label_anchor = (0, 0.5),
                            color=self.COLOR, brush=brush,
                            symbol=self._symbol(), size=size, show_label_static = True, **kwargs)

        self.sigShiftClick.connect             (self._delete_opPoint_def)


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
        self._opPoint_def.delete_me ()
        self._changed ()


    def _point_xy (self) -> tuple:  
        return self._opPoint_def.xyValues_for_xyVars (self._xyVars)     


    @override
    def mouseClickEvent(self, ev):
        """ handle callback to parent when clicked with left button to select self """

        if not self.moving and ev.button() == QtCore.Qt.MouseButton.LeftButton:
            if callable(self._callback_selected):
                ev.accept()
                # callback / emit signal delayed so we leave the scope of Graphics 
                QTimer() .singleShot(10, lambda: self._callback_selected (self._opPoint_def))   
        else:
            super().mouseClickEvent (ev)


    @override
    def mouseDoubleClickEvent(self, ev):
        """ handle callback to parent when double clicked """
        if callable(self._callback_dblClick):
            ev.accept()
            # callback / emit signal delayed so we leave the scope of Graphics 
            QTimer() .singleShot(10, lambda: self._callback_dblClick (self._opPoint_def))   
        else:
            super().mouseDoubleClickEvent (ev)


    @override
    def _moving (self, _):
        """ slot -point is moved"""
        self._opPoint_def.set_xyValues_for_xyVars (self._xyVars, (self.x,self.y))
        self.setPos (self._point_xy())                      # ... if we run against limits 

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

        # callback / emit signal delayed so we leave the scope of Graphics 
        QTimer() .singleShot(10, lambda: self._callback_changed (self._opPoint_def))   


# -------- Artists ------------------------


class Xo2_OpPoint_Defs_Artist (Artist):
    """ Plot / Modify Xoptfoil2 operating point defin itions """

    sig_opPoint_def_changed     = pyqtSignal (OpPoint_Definition)       # opPoint_def changed changed 
    sig_opPoint_def_selected    = pyqtSignal (OpPoint_Definition)
    sig_opPoint_def_dblClick    = pyqtSignal (OpPoint_Definition)

    def __init__ (self, *args, 
                  isReady_fn = None, 
                  xyVars = (var.CD, var.CL), 
                  **kwargs):
        super().__init__ (*args, **kwargs)

        self._xyVars = xyVars                               # definition of x,y axis
        self._isReady_fn = isReady_fn


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
    def optimizer_isReady (self) -> bool:
        """ True if optimier is ready - definitions can be changed"""
        return self._isReady_fn() if callable (self._isReady_fn) else False

    def _plot (self): 

        for opPoint_def in self.opPoint_defs:

            x, y = opPoint_def.xyValues_for_xyVars (self.xyVars)

            # does it fit into this x,y polar view

            if x is not None and y is not None: 

                pt = Movable_Xo2_OpPoint_Def  (self._pi, opPoint_def, self.xyVars, 
                                                movable=self.optimizer_isReady,
                                                on_changed =self.sig_opPoint_def_changed.emit,
                                                on_dblClick=self.sig_opPoint_def_dblClick.emit,
                                                on_selected=self.sig_opPoint_def_selected.emit)
                self._add (pt) 

        # make scene clickable to add wing section - delayed as during init scene is not yet available

        QTimer().singleShot (10, self._connect_scene_mouseClick)

        self.show_help_message ()


    def show_help_message (self):
        """ show mouse helper message"""
        msg = "OpPoint: double-click to edit, shift-click to remove, ctrl-click to add"
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
            new_opPoint_def = self.opPoint_defs.create_in_xyVars (self.xyVars, pos.x(), pos.y())

            if new_opPoint_def:
                self.sig_opPoint_def_changed.emit(new_opPoint_def)




class Xo2_OpPoint_Artist (Artist):
    """ Plot Xoptfoil2 operating point result """

    sig_opPoint_def_changed     = pyqtSignal()              # opPoint_def changed changed 


    def __init__ (self, *args, 
                  opPoint_defs_fn : Callable = None,
                  xyVars = (var.CD, var.CL), 
                  **kwargs):

        self._xyVars = xyVars                               # definition of x,y axis
        self._opPoint_defs_fn = opPoint_defs_fn             # method to get opPoint definitions

        super().__init__ (*args, **kwargs)

    @property
    def xyVars(self): return self._xyVars
    def set_xyVars (self, xyVars: Tuple[var, var]): 
        """ set new x, y variables for polar """
        self._xyVars = xyVars 
        self.refresh()

    @property
    def iDesign (self) -> int:
        """ current Design index"""
        return -1

    @property
    def designs_opPoints (self) -> list [list]:
        """ designs list of opPoints list"""
        return self.data_list

    @property
    def opPoints (self) -> list[OpPoint_Result]:
        """ opPoints of current Design """
        return self.designs_opPoints [self.iDesign] if self.designs_opPoints else []

    @property
    def prev_opPoints (self) -> list[OpPoint_Result]:
        """ opPoints of previous Design """
        try: 
            return self.designs_opPoints [self.iDesign - 1]
        except: 
            return [None] * len (self.opPoints) 

    @property
    def opPoint_defs (self) -> OpPoint_Definitions: 
        return self._opPoint_defs_fn () if callable (self._opPoint_defs_fn) else []


    def _plot (self): 
        """ plot all opPoints"""

        for iop, opPoint in enumerate (self.opPoints):

            x = opPoint.get_value (self.xyVars[0])
            y = opPoint.get_value (self.xyVars[1])

            color  = self._opPoint_color  (opPoint, self.opPoint_defs[iop])
            symbol = self._opPoint_symbol (opPoint, self.prev_opPoints[iop])
            size   = _size_opPoint (opPoint.weighting)

            self._plot_point (x,y, color=color, size=size, symbol=symbol, zValue=20)

        
    def _opPoint_color (self, opPoint : OpPoint_Result, opPoint_def : OpPoint_Definition):
        """ color of opPoint depending on % deviation """

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
            self._plot_point (x,y, size=5, color=COLOR_OK)



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
            self._plot_point (x,y, size=5, color=COLOR_GOOD)
