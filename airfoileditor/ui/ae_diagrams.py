#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

Diagram (items) for airfoil

"""

from copy                   import deepcopy 

from ..base.widgets         import * 
from ..base.diagram         import * 
from ..base.panels          import Edit_Panel, Toaster

from ..model.airfoil        import Airfoil
from ..model.polar_set      import *
from ..model.case           import Case_Abstract, Case_Optimize
from ..model.xo2_driver     import Worker, Xoptfoil2
from ..model.xo2_results    import OpPoint_Result, GeoTarget_Result

from .ae_artists            import *
from .ae_widgets            import Airfoil_Select_Open_Widget
from .xo2_artists           import *
from .util_dialogs          import Polar_Definition_Dialog, Airfoil_Scale_Dialog

from ..app_model            import App_Model


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


#-------------------------------------------------------------------------------
# Helper Panels   
#-------------------------------------------------------------------------------


class Panel_Airfoils (Edit_Panel):
    """ 
    Panel to show active airfoils 
    - add, delete, edit reference airfoils
    
    """

    name = "Airfoils"   

    sig_airfoils_to_show_changed    = pyqtSignal()              # changed show filter 
    sig_airfoils_scale_changed      = pyqtSignal()              # airfoil scale changed

    _main_margins  = (10, 5, 0, 5)                              # margins of Edit_Panel

    def __init__(self, *args, **kwargs):

        self._show_reference_airfoils = None                    # will be set in init_layout
        self._airfoils_ref_are_scaled = False                   # ref airfoils are scaled

        super().__init__(*args, **kwargs)


    # ---------------------------------------------

    @property
    def app_model (self) -> App_Model:
        """ the app model"""
        return self.dataObject
    
    @property
    def airfoils (self) -> list[Airfoil]: 
        return self.app_model.airfoils

    @property
    def airfoil_designs (self) -> list [Airfoil]:
        """ airfoil designs of case modify or optimize """
        if self.app_model.case is not None:
            return self.app_model.case.airfoil_designs

    @property
    def airfoils_ref (self) -> list[Airfoil]: 
        """ reference airfoils only"""
        return [a for a in self.airfoils if a.usedAs == usedAs.REF]

    @property
    def airfoil_design (self) -> Airfoil:
        """ the current design airfoil if available"""
        return self.app_model.airfoil_design


    @property 
    def show_reference_airfoils (self) -> bool: 
        return self._show_reference_airfoils
    
    def set_show_reference_airfoils (self, show : bool): 

        self._show_reference_airfoils = show 
        if not show:
            for iair, airfoil in enumerate (self.airfoils):
                if airfoil.usedAs == usedAs.REF:
                    self.set_show_airfoil (show, iair)

        self.refresh()

    def reset_show_reference_airfoils (self):
        """ set show switch to initial state""" 
        # will be set in init_layout
        self._show_reference_airfoils = None

        
    @property 
    def show_design_airfoils (self) -> bool: 
        return self.app_model.show_airfoil_design
      

    def _n_REF (self) -> int:
        """ number of reference airfoils"""
        n = 0 
        for airfoil in self.airfoils:
            if airfoil.usedAs == usedAs.REF: n += 1
        return n

    def _n_REF_to_show (self) -> int:
        """ number of reference airfoils which should be shown"""
        n = 0 
        for airfoil in self.airfoils:
            if airfoil.usedAs == usedAs.REF and airfoil.get_property ("show", True): n += 1
        return n


    def _DESIGN_in_list (self) -> bool:
        """ true if NORMAL airfoil can be switched on/off"""
        for airfoil in self.airfoils:
            if airfoil.usedAs == usedAs.DESIGN: 
                return False
        return True

    @property
    def airfoils_ref_are_scaled (self) -> bool:
        """ True if ref airfoils will be or are scaled """
        return self._airfoils_ref_are_scaled or any (airfoil.isScaled for airfoil in self.airfoils_ref)
    

    def set_airfoils_ref_are_scaled (self, aBool):

        if not aBool:
            if any (airfoil.isScaled for airfoil in self.airfoils_ref):
                for airfoil in self.airfoils_ref:
                    airfoil.set_scale_factor (1.0)                           # reset scale to 1.0
                self.sig_airfoils_scale_changed.emit()
            self._airfoils_ref_are_scaled = False
        else:
            self._airfoils_ref_are_scaled = True

        self.refresh()


    @override
    def _init_layout (self): 

        # switch on reference airfoils if there is one 
        if self._show_reference_airfoils is None: 
            self._show_reference_airfoils = self._n_REF_to_show() > 0
        # ensure consistency of show state  
        elif not self._show_reference_airfoils :
            for iair, air in enumerate (self.airfoils):
                if air.usedAs == usedAs.REF:
                    self.airfoils[iair].set_property ("show", False)

        l = QGridLayout()
        r,c = 0, 0 

        for iair, air in enumerate (self.airfoils):

            #https://docs.python.org/3.4/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result

            if air.usedAs == usedAs.NORMAL :
                CheckBox    (l,r,c  , width=18, get=self.show_airfoil, set=self.set_show_airfoil, id=iair,
                             disable=lambda: self._DESIGN_in_list(), toolTip="Show/Hide airfoil in diagram")
                Field       (l,r,c+1, colSpan=2, width=155, get=lambda i=iair:self.airfoil(i).fileName, 
                             toolTip=air.info_as_html)
                r += 1

            elif air.usedAs == usedAs.DESIGN:                
                CheckBox    (l,r,c  , width=18, get=lambda: self.show_design_airfoils, set=self.set_show_design_airfoils,
                             toolTip="Show/Hide Design airfoils in diagram")
                if self.airfoil_designs:
                    ComboBox    (l,r,c+1, colSpan=2, width=155, get=lambda: self.airfoil_design.fileName if self.airfoil_design else None,
                                 set=self._on_airfoil_design_selected,
                                 options= lambda: [airfoil.fileName for airfoil in self.airfoil_designs],  
                                 toolTip=f"Select a Design out of list of airfoil designs")
                else: 
                    Field       (l,r,c+1, colSpan=2, width=155, get=lambda i=iair:self.airfoil(i).fileName, 
                                 toolTip=air.info_as_html)
                r += 1

            elif air.usedAs in [usedAs.SECOND, usedAs.SEED, usedAs.FINAL, usedAs.DESIGN]:
                CheckBox    (l,r,c  , width=20, get=self.show_airfoil, set=self.set_show_airfoil, id=iair,
                             toolTip="Show/Hide airfoil in diagram")
                Field       (l,r,c+1, colSpan=2, width=155, get=lambda i=iair:self.airfoil(i).fileName, 
                             style=lambda i=iair: style.GOOD if self.airfoil(i).usedAs == usedAs.FINAL else style.NORMAL,
                             toolTip=air.info_as_html)
                r += 1

        CheckBox (l,r,c, colSpan=3, text="Reference airfoils", 
                  get=lambda: self.show_reference_airfoils,
                  set=self.set_show_reference_airfoils,
                  toolTip="Activate additional reference airfoils to show in diagram") 

        CheckBox (l,r,c+2, colSpan=2, text="Scaled", align=ALIGN_RIGHT, 
                  get=self.airfoils_ref_are_scaled, set=self.set_airfoils_ref_are_scaled,
                  hide=lambda: not self.show_reference_airfoils,
                  toolTip="Scale reference airfoils and their polars relative to the main airfoil") 
        
        if self.show_reference_airfoils:

            r += 1
            for iair, air in enumerate (self.airfoils):

                if air.usedAs == usedAs.REF:
                    CheckBox   (l,r,c  , width=18, get=self.show_airfoil, set=self.set_show_airfoil, id=iair,
                                toolTip="Show/Hide airfoil in diagram")
                    Button     (l,r,c+1, text=lambda a=air: f"{a.scale_factor:.0%}", width=40, 
                                set=self.edit_airfoil_scale_value, id=iair,
                                hide=lambda: not self.airfoils_ref_are_scaled,
                                toolTip="Change this scale value")

                    Airfoil_Select_Open_Widget (l,r,c+2, 
                                    get=self.airfoil, set=self.set_airfoil, id=iair,
                                    initialDir=self.airfoils[-1], addEmpty=False,       # initial dir not from DESIGN
                                    toolTip=air.info_as_html)

                    ToolButton (l,r,c+3, icon=Icon.DELETE, set=self.delete_airfoil, id=iair,
                                toolTip="Remove this airfoil as reference")
                    r += 1

            # add new reference as long as < max REF airfoils 
            if self._n_REF() < 3:
                Airfoil_Select_Open_Widget (l,r,c+2, 
                                get=None, set=self.set_airfoil, id=iair+1,
                                initialDir=self.airfoils[-1], addEmpty=True,
                                toolTip=f"New reference airfoil")
                r +=1
            # SpaceR (l,r,stretch=0)

        l.setColumnMinimumWidth (0,18)
        l.setColumnMinimumWidth (2,ToolButton._width)
        l.setColumnStretch (2,5)
        l.setColumnStretch (3,1)

        return l 


    # -- methods based on index in init_layout 

    def airfoil (self, id : int):
        """ get airfoil with index id from list"""
        return self.airfoils[id]

    def set_airfoil (self, new_airfoil : Airfoil|None = None, id : int = None):
        """ set airfoil with index id from list"""

        if new_airfoil is None: return

        cur_airfoil = self.airfoils[id] if id < len(self.airfoils) else None    # None will add new airfoil

        self.app_model.set_airfoil_ref  (cur_airfoil, new_airfoil)


    def show_airfoil (self, id : int) -> bool:
        """ is ref airfoil with id active"""
        return self.airfoils[id].get_property ("show", True)


    def set_show_airfoil (self, aBool, id : int):
        """ set ref airfoil with index id active"""
        self.airfoils[id].set_property ("show", aBool)
        self.sig_airfoils_to_show_changed.emit()


    def set_show_design_airfoils (self, show : bool): 

        self.app_model.set_show_airfoil_design(show)

        self.sig_airfoils_to_show_changed.emit()


    def delete_airfoil (self, id : int):
        """ delete ref airfoil with index idef from list"""

        if len(self.airfoils) == 0: return 

        airfoil = self.airfoils[id]

        if airfoil.usedAs == usedAs.REF:                            # only REF airfoils can be deleted 
            self.app_model.set_airfoil_ref  (airfoil, None)


    def edit_airfoil_scale_value (self, id : int):
        """ the scale value of (ref) airfoil"""

        airfoil = self.airfoils[id]

        diag = Airfoil_Scale_Dialog (self, airfoil.scale_factor, dx=400, dy=100)
        diag.exec()

        if airfoil.scale_factor != diag.scale_factor:
            airfoil.set_scale_factor (diag.scale_factor)
            self.sig_airfoils_scale_changed.emit()


    def _on_airfoil_design_selected (self, fileName):
        """ callback of combobox when an airfoil design was selected"""

        for airfoil in self.airfoil_designs:
            if airfoil.fileName == fileName:
                self.app_model.set_airfoil (airfoil)
                break


    @override
    def refresh (self, reinit_layout=False):
        """ refreshes all Widgets on self """

        # rebuild layout with new airfoil entries 
        logger.debug (f"{self} refresh with reinit layout: {reinit_layout}")

        self._set_panel_layout()



class Panel_Polar_Defs (Edit_Panel):
    """ Panel to add, delete, edit polar definitions """

    name = None                                                 # suppress header

    sig_polar_def_changed = pyqtSignal()                        # polar definition changed 


    def __init__(self, *args,
                 chord_fn = None,                               # optional callable: chord length in mm
                 **kwargs):

        self._chord_fn = chord_fn

        # no margins 
        super().__init__(*args, main_margins=(0,0,0,0), panel_margins=(0,0,0,0), **kwargs)

    # ---------------------------------------------

    @property
    def polar_defs (self) -> list[Polar_Definition]: 
        return self.dataObject

    @property
    def chord (self) -> float|None:
        """ Returns the optional chord length in mm"""
        return self._chord_fn () if callable (self._chord_fn) else None


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 

        for idef, polar_def in enumerate (self.polar_defs):

            #https://docs.python.org/3.4/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result
            w = CheckBox   (l,r,c  , width=20,  get=lambda p=polar_def: p.active, set=polar_def.set_active,
                            disable=lambda: len(self.polar_defs) == 1, 
                            toolTip="Show/Hide this polar in diagram")  
            w.sig_changed.connect (self._on_polar_def_changed)

            Field      (l,r,c+1, width=(80,None), get=lambda p=polar_def: p.name_with_v(self.chord))

            # either tool buttons 
            if not polar_def.is_mandatory: 
                ToolButton (l,r,c+2, icon=Icon.EDIT,   set=self.edit_polar_def,   id=idef,
                                toolTip="Change the settings of this polar definition")                              
                ToolButton (l,r,c+3, icon=Icon.DELETE, set=self.delete_polar_def, id=idef,
                                toolTip="Delete this polar definition",  
                                hide=lambda p=polar_def: (len(self.polar_defs) <= 1))           # no delete 
             # .. or info label 
            else:
                Label       (l,r,c+2, get=" Case", colSpan=3, style=style.COMMENT )

            r += 1

        if len (self.polar_defs) < Polar_Definition.MAX_POLAR_DEFS: #  and (not self.mode_optimize):
            ToolButton (l,r,c+1, icon=Icon.ADD,  
                            toolTip="Add a new polar definition",  
                            set=self.add_polar_def)

        l.setColumnStretch (c+1,2)
        l.setColumnMinimumWidth (c+2,20)

        return l 


    def edit_polar_def (self, id : int = None, polar_def : Polar_Definition = None):
        """ edit polar definition with index idef"""

        if isinstance (id, int):
            polar_def = self.polar_defs[id]

        diag = Polar_Definition_Dialog (self, polar_def, 
                                        parentPos=(1.1, 0.5), dialogPos=(0,0.5), fixed_chord=self.chord)
        diag.exec()

        # sort polar definitions ascending re number 
        self.polar_defs.sort (key=lambda aDef : aDef.re)

        self._on_polar_def_changed ()


    def delete_polar_def (self, id : int):
        """ delete polar definition with index idef"""

        # at least one polar def needed
        if len(self.polar_defs) <= 1: return 

        del self.polar_defs[id]

        self._on_polar_def_changed ()


    def add_polar_def (self):
        """ add a new polar definition"""

        # increase re number for the new polar definition
        if self.polar_defs:
            new_polar_def  = deepcopy (self.polar_defs[-1])
            new_polar_def.set_is_mandatory (False)                  # parent could have been mandatory
            new_polar_def.set_re (new_polar_def.re + 100000)
            new_polar_def.set_active(True)
        else: 
            new_polar_def = Polar_Definition()

        self.polar_defs.append (new_polar_def)

        # open edit dialog for new def 

        self.edit_polar_def (polar_def=new_polar_def)


    def _on_polar_def_changed (self):
        """ handle changed polar def - inform parent"""

        # ensure if only 1 polardef, this has to be active 
        if len(self.polar_defs) == 1 and not self.polar_defs[0].active:
            self.polar_defs[0].set_active(True)

        # ensure local refresh - as global will only watch for active polars 
        self.refresh()

        # signal parent - which has to refresh self to apply changed items 
        self.sig_polar_def_changed.emit()


    @override
    def refresh(self, reinit_layout=False):
        """ refreshes all Widgets on self """

        super().refresh(reinit_layout=True)                 # always reinit layout to reflect changed polar defs



class Panel_Airfoil_Settings (Edit_Panel):
    """ 
    Little helper panel to load, save settings of current airfoil
    """

    name = "Airfoil Settings"   

    sig_load_settings        = pyqtSignal()                 # settings of airfoil should be loaded
    sig_save_settings        = pyqtSignal()                 # settings of airfoil should be saved

    @property
    def app_model (self) -> App_Model:
        """ the app model"""
        return self.dataObject

    @property
    def airfoil (self) -> Airfoil:
        """ the current airfoil in diagram"""
        return self.app_model.airfoil

    @property
    def settings_exist (self) -> bool:
        """ individual settings file exists for current airfoil"""
        return self.app_model.airfoil_settings_exist

    @property
    def settings_loaded (self) -> bool:
        """ individual settings file is loaded for current airfoil"""
        return self.app_model.airfoil_settings_loaded
          

    def _init_layout(self):

        l = QGridLayout()
        r,c = 0, 0
        ToolButton (l,r,c, icon=Icon.OPEN, width=(22,None),
                text=lambda: f"Load Settings of {self.airfoil.fileName_stem}", 
                set=self._load_settings,
                hide=lambda: not self.settings_exist or self.settings_loaded,
                style=style.HINT,
                toolTip=lambda: f"Load the individual settings of {self.airfoil.fileName}")
        ToolButton (l,r,c, icon=Icon.SAVE, width=(22,None),
                text=lambda: f"Save as individual Settings", 
                set=self._save_settings,
                hide=lambda: self.settings_exist,
                toolTip=lambda: f"Save these settings being individual for {self.airfoil.fileName} to be reloaded later")
        Label (l,r,c, get=lambda: f"Settings of {self.airfoil.fileName_stem}", 
               hide=lambda: not self.settings_loaded)  
        c += 1
        l.setColumnStretch (c,1)
        c += 1
        ToolButton (l,r,c, icon=Icon.SAVE, 
                set=self._save_settings,
                hide=lambda: not self.settings_loaded,
                toolTip=lambda: f"Overwrite current settings of {self.airfoil.fileName} with these settings")
        c += 1
        ToolButton (l,r,c, icon=Icon.DELETE,
                set=self._settings_delete,
                hide=lambda: not self.settings_exist,
                toolTip=lambda: f"Delete the individual settings of {self.airfoil.fileName}")
        return l


    def _toast_message (self, msg: str, toast_style : style = style.GOOD, duration: int = 400, alpha: int = 255):
        """ toast message for action on settings"""
        Toaster.showMessage (self, msg, 
                             margin=QMargins(20,10,10,5), contentsMargins=QMargins(15,3,15,3), 
                             toast_style=toast_style, duration=duration, alpha=alpha)


    def _load_settings (self):
        """ slot load settings of current airfoil"""

        if self.settings_exist:

            self.sig_load_settings.emit()

            msg = f"Settings loaded for {self.airfoil.fileName}" 
            QTimer.singleShot (200, lambda: self._toast_message (msg, toast_style=style.GOOD, duration=1500))


    def _save_settings (self):
        """ slot save settings of current airfoil"""

        self.sig_save_settings.emit()

        self.refresh()                                              # reflect changed settings exist 

        msg = f"Settings saved for {self.airfoil.fileName}"
        self._toast_message (msg, toast_style=style.GOOD, duration=1000)    


    def _settings_delete (self):
        """ slot delete settings of current airfoil"""

        self.app_model.delete_airfoil_settings ()

        msg = f"Settings of {self.airfoil.fileName} deleted"
        self._toast_message (msg, toast_style=style.WARNING, duration=1000)


#-------------------------------------------------------------------------------
# Diagram Items  
#-------------------------------------------------------------------------------

class Item_Airfoil (Diagram_Item):
    """ 
    Diagram (Plot) Item for airfoils shape 
    """

    name = "View Airfoil"                               # used for link and section header 

    sig_geometry_changed         = pyqtSignal()         # airfoil data changed in a diagram 

    def __init__(self, *args, **kwargs):

        self._stretch_y         = False                 # show y stretched 
        self._stretch_y_factor  = 3                     # factor to stretch 
        self._geo_info_item     = None                  # item to show geometry info on plot

        self.bezier_artist      : Bezier_Artist = None                 
        self.flap_artist        : Flap_Artist = None
        self.line_artist        : Airfoil_Line_Artist = None
        self.airfoil_artist     : Airfoil_Artist = None
        self.le_artist          : LE_Radius_Artist = None
        self.te_artist          : TE_Gap_Artist = None

        super().__init__(*args, **kwargs)

        # connect signals of app model

        self.app_model.sig_airfoil_geo_changed.connect      (self.refresh_artists)
        self.app_model.sig_airfoil_geo_te_gap.connect       (self.te_artist.set_xBlend)
        self.app_model.sig_airfoil_geo_le_radius.connect    (self.le_artist.set_xBlend)
        self.app_model.sig_airfoil_geo_paneling.connect     (self._on_paneling_changed)
        self.app_model.sig_airfoil_flap_set.connect         (self.flap_artist.set_show)
        self.app_model.sig_airfoil_bezier.connect           (self.bezier_artist.refresh_from_side)

        self.app_model.sig_xo2_new_design.connect           (self.refresh_artists)


    @property
    def app_model (self) -> App_Model:
        """ the app model"""
        return self._dataObject

    @property
    def airfoils (self) -> list[Airfoil]: 
        return self.app_model.airfoils_to_show
    
    @property 
    def case (self) -> Case_Abstract:
        """ actual case (Direct Design or Optimize)"""
        return self.app_model.case


    @property
    def design_airfoil (self) -> Airfoil:
        """ design airfoil if it is available"""
        for airfoil in self.airfoils:
            if airfoil.usedAsDesign: return airfoil

    @property
    def iDesign (self) -> Airfoil:
        """ iDesign of the Design airfoil - or None if there is no design"""
        return Case_Abstract.get_iDesign (self.design_airfoil)
            

    def _is_one_airfoil_bezier (self) -> bool: 
        """ is one of airfoils Bezier based? """
        for a in self.airfoils:
            if a.isBezierBased: return True
        return False 


    def _is_one_airfoil_hicks_henne (self) -> bool: 
        """ is one of airfoils Hicks Henne based? """

        for a in self.airfoils:
            if a.isHicksHenneBased: return True
        return False 


    def _is_design_and_bezier (self) -> bool: 
        """ is one airfoil used as design ?"""

        for a in self.airfoils:
            if a.usedAsDesign and a.isBezierBased:
                return True 
        return False


    def _on_enter_panelling (self):
        """ slot user started panelling dialog - show panels """

        # switch on show panels , switch off thickness, camber 
        self.airfoil_artist.set_show_points (True)
        self.line_artist.set_show (False)
        self.section_panel.refresh() 

        logger.debug (f"{str(self)} _on_enter_panelling")


    def _on_paneling_changed (self, is_paneling : bool):
        """ slot to handle paneling of airfoil changed signal """

        # switch off Line artist
        for artist in self._get_artist (Airfoil_Line_Artist):
            if artist.show: artist.set_show (False)

        # switch on show points
        artist : Airfoil_Artist
        for artist in self._get_artist (Airfoil_Artist):
            artist.set_show_points (is_paneling)


    @property 
    def design_opPoints (self) -> OpPoint_Result:
        """ opPoint result belonging to current design airfoil"""

        if self.iDesign is None: return 

        case : Case_Optimize = self.case
        designs_opPoints = case.results.designs_opPoints if isinstance (case, Case_Optimize) else []

        # get opPoints of Design iDesign - during optimize it could not yet be available...

        try: 
            return designs_opPoints[self.iDesign]
        except:
            pass


    @property 
    def design_geoTargets (self) -> list[GeoTarget_Result]:
        """ geoTarget result belonging to current design airfoil"""

        if self.iDesign is None: return 

        case : Case_Optimize = self.case
        geoTargets = case.results.designs_geoTargets if isinstance (case, Case_Optimize) else []

        # get opPoints of Design iDesign - during optimize it could not yet be available...

        try: 
            return geoTargets[self.iDesign]
        except:
            pass

    @property
    def geoTarget_defs (self) -> list:
        """ Xo2 geo target definitions"""

        if isinstance (self.case, Case_Optimize):
            return self.case.input_file.nml_geometry_targets.geoTarget_defs
        else:
            return [] 


    @property
    def stretch_y (self) -> bool:
        """ show y axis stretched"""
        return self._stretch_y
    
    def set_stretch_y (self, aBool : bool):
        self._stretch_y = aBool
        self.section_panel.refresh()                    # show / hide stretch factor field
        self.setup_viewRange ()

    @property
    def stretch_y_factor (self) -> int:
        """ y axis stretch factor"""
        return self._stretch_y_factor
    
    def set_stretch_y_factor (self, aVal : int):
        self._stretch_y_factor = clip (aVal, 1, 50)
        self.setup_viewRange ()


    @override
    def resizeEvent(self, ev):
        """ handle resize event of self - ensure geometry info item is removed"""

        # will remove geo info if not enough height - or show it again if enough height        
        self._plot_geo_info (refresh_airfoil=False)             

        super().resizeEvent (ev)


    def _geo_info_as_html (self, airfoil : Airfoil) -> str:
        """
        geometry info of airfoil as html string - colored for xo2 geometry targets
        """

        thickness_color = None
        camber_color    = None

        if airfoil.usedAsDesign and self.design_geoTargets:

            for geoTarget in self.design_geoTargets:
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
                result_color = result_color.name(QColor.NameFormat.HexArgb) if isinstance (result_color, QColor) else result_color
                if geoTarget.optVar == "Thickness":
                    thickness_color = result_color
                elif geoTarget.optVar == "Camber":
                    camber_color = result_color
                    
        return airfoil.info_short_as_html (thickness_color=thickness_color, camber_color=camber_color)


    def _plot_geo_info (self, refresh_airfoil = False):
        """ plot geometry info of airfoil on self"""

        airfoil = self.airfoils[0] if self.airfoils else None

        # check enough height in diagram item to show info
        enough_height = self.viewBox.boundingRect().height() >= 300

        if not enough_height or airfoil is None:
            if self._geo_info_item is not None:
                self.scene().removeItem (self._geo_info_item)               #
            self._geo_info_item = None                              
            return

        # show again after resize or refresh with new airfoil 

        show_again = enough_height and self._geo_info_item is None

        if refresh_airfoil and self._geo_info_item is not None:
            self.scene().removeItem (self._geo_info_item)

        if refresh_airfoil or show_again:

            p = pg.LabelItem(self._geo_info_as_html (airfoil), color=QColor(Artist.COLOR_LEGEND), size=f"{Artist.SIZE_NORMAL}pt")    
            p.setParentItem(self)                                   # add to self (Diagram Item) for absolute position 
            p.anchor(itemPos=(0,1), parentPos=(0.0,0.95), offset=(50,-30))
            p.setZValue(5)
            self._geo_info_item = p 


    @override
    def plot_title(self, **kwargs):
        """ plot title of self - if airfoils are available"""

        if not self.airfoils: return 

        # the first airfoil get's in the title 

        airfoil = self.airfoils[0] if self.airfoils else None

        mods = ', '.join(airfoil.geo.modifications_as_list) if airfoil.usedAsDesign else None
            
        if mods:
            subtitle = "Mods: " + mods
        elif airfoil.isBezierBased:
            subtitle = 'Based on 2 Bezier curves'
        else: 
            # show name if it differs from name to show 
            subtitle = airfoil.name if airfoil.name != airfoil.name_to_show else ''

        super().plot_title (title=airfoil.name_to_show, subtitle=subtitle, **kwargs)

         # plot geometry info of airfoil on self

        self._plot_geo_info (refresh_airfoil=True)                      


    @override
    def setup_artists (self):
        """ create and setup the artists of self"""
        
        a = Airfoil_Artist   (self, lambda: self.airfoils, show_legend=True)
        self.airfoil_artist = a
        self._add_artist (a)

        a = Airfoil_Line_Artist (self, lambda: self.airfoils, show=False, show_legend=True)
        a.sig_geometry_changed.connect (self.app_model.notify_airfoil_changed)
        self.line_artist = a
        self._add_artist (a)

        a = Bezier_Artist (self, lambda: self.airfoils, show_legend=True)
        a.sig_bezier_changed.connect (self.app_model.notify_airfoil_changed)
        self.bezier_artist = a
        self._add_artist (a)

        a = Hicks_Henne_Artist (self, lambda: self.airfoils, show_legend=True, show=False)
        self.hicks_henne_artist = a
        self._add_artist (a)

        a = Bezier_Deviation_Artist (self, lambda: self.airfoils, show=False, show_legend=True)
        self.bezier_devi_artist = a
        self._add_artist (a)

        a  = Flap_Artist (self, lambda: self.design_airfoil, show=False, show_legend=True)
        self.flap_artist = a
        self._add_artist (a)

        a  = TE_Gap_Artist (self, lambda: self.design_airfoil, show=False, show_legend=False)
        self.te_artist = a
        self._add_artist (a)

        a  = LE_Radius_Artist (self, lambda: self.design_airfoil, show=False, show_legend=False)
        self.le_artist = a
        self._add_artist (a)

        a  = Xo2_Transition_Artist (self, lambda: self.design_airfoil, show=False, show_legend=True,
                                    opPoints_result_fn=lambda: self.design_opPoints)
        self._add_artist (a)


    @override
    def setup_viewRange (self):
        """ define view range of this plotItem"""

        self.viewBox.setDefaultPadding(0.05)

        if self.stretch_y:
            self.viewBox.setAspectLocked(ratio= (1 / self.stretch_y_factor))
        else: 
            self.viewBox.setAspectLocked(ratio= 1)

        self.viewBox.autoRange ()               # first ensure best range x,y 
        self.viewBox.setXRange( 0, 1)           # then set x-Range

        # self.viewBox.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)

        self.showGrid(x=True, y=True)


    @override
    def refresh_artists (self):

        # ensure Bezier deviation artist is switched off
        if not self._is_design_and_bezier():
            self.bezier_devi_artist.set_show(False, refresh=False)

        super().refresh_artists()


    @property
    def section_panel (self) -> Edit_Panel:
        """ return section panel within view panel"""

        if self._section_panel is None:    
            l = QGridLayout()
            r,c = 0, 0 
            CheckBox (l,r,c, text="Coordinate points", colSpan=2,
                    get=lambda: self.airfoil_artist.show_points,
                    set=self.airfoil_artist.set_show_points,
                    toolTip="Show coordinate points of airfoils") 
            r += 1
            CheckBox (l,r,c, text="Thickness && Camber", colSpan=2,
                    get=lambda: self.line_artist.show,
                    set=self.line_artist.set_show,
                    toolTip="Show thickness and camber line of airfoils")
            r += 1
            CheckBox (l,r,c, text="Bezier control points", colSpan=2,
                    get=lambda: self.bezier_artist.show,
                    set=self.bezier_artist.set_show,
                    hide=lambda : not self._is_one_airfoil_bezier(),
                    toolTip="Show control points of Bezier curves")
            r += 1
            CheckBox (l,r,c, text="Hicks Henne functions", colSpan=2,
                    get=lambda: self.hicks_henne_artist.show,
                    set=self.hicks_henne_artist.set_show,
                    hide=lambda : not self._is_one_airfoil_hicks_henne(),
                    toolTip="Show Hicks Henne functions which build the airfoil")
            r += 1
            CheckBox (l,r,c, text="Stretch y axis", 
                    get=lambda: self.stretch_y,
                    set=self.set_stretch_y,
                    toolTip="Stretch airfoil in y by a given factor")
            FieldF (l,r,c+1, lab="by factor", dec=0, step=1, lim=(1,50), width=40,
                    get=lambda: self.stretch_y_factor,
                    set=self.set_stretch_y_factor,
                    hide=lambda: not self.stretch_y) 
            r += 1
            CheckBox (l,r,c, text="Deviation of Design", colSpan=2,
                    get=lambda: self.bezier_devi_artist.show,
                    set=self.bezier_devi_artist.set_show,
                    toolTip="Show deviation of Design airfoil to the original airfoil",
                    hide=lambda : not self._is_design_and_bezier() or isinstance (self.case, Case_Optimize)) 
            r += 1
            l.setColumnMinimumWidth (1,55)
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (title=self.name, layout=l, auto_height=True,
                                              switchable=True, 
                                              switched_on=lambda: self.show,
                                              on_switched=lambda aBool: self.set_show (aBool))

        return self._section_panel 



class Item_Curvature (Diagram_Item):
    """ 
    Diagram (Plot) Item for airfoils curvature 
    """

    name        = "View Curvature"
    title       = "Curvature"                 
    subtitle    = None                                 # will be set dynamically 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # connect signals of app model

        self.app_model.sig_xo2_new_design.connect           (self.refresh_artists)


    @property
    def app_model (self) -> App_Model:
        """ the app model"""
        return self._dataObject

    @property
    def airfoils (self) -> list[Airfoil]: 
        return self.app_model.airfoils_to_show
        

    def setup_artists (self):
        """ create and setup the artists of self"""
        
        a = Curvature_Artist (self, lambda: self.airfoils, show_derivative=False, show_legend=True)
        self._add_artist (a)
        self.curvature_artist = a


    def setup_viewRange (self):
        """ define view range of this plotItem"""

        self.viewBox.setDefaultPadding(0.05)

        self.viewBox.autoRange ()               # first ensure best range x,y 
        self.viewBox.setXRange( 0, 1)           # then set x-Range
        self.viewBox.setYRange(-2.0, 2.0)

        self.showGrid(x=True, y=True)


    @property
    def section_panel (self) -> Edit_Panel:
        """ return section panel within view panel"""

        if self._section_panel is None:            
            l = QGridLayout()
            r,c = 0, 0 
            CheckBox (l,r,c, text="Upper side", 
                    get=lambda: self.curvature_artist.show_upper,
                    set=self.curvature_artist.set_show_upper,
                    toolTip="Show curvature of the upper side")
            r += 1
            CheckBox (l,r,c, text="Lower side", 
                    get=lambda: self.curvature_artist.show_lower,
                    set=self.curvature_artist.set_show_lower,
                    toolTip="Show curvature of the lower side")
            r += 1
            CheckBox (l,r,c, text="Derivative of curvature", 
                    get=lambda: self.curvature_artist.show_derivative,
                    set=self.curvature_artist.set_show_derivative,
                    disable=lambda: len(self.airfoils) != 1 and \
                                    not any (airfoil.usedAsDesign for airfoil in self.airfoils),
                    toolTip="Show the derivative of curvature which amplifies curvature artifacts.<br>"+
                            "Only active if one airfoil is displayed or Design airfoil is shown.")
            r += 1
            CheckBox (l,r,c, text=f"X axes linked to '{self._desired_xLink_name}'", 
                    get=lambda: self.xLinked, set=self.set_xLinked,
                    toolTip=f"Link the x axis of the curvature diagram to the x axis of {self._desired_xLink_name}")
            r += 1
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (title=self.name, layout=l, auto_height=True,
                                              switchable=True, 
                                              switched_on=lambda: self.show,
                                              on_switched=lambda aBool: self.set_show (aBool))

        return self._section_panel 



class Item_Welcome (Diagram_Item):
    """ Item with Welcome message  """

    title       = ""                                # has it's own title 
    subtitle    = None

    show_buttons = False                            # no buttons
    show_coords  = False                            # no coordinates

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # set margins (inset) of self 
        self.setContentsMargins ( 0,40,0,0)
        self.setFixedHeight(280)

        # add Welcome text as html label item
        p1 = pg.LabelItem(self._welcome_message(), color=QColor(Artist.COLOR_HEADER), size=f"{Artist.SIZE_HEADER}pt")    
        p1.setParentItem(self.viewBox)                            # add to self (Diagram Item) for absolute position 
        p1.anchor(itemPos=(0,0), parentPos=(0.0), offset=(50,0))
        p1.setZValue(5)
        self._title_item = p1


    @property
    def app_model (self) -> App_Model:
        """ the app model"""
        return self._dataObject
    
    def _welcome_message (self) -> str: 
        # use Notepad++ or https://froala.com/online-html-editor/ to edit 

        version = self.app_model._version

        if self.app_model.airfoil.isExample:
            example = f"""
<p>
This is an example airfoil as no airfoil was provided on startup.<br>
Try out the functionality with this example or <strong><span style="color: silver;">Open&nbsp;</span></strong>an existing airfoil.
</p> """
        else:
            example = ""

        new =   "- Save / Load individual airfoil settings<br>" + \
                "- Change polar diagram variables directly in diagram<br>" + \
                "- Maximize / minimize lower data panel<br>" + \
                "- Revised Match Bezier UI<br>"
        
        # ... can't get column width working ...

        message = f"""
<span style="font-size: 18pt; color: whitesmoke">Welcome to the <strong>Airfoil<span style="color:deeppink">Editor</span></strong></span>
    <span style="font-size: 10pt">{version}</span>  <br>
<span style="font-size: 10pt; color: darkgray">
<table style="width:100%">
  <tr>
    <td style="width:40%">
        {example} 
        <p>
        You can view the properties of an airfoil like thickness distribution,<br> 
        analyze with <strong><span style="color: silver;">View Curvature</span></strong> the upper and lower surface or <br>
        examine the polars created by Worker & Xfoil with <strong><span style="color: silver;">View Polar</span></strong>. 
        </p> 
        <p>
        <span style="color: deepskyblue;">Tip: </span>Assign the file extension '.dat' to the AirfoilEditor to open <br>
         an airfoil with a double click in the file Explorer.
        </p>
    </td>
    <td><p>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</p></td>
    <td style="width:40%">
        <p>
        <strong><span style="color: silver;">Modify</span></strong> lets you change the geometry of the airfoil<br> 
        creating a new design for each change.
        </p> 
        <p>
        <strong><span style="color: silver;">As Bezier based</span></strong> allows to convert the airfoil into <br> 
         a new airfoil based on two Bezier curves. 
        </p> 
        <p>
        <strong><span style="color: silver;">Optimize</span></strong> switches to airfoil optimization mode <br>
        which uses Xoptfoil2 as the optimization engine. 
        </p> 
    </td>
    <td><p>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</p></td>
    <td>
        <p>
        <strong><span style="color: springgreen;">New</span></strong><span style="color: whitesmoke"> in {version}</span>:
        </p> 
        <p>
        {new}
        </p> 
    </td>
  </tr>
</table>
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



class Item_Polars (Diagram_Item):
    """ 
    Diagram (Plot) Item for polars 
    """

    name        = "View Polar"                          # used for link and section header 
    title       = None 
    subtitle    = None                                  # optional subtitle 

    def __init__(self, *args, **kwargs):

        self._xyVars    = None
        self._xyVars_show_dict = {}                     # dict of xyVars shown up to now 

        self._title_item2 = None                        # a second 'title' for x-axis 
        self._autoRange_not_set = True                  # to handle initial no polars to autoRange 
        self._next_btn    = None
        self._prev_btn    = None 

        super().__init__(*args, **kwargs)

        # connect to model signals

        self.app_model.sig_new_polars.connect               (self.refresh)
        self.app_model.sig_polar_set_changed.connect        (self.refresh)
        self.app_model.sig_xo2_opPoint_def_selected.connect (self.refresh)

        self.app_model.sig_xo2_new_design.connect           (self.refresh)

        # buttons for prev/next diagram 

        p = Icon_Button (Icon.COLLAPSE, parent=self, itemPos=(0.5,0), parentPos=(0.5,0), offset=(0,0) )
        p.clicked.connect(self._btn_prev_next_clicked)  
        self._prev_btn = p

        p = Icon_Button (Icon.EXPAND, parent=self, itemPos=(0.5,1), parentPos=(0.5,1), offset=(0,5) )
        p.clicked.connect(self._btn_prev_next_clicked)
        self._next_btn = p

        self._refresh_prev_next_btn ()


    @property
    def app_model (self) -> App_Model:
        """ the app model"""
        return self._dataObject

    @property
    def airfoils (self) -> list[Airfoil]: 
        return self.app_model.airfoils_to_show

    @property 
    def case (self) -> Case_Abstract:
        """ actual case (Direct Design or Optimize)"""
        return self.app_model.case


    @property
    def design_airfoil (self) -> Airfoil:
        """ design airfoil if it is available"""
        for airfoil in self.app_model.airfoils:                     # all airfoils (not only those to show)
            if airfoil.usedAsDesign: return airfoil

    @property
    def iDesign (self)  -> int | None:
        """ iDesign of the Design airfoil - or None if there is no design"""
        return Case_Abstract.get_iDesign (self.design_airfoil)

    
    @property
    def opPoint_defs (self) -> list:
        """ Xo2 opPoint definitions"""

        if isinstance (self.case, Case_Optimize):
            return self.case.input_file.opPoint_defs
        else:
            return [] 


    @property 
    def design_opPoints (self) -> list[OpPoint_Result]:
        """ opPoint result belonging to current design airfoil"""

        if self.iDesign is None: return []

        # get opPoints of Design iDesign - during optimize it could not yet be available...

        case : Case_Optimize = self.case
        designs_opPoints = case.results.designs_opPoints if isinstance (case, Case_Optimize) else []

        if len (designs_opPoints) == 0:
            return None                                         # no opPoint results available 
        if self.iDesign < len (designs_opPoints):
            return designs_opPoints[self.iDesign]                    # ok - it exists 
        else: 
            return designs_opPoints[-1]                         # return the current last design 


    @property 
    def prev_design_opPoints  (self) -> list[OpPoint_Result]:
        """ opPoint result belonging to previous of current design airfoil"""

        case : Case_Optimize = self.case

        if not case.isRunning: return []

        designs_opPoints = case.results.designs_opPoints if case else []

        try: 
            i = self.case.airfoil_designs.index (self.design_airfoil)
            return designs_opPoints[i-1]
        except:
            return []
        

    @override
    def _settings (self) -> dict:
        """ return dictionary of self settings"""
        d = {}

        # axes x, y variables
        toDict (d, "xyVars", (str(self.xVar), str(self.yVar)))
        return d


    @override
    def _set_settings (self, d : dict):
        """ set settings of self from dict """

        # axes x, y variables
        xyVars = d.get('xyVars', None)                          
        if xyVars is not None:
            self.set_xyVars (xyVars)
            self._refresh_artist_xy ()
            self.setup_viewRange ()


    @property 
    def has_reset_button (self) -> bool:
        """ reset view button in the lower left corner"""
        # to be overridden
        return False 


    def _btn_prev_next_clicked (self, button : Icon_Button):
        """ prev or next buttons clicked"""

        step = -1 if button.icon_name == Icon.COLLAPSE else 1

        try:
            # save current view Range
            self._xyVars_show_dict[self._xyVars] = self.viewBox.viewRect()

            # get index of current and set new 
            l = list (self._xyVars_show_dict.keys())
            i = l.index(self._xyVars) + step
            if i >= 0 :
                self._xyVars = l[i]
                viewRect = self._xyVars_show_dict [self._xyVars]
                self.setup_viewRange (rect=viewRect)                # restore view Range
                self._refresh_artist_xy ()                             # draw new polar
            self._refresh_prev_next_btn ()                          # update visibility of buttons
        except :
            pass


    @override
    def plot_title (self):
        """ override to have 'title' at x,y axis"""

        # remove existing title item 
        if isinstance (self._title_item, pg.LabelItem):
            self.scene().removeItem (self._title_item)          # was added directly to the scene via setParentItem
        if isinstance (self._title_item2, pg.LabelItem):
            self.scene().removeItem (self._title_item2)         # was added directly to the scene via setParentItem
       
        # y-axis
        p = Text_Button (self.yVar, parent=self, color=QColor(Artist.COLOR_HEADER), size=f"{Artist.SIZE_HEADER}pt",
                         itemPos=(0,0), parentPos=(0,0), offset=(60,5))
        p.clicked.connect (lambda pos: self._btn_var_clicked("y",pos)) 
        p.setToolTip (f"Select polar variable for y axis")           
        self._title_item = p

        # x-axis
        p = Text_Button (self.xVar, parent=self, color=QColor(Artist.COLOR_HEADER), size=f"{Artist.SIZE_HEADER}pt",
                         itemPos=(1,1), parentPos=(1,1), offset=(-15,-50))
        p.setToolTip (f"Select polar variable for x axis")           
        p.clicked.connect (lambda pos: self._btn_var_clicked("x",pos))            
        self._title_item2 = p


    def _btn_var_clicked (self, axis, pos : QPoint):
        """ slot - polar var button in diagram clicked - show menu list of variables"""
        menu = QMenu()
       
        # Build popup menu 
        for v in var.list_small():
            action = QAction (v.value, menu)
            action.setCheckable (True)
            if axis == "y":
                action.setChecked (v == self.yVar)
                action.triggered.connect (lambda  checked, v=v: self.set_yVar (v))
            else:
                action.setChecked (v == self.xVar)
                action.triggered.connect (lambda  checked, v=v: self.set_xVar (v))
            menu.addAction (action)
        menu.exec (pos)


    def xo2_isRunning (self) -> bool:
        """ True if optimizer is ready """
        if isinstance (self.case, Case_Optimize):
            return self.case.xo2.isRunning
        else:
            return False


    def _add_xyVars_to_show_dict (self):
        """ add actual xyVars and viewRange to the dict of already shown combinations"""
        try:
            self._xyVars_show_dict[self._xyVars] = self.viewBox.viewRect()
            self._refresh_prev_next_btn ()
        except:
            pass


    def _refresh_prev_next_btn (self):
        """ hide/show previous / next buttons"""

        l = list (self._xyVars_show_dict.keys())

        if self._xyVars in l:
            i = l.index(self._xyVars)
            if i == 0:
                self._prev_btn.hide()
            else:
                self._prev_btn.show()
            if i >= (len (self._xyVars_show_dict) - 1):
                self._next_btn.hide()
            else:
                self._next_btn.show()
        else: 
            self._prev_btn.hide()
            self._next_btn.hide()


    def _refresh_artist_xy (self): 
        """ refresh polar artist with new diagram variables"""

        artist : Polar_Artist
        for artist in self._artists:
            artist.set_xyVars (self._xyVars)

        self.plot_title()


    @property
    def xVar (self) -> var:
        return self._xyVars[0]

    def set_xVar (self, varType : var):
        """ set x diagram variable"""

        # save current state - here: only if it is already in dict or first time
        if self._xyVars in self._xyVars_show_dict or not self._xyVars_show_dict:
            self._xyVars_show_dict[self._xyVars] = self.viewBox.viewRect()

        self._xyVars = (varType, self._xyVars[1])
        # wait a little until user is sure for new xyVars (prev/next buttons)
        QTimer.singleShot (3000, self._add_xyVars_to_show_dict)

        self._refresh_artist_xy ()
        self.setup_viewRange ()


    @property
    def yVar (self) -> var:
        return self._xyVars[1]

    def set_yVar (self, varType: var):
        """ set y diagram variable"""

        # save current state - here: only if it is already in dict or first time
        if self._xyVars in self._xyVars_show_dict or not self._xyVars_show_dict:
            self._xyVars_show_dict[self._xyVars] = self.viewBox.viewRect()

        self._xyVars = (self._xyVars[0], varType)
        # wait a little until user is sure for new xyVars (prev/next buttons)
        QTimer.singleShot (3000, self._add_xyVars_to_show_dict)

        self._refresh_artist_xy ()
        self.setup_viewRange ()


    def set_xyVars (self, xyVars : list[str]):
        """ set xyVars from a list of var strings or enum var"""

        xVar = xyVars[0]
        if not isinstance (xVar, var):
            xVar = var(xVar)
        else: 
            xVar = xVar 

        yVar = xyVars[1]
        if not isinstance (yVar, var):
            yVar = var(yVar)
        else: 
            yVar = yVar 
        self._xyVars = (xVar, yVar)


    @override
    def refresh(self): 
        """ refresh my artists and section panel """

        if self._autoRange_not_set:
            self._viewRange_set = False                     # ensure refresh will setup_viewRange (autoRange)

        super().refresh()

        return


    @override
    def setup_artists (self):
        """ create and setup the artists of self"""

        a = Polar_Artist              (self, lambda: self.airfoils, xyVars=self._xyVars, show_legend=True)
        self._add_artist (a)

        a = Xo2_OpPoint_Defs_Artist   (self, lambda: self.opPoint_defs,                   # all opPoint definitions
                                        cur_opPoint_def_fn = lambda: self.app_model.cur_opPoint_def,      
                                        isRunning_fn = self.xo2_isRunning,
                                        xyVars = self._xyVars, show_legend=True, show=False)
        
        a.sig_opPoint_def_changed.connect  (self.app_model.notify_xo2_input_changed)
        a.sig_opPoint_def_selected.connect (self.app_model.set_cur_opPoint_def)
        self._add_artist (a)

        a = Xo2_OpPoint_Artist        (self, lambda: self.airfoils, opPoint_results_fn = lambda: self.design_opPoints,
                                       prev_opPoint_results_fn = lambda: self.prev_design_opPoints,
                                       opPoint_defs_fn    = lambda: self.opPoint_defs, 
                                       xyVars=self._xyVars, show_legend=True, show=False,)
        self._add_artist (a)


    @override
    def setup_viewRange (self, rect=None):
        """ define view range of this plotItem"""

        self.viewBox.setDefaultPadding(0.05)

        if rect is None: 
            self.viewBox.autoRange ()                           # ensure best range x,y 

            # it could be that there are initially no polars, so autoRange wouldn't set a range, retry at next refresh
            if  self.viewBox.childrenBounds() != [None,None] and self._autoRange_not_set:
                self._autoRange_not_set = False 
            self.viewBox.enableAutoRange(enable=False)

            self.showGrid(x=True, y=True)
        else: 
            self.viewBox.setRange (rect=rect, padding=0.0)      # restore view Range

        self._set_legend_position ()                            # find nice legend position 


    def _set_legend_position (self):
        """ try to have a good position for legend depending on xyVars"""

        if self.legend is None:
            # normally Artist adds legend  - here to set legend during init 
            self.addLegend(offset=(-10,10),  verSpacing=0 )  
            self.legend.setLabelTextColor (Artist.COLOR_LEGEND)

        if (self.yVar == var.CL or self.yVar == var.ALPHA) and self.xVar == var.CD:
            self.legend.anchor (itemPos=(1,0.5), parentPos=(1,0.5), offset=(-10,0))     # right, middle 

        elif (self.yVar == var.GLIDE or self.yVar == var.SINK) and (self.xVar == var.ALPHA or self.xVar == var.CL):
            self.legend.anchor (itemPos=(0.2,1), parentPos=(0.5,1), offset=(0,-20))     # middle, bottom

        elif (self.yVar == var.CL) and (self.xVar == var.ALPHA):
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

    name        = "Airfoil Diagram"                                 # used for settings

    sig_opPoint_def_selected        = pyqtSignal()                  # opPoint definition selected  
    sig_opPoint_def_changed         = pyqtSignal()                  # opPoint definition changed  
    sig_opPoint_def_dblClick        = pyqtSignal(object,object, object)     # opPoint definition double clicked


    def __init__(self, *args,  **kwargs):
  
         # panels for diagram items

        self._panel_polar           = None 
        self._panel_optimization    = None 
        self._panel_airfoil_settings= None

        self._show_polar_points     = False                         # show polars data points 
        self._show_bubbles          = False                         # show bubbles in polars 

        super().__init__(*args, **kwargs)

        # load initial settings
        self.set_settings (self.app_model.settings)

        self._viewPanel.setMinimumWidth(250)
        self._viewPanel.setMaximumWidth(250)
 
         # set spacing between the two items
        self.graph_layout.setVerticalSpacing (0)

        # connect to signals of app_model
        self.app_model.sig_new_mode.connect          (self._on_new_mode)
        self.app_model.sig_new_case.connect          (self.refresh)    
        self.app_model.sig_new_airfoil.connect       (self.refresh)

        self.app_model.sig_airfoil_changed.connect   (self.refresh)
        self.app_model.sig_etc_changed.connect       (self.refresh)
        self.app_model.sig_settings_loaded.connect   (lambda: self.set_settings (self.app_model.settings))
        self.app_model.sig_polar_set_changed.connect (self.panel_polar.refresh)

        self.app_model.sig_xo2_run_started.connect   (self._on_xo2_run_started)
        self.app_model.sig_xo2_new_design.connect    (self._on_xo2_new_design)
        self.app_model.sig_xo2_new_state.connect     (self.refresh)
        self.app_model.sig_xo2_input_changed.connect (self.refresh)         # e.g. seed airfoil, opPoint def changed



    def _hide_item_welcome (self):
        """ hide the Welcome Item"""

        item_welcome : Item_Welcome = self._get_first_item (Item_Welcome)
        if item_welcome and item_welcome.show:
            item_welcome.hide()


    def _settings (self) -> dict:
        """ return dictionary of self settings"""
        s = {}
        show = self._show_item (Item_Polars)
        toDict (s, f"{Item_Polars.name}", show)

        show = self._show_item (Item_Airfoil)
        toDict (s, f"{Item_Airfoil.name}", show)

        show = self._show_item (Item_Curvature)
        toDict (s, f"{Item_Curvature.name}", show)
        return s


    def _set_settings (self, s : dict):
        """ set settings of self from dict """

        show = s.get(self.panel_polar.name, False)     
        self._set_show_item (Item_Polars, show, silent=True)        # silent set

        show = s.get(Item_Airfoil.name, None)
        self._set_show_item (Item_Airfoil, show, silent=True)       # silent set

        show = s.get(Item_Curvature.name, None)
        self._set_show_item (Item_Curvature, show, silent=True)     # silent set

        self._rebuild_grid_layout()


    def _load_settings_of_airfoil (self):
        """ load settings of current airfoil from app_model"""

        if self.app_model.airfoil_settings_exist:
            self.app_model.load_settings ()
            self.set_settings (self.app_model.settings)


    def _save_settings_of_airfoil (self):
        """ save settings of current airfoil to app_model"""

        self.app_model.save_settings (add_key=self.name, add_value=self.settings())

    # -------------

    @property 
    def app_model (self) -> App_Model:
        """ application model"""
        return self.dataObject()

    @property 
    def polar_defs (self) -> list [Polar_Definition]:
        """ actual polar definitions"""
        return self.app_model.polar_definitions

    @property 
    def case (self) -> Case_Abstract:
        """ actual case (Direct Design or Optimize)"""
        return self.app_model.case

    @property
    def is_mode_optimize (self) -> bool: 
        """ True if optimize mode"""
        return self.app_model.is_mode_optimize

    @property
    def airfoil_designs (self) -> list [Airfoil]:
        """ list of airfoil designs in mode modify and optimize"""
        return self.case.airfoil_designs if self.case else []
    
    @property
    def airfoil_design (self) -> Airfoil:
        """ design airfoil if it is in airfoils"""
        return self.app_model.airfoil_design
    
    @property
    def iDesign (self) -> Airfoil:
        """ iDesign of the Design airfoil - or None if there is no design"""

        for airfoil in self.app_model.airfoils:
            if airfoil.usedAsDesign: 
                return Case_Abstract.get_iDesign (airfoil)


    def create_diagram_items (self):
        """ create all plot Items and add them to the layout """

        r = 0 
        if self.app_model._is_first_run:

            # show Welcome text if App runs the first time
            item = Item_Welcome (self, self.app_model)
            self._add_item (item, r, 0, colspan=2)                          # item has fixed height
            r += 1

        item = Item_Airfoil (self, self.app_model)     
        self._add_item (item, r, 0, colspan=2, rowStretch=2)

        r += 1
        item = Item_Curvature (self, self.app_model, show=False)
        item.set_desired_xLink_name (Item_Airfoil.name)             # link x axis to airfoil item
        self._add_item (item, r, 0, colspan=2, rowStretch=2)

        if Worker.ready:
            r += 1
            default_settings = [{"xyVars" : (var.CD,var.CL)}, {"xyVars" : (var.CL,var.GLIDE)}]

            for iItem in [0,1]:
                # create Polar items with init values vor axes variables 
                item = Item_Polars (self, self.app_model, show=False)
                item.name = f"{Item_Polars.name}_{iItem+1}"                 # set unique name as there a multiple items
                item._set_settings (default_settings[iItem])                        # set default settings first
                self._add_item (item, r, iItem, rowStretch=3)
 

    @override
    def create_view_panel (self):
        """ 
        creates a view panel to the left of at least one diagram item 
        has a section_panel
        """
 
        # build side view panel with the section panels 

        l = QVBoxLayout()
        l.setContentsMargins (QMargins(0, 0, 0, 0)) 

        # airfoils panel 
        l.addWidget (self.section_panel,stretch=0)

        # optimization panel 
        if Worker.ready and Xoptfoil2.ready:
            l.addWidget (self.panel_optimization,stretch=0)

        # diagram items panel
        for item in self.diagram_items:
            if item.section_panel is not None: 
                l.addWidget (item.section_panel,stretch=0)

        # polar panel
        l.addWidget (self.panel_polar, stretch=0)
        
        # stretch add end 
        l.addStretch (3)

        # settings panel
        l.addWidget (self.panel_airfoil_settings, stretch=0)

        self._viewPanel = Container_Panel(layout=l,width=250)
 

    @property
    def section_panel (self) -> Panel_Airfoils:
        """ return section panel within view panel"""

        if self._section_panel is None:
        
            p = Panel_Airfoils (self, self.app_model,auto_height=True)
            
            p.sig_airfoils_to_show_changed.connect (self._on_show_airfoil_changed)
            p.sig_airfoils_scale_changed.connect   (self.app_model.notify_airfoils_scale_changed)

            self._section_panel = p 

        return self._section_panel 


    @property
    def panel_optimization (self) -> Edit_Panel:
        """ common options in mode_optimization """

        if self._panel_optimization is None:

            case : Case_Optimize = self.case
        
            l = QGridLayout()
            r,c = 0, 0

            CheckBox (l,r,c, text="Op Point Definitions", colSpan=6,
                            get=lambda: self.show_xo2_opPoint_def, set=self.set_show_xo2_opPoint_def) 
            r += 1
            CheckBox (l,r,c, text="Op Point Results", colSpan=6,
                            get=lambda: self.show_xo2_opPoint_result, set=self.set_show_xo2_opPoint_result,
                            disable=lambda: not case.results.designs_opPoints)               

            self._panel_optimization = Edit_Panel (title="Optimization", layout=l, switchable=False, height=(100,None),
                                                   hide=lambda: not self.is_mode_optimize)

        return self._panel_optimization 


    @property
    def panel_airfoil_settings (self) -> Panel_Airfoil_Settings:
        """ little panel to save, load individual airfoil settings """

        if self._panel_airfoil_settings is None:
            self._panel_airfoil_settings = Panel_Airfoil_Settings (self, getter=self.app_model, 
                                                   auto_height=True, has_head=False,
                                                   lazy=True,
                                                   hide=lambda: self.case)      # dont show in optimize and modify mode
            
            self._panel_airfoil_settings.sig_save_settings.connect   (self._save_settings_of_airfoil)
            self._panel_airfoil_settings.sig_load_settings.connect   (self._load_settings_of_airfoil)

        return self._panel_airfoil_settings


    @property
    def show_polars (self) -> bool:
        """ show polar diagrams """
        return self._show_item (Item_Polars)

    def set_show_polars (self, aBool : bool, silent=False):
        self._set_show_item (Item_Polars, aBool, silent=silent)

    @property 
    def show_polar_points (self) -> bool:
        """ show polar operating points """
        return self._show_polar_points

    def set_show_polar_points (self, aBool : bool):
        self._show_polar_points = aBool

        artist : Polar_Artist
        for artist in self._get_artist (Polar_Artist):
            artist.set_show_points (aBool) 


    @property 
    def show_bubbles (self) -> bool:
        """ show bubbles in polar diagrams """
        return self._show_bubbles

    def set_show_bubbles (self, aBool : bool):
        self._show_bubbles = aBool

        artist : Polar_Artist
        for artist in self._get_artist (Polar_Artist):
            artist.set_show_bubbles (aBool) 

    @property 
    def show_xo2_opPoint_def (self) -> bool:
        """ show opPoint definitions"""
        artists = self._get_artist (Xo2_OpPoint_Defs_Artist)
        return artists[0].show if artists else False 

    def set_show_xo2_opPoint_def (self, aBool : bool, refresh=True):
        self._show_artist (Xo2_OpPoint_Defs_Artist, aBool, refresh=refresh)


    @property 
    def show_xo2_opPoint_result (self) -> bool:
        """ show opPoint result"""
        artists = self._get_artist (Xo2_OpPoint_Artist)
        return artists[0].show if artists else False

    def set_show_xo2_opPoint_result (self, aBool : bool, refresh=True):
        self._show_artist (Xo2_OpPoint_Artist, aBool, refresh=refresh)
        self._show_artist (Xo2_Transition_Artist, aBool, refresh=refresh)


    @property
    def panel_polar (self) -> Edit_Panel:
        """ return polar extra panel to admin polar definitions and define polar diagrams"""

        if self._panel_polar is None:
        
            l = QGridLayout()
            r,c = 0, 0

            if Worker.ready:

                Label (l,r,c, colSpan=2, get="Polar definitions") 
                r += 1

                # helper panel for polar definitions 

                p = Panel_Polar_Defs (self, lambda: self.polar_defs, auto_height=True)

                p.sig_polar_def_changed.connect (self.app_model.notify_polar_definitions_changed)

                l.addWidget (p, r, c, 1, 2)

                # polar diagrams variables setting 

                r += 1
                Label (l,r,c, colSpan=2, style=style.COMMENT, height=40,
                       get="To change polar variables, <br>click the axis labels in the diagram.")
                r += 1
                CheckBox (l,r,c, text="Polar points", colSpan=2,
                            get=lambda: self.show_polar_points, set=self.set_show_polar_points,
                            toolTip="Show the polar data points")
                r += 1
                CheckBox (l,r,c, text="Bubbles - see xtr diagram", colSpan=2,
                            get=lambda: self.show_bubbles, set=self.set_show_bubbles,
                            disable=not Worker.can_detect_bubbles(),
                            toolTip=("Show bubbles in the polar diagram - see xtr transition diagram for details.<br>" + \
                                    "<br>Laminar separation bubbles are identified by a range of negative shear stress " + \
                                    "along the airfoil surface.") if Worker.can_detect_bubbles()\
                                        else f"Worker version {Worker.version} cannot detect bubbles")

                l.setColumnMinimumWidth (0,18)
                l.setColumnStretch (1,1)

            else: 
                SpaceR (l,r, height=10, stretch=0) 
                r += 1
                Label (l,r,c, colSpan=2, get="No polars available", fontSize=size.HEADER_SMALL, style=style.COMMENT) 
                r += 1
                SpaceR (l,r, height=10, stretch=0) 
                r += 1
                Label (l,r,c, colSpan=2, get=f"{Worker.NAME} not ready", style=style.ERROR) 
                r += 1
                Label (l,r,c, colSpan=2, get=f"{Worker.ready_msg}", style=style.COMMENT, height=(None,100), wordWrap=True) 
                r += 1
                SpaceR (l,r, height=5) 
                l.setColumnStretch (1,1)

            self._panel_polar = Edit_Panel (title=Item_Polars.name, layout=l, auto_height=True, switchable  = True, 
                                            switched_on = lambda: self.show_polars,
                                            on_switched = lambda aBool: self.set_show_polars(aBool))
            
            # patch Worker version into head of panel 
            if Worker.ready:
                l_head = self._panel_polar._head.layout()
                Label  (l_head, get=f"{Worker.NAME} {Worker.version}", style=style.COMMENT, fontSize=size.SMALL,
                        align=Qt.AlignmentFlag.AlignBottom)

        return self._panel_polar 


    # --- public slots ---------------------------------------------------


    @override
    def refresh(self, also_viewRange=False): 
        """ refresh my artists and section panel - default stick to view range """

        # hide Welcome item with first refresh
        self._hide_item_welcome()

        # switch off optimize opPoint definitions
        if not self.is_mode_optimize and self.show_xo2_opPoint_def:
            self.set_show_xo2_opPoint_def (False) 

        super().refresh(also_viewRange=also_viewRange) 



    # --- private slots ---------------------------------------------------

    def _on_new_mode (self):
        """ slot when entering / leaving mode  """

        if self.app_model.is_mode_optimize:
            self.panel_polar.set_switched_on (True)                         # switch on view polars
            self.set_show_xo2_opPoint_def    (True, refresh=False)          # show opPoint definitions
            self.set_show_xo2_opPoint_result (True, refresh=False)          # show opPoint result
            self.section_panel.set_show_design_airfoils (False)             # don't show design airfoil initially - would be too much
            self.section_panel.reset_show_reference_airfoils ()             # show reference airfoils if there are

        self.refresh(also_viewRange=True)



    def _on_view_polars_switched (self, aBool):
        """ slot to handle polars switched on/off """

        logger.debug (f"{str(self)} on polars switched")

        if aBool:
            self._hide_item_welcome ()
    
        for item in self._get_items (Item_Polars):
            if item.show != aBool:   
                item.set_show (aBool)


    def _on_show_airfoil_changed (self):
        """ slot to handle show airfoil switched on/off """

        logger.debug (f"{str(self)} on show airfoil switched")

        # list of airfoils will be dependent of property "show" in app_model
        for item in self.diagram_items:
            if item.show: 
                item.refresh()


    def _on_opPoint_def_changed (self):
        """ slot to handle change of xo2 opPoint definition in diagram """

        if self.is_mode_optimize:
            logger.debug (f"{str(self)} on opPoint_def changed in diagram - save input ")

            self.panel_polar.refresh()

            for artist in self._get_artist (Xo2_OpPoint_Defs_Artist):
                artist.refresh ()
                
            self.sig_opPoint_def_changed.emit ()


    def _on_xo2_run_started (self): 
        """ slot optimization will start soon ..."""

        logger.debug (f"{str(self)} on Xoptfoil2 about to run")

        # switch on opPoints 
        self.set_show_xo2_opPoint_def    (True, refresh=False)
        self.set_show_xo2_opPoint_result (True, refresh=False)

        self.refresh ()


    def _on_xo2_new_design (self):
        """ slot - new design available from xo2 optimization """

        logger.debug (f"{str(self)} on Xoptfoil2 new design")

        # just panel for new design airfoil - items are signaled from app_model
        self.section_panel.refresh ()

        # refresh of artists is done in items        