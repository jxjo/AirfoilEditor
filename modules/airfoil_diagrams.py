#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Diagram (items) for airfoil

"""

import logging

from base.widgets           import * 
from base.diagram           import * 

from model.airfoil          import Airfoil
from model.polar_set        import *

from airfoil_artists        import *
from airfoil_widgets        import Airfoil_Select_Open_Widget
from airfoil_ui_panels      import Panel_Polar_Defs, Panel_Airfoils 

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)



#-------------------------------------------------------------------------------
# Diagram Items  
#-------------------------------------------------------------------------------



class Diagram_Item_Airfoil (Diagram_Item):
    """ 
    Diagram (Plot) Item for airfoils shape 
    """

    name = "View Airfoil"           # used for link and section header 


    sig_geometry_changed         = pyqtSignal()          # airfoil data changed in a diagram 


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # set margins (inset) of self 
        self.setContentsMargins ( 0,30,10,20)


    def airfoils (self) -> list[Airfoil]: 
        return self._getter()
    
    def _one_is_bezier_based (self) -> bool: 
        """ is one of airfoils Bezier based? """
        a : Airfoil
        for a in self.airfoils():
            if a.isBezierBased: return True
        return False 


    def _on_enter_panelling (self):
        """ slot user started panelling dialog - show panels """

        # switch on show panels , switch off thciknes, camber 
        self.airfoil_artist.set_show_points (True)
        self.line_artist.set_show (False)
        self.section_panel.refresh() 

        logger.debug (f"{str(self)} _on_enter_panelling")


    def _on_blend_airfoil (self):
        """ slot to handle blend airfoil entered"""

        self.line_artist.set_show (False)           # switch off thickness & camber 
        self.section_panel.refresh()

        logger.debug (f"{str(self)} _on_blend_airfoil")


    @override
    def plot_title(self, **kwargs):

        # the first airfoil get's in the title 
        airfoil = self.airfoils()[0]

        mods = None 
        if airfoil.usedAsDesign:
            mods = ', '.join(airfoil.geo.modifications) 
        if mods:
            subtitle = "Mods: " + mods
        elif not mods and airfoil.isBezierBased:
            subtitle = 'Based on 2 Bezier curves'
        else: 
            subtitle = "" 

        super().plot_title (title=airfoil.name, subtitle=subtitle, **kwargs)


    @override
    def setup_artists (self):
        """ create and setup the artists of self"""
        
        self.airfoil_artist = Airfoil_Artist   (self, self.airfoils, show_legend=True)

        self.line_artist = Airfoil_Line_Artist (self, self.airfoils, show=False, show_legend=True)
        self.line_artist.sig_geometry_changed.connect (self.sig_geometry_changed.emit)

        self.bezier_artist = Bezier_Artist (self, self.airfoils)
        self.bezier_artist.sig_bezier_changed.connect (self.sig_geometry_changed.emit)


    @override
    def setup_viewRange (self):
        """ define view range of this plotItem"""

        self.viewBox.setDefaultPadding(0.05)

        self.viewBox.autoRange ()               # first ensure best range x,y 
        self.viewBox.setXRange( 0, 1)           # then set x-Range

        self.viewBox.setAspectLocked()

        self.viewBox.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)

        self.showGrid(x=True, y=True)


    @override
    def refresh_artists (self):
        self.airfoil_artist.refresh() 
        self.line_artist.refresh() 

        # show Bezier shape function when current airfoil is Design and Bezier 
        cur_airfoil : Airfoil = self.airfoils()[0]
        if cur_airfoil.isBezierBased and cur_airfoil.usedAsDesign:
            self.bezier_artist.set_show (True)
        else: 
            self.bezier_artist.refresh() 

    @property
    def section_panel (self) -> Edit_Panel:
        """ return section panel within view panel"""

        if self._section_panel is None:    
            l = QGridLayout()
            r,c = 0, 0 
            CheckBox (l,r,c, text="Coordinate points", 
                    get=lambda: self.airfoil_artist.show_points,
                    set=self.airfoil_artist.set_show_points) 
            r += 1
            CheckBox (l,r,c, text="Thickness && Camber", 
                    get=lambda: self.line_artist.show,
                    set=self.line_artist.set_show) 
            r += 1
            CheckBox (l,r,c, text="Shape function (Bezier)", 
                    get=lambda: self.bezier_artist.show,
                    set=self.bezier_artist.set_show,
                    hide=lambda : not self._one_is_bezier_based()) 
            r += 1
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (title=self.name, layout=l, height=(100,None), 
                                              switchable=True, on_switched=self.setVisible)

        return self._section_panel 



class Diagram_Item_Curvature (Diagram_Item):
    """ 
    Diagram (Plot) Item for airfoils curvature 
    """

    name        = "View Curvature"
    title       = "Curvature"                 
    subtitle    = None                                 # will be set dynamically 

    def __init__(self, *args, **kwargs):

        self._link_x  = False 

        super().__init__(*args, **kwargs)

        # set margins (inset) of self 
        self.setContentsMargins ( 0,30,10,20)


    def airfoils (self) -> list[Airfoil]: 
        return self.data_list()
    

    @override
    def set_show (self, aBool):
        """ switch on/off artists of self when diagram_item is switched on/off"""
        super().set_show (aBool)

        self.curvature_artist.set_show (aBool)


    @property
    def link_x (self) -> bool:
        """ is x axes linked with View Airfoil"""
        return self._link_x
    def set_link_x (self, aBool):
        """ link x axes to View Airfoil"""
        self._link_x = aBool is True
        if self.link_x:
            self.setXLink(Diagram_Item_Airfoil.name)
        else: 
            self.setXLink(None)


    def setup_artists (self):
        """ create and setup the artists of self"""
        
        self.curvature_artist = Curvature_Artist (self, self.airfoils, show_derivative=False, show_legend=True)


    def setup_viewRange (self):
        """ define view range of this plotItem"""

        self.viewBox.setDefaultPadding(0.05)

        self.viewBox.autoRange ()               # first ensure best range x,y 
        self.viewBox.setXRange( 0, 1)           # then set x-Range
        self.viewBox.setYRange(-2.0, 2.0)

        self.showGrid(x=True, y=True)


    def refresh_artists (self):
        self.curvature_artist.refresh() 


    @property
    def section_panel (self) -> Edit_Panel:
        """ return section panel within view panel"""

        if self._section_panel is None:            
            l = QGridLayout()
            r,c = 0, 0 
            CheckBox (l,r,c, text="Upper side", 
                    get=lambda: self.curvature_artist.show_upper,
                    set=self.curvature_artist.set_show_upper) 
            r += 1
            CheckBox (l,r,c, text="Lower side", 
                    get=lambda: self.curvature_artist.show_lower,
                    set=self.curvature_artist.set_show_lower) 
            r += 1
            CheckBox (l,r,c, text="Derivative of curvature", 
                    get=lambda: self.curvature_artist.show_derivative,
                    set=self.curvature_artist.set_show_derivative) 
            r += 1
            SpaceR   (l,r)
            r += 1
            CheckBox (l,r,c, text=f"X axes linked to '{Diagram_Item_Airfoil.name}'", 
                    get=lambda: self.link_x, set=self.set_link_x) 
            r += 1
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (title=self.name, layout=l, 
                                              height=160, switchable=True, switched_on=self._show, 
                                              on_switched=self.setVisible)

        return self._section_panel 



class Diagram_Item_Welcome (Diagram_Item):
    """ Item with Welcome message  """

    title       = ""                                    # has it's own title 
    subtitle    = None

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.buttonsHidden      = True                          # don't show buttons and coordinates

        # set margins (inset) of self 
        self.setContentsMargins ( 0,20,0,0)

        parentPos = (0.0)                               # parent x starts at PlotItem (including axis)       
        itemPos   = (0,0)
        offset    = (50,5)

        p1 = pg.LabelItem(self._welcome_message(), color=QColor(Artist.COLOR_HEADER), size=f"{Artist.SIZE_HEADER}pt")    

        p1.setParentItem(self.viewBox)                            # add to self (Diagram Item) for absolute position 
        p1.anchor(itemPos=itemPos, parentPos=parentPos, offset=offset)
        p1.setZValue(5)
        self._title_item = p1

        self.setFixedHeight(200)


    def _welcome_message (self) -> str: 
        # use Notepad++ or https://froala.com/online-html-editor/ to edit 

        message = """
<span style="font-size: 18pt; color: whitesmoke">Welcome to <strong>Airfoil<span style="color:deeppink">Editor</span></strong></span>

<span style="font-size: 10pt; color: darkgray">
<p>
    This is an example airfoil as no airfoil was provided on startup. Try out the functionality with this example airfoil or  
    <strong><span style="color: silver;">Open&nbsp;</span></strong>an existing airfoil.
    <p>
    You can view the properties of an airfoil like thickness distribution or camber, analyze the curvature of the surface or  
    <strong><span style="color: silver;">Modify</span></strong> the airfoils geometry. 
    </p> 
    <p>
    <strong><span style="color: silver;">New as Bezier</span></strong> allows to convert the airfoil into an airfoil which is based on two Bezier curves.
    </p> 
    <p>
    <span style="color: deepskyblue;">Tip: </span>Assign the file extension '.dat' to the Airfoil Editor to open an airfoil with a double click.
    </p>
</p>
</span>
"""
        return message


    def setup_artists (self):
        pass

    @override
    def setup_viewRange (self):
        self.viewBox.autoRange ()  
        self.viewBox.setXRange( 0, 1, padding=0.08)    
        self.showAxis('left', show=False)
        self.showAxis('bottom', show=False)
        self.showGrid(x=False, y=False)



class Diagram_Item_Polars (Diagram_Item):
    """ 
    Diagram (Plot) Item for polars 
    """

    name        = "Polar"                               # used for link and section header 
    title       = None 
    subtitle    = None                                  # optional subtitle 


    sig_geometry_changed         = pyqtSignal()          # airfoil data changed in a diagram 


    def __init__(self, *args, iItem= 1, itemDict: dict = None, xyVars=None, **kwargs):

        self._iItem  = iItem
        self.set_xyVars (xyVars)                        # polar vars for x,y axis 

        self._title_item2 = None                        # a second 'title' for x-axis 

        self.name = f"{self.name} {iItem}"

        super().__init__(*args, **kwargs)

        # set margins (inset) of self 
        self.setContentsMargins ( 0,10,10,20)


    @override
    def plot_title (self):
        """ override to have 'title' at x,y axis"""

        # remove existing title item 
        if isinstance (self._title_item, pg.LabelItem):
            self.scene().removeItem (self._title_item)          # was added directly to the scene via setParentItem
        if isinstance (self._title_item2, pg.LabelItem):
            self.scene().removeItem (self._title_item2)         # was added directly to the scene via setParentItem
       
        # y-axis
        p = pg.LabelItem(self.yVar, color=QColor(Artist.COLOR_HEADER), size=f"{Artist.SIZE_HEADER}pt")    

        p.setParentItem(self)                              # add to self (Diagram Item) for absolute position 
        p.anchor(itemPos=(0,0), parentPos=(0,0), offset=(50,5))
        p.setZValue(5)
        self._title_item = p

        # x-axis
        p = pg.LabelItem(self.xVar, color=QColor(Artist.COLOR_HEADER), size=f"{Artist.SIZE_HEADER}pt")    

        p.setParentItem(self)                              # add to self (Diagram Item) for absolute position 
        p.anchor(itemPos=(1.0,1), parentPos=(0.98,1.0), offset=(0,-40))
        p.setZValue(5)
        self._title_item2 = p


    def airfoils (self) -> list[Airfoil]: 
        return self._getter()
    

    @property
    def xVar (self) -> var:
        return self._xyVars[0]
    def set_xVar (self, varType : var):
        self._xyVars = (varType, self._xyVars[1])

        self.setup_viewRange ()
        artist : Polar_Artist = self._artists [0]
        artist.set_xyVars (self._xyVars)

        self.plot_title()


    @property
    def yVar (self) -> var:
        return self._xyVars[1]
    def set_yVar (self, varType: var):
        self._xyVars = (self._xyVars[0], varType)

        self.setup_viewRange ()
        artist : Polar_Artist = self._artists [0]
        artist.set_xyVars (self._xyVars)

        self.plot_title ()

    def set_xyVars (self, xyVars : list[str]):
        """ set xyVars from a list of var strings or enum var"""

        if isinstance (xyVars[0], str):
            xVar = var(xyVars[0])
        else: 
            xVar = xVar 
        if isinstance (xyVars[1], str):
            yVar = var(xyVars[1])
        else: 
            yVar = xVar 
        self._xyVars = (xVar, yVar)


    @override
    def setup_artists (self):
        """ create and setup the artists of self"""

        self._add_artist (Polar_Artist     (self, self.airfoils, xyVars=self._xyVars, show_legend=True))


    @override
    def setup_viewRange (self):
        """ define view range of this plotItem"""

        self.viewBox.setDefaultPadding(0.05)

        self.viewBox.autoRange ()                           # first ensure best range x,y 
        self.viewBox.enableAutoRange(enable=True)

        self.showGrid(x=True, y=True)

        self._set_legend_position ()                         # find nice legend position 


    def _set_legend_position (self):
        """ try to have a good position for legend depending on xyVars"""

        if (self.yVar == CL or self.yVar == ALPHA) and self.xVar == CD:
            self.legend.anchor (itemPos=(1,0.5), parentPos=(1,0.5), offset=(-10,0))     # right, middle 

        elif (self.yVar == GLIDE or self.yVar == SINK) and (self.xVar == ALPHA or self.xVar == CL):
            self.legend.anchor (itemPos=(0.2,1), parentPos=(0.5,1), offset=(0,-20))     # middle, bottom

        elif (self.yVar == CL) and (self.xVar == ALPHA):
            self.legend.anchor (itemPos=(0,0), parentPos=(0,0), offset=(40,10))         # left, top

        else:  
            self.legend.anchor (itemPos=(1,0), parentPos=(1,0), offset=(-10,10))        # right, top 

        # reduce vertical spacing 
        l : QGraphicsGridLayout = self.legend.layout
        l.setVerticalSpacing(-5)




#-------------------------------------------------------------------------------
# Diagrams   
#-------------------------------------------------------------------------------



class Diagram_Airfoil_Polar (Diagram):
    """    
    Diagram view to show/plot airfoil diagrams - Container for diagram items 
    """


    sig_airfoil_changed         = pyqtSignal()          # airfoil data changed in a diagram 
    sig_new_airfoil_ref1        = pyqtSignal(object)    # new ref1 airfoil  
    sig_airfoil_ref_changed     = pyqtSignal(object, object) # changed reference airfoil 
    sig_polar_def_changed       = pyqtSignal()          # polar definition changed  


    def __init__(self, *args, polar_defs_fn= None, diagram_settings=[], **kwargs):

        self._polar_panel   = None 
        self._polar_defs_fn = polar_defs_fn 
        self._diagram_settings = diagram_settings

        super().__init__(*args, **kwargs)

        self._viewPanel.setMinimumWidth(240)
        self._viewPanel.setMaximumWidth(240)
 
         # set spacing between the two items
        self.graph_layout.setVerticalSpacing (0)

    # --- save --------------------- 

    def _as_dict_list (self) -> list:
        """ returns a list with data dict of the parameters of diagram items """

        l = []
        item : Diagram_Item_Polars
        for item in self._get_item (Diagram_Item_Polars):
            item_dict = {}
            toDict (item_dict, "xyVars", (item.xVar, item.yVar))

            l.append (item_dict)
        return l


    def _get_item (self, items : Type[Diagram_Item] | list[type[Diagram_Item]]) -> list[Diagram_Item]:
        """get Diagram Items of self having class name(s)

        Args:
            items: class or list of class of Diagram Items to retrieve
        Returns:
            List of Item with this classes
        """
        look_for = [items] if not isinstance (items,list) else items
        result = []
        for item in self.diagram_items:
            if item.__class__ in look_for:
                result.append(item)
        return result 


    # -------------


    @property 
    def polar_defs (self) -> list [Polar_Definition]:
        """ actual polar definitions"""
        return self._polar_defs_fn() if self._polar_defs_fn else []


    def all_airfoils (self) -> list[Airfoil]: 
        """ the airfoil(s) currently to show as list"""
        return self.data_list()


    def airfoils (self) -> list[Airfoil]: 
        """ the airfoil(s) currently to show as list (filtered)"""
        return list(filter(lambda airfoil: airfoil.get_property("show",True), self.all_airfoils()))  


    def create_diagram_items (self):
        """ create all plot Items and add them to the layout """

        r = 0 
        # if self.airfoils()[0].isExample:

        #     # show Welcome text if Airfoil is the Example arfoil 
        #     item = Diagram_Item_Welcome (self)
        #     self._add_item (item, r, 0)
        #     r += 1

        item = Diagram_Item_Airfoil (self, getter=self.airfoils)
        self._add_item (item, r, 0, colspan=2)
 
        item.sig_geometry_changed.connect (self._on_geometry_changed)

        r += 1
        item = Diagram_Item_Curvature (self, getter=self.airfoils, show=False)
        self._add_item (item, r, 0, colspan=2)

        if Worker.ready:
            r += 1

            # create Polar items with init values from settings 

            dataDict = self._diagram_settings[0] if len(self._diagram_settings) > 0 else {"xyVars" : (var.CD,var.CL)}
            xyVars = dataDict ["xyVars"]

            item = Diagram_Item_Polars (self, iItem=1, getter=self.airfoils, xyVars=xyVars)
            self._add_item (item, r, 0)

            dataDict = self._diagram_settings[1] if len(self._diagram_settings) > 1 else {"xyVars" : (var.CL,var.GLIDE)}
            xyVars = dataDict ["xyVars"]

            item = Diagram_Item_Polars (self, iItem=2, getter=self.airfoils, xyVars=(var.CL,var.GLIDE))
            self._add_item (item, r, 1)
 

    @override
    def create_view_panel (self):
        """ 
        creates a view panel to the left of at least one diagram item 
        has a section_panel
        """
 
        # build side view panel with the section panels 

        layout = QVBoxLayout()
        layout.setContentsMargins (QMargins(0, 0, 0, 0)) 

        # airfoils panel 

        if self.section_panel is not None: 
            layout.addWidget (self.section_panel,stretch=0)

        # diagram items panel

        for item in self.diagram_items:
            if item.section_panel is not None: 
                layout.addWidget (item.section_panel,stretch=0)

        # polar panel

        layout.addWidget (self.polar_panel)
        
        # stretch add end 

        layout.addStretch (1)

        self._viewPanel = Container_Panel()
        self._viewPanel.setMinimumWidth(180)
        self._viewPanel.setMaximumWidth(250)
        self._viewPanel.setLayout (layout)
 

    @property
    def section_panel (self) -> Edit_Panel:
        """ return section panel within view panel"""

        if self._section_panel is None:
        
            p = Panel_Airfoils (self, getter=self.all_airfoils, height=(80,None))
            
            p.sig_airfoil_ref_changed.connect (self.sig_airfoil_ref_changed.emit)
            p.sig_airfoils_to_show_changed.connect (self._on_show_airfoil_changed)

            self._section_panel = p 

        return self._section_panel 


    @property
    def polar_panel (self) -> Edit_Panel:
        """ return polar extra panel to admin polar definitions and define polar diagrams"""

        if self._polar_panel is None:
        
            l = QGridLayout()
            r,c = 0, 0

            Label (l,r,c, colSpan=4, get="Polar definitions", style=style.COMMENT) 
            r += 1

            # helper panel for polar definitions 

            p = Panel_Polar_Defs (self, self.polar_defs, height=(None,None),)

            p.sig_polar_def_changed.connect (self.sig_polar_def_changed.emit)

            l.addWidget (p, r, c, 1, 6)
            l.setRowStretch (r,1)

            # polar diagrams variables setting 

            r += 1
            if Worker.ready:
                SpaceR (l,r, height=5, stretch=0) 
                r += 1
                Label (l,r,c, colSpan=4, get="Diagram variables", style=style.COMMENT) 
                r += 1
                for item in self._get_item (Diagram_Item_Polars):

                    Label       (l,r,c,   width=20, get="y")
                    ComboBox    (l,r,c+1, width=60, obj=item, prop=Diagram_Item_Polars.yVar, options=var.list)
                    SpaceC      (l,c+2,   width=15, stretch=0)
                    Label       (l,r,c+3, width=20, get="x")
                    ComboBox    (l,r,c+4, width=60, obj=item, prop=Diagram_Item_Polars.xVar, options=var.list)
                    SpaceC      (l,c+5)
                    r += 1

                SpaceR (l,r, height=10, stretch=1)
                r += 1
                Label  (l,r,c, colSpan=6, get="Powered by Worker using Xfoil", style=style.COMMENT)

            else: 
                SpaceR (l,r, height=10) 
                r += 1
                Label (l,r,c, colSpan=4, get="No polars available", style=style.ERROR, fontSize=size.HEADER_SMALL) 
                r += 1
                Label (l,r,c, colSpan=4, get="Worker not ready", style=style.ERROR) 
                r += 1
                SpaceR (l,r, height=5, stretch=0) 
                r += 1
                lab = Label (l,r,c, colSpan=6, get=Worker.ready_msg, style=style.COMMENT, height=(None,100)) 
                lab.setWordWrap(True)
                r += 1
                SpaceR (l,r, height=10, stretch=3) 

            self._polar_panel = Edit_Panel (title="View Polars", layout=l, height=(150,None),
                                              switchable=True, switched_on=True, on_switched=self._on_polars_switched)
        return self._polar_panel 


    # --- public slots ---------------------------------------------------


    def on_airfoil_changed (self):
        """ slot to handle airfoil changed signal """

        logger.debug (f"{str(self)} on airfoil changed")
        self.refresh()


    def on_bezier_changed (self, aSide_type: Line.Type):
        """ slot to handle bezier changes (dureing match bezier"""

        # high speed - make direct call to artist
        item : Diagram_Item_Airfoil = self._get_item (Diagram_Item_Airfoil)
        item.bezier_artist.refresh_from_side (aSide_type)


    def on_blend_airfoil (self):
        """ slot to handle blend airfoil entered signal -> show org airfoil"""

        item : Diagram_Item_Airfoil = self._get_item (Diagram_Item_Airfoil)
        item._on_blend_airfoil ()

        self.refresh()                          # plot ref airfoils 
        logger.debug (f"{str(self)} on_blend_airfoil")


    def on_target_changed (self):
        """ slot to handle airfoil target changed signal """

        logger.debug (f"{str(self)} on airfoil target changed")
        self.refresh(also_viewRange=False)


    def on_enter_panelling (self):
        """ slot user started panelling dialog - show panels """

        item : Diagram_Item_Airfoil = self._get_item (Diagram_Item_Airfoil)
        item._on_enter_panelling ()


    def on_polar_set_changed (self):
        """ slot to handle changed polar set signal """

        logger.debug (f"{str(self)} on polar set changed")
        self.refresh(also_viewRange=False)


    def on_airfoils_ref_changed (self):
        """ slot to handle new list of reference airfoils"""

        logger.debug (f"{str(self)} on airfoils ref changed")
        self.refresh(also_viewRange=False)

        # for item in self.diagram_items:
        #     if item.isVisible(): 
        #         item.refresh()


    # --- private slots ---------------------------------------------------


    def _on_geometry_changed (self):
        """ slot to handle geometry change made in diagram """

        logger.debug (f"{str(self)} on geometry changed in diagram")
    
        self.refresh()                          # refresh other diagram items 
        self.sig_airfoil_changed.emit()         # refresh app



    def _on_polars_switched (self, aBool):
        """ slot to handle polars switched on/off """

        logger.debug (f"{str(self)} on polars switched")
    
        for item in self._get_item (Diagram_Item_Polars):
            item.setVisible (aBool)


    def _on_airfoils_ref_switched (self, aBool):
        """ slot to handle airfoil reference switched on/off """

        logger.debug (f"{str(self)} on airfoils switched")
    
        for item in self.diagram_items:
            if item.isVisible(): 
                item.refresh()

    def _on_show_airfoil_changed (self):
        """ slot to handle show airfoil switched on/off """

        logger.debug (f"{str(self)} on show airfoil switched")
    
        for item in self.diagram_items:
            if item.isVisible(): 
                item.refresh()



class Diagram_Airfoil (Diagram):
    """    
    Diagram view to show/plot airfoil diagrams - Container for diagram items 
    """


    sig_airfoil_changed         = pyqtSignal()          # airfoil data changed in a diagram 
    sig_new_airfoil_ref1        = pyqtSignal(object)    # new ref1 airfoil  
    sig_new_airfoil_ref2        = pyqtSignal(object)    # new ref2 airfoil  


    def __init__(self, *args, **kwargs):

        self._item_airfoil = None                   # the diagram items of self 
        self._item_curvature = None
        self._item_welcome = None

        self._bezier_match_first_time = True        # switch to show target airfoil 

        super().__init__(*args, **kwargs)

        self._viewPanel.setMinimumWidth(240)
        self._viewPanel.setMaximumWidth(240)
 
         # set spacing between the two items
        self.graph_layout.setVerticalSpacing (10)


    @property
    def airfoil_ref1 (self) -> Airfoil | None:
        """ ref1 airfoil"""
        for airfoil in self.airfoils():
            if airfoil.usedAs == usedAs.REF: return airfoil
        
    def set_airfoil_ref1 (self, airfoil: Airfoil | None = None): 
        self.sig_new_airfoil_ref1.emit (airfoil)
        self.refresh ()

    @property
    def airfoil_ref2 (self) -> Airfoil | None:
        """ ref2 airfoil"""
        for airfoil in self.airfoils():
            if airfoil.usedAs == usedAs.REF: return airfoil

    def set_airfoil_ref2 (self, airfoil: Airfoil | None = None): 
        self.sig_new_airfoil_ref2.emit (airfoil)
        self.refresh ()


    @property
    def airfoil_target (self) -> Airfoil | None:
        """ target airfoil"""
        for airfoil in self.airfoils():
            if airfoil.usedAs == usedAs.TARGET: return airfoil


    @property
    def airfoil_org (self) -> Airfoil | None:
        """ original airfoil only if there is a design airfoil"""
        for airfoil in self.airfoils():
            if airfoil.usedAs == usedAs.DESIGN:
                for airfoil in self.airfoils():                
                    if airfoil.usedAs == usedAs.NORMAL: 
                        return airfoil
                return


    @property
    def show_airfoils_ref (self) -> bool: 
        """ is switch show_reference_airfoils on """
        if self._section_panel is not None: 
            return self.section_panel.switched_on
        else: 
            return False
        
    def set_show_airfoils_ref (self, aBool : bool): 
        self.section_panel.set_switched_on (aBool, silent=True)
        self.section_panel.refresh ()
   

    def airfoils (self) -> list[Airfoil]: 
        """ the airfoil(s) currently to show as list"""
        if not self.show_airfoils_ref:
            airfoils = [self.data_list()[0]]
        else: 
            airfoils = self.data_list()
        return airfoils


    def create_diagram_items (self):
        """ create all plot Items and add them to the layout """

        r = 0 
        if self.airfoils()[0].isExample:

            # show Welcome text if Airfoil is the Example arfoil 
            self._item_welcome = Diagram_Item_Welcome (self)
            self._add_item (self._item_welcome, r, 0)
            r += 1

        self._item_airfoil = Diagram_Item_Airfoil (self, getter=self.airfoils)
        self._add_item (self._item_airfoil, r, 0)
 
        self._item_airfoil.sig_geometry_changed.connect (self._on_geometry_changed)

        r += 1
        self._item_curvature = Diagram_Item_Curvature (self, getter=self.airfoils, show=False)
        self._add_item (self._item_curvature, r, 0)
 

    @property
    def section_panel (self) -> Edit_Panel:
        """ return section panel within view panel"""

        if self._section_panel is None:
        
            l = QGridLayout()
            r,c = 0, 0
            Field (l,r,c, width=175, get=lambda: self.airfoil_org.fileName if self.airfoil_org else '', 
                            disable=True,
                            hide=lambda: (self.airfoil_org is None) or (self.airfoil_org == self.airfoil_target),
                            toolTip="Original airfoil")
            r += 1
            Field (l,r,c, width=175, get=lambda: self.airfoil_target.fileName if self.airfoil_target else '', 
                            disable=True,
                            hide=lambda: self.airfoil_target is None,
                            toolTip="Target airfoil")
            r += 1
            Airfoil_Select_Open_Widget (l,r,c, widthOpen=60,
                            get=lambda: self.airfoil_ref1, set=self.set_airfoil_ref1,
                            initialDir=self.airfoils()[0], addEmpty=True,
                            toolTip="Reference 1 airfoil")
            r += 1
            Airfoil_Select_Open_Widget (l,r,c, widthOpen=60,
                            get=lambda: self.airfoil_ref2, set=self.set_airfoil_ref2,
                            initialDir=self.airfoils()[0], addEmpty=True,
                            hide=lambda: not self.airfoil_ref1 and not self.airfoil_ref2,
                            toolTip="Reference 2 airfoil")
            r += 1
            SpaceR (l,r)
            l.setColumnStretch (0,2)

            self._section_panel = Edit_Panel (title="Reference Airfoils", layout=l, height=(80,None),
                                              switchable=True, switched_on=False, on_switched=self.refresh)

        return self._section_panel 


    # --- public slots ---------------------------------------------------


    def on_airfoil_changed (self):
        """ slot to handle airfoil changed signal """

        logger.debug (f"{str(self)} on airfoil changed")
        self.refresh()


    def on_bezier_mode (self, is_enter):
        """ slot to handle bezier mode entered signal -> show ref airfoil"""

        # ensure to show target airfoil in bezier 
        if is_enter:
            self.set_show_airfoils_ref (True)
            self.refresh()                          # plot ref airfoils 
            logger.debug (f"{str(self)} on_bezier_mode {is_enter}")


    def on_bezier_changed (self, aSide_type: Line.Type):
        """ slot to handle bezier changes (dureing match bezier"""

        # high speed - make direct call to artist
        self._item_airfoil.bezier_artist.refresh_from_side (aSide_type)


    def on_blend_airfoil (self):
        """ slot to handle blend airfoil entered signal -> show org airfoil"""

        self.set_show_airfoils_ref (True)

        self._item_airfoil._on_blend_airfoil ()


        self.refresh()                          # plot ref airfoils 
        logger.debug (f"{str(self)} on_blend_airfoil")


    def on_edit_mode (self):
        """ slot to handle edit mode entered signal"""

        self.section_panel.refresh()                        # to show additional airfoils in edit 
        logger.debug (f"{str(self)} on_edit_mode")


    def on_target_changed (self, refresh=True):
        """ slot to handle airfoil target changed signal """

        logger.debug (f"{str(self)} on airfoil target changed")

        # is there a target airfoil (match Bezier)? switch ref panel on
        if self.airfoil_target:
            self.set_show_airfoils_ref (True)
        
        if refresh: 
            self.refresh()
        elif self.section_panel is not None:                    # refresh just section panel
            self.section_panel.refresh()

    def on_enter_panelling (self):
        """ slot user started panelling dialog - show panels """

        self._item_airfoil._on_enter_panelling ()



    # --- private slots ---------------------------------------------------

    @override
    def refresh (self, *_):

        if self._item_welcome and self._item_welcome.isVisible():

            self._item_welcome.hide()

        super().refresh() 


    def _on_geometry_changed (self):
        """ slot to handle geometry change made in diagram """

        logger.debug (f"{str(self)} on geometry changed in diagram")
    
        self.refresh()                          # refresh other diagram items 
        self.sig_airfoil_changed.emit()         # refresh app

