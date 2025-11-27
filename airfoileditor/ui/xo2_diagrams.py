#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

Diagram (items) for xo2

"""

from typing                 import override

import pyqtgraph as pg                                

from ..base.artist          import Artist
from ..base.diagram         import Diagram, Diagram_Item 
from ..model.polar_set      import var
from ..model.xo2_results    import Optimization_History_Entry

from .xo2_artists           import Xo2_Design_Radius_Artist, Xo2_Improvement_Artist, Xo2_OpPoint_Defs_Artist
from .ae_artists            import Polar_Artist

from ..app_model            import App_Model


import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class Diagram_Xo2_Airfoil_and_Polar (Diagram):
    """ Little Diagram with Airfoil and Polar Item used for new xo2 optimization case"""

    width  = (None, None)               # (min,max) 
    height = (400, None)                # (min,max)


    def __init__(self, *args,  **kwargs):
        super().__init__(*args, **kwargs)

        self.graph_layout.setContentsMargins (5,10,5,5)  # default margins

        # show opPoint definitions
        for artist in self._get_artist (Xo2_OpPoint_Defs_Artist):
            artist.set_show (True)
            artist.set_show_mouse_helper (False) 

        # switch off polar legend 
        for artist in self._get_artist (Polar_Artist):
            artist.set_show_legend (False) 

    @property 
    def app_model (self) -> App_Model:
        """ application model"""
        return self.dataObject()


    @override
    def create_diagram_items (self):
        """ create all plot Items and add them to the layout """

        from ui.ae_diagrams       import Diagram_Item_Airfoil, Diagram_Item_Polars

        r = 0
        item = Diagram_Item_Airfoil (self,self.app_model)
        item.setMinimumSize (300, 200)
        self._add_item (item, r, 0, colspan=2)

        r += 1
        default_settings = [{"xyVars" : (var.CD,var.CL)}, {"xyVars" : (var.CL,var.GLIDE)}]

        for iItem in [0,1]:
            # create Polar items with init values vor axes variables 
            item = Diagram_Item_Polars (self, self.app_model, show=True)
            item.name = f"{Diagram_Item_Polars.name}_{iItem+1}"                 # set unique name as there a multiple items
            item._set_settings (default_settings[iItem])                        # set default settings first
            self._add_item (item, r, iItem, rowStretch=3)

        self.graph_layout.setRowStretchFactor (0,2)
        self.graph_layout.setRowStretchFactor (1,3)


    @override
    def create_view_panel (self):
        """ no view_panel"""
        pass



class Diagram_Item_Design_Radius (Diagram_Item):
    """ 
    Diagram (Plot) Item to plot design radius during optimization
    """

    title       = "Design Radius"
    subtitle    = None                

    min_width   = 100                                    # min size needed - see below 
    min_height  = 100 

    show_buttons = False                                 # no buttons
    show_coords  = False                                 # no coordinates

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setContentsMargins ( 0,10,5,0)


    @property
    def steps (self) -> list ['Optimization_History_Entry']: 
        return self._dataObject ()


    @override
    def plot_title(self):
        super().plot_title (title=self.title, title_size=8, title_color=Artist.COLOR_LEGEND,offset= (10,-10))


    @override
    def setup_artists (self):
        """ create and setup the artists of self"""
        self._add_artist (Xo2_Design_Radius_Artist (self, lambda: self.steps))


    @override
    def setup_viewRange (self):
        """ define view range of this plotItem"""
        axis : pg.AxisItem = self.getAxis ('left')
        axis.setWidth (5)
        axis : pg.AxisItem = self.getAxis ('bottom')
        axis.setHeight (5)
        self.viewBox.enableAutoRange (axis == 'xy')
        self.viewBox.setDefaultPadding (0.0)



class Diagram_Item_Improvement (Diagram_Item):
    """ 
    Diagram (Plot) Item to plot improvement during optimization
    """

    title       = "Improvement"
    subtitle    = None                

    min_width   = 100                                    # min size needed - see below 
    min_height  = 100 

    show_buttons = False                                 # no buttons
    show_coords  = False                                 # no coordinates

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setContentsMargins ( 0,10,5,0)

    @property
    def steps (self) -> list ['Optimization_History_Entry']: 
        return self._dataObject ()


    @override
    def plot_title(self):
        super().plot_title (title=self.title, title_size=8, title_color=Artist.COLOR_LEGEND,offset= (10,-10))


    @override
    def setup_artists (self):
        """ create and setup the artists of self"""
        self._add_artist (Xo2_Improvement_Artist (self, lambda: self.steps))


    @override
    def setup_viewRange (self):
        """ define view range of this plotItem"""
        axis : pg.AxisItem = self.getAxis ('left')
        axis.setWidth (5)
        axis : pg.AxisItem = self.getAxis ('bottom')
        axis.setHeight (5)
        self.viewBox.enableAutoRange (axis == 'xy')
        self.viewBox.setDefaultPadding (0.0)



class Diagram_Xo2_Progress (Diagram):
    """ Diagram with design radius and improvement development  """

    _width  = (None, None)               # (min,max) 
    _height = (140, None)                # (min,max)


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.graph_layout.setContentsMargins (5,10,5,5)  # default margins


    @property
    def steps (self) -> list ['Optimization_History_Entry']:
        """ optimization steps imported (up to now)""" 
        return self._dataObject ()
    

    def create_diagram_items (self):
        """ create all plot Items and add them to the layout """
        item = Diagram_Item_Design_Radius (self, lambda: self.steps)
        self._add_item (item, 0, 0)
        item = Diagram_Item_Improvement   (self, lambda: self.steps)
        self._add_item (item, 0, 1)


    @override
    def create_view_panel (self):
        """ no view_panel"""
        pass

