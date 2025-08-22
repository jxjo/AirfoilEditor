#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

All abstract diagram items to build a complete diagram view 

"""

import logging

from typing             import override, Type

from PyQt6.QtCore       import QSize, QMargins, pyqtSignal, QTimer
from PyQt6.QtWidgets    import QLayout, QGridLayout, QVBoxLayout, QHBoxLayout, QGraphicsGridLayout
from PyQt6.QtWidgets    import QWidget
from PyQt6.QtGui        import QPalette, QIcon, QColor

import pyqtgraph as pg                          # import PyQtGraph after PyQt6
from pyqtgraph          import icons

from base.common_utils  import *
from base.panels        import Edit_Panel, Container_Panel
from base.widgets       import ToolButton, Icon, Widget
from base.artist        import Artist

logger = logging.getLogger(__name__)
# logger.setLevel(logging.WARNING)



class Diagram (QWidget):
    """ 
    Abstract container panel/widget which may hold
     - serveral PlotItems 
     - each having optional view panel sections (to the left) 

    see: https://pyqtgraph.readthedocs.io/en/latest/getting_started/plotting.html

    """

    _width  = (200, None)                # (min,max) 
    _height = (100, None)                # (min,max)

    name   = "My Diagram"               # will be shown in Tabs 


    def __init__(self, parent, 
                 getter = None, 
                 width=None, 
                 height=None, 
                 **kwargs):
        super().__init__(parent, **kwargs)

        self._getter = getter
        self._myApp  = parent
        self._section_panel = None 
        self._diagram_items_grid_dict = {}

        # set width and height 

        if width is not None: 
            self._width = width
        if height is not None: 
            self._height = height

        Widget._set_width  (self, self._width)
        Widget._set_height (self, self._height)

        # create graphics widget 

        self._graph_widget = pg.GraphicsLayoutWidget (parent=self, show=True, size=None, title=None)
        self.graph_layout.setContentsMargins (20,20,20,10)  # default margins

        # remove default context menu of scene

        self._graph_widget.ci.scene().contextMenu = []

        # create all plot diagram items and setup layout with them  

        self.create_diagram_items () 

        #  add a message view box at bottom   

        self._message_vb = None
        self._add_message_box ()
    
        # create optional view panel add the left side 

        self._viewPanel   = None
        self.create_view_panel ()

        # build main layout with view panel to the left and graphics layout to the right

        l_main = QHBoxLayout()
        l_main.setContentsMargins (QMargins(0, 0, 0, 0))

        if self._viewPanel is not None: 
            l_main.addWidget (self._viewPanel)
        l_main.addWidget (self._graph_widget, stretch=10)

        self.setLayout (l_main)


    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        text = '' 
        return f"<{type(self).__name__}{text}>"


    def data_list (self): 
        # to be overloaded - or implemented with semantic name   

        if callable(self._getter):
            obj = self._getter()
        else: 
            obj = self._getter     
        return obj if isinstance (obj, list) else [obj]


    def _add_item (self, anItem: 'Diagram_Item', row, col, rowspan=1, colspan=1, rowStretch=0, columnStretch=0):
        """ adds a diagram item to self list of diagram items  """

        # save all grid paramters of diagram item to be able to rebuild grid 

        args = {**locals()}                                         # make a copy of argumnets 
        args.pop ("self")
        args.pop ("anItem")
        self._diagram_items_grid_dict [anItem] = args               # build dict of diagram items 

        # now add to pg.GraphicsLayout (a proxy of QGraphicsGridLayout)

        graphicsLayout : pg.GraphicsLayout = self._graph_widget.ci

        graphicsLayout.addItem (anItem, row, col, rowspan=rowspan, colspan=colspan)

        if anItem.isVisible(): 

            # core of Qt bug hack: set stretch only to visible items 
            if rowStretch:      self.graph_layout.setRowStretchFactor    (row, rowStretch)
            if columnStretch:   self.graph_layout.setColumnStretchFactor (col, columnStretch)

        # connect to visible signal of item to rebuild grid 
        try:
            anItem.sig_visible.disconnect (self._on_item_visible)
        except:
            pass
        anItem.sig_visible.connect (self._on_item_visible)


    def _add_message_box (self):
        """ add a message view box in the middle of the grid layout"""

        graphicsLayout : pg.GraphicsLayout = self._graph_widget.ci
        gridLayout : QGraphicsGridLayout   = graphicsLayout.layout

        self._message_vb = pg.ViewBox()
        self._message_vb.hide()
        nrows = gridLayout.rowCount()
        ncols = gridLayout.columnCount()
        graphicsLayout.addItem (self._message_vb, nrows, 0, rowspan=1, colspan=ncols-1)


    def _rebuild_grid_layout (self):
        """ rebuild graphics grid layout out of saved diagram items"""

        # ! rebuild is needed because of a Qt bug in QGraphicsGridLayout
        # !     If a stretchFactor is set to a row (column), then this row
        # !     does not disappear completly if the item is hidden
        # !     Therefore a new grid has to be build up with now stretch factor for the hidden item (row)

        # clear current graphicsLayout / delete QGraphicsGridLayout to remove exisating row or column stretches 

        graphicsLayout : pg.GraphicsLayout = self._graph_widget.ci
        graphicsLayout.clear()
        graphicsLayout.rows = {}
        graphicsLayout.layout=QGraphicsGridLayout()                         # hack to set fresh QGridLayout with *no* stretches
        graphicsLayout.setLayout(graphicsLayout.layout)

        # build grid layout with collected diagram items and their row, col specification

        diagram_item: Diagram_Item
        for diagram_item, args in self._diagram_items_grid_dict.items():

            self._add_item (diagram_item, **args)

        self._add_message_box()                                                # add a message box at the bottom                                

        # ensure grid fills the widget - sometimes this little kick is needed 

        self._graph_widget.resizeEvent(None)


    def _get_items (self, item_classes : Type['Diagram_Item'] | list[type['Diagram_Item']]) -> list['Diagram_Item']:
        """get Diagram Items of self having class name(s)

        Args:
            items: class or list of class of Diagram Items to retrieve
        Returns:
            List of Item with this classes
        """
        look_for = [item_classes] if not isinstance (item_classes,list) else item_classes
        result = []
        for item in self.diagram_items:
            if item.__class__ in look_for:
                result.append(item)
        return result 


    def _get_first_item (self, item_class : Type['Diagram_Item']) -> list['Diagram_Item']:
        """get Diagram Items of self having class name(s)"""
        items = self._get_items (item_class)
        if items:
            return items [0]
        else: 
            return None
        

    def _show_section_and_item (self, item_class : Type['Diagram_Item'], show = True) -> list['Diagram_Item']:
        """show view_panel section and the diagram item """
        for item in self._get_items (item_class):
            item.section_panel.set_switched_on (show)


    def _get_artist (self, artists : Type[Artist] | list[type[Artist]]) -> list[Artist]:
        """get artists of all my items having class name(s)

        Args:
            artists: class or list of class of Artists to retrieve
        Returns:
            List of artists with this classes
        """
        result = []
        for item in self.diagram_items: 
            result.extend (item._get_artist (artists))
        return result 


    def _show_artist (self, artist_class : Type[Artist], show = True, refresh = True):
        """show on/off of artist having artist_class name """

        for item in self.diagram_items:
            item._show_artist (artist_class, show, refresh=refresh)


    @property
    def myApp (self): 
        return self._myApp
    
    @property
    def diagram_items (self) -> list['Diagram_Item']:
        """ list of my diagram items """

        return list (self._diagram_items_grid_dict.keys())


    @property
    def graph_layout (self) -> QGraphicsGridLayout:
        """ the graphics grid layout of self"""
        return self._graph_widget.ci.layout

    @property
    def section_panel (self) -> Edit_Panel | None:
        """ small section panel representing self in view panel"""
        # overload for constructor 
        return self._section_panel
    

    def refresh(self, also_viewRange=True): 
        """ 
        refresh all childs (Diagram_Items) of self
        Args:
           also_viewRange: also re-init viewRange     
        """

        if self.isVisible():

            logger.debug (f"{str(self)} refresh")

            if self._viewPanel:
                self._viewPanel.refresh()                                       # first view panel as diagram settings could change

            item : Diagram_Item
            for item in self.diagram_items:
                if item.isVisible(): 
                    item.refresh()
                if also_viewRange:                                              # also setup view range if not visible
                    item.setup_viewRange()  


    @override
    def showEvent (self, ev):
        """ QShowEvent - self becomes visible  - Tab switch or first time"""

        # refresh plotItems - if it is first time they are intially plotted

        item : Diagram_Item
        for item in self.diagram_items:
            if item.isVisible(): 
                item.refresh() 

        # refresh all panels on viewPanel 

        if self._viewPanel:
            self._viewPanel.refresh()

        super().showEvent (ev) 



    def create_diagram_items ():
        """ create all plot Items and add them to the layout """
        # to be overlaoded 
        # like ... 
        #   item = Airfoil_Diagram_Item (self, getter=self.airfoil)
        #   self._add_item (item, 0, 0)
        pass


    def create_view_panel (self):
        """ 
        creates a view panel to the left of at least one diagram item 
        has a section_panel
        """

        # build side view panel with the section panels 

        layout = QVBoxLayout()
        layout.setContentsMargins (QMargins(0, 0, 0, 0)) 
        for item in self.diagram_items:
            if item.section_panel is not None: 
                layout.addWidget (item.section_panel,stretch=1)

        # add section panel of self (master) 

        if self.section_panel is not None: layout.addWidget (self.section_panel,stretch=0)
        
        layout.addStretch (1)

        self._viewPanel = Container_Panel()
        self._viewPanel.setMinimumWidth(180)
        self._viewPanel.setMaximumWidth(250)
        self._viewPanel.setLayout (layout)


    def _on_item_visible (self, aBool):
        """ slot to handle actions when switch on/off of diagram items"""

        nItems = len([item for item in self.diagram_items if item.isVisible()])

        if nItems == 0: 
            self._message_show ("No diagram items selected ")
        else:
            if aBool: 
                self._message_clear()

            # QT Bug: the GraphicsGirdLayout doesn't handle invisible items having stretch properly
            self._rebuild_grid_layout()


    def _message_show (self, aMessage):
        """ shows aMessage in the middle of the diagram """
        text = pg.TextItem(aMessage, anchor=(0.5,0))
        text.setPos(0, 0)
        self._message_vb.addItem (text)
        self._message_vb.show()


    def _message_clear (self):
        """ shows aMessage in the middle of the diagram """
        self._message_vb.clear()
        self._message_vb.hide()




class Diagram_Item (pg.PlotItem):
    """ 
    Abstract PlotItem  

    see: https://pyqtgraph.readthedocs.io/en/latest/getting_started/plotting.html

    """

    name        = "Abstract Diagram_Item"               # used for link and section header
    title       = "The Title"                           # title of diagram item
    subtitle    = "my subtitle"                         # optional subtitle 

    min_width   = 500                                   # min size needed - see below 
    min_height  = 150 

    # Signals 

    sig_visible = pyqtSignal(bool)                      # when self is set to show/hide 


    def __init__(self, parent, 
                 getter = None, 
                 show = True,                           # show initially 
                 **kwargs):

        super().__init__(name=self.name,                # to link view boxes 
                         **kwargs)

        self._parent : Diagram = parent 
        self._getter = getter
        self._show   = show 

        self._section_panel = None                      # view section to the left 
        self._artists : list [Artist] = []              # list of my artists

        self._title_item = None                         # LabelItem of the diagram title
        self._subtitle_item = None  

        self._help_messages         = {}                # current help messages which are shown 
        self._help_messages_shown   = {}                # all help messages shown up to now 
        self._help_message_items    = {}

        # setup additional, optional button to reset view range 

        self._vb_state_changed = False 
        self._resetBtn = None
        if self.has_reset_button:
            ico = Icon (Icon.RESETVIEW,light_mode = False)
            self._resetBtn = pg.ButtonItem(pixmap=ico.pixmap(QSize(52,52)), width=16, parentItem=self)
            self._resetBtn.mode = 'auto'
            self._resetBtn.clicked.connect(self._resetBtn_clicked)
            timer = QTimer()                                
            timer.singleShot(50, self._reset_prepare)           # delayed when all initial drawing done 

        # setup item to print coordinates 

        self._coordItem = pg.LabelItem("", color=QColor(Artist.COLOR_LEGEND), size=f"{Artist.SIZE_NORMAL}pt", justify="left")  
        self._coordItem.setParentItem(self)  
        self._coordItem.anchor(parentPos=(0,1), itemPos=(0.0,0.0), offset=(45, -20))                       

        # set margins (inset) of self - ensure some space for coordinates

        self.setContentsMargins ( 10,20,10,20)

        # PlotItem needs a some size so that inital boundingBox calculation having pixel calculation work properly
        #   - see pixelVectors  (important for clickable and movable (mousesize))
        
        self.setMinimumSize (self.min_width, self.min_height)

        # setup artists - must be override

        self.setup_artists ()

        for artist in self._artists:
            artist.sig_help_message.connect (self._on_help_message)

        # setup view range (must be override) is done in refresh() - 

        self._viewRange_set = False

        # setup axis - can be override
        
        self.setup_axis()

        # no pyqtgraph context menu  - no view box context menu , no plot item 

        self.setMenuEnabled(enableMenu=False, enableViewBoxMenu=False)

        # initial show or hide - use super() - avoid refresh
 
        super().setVisible (show) 


    @override
    def __repr__(self) -> str:
        text = '' 
        return f"<{type(self).__name__}{text}>"


    def _add_artist (self, artist : Artist):
        """ add a new artist to my list"""  
    
        self._artists.append (artist)
     
    def _get_artist (self, artists : Type[Artist] | list[type[Artist]]) -> list[Artist]:
        """get my artists having class name(s)

        Args:
            artists: class or list of class of Artists to retrieve
        Returns:
            List of artists with this classes
        """
        look_for = [artists] if not isinstance (artists,list) else artists
        result = []
        for artist in self._artists:
            if artist.__class__ in look_for:
                result.append(artist)
        return result 


    def _show_artist (self, artist_class : Type[Artist], show : bool = True, refresh=True):
        """show on/off of artist having artist_class name """

        # logger.debug (f"{self} show artists: {show} - is visible: {self.isVisible()}")
        for artist in self._get_artist (artist_class):
            artist.set_show (show, refresh=refresh)            


    def _on_help_message (self, aArtist :Artist | None, aMessage: str | None):
        """ slot for help message signal of an artist. show it"""

        # if aArtist: 
        #     logger.warning (f"{self} on_help of {aArtist} of item: {aArtist._pi} with message: {aMessage}")
        # else: 
        #     logger.warning (f"{self} on_help  -> refresh ")

        # remove all existing message item 
        for item in self._help_message_items.values():
            self.scene().removeItem (item)                             # was added directly to the scene via setParentItem
        self._help_message_items = {}

        # add / remove message of artist to my list 
        if aArtist:                                                    # could be called without artist -> refresh only 
            if not aMessage:
                self._help_messages.pop (aArtist, None)                # remove existing message of this artist
            else:
                if aArtist in self._help_messages_shown:
                    self._help_messages.pop (aArtist, None) 
                else:   
                    self._help_messages[aArtist] = aMessage            # add this message 
                    self._help_messages_shown[aArtist] = aMessage      # add to the list already shown           


        # plot all current messages 
        i = 0 
        for artist, message in self._help_messages.items():
            parentPos = (0.3,0.03)                                      # parent x starts at PlotItem (including axis)       
            itemPos   = (0.0,0.0)
            y_offset  = i * 20

            p1 = pg.LabelItem(f"- {message}", color=Artist.COLOR_HELP, size=f"{Artist.SIZE_NORMAL}pt")    

            p1.setParentItem(self)                                      # add to self (Diagram Item) for absolute position 
            p1.anchor(itemPos=itemPos, parentPos=parentPos, offset=(0,y_offset))
            p1.setZValue(5)

            self._help_message_items[artist] = p1
            i +=1


    @override
    def setVisible (self, aBool):
        """ Qt overloaded to signal parent """
        super().setVisible (aBool)

        logger.debug  (f"{self} - setVisible {aBool}")

        self.set_show (aBool)

        self.sig_visible.emit (aBool)


    def set_show (self, aBool):
        """ switch on/off artists of self"""
        # to override
        self._show = aBool

        if aBool: 
            self.refresh_artists ()
            self.setup_viewRange()   
            self._viewRange_set = True

            self.plot_title ()


    @override
    def close (self):
        # PlotItem override to remove button
        if self._resetBtn is not None:
            self._resetBtn.setParent (None) 
            self._resetBtn = None
        super().close()


    @override
    def hoverEvent(self, ev):
        """ overridden to show coordinates of mouse cursor"""
        super().hoverEvent (ev)

        if self.mouseHovering and not self.buttonsHidden:
            pos : pg.Point = self.viewBox.mapSceneToView(ev.scenePos())

            if self.viewBox.viewRect().contains(pos):
                self._coordItem.show()
                self._coordItem.setText (self._coord_as_text (pos))
            else:
                self._coordItem.hide()


    def _coord_as_text (self, pos : pg.Point) -> str:
        """ current mouse coordinates as formatted text string """

        viewRange = self.viewBox.viewRange()
        x_range = viewRange [0]
        y_range = viewRange [1]
        x_size  = abs (x_range[1] - x_range[0])
        y_size  = abs (y_range[1] - y_range[0])

        return f"x {self._format_coord(pos.x(),x_size)}&nbsp;&nbsp;y {self._format_coord(pos.y(),y_size)}"

    def _format_coord (self, coord: float, range : float) -> str:
        """ format a coordinate number depending on view range size"""
        if range < 0.01:
            dec = 5
        elif range < 0.1:
            dec = 4
        elif range < 10:
            dec = 3
        elif range < 100:
            dec = 2
        elif range < 10000:
            dec = 1
        else: 
            dec = 0
        return f"{coord:#.{dec}f}"


    @override
    def resizeEvent(self, ev):

        # update position reset button 
        if self._resetBtn is not None:                  # item could be already closed 
            btnRect = self.mapRectFromItem(self._resetBtn, self._resetBtn.boundingRect())
            y = self.size().height() - btnRect.height()
            self._resetBtn.setPos(20, y+3)              # right aside autoBtn

        super().resizeEvent (ev)


    @property 
    def has_reset_button (self) -> bool:
        """ reset view button in the lower left corner"""
        # to be overridden
        return True 
    

    @override
    def updateButtons(self):
        # PlotItem override to show/hide reset button
        super().updateButtons ()
        try:
            if self.mouseHovering and not self.buttonsHidden and self._vb_state_changed: #  and not all(self.vb.autoRangeEnabled()):
                if self._resetBtn is not None: 
                    self._resetBtn.show()
                self._coordItem.show()
            else:
                if self._resetBtn is not None: 
                    self._resetBtn.hide()
                self._coordItem.hide()
        except RuntimeError:
            pass  # this can happen if the plot has been deleted.


    def _resetBtn_clicked(self):
        """ reset button was clicked - set initial view range"""

        if self._vb_state_changed:
            self.setup_viewRange ()
            self._vb_state_changed = False


    def _reset_prepare (self):
        """ prepare reset button - save initial range"""
        self.sigRangeChanged.connect(self._viewRangeChanged)


    def _viewRangeChanged (self): 
        """ slot - view Range changed"""
        self._vb_state_changed = True 


    @property
    def viewBox (self) -> pg.ViewBox:
        """ viewBox of self""" 
        return self.getViewBox()

    def data_object (self): 
        # to be ooverloaded - or implemented with semantic name 
        if callable(self._getter):
            return self._getter()
        else: 
            return self._getter


    def data_list (self): 
        # to be overloaded - or implemented with semantic name        
        if isinstance (self.data_object(), list):
            return self.data_object()
        else: 
            return [self.data_object()]   


    def refresh(self): 
        """ refresh my artits and section panel """

        refresh_done = False

        if self._section_panel is not None: 
            # refresh artists only if self section is switched on 
            if self.section_panel.switched_on:
                self.refresh_artists()          # first artist and then panel 
                refresh_done = True

            self.section_panel.refresh()

        else: 
            self.refresh_artists() 
            refresh_done = True

        # initial setup of viewRange if artists were shown by refresh

        if not self._viewRange_set and refresh_done:
            self.setup_viewRange()   
            self._viewRange_set = True

        # plot title and sub title with default values of class

        self.plot_title () 


    def setup_artists (self):
        """ create and setup the artists of self"""
        # must be implemented by subclass
        
        logger.warning (f"{self} no artists are setup")


    def setup_viewRange (self):
        """ define view range of this plotItem"""
        # must be implemented by subclass
        
        logger.warning (f"{self} no view range defined")


    def setup_axis (self):
        """ setup axis of of this plotItem"""
        # can be implemented by subclass
        
        # define a constant width 
        yaxis : pg.AxisItem = self.getAxis ('left')
        yaxis.setWidth (40)


    def refresh_artists (self):
        """ refresh all artists of self - can be overridden"""
        for artist in self._artists:
            artist.refresh()


    def plot_title (self, 
                    title : str|None = None,
                    title_size : int = None,
                    title_color : str|QColor = None,
                    subtitle : str|None = None, 
                    align :str ='left', 
                    offset : tuple = (50,5)):
        """plot a title, optionally with a sub title, at fixed position

        Args:
            title: optional - default is class.title
            title_size: optional - title font size in pt 
            title_color: optional - title color as String or QColor
            subtitle: optional - default is class.subtitle
            align: aligned to the left or right of th item .
            offset: from the upper left (right) corner in pixel  
        """

        if title is None:
            if not self.title: return                       # show no title  
            title = self.title

        if title_size is None:
            title_size = Artist.SIZE_HEADER  

        if subtitle is None:
            subtitle = self.subtitle

        # remove existing title item 
        if isinstance (self._title_item, pg.LabelItem):
            if self._title_item:
                self.scene().removeItem (self._title_item)      # was added directly to the scene via setParentItem
            if self._subtitle_item:
                self.scene().removeItem (self._subtitle_item)    
       

        if align == 'left':
            parentPos = (0.0)                               # parent x starts at PlotItem (including axis)       
            itemPos   = (0,0)
        else:  
            parentPos = (0.98,0)
            itemPos   = (1,0)

        if title_color is None: 
            color = Artist.COLOR_HEADER
        else:
            color = title_color

        p1 = pg.LabelItem(title, color=color, size=f"{title_size}pt")    

        p1.setParentItem(self)                            # add to self (Diagram Item) for absolute position 
        p1.anchor(itemPos=itemPos, parentPos=parentPos, offset=offset)
        p1.setZValue(5)
        self._title_item = p1

        if subtitle is not None:
            sub_offset = (offset[0], offset[1]+30)
            p2 = pg.LabelItem(subtitle, color=QColor(Artist.COLOR_LEGEND), size=f"{Artist.SIZE_NORMAL}pt")    
            p2.setParentItem(self)                            # add to self (Diagram Item) for absolute position 
            p2.anchor(itemPos=itemPos, parentPos=parentPos, offset=sub_offset)
            p2.setZValue(5)
            self._subtitle_item = p2 



    @property
    def section_panel (self) -> Edit_Panel | None:
        """ small section panel representing self in view panel"""
        # overload for constructor 
        return  self._section_panel
    
