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
from common_utils import *
import numpy as np

import numpy as np

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

import colorsys


cl_background       = '#101010'
cl_labelGrid        = '#B0B0B0'    
cl_axes             = '#606060'
cl_text             = '#D0D0D0'
cl_textHeader       = '#808080'
cl_userHint         = '#E0A721'
cl_toolbar          = ('gray85', 'gray35')


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





# ---------------------------------------------------------------------------


class Artist():
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
        self._pi = pi                       # (parent) plotItem)
        self._getter = getter               # bounded method to the model e.g. Wing 

        self._show = show is True           # should self be plotted? 
        self._show_points = show_points is True 
        self._show_legend = show_legend is True 

        self._plots = []                    # plots (PlotDataItem) made up to now 
        self._plot_symbols = []             # plot symbol for each plot 

        if self.show:
            self.plot()

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
                for p in self._plots:
                    p.show()
                if self.show_legend:
                    self._add_legend_items()
            else: 
                for p in self._plots:
                    p.hide()
                if self.show_legend:
                    self._remove_legend_items ()

    @property
    def pi_isVisible(self):
        """ true if 'plot item' of self is visible"""
        return self._pi.isVisible() if self._pi is not None else False

    @property
    def show_points (self): return self._show_points
    def set_show_points (self, aBool):
        """ user switch to show point (marker )
        """
        self._show_points = aBool is True 

        p : pg.PlotDataItem
        for ip, p in enumerate (self._plots):
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
        if self.show and self.pi_isVisible:
            self._remove_legend_items ()
            self._remove_plots ()

            if self.show_legend:
                # must be before .plot 
                self._pi.addLegend(offset=(-50,10), verSpacing=-8)                

            if len(self.data_list) > 0:
                self._plot()                        # plot data list 


    def refresh(self):
        """ refresh self plots by setting new x,y data """

        if self.show and self.pi_isVisible:
            self._refresh_plots ()

            if self.show_legend:
                self._remove_legend_items ()
                self._add_legend_items()

            logging.debug (f"{self} refresh")


    # --------------  private -------------

    def _plot (self):
        """ main method to plot the items"""
        # do plot - overwritten in sublass
        pass


    def _plot_dataItem (self, *args, name=None, **kwargs):
        """ plot DataItem and add it to self._plots etc """

        p = pg.PlotDataItem  (*args, **kwargs)
        self._add (p, name=name)
        

    def _plot_point (self, x, y, color=None, 
                     symbol='o', symbolSize=7, symbolPen=None, symbolBrush=None,
                     text=None, textColor=None, anchor=None):
        """ pot point with text label at x, y """

        # plot point as DataItem
        color = QColor(color) if color else QColor("whitesmoke")
        sBrush = symbolBrush if symbolBrush else pg.mkBrush(QColor('black'))
        sPen = pg.mkPen (color)       
        
        p = pg.PlotDataItem  ([x], [y], symbol=symbol, symbolSize=symbolSize, symbolPen=sPen, symbolBrush=sBrush)
        self._add(p) 

        # plot label as TextItem 
        if text is not None: 
            color = QColor(textColor) if textColor else QColor("whitesmoke")
            anchor = anchor if anchor else (0, 1)
            p = pg.TextItem(text, color, anchor=anchor)
            p.setPos (x,y)
            self._add (p)



    def _remove_plots (self):
        """ remove self plots from GraphicsView """

        p : pg.PlotDataItem
        for p in self._plots:
            self._pi.removeItem (p)

        self._plots = []
        self._plot_symbols = []


    def _add_legend_items (self):
        """ removes legend items of self """
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
 
