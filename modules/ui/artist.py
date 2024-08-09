#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

An Artist is responsible for plotting one or more PlotDataItem (pg)
of a given PlotItem 

An Artist is alawys subclassed from Artist_Abstract and enriched with
data aware, semantic functions to plot the data it is intended to do

All PlotItem, ViewBox settings are made 'outside' of an Artist

see: https://pyqtgraph.readthedocs.io/en/latest/getting_started/plotting.html

"""
from enum               import Enum, StrEnum

import numpy as np

import pyqtgraph as pg
from pyqtgraph.Qt       import QtCore, QtWidgets
from pyqtgraph.graphicsItems.ScatterPlotItem import Symbols
# from pyqtgraph.graphicsItems.GraphicsItem import GraphicsItemChange



from PyQt6.QtCore       import Qt, QTimer, QObject
from PyQt6.QtGui        import QColor, QFont, QPen

from common_utils       import *



cl_background       = '#101010'
cl_labelGrid        = '#B0B0B0'    
cl_axes             = '#606060'
cl_text             = '#D0D0D0'
cl_textHeader       = '#808080'
cl_userHint         = '#E0A721'
cl_toolbar          = ('gray85', 'gray35')


class qcolors (StrEnum):

    EDITABLE      = 'orange' 
    HOVER         = 'deepskyblue'


# -------- common methodes ------------------------

# helper functions to position values and text 

# def print_number (ax : plt.Axes, val, decimals, xy, xytext, color, alpha=0.8, asPercent=False):
#     """ print a formatted numer at axes x,y with pixel offset xytext"""

#     if asPercent: 
#         text = f"{val:.{decimals}%}"  
#     else: 
#         text = f"{val:.{decimals}f}"  

#     p = ax.annotate(text, xy=xy, xytext=xytext, va='top', ha='right',
#                             xycoords='axes fraction', textcoords='offset points', fontsize='small',
#                             color = color, alpha=alpha)
#     return p


# def print_text  (ax : plt.Axes , text, ha, xy, xytext, color, alpha=1.0, xycoords='data'):
#     """ print a text at axes x,y with pixel offset xytext
        
#     xycoords: 'data' (default), 'axes fraction', ... 
#         """
#     p = ax.annotate(text, xy=xy, xytext=xytext, va='top', ha=ha,
#                             xycoords=xycoords, textcoords='offset points', fontsize='small',
#                             color = color, alpha=alpha)
#     return p


# def adjust_lightness(color, amount=1.0):
#     """
#     Lightens the given color by multiplying by the given amount.
#     Input can be matplotlib color string, hex string, or RGB tuple.

#     Examples:
#     >> lighten_color('g', 0.3)
#     >> lighten_color('#F034A3', 0.6)
#     >> lighten_color((.3,.55,.1), 0.5)
#     """    
#     try:
#         c = mc.cnames[color]
#     except:
#         c = color
#     c = colorsys.rgb_to_hls(*mc.to_rgb(c))
#     return colorsys.hls_to_rgb(c[0], max(0, min(1, amount * c[1])), c[2])


def random_colors (nColors) -> list:
    """ returns a list of random QColors"""

    # https://martin.ankerl.com/2009/12/09/how-to-create-random-colors-programmatically/
    golden_ratio = 0.618033988749895
    colors = []

    for i in range (nColors):
        h = golden_ratio * i/nColors 
        h = h % 1.0
        colors.append(QColor.fromHsvF (h, 0.5, 0.95, 1.0) )


# -------- pg defaults ------------------------


pg.setConfigOptions(antialias=False)
pg.setConfigOptions(mouseRateLimit=30)



# ---------------------------------------------------------------------------


class Moveable_Point (pg.TargetItem):
    """
    Abstract pg.TargetItem/UIGraphicsItem which represents a single, moveable point.
    
    A Moveable_Point reacts on mouse move (drag) and finished to perform 
    modifications of an model object.

    A Moveable_Point can also be fixed ( movable=False).

    See pg.TargetItem for all arguments 

    """

    name = 'Point'                  # name of self - shown in 'label'

    def __init__ (self, xy : tuple, 
                  parent = None,                # to attach self to parent (polyline)
                  name : str = None, 
                  symbol = '+',
                  size = None,
                  movable : bool = False,
                  movable_color = None,
                  show_label_static : bool = True, 
                  label_anchor = (0,1),
                  color = "red",
                  on_changed = None,
                  **kwargs):

        self.name = name if name is not None else self.name
        self._callback_changed = on_changed
        self._show_label_static = show_label_static
        self._label_anchor = label_anchor


        self._symbol_moving  = 'crosshair' 
        self._symbol_hover   = 'crosshair' 
        self._symbol_movable = symbol 
        self._symbol_fixed   = symbol


        if movable:
            symbol = self._symbol_movable
            size = size if size is not None else 9 
            color = movable_color if movable_color is not None else qcolors.EDITABLE
            brush = QColor(color)
            hoverBrush = qcolors.HOVER

            pen = pg.mkPen (color, width=1) 
            hoverPen = pg.mkPen (color, width=1)

        else: 
            symbol = self._symbol_fixed
            size = size if size is not None else 9 

            penColor = QColor (color).darker (150)

            pen = pg.mkPen (penColor, width=1)
            brush = QColor (penColor) # QColor (color)

            hoverPen = pg.mkPen (color, width=1) 
            hoverBrush = QColor(color)

        # label 

        super().__init__(pos=xy, pen= pen, brush = brush, 
                         hoverPen = hoverPen, hoverBrush = hoverBrush,
                         symbol=symbol, size=size, movable=movable,
                         label = self._label_static, 
                         labelOpts = self._label_opts(),
                         **kwargs)

        # attach to parent (polyline) 
        if parent is not None: 
            self.setParentItem (parent)

        # default callback setup 
        self.sigPositionChanged.connect (self._moving)
        self.sigPositionChangeFinished.connect (self._finished)


    @property
    def x (self) -> float: return self.pos().x()

    @property
    def y (self) -> float: return self.pos().y()


    def set_name (self, aName :str):
        """ set a(dynamic) name of self"""
        self.name = aName
        self._label.valueChanged()                  # force label callback


    def _label_static (self,*_) -> str:

        if self._show_label_static:
            return f"{self.name}" 
        else:
            return None

    def _label_moving (self, x, y):

        return f"{self.name} {y:.4n}@{x:.4n}"

    def _label_hover (self,*_):

        return self._label_moving (self.x, self.y)
        # return f"Point {self.y:.4n}@{self.x:.4n} hovered"

    def _label_opts (self, moving=False, hover=False) -> dict:
        """ returns the label options as dict """

        if moving or hover:
            labelOpts = {'color': QColor(Artist.COLOR_NORMAL),
                        'anchor': self._label_anchor,
                        'offset': (5, 0)}
        else: 
            labelOpts = {'color': QColor(Artist.COLOR_LEGEND),
                        'anchor': self._label_anchor,
                        'offset': (5, 0)}
        return labelOpts


    def _moving (self):
        """ callback when point is moved by mouse """
        # to be overlaoded 

    def _finished (self):
        """ callback when point move is finished """
        # to be overlaoded 

    def _changed (self): 
        """ handle callback when finished """
        if callable(self._callback_changed):
            # callback / emit signal delayed so we leave the scope of Graphics 
            timer = QTimer()                                
            timer.singleShot(10, self._callback_changed)     # delayed emit 


    # TargetItem overloaded ---------------------------

    def mouseDragEvent(self, ev):

        super().mouseDragEvent (ev) 

        if ev.isStart() and self.moving:
            self.setLabel (self._label_moving, self._label_opts(moving=True))
            self.setPath (Symbols[self._symbol_moving])

        if ev.isFinish() and not self.moving:
            self.setLabel (self._label_static, self._label_opts(moving=False))
            self.setPath (Symbols[self._symbol_movable])


    def hoverEvent(self, ev):
        # overwritten to allow mouse hover also for points which are not mavalble
        if (not ev.isExit()) and ev.acceptDrags(QtCore.Qt.MouseButton.LeftButton):
            self.setMouseHover(True)
        else:
            self.setMouseHover(False)


    def setMouseHover (self, hover: bool):
        # overloaded from TargetItem to get hover event for new label 

        if not self.mouseHovering is hover:
            if hover:
                self.setLabel (self._label_hover, self._label_opts(hover=hover))
            else: 
                self.setLabel (self._label_static, self._label_opts(hover=hover))        
                
        super().setMouseHover(hover)








# ---------------------------------------------------------------------------


class Artist(QObject):
    """
        Abstract class:
        
        An Artist is responsible for plotting one or more PlotDataItem (pg)
        within a given ViewBox 

        An Artist is alawys subclassed from Artist_Abstract and enriched with
        data aware, semantic functionsto plot the data it is intended to do

        All ViewBox settings are made 'outside' of an Artist
        The "Artists" to plot a wing object on a matplotlib axes

    """

    name = "Abstract Artist" 

    SIZE_HEADER         = 14                    # size in pt 
    SIZE_NORMAL         = 10 

    COLOR_HEADER        = "whitesmoke"
    COLOR_NORMAL        = "silver"
    COLOR_LEGEND        = "gray"


    def __init__ (self, pi: pg.PlotItem , 
                  getter = None,       
                  show = True,
                  show_points = False,
                  show_legend = False):
        """
 
        Args:
            gv: GraphicsView where PlotDataItes will be added 
            get: getter for data_objects (either bound method or objects)  
            show: True: items will be show immidiatly show_points
            show_points: show data points as markers  
        """

        super().__init__()

        self._pi = pi                       # (parent) plotItem)
        self._getter = getter               # bounded method to the model e.g. Wing 

        self._show = show is True           # should self be plotted? 
        self._show_points = show_points is True 
        self._show_legend = show_legend is True 

        self._plots = []                    # plots (PlotDataItem) made up to now 
        self._plot_symbols = []             # plot symbol for each plot 

        self.plot ()


    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        text = '' 
        return f"<{type(self).__name__}{text}>"


    # ------- public ----------------------

    @property
    def data_object (self): 
        # to be ooverloaded - or implemented with semantic name 
        if callable(self._getter):
            return self._getter()
        else: 
            return self._getter
        
    @property
    def data_list (self): 
        # to be ooverloaded - or implemented with semantic name        
        if isinstance (self.data_object, list):
            return self.data_object
        else: 
            return [self.data_object]   


    @property
    def show (self): return self._show

    def set_show (self, aBool):
        """ user switch to disable ploting the data
        """
        self._show = aBool is True 

        if self.show and not self._plots:
            # first time, up to now no plots created ...
            self.plot()
        else: 
            p : pg.PlotDataItem
            if self.show: 
                self.refresh()
            else: 
                for p in self._plots:
                    p.hide()
                if self.show_legend:
                    self._remove_legend_items ()


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

    @property
    def show_legend (self): return self._show_legend
    def set_show_legend (self, aBool):
        """ user switch to show legend for self plots
        """
        self._show_legend = aBool is True 

        if self.show_legend:
            self.plot()
        else: 
            self._remove_legend_items ()


    def plot (self):
        """the artist will (re)plot - existing plots will be deleted 
        """
        if self.show:

            self._remove_legend_items ()
            self._remove_plots ()

            if self.show_legend:
                # must be before .plot 
                self._pi.addLegend(offset=(-50,10), verSpacing=-8)  
                self._pi.legend.setLabelTextColor (self.COLOR_LEGEND)

                # print ("rows:", self._pi.legend.layout.rowCount(), self._pi.legend)

            if len(self.data_list) > 0:
                self._plot()                        # plot data list 


    def refresh(self):
        """ refresh self plots by setting new x,y data """

        if self.show:
            self._refresh_plots ()

            if self.show_legend:
                self._remove_legend_items ()
                self._add_legend_items()

            # logging.debug (f"{self} refresh")


    # --------------  private -------------

    def _plot (self):
        """ main method to plot the items"""
        # do plot - overwritten in sublass
        pass


    def _plot_dataItem (self, *args, name=None, **kwargs) -> pg.PlotDataItem:
        """ plot DataItem and add it to self._plots etc """

        p = pg.PlotDataItem  (*args, **kwargs)
        self._add (p, name=name)

        return p 
        

    def _plot_point (self, 
                    *args,                     # optional: tuple or x,y
                     symbol='o', color=None, style=Qt.PenStyle.SolidLine, 
                     size=7, pxMode=True, 
                     brushColor=None, brushAlpha=1.0,
                     text=None, textColor=None, textPos=None, anchor=None):
        """ plot point with text label at x, y - text will follow the point """

        if isinstance (args[0], tuple):
            x = args[0][0] 
            y = args[0][1] 
        else: 
            x = args[0]
            y = args[1] 

        # pen style
        color = QColor(color) if color else QColor(self.COLOR_NORMAL)
        pen = pg.mkPen (color, style=style)   

        # brush style 
        brushColor = QColor(brushColor) if brushColor else color 
        brushColor.setAlphaF (brushAlpha)
        brush = pg.mkBrush(brushColor) 

        p = pg.ScatterPlotItem  ([x], [y], symbol=symbol, size=size, pxMode=pxMode, 
                                 pen=pen, brush=brush)
        
        # plot label as TextItem 

        if text is not None: 
            color = QColor(textColor) if textColor else QColor(self.COLOR_NORMAL)
            anchor = anchor if anchor else (0, 1)
            t = pg.TextItem(text, color, anchor=anchor)

            # ? attach to parent doesn't work (because of PlotDataItem? )
            textPos = textPos if textPos is not None else (x,y)
            t.setPos (*textPos)

            self._add (t)

        return self._add(p) 




    def _plot_text (self, text : str, color=None, fontSize=None, 
                          parentPos = (0.5,0.5),    # pos within PlotItem 
                          itemPos = (0,1),          # box anchor of TextItem 
                          offset = (0,0)            # offet in px 
                          ):
        """ plot text label at fixed position using LabelItem """

        if not text: return 

        fontSize = fontSize if fontSize is not None else self.SIZE_NORMAL
        color = color if color is not None else self.COLOR_NORMAL

        label = pg.LabelItem(text, color=QColor(color), size=f"{fontSize}pt")    

        # addItem to PlotItem doesn't work (would be added to viewbox and scaled)     
        label.setParentItem(self._pi)
        label.anchor(itemPos=itemPos, parentPos=parentPos, offset=offset)

        # manuel add to self items 
        self._plots.append(label)


    def _plot_title (self, title : str, subTitle : str|None = None, 
                     align='left', offset : tuple = (30,10)):
        """ 
        plot a title, optionally with a sub title, at fixed position 
            - subTitle - optional text below title 
            - align = 'left' | 'center' | 'right'
            - offset - optional - tuple (x,y)
            """

        if align == 'left':
            parentPos = (0.02 + 0.03,0)          # parent x starts at PlotItem (including axis)       
            itemPos   = (0.0,0)
        elif align =='right':
            parentPos = (0.98,0)
            itemPos   = (1,0)
        else:
            parentPos = (0.5 + 0.02,0)
            itemPos   = (0.5,0)

        self._plot_text (title, color=QColor(self.COLOR_HEADER), fontSize=self.SIZE_HEADER, 
                         parentPos=parentPos, itemPos=itemPos, offset=offset)

        if subTitle is not None: 
            sub_offset = (offset[0], offset[1]+25)
            self._plot_text (subTitle, color=QColor(self.COLOR_LEGEND), fontSize=self.SIZE_NORMAL, 
                            parentPos=parentPos, itemPos=itemPos, offset=sub_offset)



    def _remove_plots (self):
        """ remove self plots from GraphicsView """

        p : pg.PlotDataItem
        for p in self._plots:

            if isinstance (p, pg.LabelItem):
                # in case of LabelItem, p is added directly to the scene via setParentItem
                self._pi.scene().removeItem (p)
            else: 
                # normal case - p is an item of PlotItem 
                self._pi.removeItem (p)

        self._plots = []
        self._plot_symbols = []


    def _get_plot_item (self, aName : str ):
        """ returns the plot item having 'name' """
        for p in self._plots:
            if isinstance (p, pg.PlotDataItem) :
                if aName == p.name():
                    return p
        return None 


    def _add_legend_items (self):
        """ add legend items of self """
        if self._pi.legend is not None:
            p : pg.PlotDataItem
            for p in self._plots:
                if isinstance (p, pg.PlotDataItem) :
                    name = p.name()
                    if name:
                        self._pi.legend.addItem (p, name)


    def _remove_legend_items (self):
        """ removes legend items of self """
        if self._pi.legend is not None:
            for p in self._plots:
                if isinstance (p, pg.PlotDataItem):
                    self._pi.legend.removeItem (p)

            # ... try to rebuild layout of legend because of strange spacing 
            # legend_ncol = self._pi.legend.columnCount
            # self._pi.legend.setColumnCount (legend_ncol+1)
            # self._pi.legend.setColumnCount (legend_ncol)


    def _refresh_plots (self):
        """ set new x,y data into plots"""
        # can be overloaded for high speed refresh 

        self.plot()             # default - normal plot 


    def _add(self, aPlot: pg.PlotDataItem, name = None):
        """ 
        Add new plot item to self plots
            name: ... of item in legend  
        """

        self._pi.addItem (aPlot)
        self._plots.append(aPlot)
        if isinstance (aPlot, pg.PlotDataItem):
            self._plot_symbols.append (aPlot.opts['symbol'])

        # 'manual' control if aPlot should appear in legend 
        if self.show_legend and name and isinstance (aPlot, pg.PlotDataItem): 
            self._pi.legend.addItem (aPlot, name)
            aPlot.opts['name'] = name
 
        return aPlot 