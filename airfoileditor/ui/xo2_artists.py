#!/usr/bin/env pythonupper
# -*- coding: utf-8 -*-

"""  

The "Artists" to plot a airfoil object on a pg.PlotItem 

"""

from PyQt6.QtGui                import QColor, QPainterPath, QTransform
from PyQt6.QtCore               import Qt, pyqtSignal, QRectF
from math                        import sin, cos, radians, tan, atan, degrees

from ..base.artist              import *
from ..base.common_utils        import *

from ..model.polar_set          import * 
from ..model.geometry           import geo_parm
from ..model.xo2_input          import (
    OpPoint_Definition,
    OpPoint_Definitions,
    GeoConstraint_Definition,
    OPT_TARGET,
    OPT_MAX,
    OPT_MIN,
)
from ..model.xo2_results        import OpPoint_Result, Optimization_History_Entry

from .ae_artists                import _color_airfoil


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# -------- helper functions ------------------------

def _size_opPoint (weighting : float, normal_size = 13) -> float:
    """ returns plot size of an opPoint (def) depending on weighting"""

    return abs(weighting) ** 0.8 * normal_size 



# -------- Movable Points  ------------------------


class Movable_OpPoint_Def (Movable_Point):
    """ 
    Movable opPoint definition
    """

    name = "OpPoint Definition"

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

        path.addRect(QRectF(-width / 2, -height1 / 2, width, height1))
        # verticial line
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
                    on_delete   = None,
                    **kwargs):

        self._pi = pi
        self._opPoint_def = opPoint_def
        self._xyVars = xyVars

        self._callback_selected = on_selected if (callable(on_selected) and movable) else None
        self._callback_delete   = on_delete if (callable(on_delete) and movable) else None
        self._highlight_item    = None                       

        brush = QColor ("black")
        brush.setAlphaF (0.3) 

        size    = _size_opPoint (opPoint_def.weighting)
        xy      = self.xy_in_xyVars()                                   # get x,y coordinates in xyVars

        # sanity - opPoint_def could be not ready because seed polar has to be calculated async
        if xy == (None, None):
            return 

        movable = movable and self.is_movable_in_xyVars()               # can be moved in xyVars?

        super().__init__(xy, movable=movable, label_anchor = (0, 0.5),
                            color=QColor(self.COLOR), brush=brush,
                            symbol=self._symbol(), size=size, show_label_static = True, **kwargs)

        self.sigShiftClick.connect  (self._delete_opPoint_def)


    def is_movable_in_xyVars (self) -> bool:
        """ returns True if self can be moved in xyVars"""

        opPoint_def = self._opPoint_def

        if opPoint_def.specVar in self._xyVars and opPoint_def.optVar in self._xyVars:
            return True 
        elif opPoint_def._xyVars_are_indirect (self._xyVars):
            return True
        if opPoint_def.specVar in self._xyVars and opPoint_def.optType in [OPT_MIN, OPT_MAX]:
            return True 
        else:
            return False
    

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
        else:                                           # either optVar nor specVar are in diagram
            s = 's'
        
        return s


    def _delete_opPoint_def (self, _):
        """ shift-click - delete me opPoint_dev"""

        if callable(self._callback_delete):
            # callback / emit signal delayed so we leave the scope of Graphics 
            QTimer() .singleShot(0, lambda: self._callback_delete (self._opPoint_def))   


    def xy_in_xyVars (self) -> tuple: 
        """ returns the x,y coordinates of self in xyVars"""

        # if target variable is in diagram, take target value as coordinate        
        x= self._opPoint_def.get_polar_value(self._xyVars[0], or_target=True)    
        y= self._opPoint_def.get_polar_value(self._xyVars[1], or_target=True)     
        if x is None or y is None:
            return None, None       
        
        return x,y 


    @override
    def mouseClickEvent(self, ev):
        """ handle callback to parent when clicked with left button to select self """

        if not self.moving and ev.button() == Qt.MouseButton.LeftButton  \
                           and not (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier): # shift is handled in super
            if callable(self._callback_selected):
                ev.accept()

                # callback / emit delayed so we leave the scope of Graphics 
                QTimer() .singleShot(0, lambda: self._callback_selected (self._opPoint_def))   
        else:
            super().mouseClickEvent (ev)


    @override
    def _moving (self, _):
        """ slot -point is moved"""
        self._opPoint_def.set_xyValues_for_xyVars (self._xyVars, (self.x,self.y))

        self.setPos (self.xy_in_xyVars())                      # ... if we run against limits 

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

        if callable(self._callback_selected):
            # ensure self will be selected after moving 
            QTimer() .singleShot (0, lambda: self._callback_selected (self._opPoint_def)) 

        if callable(self._callback_changed):
            # callback / emit  delayed so we leave the scope of Graphics 
            QTimer() .singleShot (0, self._callback_changed )   


    def set_highlight_item (self, aItem: pg.TargetItem):
        """ a point item used to highlight current"""

        self._highlight_item = aItem
        if self._highlight_item:
            self._highlight_item.setPos (self.pos())



class Movable_GeoConstraint (Movable_Point):
    """Display a single active geometry constraint as point marker."""

    name = "Geo Constraint"

    HELPER_LEN = 0.2
    TE_SIDE_HELPER_LEN = 0.15

    def __init__ (self, pi : pg.PlotItem,
                  constraint : GeoConstraint_Definition,
                  te : tuple[float, float, float, float] | None = None,
                  movable=False,
                  symbol='d',
                  size=10,
                  label_anchor=(0, 0.5),
                  color="orangered",
                  on_selected = None,
                  **kwargs):

        self._pi = pi
        self._constraint = constraint
        self._te = te
        self._callback_selected = on_selected if callable(on_selected) else None
        self._helper_pen = pg.mkPen(QColor(color), width=1, style=Qt.PenStyle.SolidLine)

        self._xy = self._xy_for_constraint ()
        self._is_plottable = self._xy != (None, None)

        # Keep base class initialized even for unsupported constraints.
        xy = self._xy if self._is_plottable else (0.0, 0.0)

        super().__init__(xy,
                         movable=movable and self._is_plottable,
                         color=QColor(color) ,
                         brush=QColor("black"),
                         symbol=symbol,
                         size=size,
                         show_label_static=True,
                         label_anchor=label_anchor,
                         **kwargs)

        self._helper_items = self._create_helper_items()
        self._update_helper_items()


    @property
    def is_plottable (self) -> bool:
        return self._is_plottable


    def xy_in_diagram (self) -> tuple:
        return self._xy


    @property
    def helper_items(self) -> list[pg.PlotDataItem]:
        return self._helper_items


    def _xy_for_constraint (self) -> tuple:
        """Map a supported active constraint to diagram x/y coordinates."""

        parm = self._constraint.parm
        val  = self._constraint.value

        if val is None:
            return None, None

        if parm == geo_parm.THICKNESS_AT:
            return val[0], val[1]

        seed_at = self._constraint.seed_at

        if parm in (geo_parm.THICKNESS, geo_parm.CAMBER):
            return seed_at, val

        if parm == geo_parm.TE_ANGLE:
            try:
                angle = float(val)
            except (TypeError, ValueError):
                return None, None

            helper_pts = self._te_angle_helper_points(angle)
            if helper_pts is None:
                return None, None

            # Marker sits on the endpoint of the upper helper line.
            _, _, x_end, y_up, _ = helper_pts
            return x_end, y_up

        if parm in (geo_parm.TE_ANGLE_UPPER, geo_parm.TE_ANGLE_LOWER):
            try:
                angle = float(val)
            except (TypeError, ValueError):
                return None, None

            side_pts = self._te_side_helper_points(parm, angle)
            if side_pts is None:
                return None, None

            # Marker sits on the left endpoint (helper start when read left -> right).
            x0, y0, x1, y1 = side_pts
            return x1, y1

        return None, None


    def _create_helper_items(self) -> list[pg.PlotDataItem]:

        parm = self._constraint.parm
        items: list[pg.PlotDataItem] = []

        if parm in (geo_parm.THICKNESS, geo_parm.CAMBER, geo_parm.THICKNESS_AT):
            p_main = pg.PlotDataItem([], [], pen=self._helper_pen)
            p_main.setZValue(5)  # above airfoil
            items.append(p_main)

        elif parm == geo_parm.TE_ANGLE:
            p1 = pg.PlotDataItem([], [], pen=self._helper_pen)
            p2 = pg.PlotDataItem([], [], pen=self._helper_pen)
            p1.setZValue(5)  # above airfoil
            p2.setZValue(5)  # above airfoil
            items.extend([p1, p2])

        elif parm in (geo_parm.TE_ANGLE_UPPER, geo_parm.TE_ANGLE_LOWER):
            p = pg.PlotDataItem([], [], pen=self._helper_pen)
            p.setZValue(5)  # above airfoil
            items.append(p)

        return items


    def _set_helper_data(self, idx: int, x, y):
        if 0 <= idx < len(self._helper_items):
            self._helper_items[idx].setData(x, y)


    def _helper_span_x(self, x_center: float) -> tuple[float, float]:
        half = self.HELPER_LEN / 2.0
        return max(0.0, x_center - half), min(1.0, x_center + half)


    def _hide_all_helpers(self):
        for item in self._helper_items:
            item.setData([], [])


    def _te_angle_helper_points(self, angle: float) -> tuple[float, float, float, float, float] | None:
        """Return TE angle helper geometry as (x_te, y_te, x_end, y_up, y_lo)."""
        if self._te is None:
            return None

        x_u, y_u, x_l, y_l = self._te
        x_te = (x_u + x_l) / 2.0
        y_te = (y_u + y_l) / 2.0

        angle_rad = radians(max(0.0, angle))

        # Keep same convention as thickness/camber helpers: x/c span of 0.2.
        dx = min(self.HELPER_LEN, max(0.0, x_te))
        x_end = x_te - dx
        dy = dx * tan(angle_rad)

        y_up = y_te + dy
        # Lower helper is baseline along thickness/x-axis direction.
        y_lo = y_te

        return (x_te, y_te, x_end, y_up, y_lo)


    def _te_side_helper_points(self, parm: geo_parm, angle: float) -> tuple[float, float, float, float] | None:
        """Return side TE helper geometry as (x0, y0, x1, y1)."""
        if self._te is None:
            return None

        x_u, y_u, x_l, y_l = self._te
        if parm == geo_parm.TE_ANGLE_UPPER:
            x0, y0 = x_u, y_u
        elif parm == geo_parm.TE_ANGLE_LOWER:
            x0, y0 = x_l, y_l
        else:
            return None

        dx = min(self.TE_SIDE_HELPER_LEN, max(0.0, x0))
        dy = dx * tan(radians(angle))

        x1 = x0 - dx
        y1 = y0 + dy
        return (x0, y0, x1, y1)


    def _update_helper_items(self):
        con = self._constraint
        seed_at = con.seed_at

        if con.parm in (geo_parm.THICKNESS, geo_parm.CAMBER):
            y = float(con.value)
            x0, x1 = self._helper_span_x(seed_at)
            self._set_helper_data(0, [x0, x1], [y, y])
            return

        if con.parm == geo_parm.THICKNESS_AT :
            x_center = con.value[0]
            t = con.value[1]
            if x_center is None or t is None:
                self._hide_all_helpers()
                return

            x0, x1 = self._helper_span_x(x_center)
            self._set_helper_data(0, [x0, x1], [t, t])
            return

        if con.parm == geo_parm.TE_ANGLE:
            try:
                angle = float(con.value)
            except (TypeError, ValueError):
                self._hide_all_helpers()
                return

            helper_pts = self._te_angle_helper_points(angle)
            if helper_pts is None:
                self._hide_all_helpers()
                return

            x_te, y_te, x_end, y_up, y_lo = helper_pts

            self._set_helper_data(0, [x_te, x_end], [y_te, y_up])
            self._set_helper_data(1, [x_te, x_end], [y_te, y_lo])
            return

        if con.parm in (geo_parm.TE_ANGLE_UPPER, geo_parm.TE_ANGLE_LOWER):
            try:
                angle = float(con.value)
            except (TypeError, ValueError):
                self._hide_all_helpers()
                return

            side_pts = self._te_side_helper_points(con.parm, angle)
            if side_pts is None:
                self._hide_all_helpers()
                return

            x0, y0, x1, y1 = side_pts

            self._set_helper_data(0, [x0, x1], [y0, y1])
            return

        self._hide_all_helpers()


    @override
    def _moving(self, _):
        if self._constraint is None:
            return

        parm = self._constraint.parm
        if parm == geo_parm.THICKNESS_AT:
            self._constraint.set_value((self.x, self.y))
        elif parm in (geo_parm.THICKNESS, geo_parm.CAMBER):
            self._constraint.set_value(self.y)
        elif parm == geo_parm.TE_ANGLE:
            helper_pts = self._te_angle_helper_points(float(self._constraint.value))
            if helper_pts is None:
                return

            x_te, y_te, x_end, _, _ = helper_pts
            dx = x_te - x_end
            if dx <= 0.0:
                return

            angle = degrees(atan((self.y - y_te) / dx))
            self._constraint.set_value(angle)
        elif parm in (geo_parm.TE_ANGLE_UPPER, geo_parm.TE_ANGLE_LOWER):
            if self._te is None:
                return

            x_u, y_u, x_l, y_l = self._te
            if parm == geo_parm.TE_ANGLE_UPPER:
                x0, y0 = x_u, y_u
            else:
                x0, y0 = x_l, y_l

            dx = x0 - self.x
            if dx <= 0.0:
                dx = min(self.TE_SIDE_HELPER_LEN, max(0.0, x0))
            if dx <= 0.0:
                return

            angle = degrees(atan((self.y - y0) / dx))
            self._constraint.set_value(angle)
        else:
            return

        self._xy = self._xy_for_constraint()
        if self._xy != (None, None):
            self.setPos(self._xy)

        self._update_helper_items()


    @override
    def label_static (self, *_):
        return self._label_text()


    def _value_as_label(self) -> str | None:
        con = self._constraint
        val = con.value

        if val is None:
            return None

        parm = con.parm
        if parm in (geo_parm.THICKNESS, geo_parm.CAMBER):
            return f"{float(val):.2%}"

        if parm == geo_parm.THICKNESS_AT and isinstance(val, (tuple, list)) and len(val) >= 2:
            x_val, t_val = val[0], val[1]
            if x_val is None or t_val is None:
                return None
            return f" {float(x_val):.2f}, t={float(t_val):.2%}"

        if parm in (geo_parm.TE_ANGLE, geo_parm.TE_ANGLE_UPPER, geo_parm.TE_ANGLE_LOWER, geo_parm.FLAP_ANGLE):
            angle = float(val)
            if parm == geo_parm.TE_ANGLE:
                angle = abs(angle)
            return f"{angle:.2f}°"

        return f"{val}"


    def _label_text(self) -> str:
        key = self._constraint.key.replace('_', ' ')
        value_label = self._value_as_label()
        return key if value_label is None else f"{key}: {value_label}"


    @override
    def label_moving (self, *_):
        return self._label_text()


    @override
    def mouseClickEvent(self, ev):
        if not self.moving and ev.button() == Qt.MouseButton.LeftButton:
            if callable(self._callback_selected):
                ev.accept()
                QTimer() .singleShot(0, lambda: self._callback_selected (self._constraint))
        else:
            super().mouseClickEvent (ev)




# -------- Artists ------------------------


class Xo2_OpPoint_Defs_Artist (Artist):
    """ Plot / Modify Xoptfoil2 operating point definitions """

    sig_opPoint_def_changed     = pyqtSignal ()                       # opPoint_def changed  
    sig_opPoint_def_selected    = pyqtSignal (OpPoint_Definition)     # opPoint_def selected 

    def __init__ (self, *args,
                  cur_opPoint_def_fn = None,   
                  isRunning_fn = None, 
                  xyVars = (var.CD, var.CL), 
                  **kwargs):

        super().__init__(*args, **kwargs)

        self._cur_opPoint_def_fn = cur_opPoint_def_fn           # method to get current opPoint definition
        self._isRunning_fn = isRunning_fn
        self._xyVars = xyVars                                   # definition of x,y axis


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
    def cur_opPoint_def (self) -> OpPoint_Definition | None: 
        return self._cur_opPoint_def_fn() if callable (self._cur_opPoint_def_fn) else None

    @property
    def optimizer_isRunning (self) -> bool:
        """ True if optimizer is ready - definitions can be changed"""
        return self._isRunning_fn() if callable (self._isRunning_fn) else False


    def _plot (self): 

        for opPoint_def in self.opPoint_defs:

            pt = Movable_OpPoint_Def  (self._pi, opPoint_def, self.xyVars, 
                                            movable=not self.optimizer_isRunning and self.show_mouse_helper,
                                            on_changed =self.sig_opPoint_def_changed.emit,
                                            on_delete  =self._on_delete,
                                            on_selected=self.sig_opPoint_def_selected.emit)

            if pt.xy_in_xyVars() != (None, None):                   # sanity - if not None, it is in the view

                self._add (pt, name = pt.name_for_legend) 

                # highlight current opPoint def for edit with a big circle 

                if opPoint_def == self.cur_opPoint_def and not self.optimizer_isRunning:

                    brush = QColor (Movable_OpPoint_Def.COLOR)
                    brush.setAlphaF (0.3)
                    highlight_item = self._plot_point (0.02,0.2, color="black", size=60, brush=brush)

                    pt.set_highlight_item (highlight_item)


        # show mouse helper message
        msg = "OpPoint: click to select, shift-click to remove,  ctrl-click to add"
        self.set_help_message (msg)

        # make scene clickable to opPoint:def - delayed as during init scene is not yet available
        QTimer().singleShot (10, self._connect_scene_mouseClick)


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
        slot - mouse click in scene of self - handle add opPoint_def with ctrl-click 
        """ 

        # handle only ctrl-click
        if not (ev.modifiers() & Qt.KeyboardModifier.ControlModifier): return  
       
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

            if new_opPoint_def is not None:
                self.sig_opPoint_def_changed.emit()
                self.sig_opPoint_def_selected.emit (new_opPoint_def)

            else: 
                self._plot_text ('New OpPoint Definition cannot be created in this diagram', color=COLOR_ERROR, itemPos=(0.5,0.5))
                QTimer().singleShot (1000, self.refresh)            # remove after 1 second


    def _on_delete (self, opPoint_def : OpPoint_Definition):
        """ callback of Movable Point to delete opPoint_def"""

        self.opPoint_defs.delete (opPoint_def)

        self.sig_opPoint_def_changed.emit ()


class Xo2_GeoConstraint_Artist (Artist):
    """Plot active geometry constraints as markers in the airfoil diagram."""

    sig_geo_constraint_selected = pyqtSignal (GeoConstraint_Definition)

    def __init__ (self, *args,
                  airfoil_fn : Callable = None,
                  **kwargs):

        self._airfoil_fn = airfoil_fn

        super().__init__(*args, **kwargs)


    @property
    def constraints (self) -> list[GeoConstraint_Definition]:
        return self.data_list if self.data_list else []


    @property
    def airfoil (self) -> Airfoil | None:
        return self._airfoil_fn() if callable(self._airfoil_fn) else None


    def _plot (self):

        legend_name = "Geo Constraint"
        te = self.airfoil.geo.te if self.airfoil is not None else None

        for con in self.constraints:

            if not con.is_active:
                continue

            symbol = 'd'
            label_anchor_y = 0.5

            if con.parm == geo_parm.THICKNESS_AT:
                symbol = 't'
            elif con.is_min:
                symbol = 't'
            elif con.is_max:
                symbol = 't1'

            if con.is_max:
                label_anchor_y = 1.2
            elif con.is_min:
                label_anchor_y = -0.2

            label_anchor = (0.5, label_anchor_y)

            pt = Movable_GeoConstraint(self._pi, con,
                                       te=te,
                                       movable=True,
                                       symbol=symbol,
                                       label_anchor=label_anchor,
                                       on_selected=self.sig_geo_constraint_selected.emit)

            if pt.is_plottable:
                for helper_item in pt.helper_items:
                    self._add(helper_item)
                self._add (pt, name=legend_name)
                legend_name = None


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

            if x is None or y is None:
                logger.debug(f"OpPoint {iop} has no coordinates for this diagram - skipping")
                continue

            # get opPoint definition for this opPoint - if not available, use None
            # sanity - opPoint def could be deleted in the meantime 
            if iop < len(opPoint_defs):
                opPoint_def = opPoint_defs[iop]
                if opPoint_def.specValue != opPoint.get_value(opPoint_def.specVar):
                    # logger.warning(f"OpPoint {iop} has no definition with same specValue - skipping")
                    opPoint_def = None
            else:
                opPoint_def = None


            color  = self._opPoint_color  (opPoint, opPoint_def)
            symbol = self._opPoint_symbol (opPoint, prev_opPoint)
            label  = self._opPoint_label  (opPoint, opPoint_def, self.xyVars)
            size   = _size_opPoint (opPoint_def.weighting if opPoint_def is not None else 1.0)

            textColor = QColor (color).darker(130)

            self._plot_point ((x,y), color=color, size=size, symbol=symbol, zValue=20, name=legend_name,
                              text=label, anchor=(0, 0.5), textOffset = (8,0), textColor=textColor, textFill=textFill)

            legend_name = None 


        
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

        label   = None 
        optVar  = opPoint_def.optVar
        optType = opPoint_def.optType
        allow_improved = opPoint_def._myList.allow_improved_target

        # optVar must be in diagram to show distance as it comes from Xo2 results 

        if optVar in xyVars:  

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
                    label = f"d{var.CD} {improv:.5f}" if optVar == var.CD else f"d{var.CD} {improv:.2f}"

        # add flap angle if flap optimize 

        if opPoint_def.flap_optimize:
            if label:
                label = f"{label}, F{opPoint.flap:.1f}°"
            else:
                label = f"F{opPoint.flap:.1f}°"

        return label 
        



class Xo2_Design_Radius_Artist (Artist):
    """ Plot Xoptfoil2 design radius during optimization """

    
    @property
    def steps (self) -> list[Optimization_History_Entry]: 
        """ optimization step entries up to now """
        return self.data_object

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
    def steps (self) -> list[Optimization_History_Entry]: 
        """ optimization step entries up to now """
        return self.data_object  

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
     
