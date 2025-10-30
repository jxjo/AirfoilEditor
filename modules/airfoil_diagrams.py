#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

Diagram (items) for airfoil

"""

import logging
from copy                   import deepcopy 
from base.widgets           import * 
from base.diagram           import * 
from base.panels            import Edit_Panel, Toaster

from model.airfoil          import Airfoil
from model.polar_set        import *
from model.case             import Case_Abstract, Case_Optimize
from model.xo2_driver       import Worker, Xoptfoil2
from model.xo2_results      import OpPoint_Result
from model.xo2_controller   import xo2_state

from airfoil_artists        import *
from airfoil_widgets        import Airfoil_Select_Open_Widget

from xo2_artists            import *


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

    sig_airfoil_ref_changed         = pyqtSignal(object, object)    # changed reference airfoil 
    sig_airfoils_ref_scale_changed  = pyqtSignal()                  # switch off/on, set scale of reference airfoil 
    sig_airfoils_to_show_changed    = pyqtSignal()                  # changed show filter 
    sig_airfoil_design_selected     = pyqtSignal(int)               # an airfoil design iDesign was selected in the Combobox

    _main_margins  = (10, 5, 0, 5)                 # margins of Edit_Panel


    def __init__(self, *args, airfoils_ref_scale_fn=None, airfoil_designs_fn=None, **kwargs):

        self._airfoil_designs_fn = airfoil_designs_fn
        self._airfoils_ref_scale_fn = airfoils_ref_scale_fn
        self._show_reference_airfoils = None                    # will be set in init_layout
        self._show_design_airfoils = True                       # show all design airfoils on/off

        super().__init__(*args, **kwargs)

        # ensure design airfoil is set
        if self.airfoil_design:
            self.airfoil_design.set_property ("show", self.show_design_airfoils)

    # ---------------------------------------------

    @property
    def airfoils (self) -> list[Airfoil]: 
        return self.dataObject

    @property
    def airfoil_designs (self) -> list [Airfoil]:
        """ airfoil designs of case modify or optimize """
        return self._airfoil_designs_fn() if self._airfoil_designs_fn else []

    @property
    def airfoils_ref_scale (self) -> list:
        """ chord/re scale factor of ref airfoils"""
        return self._airfoils_ref_scale_fn() if self._airfoils_ref_scale_fn else []


    @property
    def airfoil_design (self) -> Airfoil:
        """ the current design airfoil if available"""
        for airfoil in self.airfoils:
            if airfoil.usedAs == usedAs.DESIGN:
                return airfoil

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
        return self._show_design_airfoils
      

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
    def airfoils_refs_are_scaled (self) -> bool:
        """ True if ref airfoils will be scaled """
        return any (scale for scale in self.airfoils_ref_scale)
    

    def set_airfoils_refs_are_scaled (self, aBool):

        for i, scale in enumerate(self.airfoils_ref_scale):
            self.airfoils_ref_scale[i] = 1.0 if aBool else None

        self.refresh()

        # app will handle setting 
        self.sig_airfoils_ref_scale_changed.emit()


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
                  get=self.airfoils_refs_are_scaled, set=self.set_airfoils_refs_are_scaled,
                  hide=lambda: not self.show_reference_airfoils,
                  toolTip="Scale reference airfoils and their polars relative to the main airfoil") 
        
        if self.show_reference_airfoils:

            iRef = 0
            r += 1
            for iair, air in enumerate (self.airfoils):

                if air.usedAs == usedAs.REF:
                    CheckBox   (l,r,c  , width=18, get=self.show_airfoil, set=self.set_show_airfoil, id=iair,
                                toolTip="Show/Hide airfoil in diagram")
                    Button     (l,r,c+1, text=lambda i=iRef: f"{self.airfoil_scale_value(i):.0%}", width=40, 
                                set=self.edit_airfoil_scale_value, id=iRef,
                                hide=lambda: not self.airfoils_refs_are_scaled,
                                toolTip="Change this scale value")

                    Airfoil_Select_Open_Widget (l,r,c+2, 
                                    get=self.airfoil, set=self.set_airfoil, id=iair,
                                    initialDir=self.airfoils[-1], addEmpty=False,       # initial dir not from DESIGN
                                    toolTip=air.info_as_html)

                    ToolButton (l,r,c+3, icon=Icon.DELETE, set=self.delete_airfoil, id=iair,
                                toolTip="Remove this airfoil as reference")
                    r += 1
                    iRef += 1

            # add new reference as long as < max REF airfoils 
            if self._n_REF() < 3:
                Airfoil_Select_Open_Widget (l,r,c+2, 
                                get=None, set=self.set_airfoil, id=iair+1,
                                initialDir=self.airfoils[-1], addEmpty=True,
                                toolTip=f"New reference airfoil {iRef+1}")
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

        if id < len(self.airfoils): 
            cur_airfoil = self.airfoils[id]
        else: 
            cur_airfoil = None                                  # will add new_airfoil 
        self.sig_airfoil_ref_changed.emit(cur_airfoil, new_airfoil)


    def show_airfoil (self, id : int) -> bool:
        """ is ref airfoil with id active"""
        return self.airfoils[id].get_property ("show", True)


    def set_show_airfoil (self, aBool, id : int):
        """ set ref airfoil with index id active"""
        self.airfoils[id].set_property ("show", aBool)
        self.sig_airfoils_to_show_changed.emit()


    def set_show_design_airfoils (self, show : bool): 

        self._show_design_airfoils = show 

        if self.airfoil_design:
            self.airfoil_design.set_property ("show", show)
            self.sig_airfoils_to_show_changed.emit()


    def delete_airfoil (self, id : int):
        """ delete ref airfoil with index idef from list"""

        if len(self.airfoils) == 0: return 

        airfoil = self.airfoils[id]

        # only REF airfoils can be deleted 
        if airfoil.usedAs == usedAs.REF:
            self.sig_airfoil_ref_changed.emit (airfoil, None)


    def airfoil_scale_value (self, id : int) -> float:
        """ the scale value of ref airfoil - defaults to 1.0"""
        return self.airfoils_ref_scale[id] if self.airfoils_ref_scale[id]  else 1.0 


    def edit_airfoil_scale_value (self, id : int):
        """ the scale value of (ref) airfoil"""

        from airfoil_dialogs import Airfoil_Scale_Dialog

        scale_value = self.airfoils_ref_scale [id] if self.airfoils_ref_scale[id]  else 1.0

        diag = Airfoil_Scale_Dialog (self, scale_value, dx=400, dy=100)
        diag.exec()

        self.airfoils_ref_scale [id] = diag.scale_value
        self.refresh()

        self.sig_airfoils_ref_scale_changed.emit()
    

    def _on_airfoil_design_selected (self, fileName):
        """ callback of combobox when an airfoil design was selected"""

        # signal app of new selected current design airfoil 
        for iDesign, airfoil in enumerate (self.airfoil_designs):
            if airfoil.fileName == fileName:
                airfoil.set_property ("show", self.show_design_airfoils)
                self.sig_airfoil_design_selected.emit (iDesign)
                break


    @override
    def refresh (self, reinit_layout=False):
        """ refreshes all Widgets on self """

        # ensure (new) show of design airfoil is set accordingly
        if self.airfoil_design:
            self.airfoil_design.set_property ("show", self.show_design_airfoils)

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

        from airfoil_dialogs import Polar_Definition_Dialog

        if isinstance (id, int):
            polar_def = self.polar_defs[id]

        diag = Polar_Definition_Dialog (self, polar_def, dx=260, dy=-150, fixed_chord=self.chord)
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
            new_polar_def.set_is_mandatory (False)                  # parent could have been madatory
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

    def __init__(self, *args,  **kwargs):

        self._loaded_for : Airfoil = None                   # airfoil for which settings are last loaded

        super().__init__(*args, **kwargs)


    @property
    def parent (self) -> 'Diagram_Item_Airfoil':
        """ parent diagram item"""
        return self._app

    @property
    def airfoil (self) -> Airfoil:
        """ the current airfoil in diagram"""
        return self.dataObject
    
    @property
    def airfoil_has_settings(self) -> bool:
        """ does the current airfoil have individual settings"""
        return self.airfoil.get_property ("has_settings", False) 
    
    @property
    def airfoil_settings_loaded (self) -> bool:
        """ are settings loaded for current airfoil"""
        return self.airfoil == self._loaded_for and self.airfoil_has_settings


    def set_settings_loaded_for (self, airfoil : Airfoil):
        """ set that settings are loaded for airfoil"""
        self._loaded_for = airfoil
        self.refresh() 

        if isinstance (airfoil, Airfoil):
            msg = f"Settings loaded for {airfoil.fileName}" 
            # during startup UI may not be ready
            QTimer.singleShot (200, lambda: self._toast_message (msg, toast_style=style.GOOD, duration=1500))
 

    def _init_layout(self):

        l = QGridLayout()
        r,c = 0, 0
        ToolButton (l,r,c, icon=Icon.OPEN, width=(22,None),
                text=lambda: f"Load Settings of {self.airfoil.fileName_stem}", 
                set=self._settings_load,
                hide=lambda: not self.airfoil_has_settings or self.airfoil_settings_loaded,
                style=style.HINT,
                toolTip=lambda: f"Load the individual settings of {self.airfoil.fileName}")
        ToolButton (l,r,c, icon=Icon.SAVE, width=(22,None),
                text=lambda: f"Save as individual Settings", 
                set=self._settings_save,
                hide=lambda: self.airfoil_has_settings,
                toolTip=lambda: f"Save these settings being individual for {self.airfoil.fileName} to be reloaded later")
        Label (l,r,c, get=lambda: f"Settings of {self.airfoil.fileName_stem}", 
               hide=lambda: not self.airfoil_settings_loaded)  
        c += 1
        l.setColumnStretch (c,1)
        c += 1
        ToolButton (l,r,c, icon=Icon.SAVE, 
                set=self._settings_save,
                hide=lambda: not self.airfoil_settings_loaded,
                toolTip=lambda: f"Overwrite current settings of {self.airfoil.fileName} with these settings")
        c += 1
        ToolButton (l,r,c, icon=Icon.DELETE,
                set=self._settings_delete,
                hide=lambda: not self.airfoil_has_settings,
                toolTip=lambda: f"Delete the individual settings of {self.airfoil.fileName}")
        return l


    def _toast_message (self, msg: str, toast_style : style = style.GOOD, duration: int = 400, alpha: int = 255):
        """ toast message for action on settings"""
        Toaster.showMessage (self, msg, 
                             margin=QMargins(20,10,10,5), contentsMargins=QMargins(15,3,15,3), 
                             toast_style=toast_style, duration=duration, alpha=alpha)


    def _settings_load (self):
        """ slot load settings of current airfoil"""

        self.parent.sig_settings_load.emit (self.airfoil)


    def _settings_save (self):
        """ slot save settings of current airfoil"""

        self.parent.sig_settings_save.emit (self.airfoil)

        self._loaded_for = self.airfoil                     # settings now saved for this airfoil
        self.refresh()

        msg = f"Settings saved for {self.airfoil.fileName}"
        self._toast_message (msg, toast_style=style.GOOD, duration=1000)    


    def _settings_delete (self):
        """ slot delete settings of current airfoil"""

        self.parent.sig_settings_delete.emit (self.airfoil)

        msg = f"Settings of {self.airfoil.fileName} deleted"
        self._toast_message (msg, toast_style=style.WARNING, duration=1000)


#-------------------------------------------------------------------------------
# Diagram Items  
#-------------------------------------------------------------------------------

class Diagram_Item_Airfoil (Diagram_Item):
    """ 
    Diagram (Plot) Item for airfoils shape 
    """

    name = "View Airfoil"           # used for link and section header 


    sig_geometry_changed         = pyqtSignal()          # airfoil data changed in a diagram 


    def __init__(self, *args, case_fn=None, iDesign_fn= None, **kwargs):

        self._case_fn    = case_fn 
        self._iDesign_fn = iDesign_fn 

        self._stretch_y         = False                 # show y stretched 
        self._stretch_y_factor  = 3                     # factor to stretch 
        self._geo_info_item     = None                  # item to show geometry info on plot

        super().__init__(*args, **kwargs)


    def airfoils (self) -> list[Airfoil]: 
        return self._getter()


    def _is_one_airfoil_bezier (self) -> bool: 
        """ is one of airfoils Bezier based? """
        for a in self.airfoils():
            if a.isBezierBased: return True
        return False 


    def _is_one_airfoil_hicks_henne (self) -> bool: 
        """ is one of airfoils Hicks Henne based? """

        for a in self.airfoils():
            if a.isHicksHenneBased: return True
        return False 


    def _is_design_and_bezier (self) -> bool: 
        """ is one airfoil used as design ?"""

        for a in self.airfoils():
            if a.usedAsDesign and a.isBezierBased:
                return True 
        return False


    def _on_enter_panelling (self):
        """ slot user started panelling dialog - show panels """

        # switch on show panels , switch off thciknes, camber 
        self.airfoil_artist.set_show_points (True)
        self.line_artist.set_show (False)
        self.section_panel.refresh() 

        logger.debug (f"{str(self)} _on_enter_panelling")


    @property 
    def case (self) -> Case_Abstract:
        """ actual case (Direct Design or Optimize)"""
        return self._case_fn() if self._case_fn else None


    @property
    def design_airfoil (self) -> Airfoil:
        """ design airfoil if it is available"""
        for airfoil in self.airfoils():
            if airfoil.usedAsDesign: return airfoil

    @property
    def iDesign (self) -> int|None:
        """ number of Design airfoil """ 
        return self._iDesign_fn () if callable (self._iDesign_fn) else None


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
        """ y axis stretche factor"""
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

        airfoil = self.airfoils()[0] if self.airfoils() else None

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

        if not self.airfoils(): return 

        # the first airfoil get's in the title 

        airfoil = self.airfoils()[0]

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
        
        a = Airfoil_Artist   (self, self.airfoils, show_legend=True)
        self.airfoil_artist = a
        self._add_artist (a)

        a = Airfoil_Line_Artist (self, self.airfoils, show=False, show_legend=True)
        a.sig_geometry_changed.connect (self.sig_geometry_changed.emit)
        self.line_artist = a
        self._add_artist (a)

        self.bezier_artist = Bezier_Artist (self, self.airfoils)
        self.bezier_artist.sig_bezier_changed.connect (self.sig_geometry_changed.emit)

        self.hicks_henne_artist = Hicks_Henne_Artist (self, self.airfoils, show_legend=True, show=False)

        self.bezier_devi_artist = Bezier_Deviation_Artist (self, self.airfoils, show=False, show_legend=True)

        a  = Flap_Artist (self, lambda: self.design_airfoil, show=False, show_legend=True)
        self._add_artist (a)

        a  = TE_Gap_Artist (self, lambda: self.design_airfoil, show=False, show_legend=False)
        self._add_artist (a)

        a  = LE_Radius_Artist (self, lambda: self.design_airfoil, show=False, show_legend=False)
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

        # switch off deviation artist if not design
        if not self._is_design_and_bezier():
            self.bezier_devi_artist.set_show(False)
        else: 
            self.bezier_devi_artist.refresh()

        # show Bezier shape function when current airfoil is Design and Bezier 
        if self.airfoils():
            cur_airfoil : Airfoil = self.airfoils()[0]
            if cur_airfoil.isBezierBased and cur_airfoil.usedAsDesign:
                self.bezier_artist.set_show (True)
            else: 
                self.bezier_artist.refresh() 

        # show Hicks Henne shape functions 
        self.hicks_henne_artist.refresh()

        # the other artists
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
                                              switchable=True, on_switched=self.setVisible)

        return self._section_panel 



class Diagram_Item_Curvature (Diagram_Item):
    """ 
    Diagram (Plot) Item for airfoils curvature 
    """

    name        = "View Curvature"
    title       = "Curvature"                 
    subtitle    = None                                 # will be set dynamically 


    def airfoils (self) -> list[Airfoil]: 
        return self.data_list()
    

    @override
    def set_show (self, aBool):
        """ switch on/off artists of self when diagram_item is switched on/off"""
        super().set_show (aBool)

        self.curvature_artist.set_show (aBool)


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

        # disable derivative of curvature if not one airfoil is shown or Design airfoil is shown 
        self.section_panel.refresh()


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
                    disable=lambda: len(self.airfoils()) != 1 and \
                                    not any (airfoil.usedAsDesign for airfoil in self.airfoils()),
                    toolTip="Show the derivative of curvature which amplifies curvature artefacts.<br>"+
                            "Only active if one airfoil is displayed or Design airfoil is shown.")
            r += 1
            CheckBox (l,r,c, text=f"X axes linked to '{self._desired_xLink_name}'", 
                    get=lambda: self.xLinked, set=self.set_xLinked,
                    toolTip=f"Link the x axis of the curvature diagram to the x axis of {self._desired_xLink_name}")
            r += 1
            l.setColumnStretch (3,2)
            l.setRowStretch    (r,2)

            self._section_panel = Edit_Panel (title=self.name, layout=l, auto_height=True,
                                              switchable=True, switched_on=self._show, 
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
        self.setContentsMargins ( 0,40,0,0)
        self.setFixedHeight(280)

        # add Welcome text as html label item
        p1 = pg.LabelItem(self._welcome_message(), color=QColor(Artist.COLOR_HEADER), size=f"{Artist.SIZE_HEADER}pt")    
        p1.setParentItem(self.viewBox)                            # add to self (Diagram Item) for absolute position 
        p1.anchor(itemPos=(0,0), parentPos=(0.0), offset=(50,0))
        p1.setZValue(5)
        self._title_item = p1


    def _welcome_message (self) -> str: 
        # use Notepad++ or https://froala.com/online-html-editor/ to edit 

        # ... can't get column width working ...
         
        message = """
<span style="font-size: 18pt; color: whitesmoke">Welcome to the <strong>Airfoil<span style="color:deeppink">Editor</span></strong></span>
<br>

<span style="font-size: 10pt; color: darkgray">
<table style="width:100%">
  <tr>
    <td style="width:40%">
        <p>
        This is an example airfoil as no airfoil was provided on startup.<br>
        Try out the functionality with this example airfoil or <strong><span style="color: silver;">Open&nbsp;</span></strong>an existing airfoil.
        </p> 
        <p>
        You can view the properties of an airfoil like thickness distribution or camber,<br> 
        analyze with <strong><span style="color: silver;">View Curvature</span></strong> the upper and lower surface or <br>
        examine the polars created by Worker & Xfoil with <strong><span style="color: silver;">View Polar</span></strong>. 
        </p> 
        <p>
        <span style="color: deepskyblue;">Tip: </span>Assign the file extension '.dat' to the AirfoilEditor to open an airfoil <br>
        with a double click in the file Explorer.
        </p>
    </td>
    <td style="width:20%">
        <p>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</p>
    </td>
    <td style="width:40%">
        <p>
        <strong><span style="color: silver;">Modify</span></strong> lets you change the geometry of the airfoil<br> 
        creating a new design for each change.
        </p> 
        <p>
        <strong><span style="color: silver;">As Bezier based</span></strong> allows to convert the airfoil into a new airfoil<br> 
        based on two Bezier curves. Use the 'Match Bezier' optimization algorithm. 
        </p> 
        <p>
        <strong><span style="color: silver;">Optimize</span></strong> switches to airfoil optimization based on Xoptfoil2. 
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



class Diagram_Item_Polars (Diagram_Item):
    """ 
    Diagram (Plot) Item for polars 
    """

    name        = "View Polar"                          # used for link and section header 
    title       = None 
    subtitle    = None                                  # optional subtitle 

    sig_xyVars_changed           = pyqtSignal()         # airfoil data changed in a diagram 
    sig_opPoint_def_changed      = pyqtSignal()         # opPoint definition changed in diagram 
    sig_opPoint_def_selected     = pyqtSignal()         # opPoint definition selected in diagram 
    sig_opPoint_def_dblClick     = pyqtSignal()         # opPoint definition double clicked in diagram 


    def __init__(self, *args, case_fn=None, iDesign_fn=None, **kwargs):

        self._case_fn   = case_fn
        self._iDesign_fn = iDesign_fn 

        self._xyVars    = None
        self._xyVars_show_dict = {}                     # dict of xyVars shown up to now 

        self._title_item2 = None                        # a second 'title' for x-axis 
        self._autoRange_not_set = True                  # to handle initial no polars to autoRange 
        self._next_btn    = None
        self._prev_btn    = None 

        super().__init__(*args, **kwargs)

        # buttons for prev/next diagram 

        ico = Icon (Icon.COLLAPSE,light_mode = False)
        self._prev_btn = pg.ButtonItem(pixmap=ico.pixmap(QSize(52,52)), width=26, parentItem=self)
        self._prev_btn.mode = 'auto'
        self._prev_btn.clicked.connect(self._prev_btn_clicked)  

        ico = Icon (Icon.EXPAND,light_mode = False)
        self._next_btn = pg.ButtonItem(pixmap=ico.pixmap(QSize(52,52)), width=26, parentItem=self)
        self._next_btn.mode = 'auto'
        self._next_btn.clicked.connect(self._next_btn_clicked)       

        self._refresh_prev_next_btn ()


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

    @override
    def resizeEvent(self, ev):

        # update position next/prev button 
        if self._next_btn is not None:  
            item_height = self.size().height()
            item_width  = self.size().width()

            btn_rect = self.mapRectFromItem(self._next_btn, self._next_btn.boundingRect())
            x = item_width / 2
            y = item_height - btn_rect.height() + 3
            self._next_btn.setPos(x, y)             

            y = 5
            self._prev_btn.setPos(x, y)             

        super().resizeEvent (ev)


    def _handle_prev_next (self, step = 0):
        """ activates prev or next xy view defined by step"""

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
                self.sig_xyVars_changed.emit()                      # update view panel 
            self._refresh_prev_next_btn ()                          # update vsibility of buttons
        except :
            pass


    def _prev_btn_clicked (self):
        """ previous diagram button clicked"""
        # leave scene clicked event as plot items will be removed with new xy vars 
        QTimer.singleShot (10, lambda: self._handle_prev_next (step=-1))


    def _next_btn_clicked (self):
        """ next diagram button clicked"""
        # leave scene clicked event as plot items will be removed with new xy vars 
        QTimer.singleShot (10, lambda: self._handle_prev_next (step=1))


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


    @property 
    def case (self) -> Case_Abstract:
        """ actual case (Direct Design or Optimize)"""
        return self._case_fn() if self._case_fn else None


    def airfoils (self) -> list[Airfoil]: 
        return self._getter()
    
    @property
    def opPoint_defs (self) -> list:
        """ Xo2 opPoint definitions"""

        if isinstance (self.case, Case_Optimize):
            return self.case.input_file.opPoint_defs
        else:
            return [] 


    @property
    def design_airfoil (self) -> Airfoil:
        """ current design airfoil if it is available"""
        for airfoil in self.airfoils():
            if airfoil.usedAsDesign: return airfoil


    @property 
    def design_opPoints (self) -> list[OpPoint_Result]:
        """ opPoint result belonging to current design airfoil"""

        # get iDesign 

        iDesign = self._iDesign_fn () if callable (self._iDesign_fn) else None

        if iDesign is None: return 

        # get opPoints of Design iDesign - during optimize it could not yet be available...

        case : Case_Optimize = self.case
        designs_opPoints = case.results.designs_opPoints if isinstance (case, Case_Optimize) else []

        if len (designs_opPoints) == 0:
            return None                                         # no opPoint results available 
        if iDesign < len (designs_opPoints):
            return designs_opPoints[iDesign]                    # ok - it exists 
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
        """ refresh my artits and section panel """

        if self._autoRange_not_set:
            self._viewRange_set = False                     # ensure refresh will setup_viewRange (autoRange)

        super().refresh()

        return


    @override
    def setup_artists (self):
        """ create and setup the artists of self"""

        a = Polar_Artist              (self, self.airfoils,     xyVars=self._xyVars, show_legend=True)
        self._add_artist (a)

        a = Xo2_OpPoint_Defs_Artist   (self, lambda: self.opPoint_defs, isRunning_fn=self.xo2_isRunning,
                                       xyVars=self._xyVars, show_legend=True, show=False)
        a.sig_opPoint_def_changed.connect  (self.sig_opPoint_def_changed.emit)
        a.sig_opPoint_def_selected.connect (self.sig_opPoint_def_selected.emit)
        a.sig_opPoint_def_dblClick.connect (self.sig_opPoint_def_dblClick.emit)
        self._add_artist (a)

        a = Xo2_OpPoint_Artist        (self, self.airfoils, opPoint_results_fn = lambda: self.design_opPoints,
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

    sig_geometry_changed             = pyqtSignal()                 # airfoil geometry changed in a diagram 
    sig_new_airfoil_ref1            = pyqtSignal(object)            # new ref1 airfoil  
    sig_airfoil_ref_changed         = pyqtSignal(object, object)    # changed reference airfoil 
    sig_airfoil_design_selected     = pyqtSignal(int)               # a airfoil design iDesign was selected in ComboBox 
    sig_airfoils_ref_scale_changed  = pyqtSignal()                  # switch off/on, set scale of reference airfoil 
    sig_polar_def_changed           = pyqtSignal()                  # polar definition changed  

    sig_opPoint_def_selected        = pyqtSignal()                  # opPoint definition selected  
    sig_opPoint_def_changed         = pyqtSignal()                  # opPoint definition changed  
    sig_opPoint_def_dblClick        = pyqtSignal(object,object, object)     # opPoint definition double clicked

    sig_settings_save               = pyqtSignal(object)            # settings of airfoil should be saved
    sig_settings_load               = pyqtSignal(object)            # settings of airfoil should be loaded
    sig_settings_delete             = pyqtSignal(object)            # settings of airfoil should be deleted

    def __init__(self, *args, polar_defs_fn= None, airfoils_ref_scale_fn=None, case_fn=None,  **kwargs):

        self._polar_defs_fn         = polar_defs_fn
        self._airfoils_ref_scale_fn = airfoils_ref_scale_fn 
        self._case_fn               = case_fn 

        self._panel_polar           = None 
        self._panel_optimization    = None 
        self._panel_airfoil_settings= None

        self._show_polar_points     = False                         # show polars data points 
        self._show_bubbles          = False                         # show bubbles in polars 

        super().__init__(*args, **kwargs)

        self._viewPanel.setMinimumWidth(250)
        self._viewPanel.setMaximumWidth(250)
 
         # set spacing between the two items
        self.graph_layout.setVerticalSpacing (0)


    def _hide_item_welcome (self):
        """ hide the Welcome Item"""

        item_welcome : Diagram_Item_Welcome = self._get_first_item (Diagram_Item_Welcome)
        if item_welcome and item_welcome.isVisible():
            item_welcome.hide()


    def _settings (self) -> dict:
        """ return dictionary of self settings"""
        s = {}
        toDict (s, f"{self.panel_polar.name}", self.panel_polar.switched_on)

        item = self._get_first_item (Diagram_Item_Airfoil)
        toDict (s, f"{item.name}", item.isVisible() if item else None)

        item = self._get_first_item (Diagram_Item_Curvature)
        toDict (s, f"{item.name}", item.isVisible() if item else None)

        return s


    def _set_settings (self, s : dict):
        """ set settings of self from dict """

        show = s.get(self.panel_polar.name, None)                          # axes variables
        if show is not None:
            self.panel_polar.set_switched_on (show)

        show = s.get(Diagram_Item_Airfoil.name, None)
        self._show_section_and_item (Diagram_Item_Airfoil, show)

        show = s.get(Diagram_Item_Curvature.name, None)
        self._show_section_and_item (Diagram_Item_Curvature, show)


    # -------------


    @property 
    def polar_defs (self) -> list [Polar_Definition]:
        """ actual polar definitions"""
        return self._polar_defs_fn() if self._polar_defs_fn else []


    @property 
    def airfoils_ref_scale (self) -> list:
        """ chord/re scale factor of ref airfoils"""
        return self._airfoils_ref_scale_fn() if self._airfoils_ref_scale_fn else []


    @property 
    def case (self) -> Case_Abstract:
        """ actual case (Direct Design or Optimize)"""
        return self._case_fn() if self._case_fn else None


    @property
    def mode_optimize (self) -> bool: 
        """ True if optimize mode"""
        return isinstance (self.case, Case_Optimize) 


    def all_airfoils (self) -> list[Airfoil]: 
        """ the airfoil(s) currently to show as list"""
        return self.data_list()


    def airfoils (self) -> list[Airfoil]: 
        """ the airfoil(s) currently to show as list (filtered)"""

        # filter airfoils with 'show' property

        airfoils = []
        for airfoil in self.all_airfoils():
            if airfoil.get_property("show",True):
                airfoils.append (airfoil)

        # at least one airfoil should be there - take first 

        if not airfoils: 
            first_airfoil = self.all_airfoils()[0]
            first_airfoil.set_property("show", True)
            airfoils = [first_airfoil]

        return  airfoils 


    @property
    def airfoil_designs (self) -> list [Airfoil]:
        """ list of airfoil designs in mode modify and optimize"""
        return self.case.airfoil_designs if self.case else []
    
    @property
    def airfoil_design (self) -> Airfoil:
        """ design airfoil if it is in airfoils"""
        for airfoil in self.airfoils():
            if airfoil.usedAsDesign: return airfoil 

    @property
    def iDesign (self) -> Airfoil:
        """ iDesign of the Design airfoil - or None if there is no design"""

        for airfoil in self.all_airfoils():
            if airfoil.usedAsDesign: 
                return Case_Abstract.get_iDesign (airfoil)


    def create_diagram_items (self):
        """ create all plot Items and add them to the layout """

        r = 0 
        if self.airfoils()[0].isExample:

            # show Welcome text if Airfoil is the Example arfoil 
            item = Diagram_Item_Welcome (self)
            self._add_item (item, r, 0, colspan=2)                          # item has fixed height
            r += 1

        item = Diagram_Item_Airfoil (self, getter=self.airfoils, 
                                     case_fn=self._case_fn,
                                     iDesign_fn= lambda: self.iDesign)     
        self._add_item (item, r, 0, colspan=2, rowStretch=2)
 
        item.sig_geometry_changed.connect (self._on_geometry_changed)

        r += 1
        item = Diagram_Item_Curvature (self, getter=self.airfoils, show=False)
        item.set_desired_xLink_name (Diagram_Item_Airfoil.name)             # link x axis to airfoil item
        self._add_item (item, r, 0, colspan=2, rowStretch=2)

        if Worker.ready:
            r += 1
            default_settings = [{"xyVars" : (var.CD,var.CL)}, {"xyVars" : (var.CL,var.GLIDE)}]

            for iItem in [0,1]:
                # create Polar items with init values vor axes variables 

                item = Diagram_Item_Polars (self, getter=self.airfoils, 
                                            case_fn=self._case_fn, 
                                            iDesign_fn= lambda: self.iDesign,
                                            show=False)
                item.name = f"{Diagram_Item_Polars.name}_{iItem+1}"                 # set unique name as there a multiple items
                item._set_settings (default_settings[iItem])                           # set default settings first

                item.sig_xyVars_changed.connect       (self._on_xyVars_changed)
                item.sig_opPoint_def_changed.connect  (self._on_opPoint_def_changed)
                item.sig_opPoint_def_selected.connect (self._on_opPoint_def_selected)
                item.sig_opPoint_def_dblClick.connect (self._on_opPoint_def_dblClick)
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
        
            p = Panel_Airfoils (self, getter=self.all_airfoils,
                                airfoils_ref_scale_fn=lambda: self.airfoils_ref_scale,
                                airfoil_designs_fn=lambda: self.airfoil_designs,
                                auto_height=True)
            
            p.sig_airfoil_ref_changed.connect (self.sig_airfoil_ref_changed.emit)
            p.sig_airfoils_to_show_changed.connect (self._on_show_airfoil_changed)
            p.sig_airfoil_design_selected.connect (self.sig_airfoil_design_selected.emit)
            p.sig_airfoils_ref_scale_changed.connect (self.sig_airfoils_ref_scale_changed.emit)

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
                                                   hide=lambda: not self.mode_optimize)

        return self._panel_optimization 


    @property
    def panel_airfoil_settings (self) -> Panel_Airfoil_Settings:
        """ little panel to save, load individual airfoil settings """

        if self._panel_airfoil_settings is None:
            self._panel_airfoil_settings = Panel_Airfoil_Settings (self, getter=lambda:self.all_airfoils()[0], 
                                                   auto_height=True, has_head=False,
                                                   hide=lambda: self.case)      # dont show in optimize and modifiy mode
        return self._panel_airfoil_settings


    @property 
    def show_polar_points (self) -> bool:
        """ show polar operatins points """
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

                Label (l,r,c, colSpan=5, get="Polar definitions") 
                r += 1

                # helper panel for polar definitions 

                p = Panel_Polar_Defs (self, lambda: self.polar_defs, auto_height=True)

                p.sig_polar_def_changed.connect (self.sig_polar_def_changed.emit)

                l.addWidget (p, r, c, 1, 6)

                # polar diagrams variables setting 

                r += 1
                Label (l,r,c, colSpan=4, get="Diagram variables") 
                r += 1
                for i, item in enumerate(self._get_items (Diagram_Item_Polars)):

                    Label       (l,r,c,   width=20, get="y")
                    ComboBox    (l,r,c+1, width=60, obj=item, prop=Diagram_Item_Polars.yVar, options=var.values,
                                    toolTip=f"Select the polar variable of the y axis for diagram {i+1}")
                    SpaceC      (l,c+2,   width=15, stretch=0)
                    Label       (l,r,c+3, width=20, get="x")
                    ComboBox    (l,r,c+4, width=60, obj=item, prop=Diagram_Item_Polars.xVar, options=var.values,
                                    toolTip=f"Select the polar variable of the x axis for diagram {i+1}")
                    SpaceC      (l,c+5)
                    r += 1

                r += 1
                CheckBox (l,r,c, text="Polar points", colSpan=4,
                            get=lambda: self.show_polar_points, set=self.set_show_polar_points,
                            toolTip="Show the polar data points")
                r += 1
                CheckBox (l,r,c, text="Bubbles - see xtr diagram", colSpan=6,
                            get=lambda: self.show_bubbles, set=self.set_show_bubbles,
                            disable=not Worker.can_detect_bubbles(),
                            toolTip=("Show bubbles in the polar diagram - see xtr transition diagram for details.<br>" + \
                                    "<br>Laminar separation bubbles are identified by a range of negative shear stress " + \
                                    "along the airfoil surface.") if Worker.can_detect_bubbles()\
                                        else f"Worker version {Worker.version} cannot detect bubbles")

            else: 
                SpaceR (l,r, height=10, stretch=0) 
                r += 1
                Label (l,r,c, colSpan=4, get="No polars available", fontSize=size.HEADER_SMALL, style=style.COMMENT) 
                r += 1
                SpaceR (l,r, height=10, stretch=0) 
                r += 1
                Label (l,r,c, colSpan=4, get=f"{Worker.NAME} not ready", style=style.ERROR) 
                r += 1
                Label (l,r,c, colSpan=6, get=f"{Worker.ready_msg}", style=style.COMMENT, height=(None,100), wordWrap=True) 
                r += 1
                SpaceR (l,r, height=5) 

            self._panel_polar = Edit_Panel (title=Diagram_Item_Polars.name, layout=l, auto_height=True,
                                            switchable=True, switched_on=False, on_switched=self._on_polars_switched)
            
            # patch Worker version into head of panel 
            if Worker.ready:
                l_head = self._panel_polar._head.layout()
                Label  (l_head, get=f"{Worker.NAME} {Worker.version}", style=style.COMMENT, fontSize=size.SMALL,
                        align=Qt.AlignmentFlag.AlignBottom)

        return self._panel_polar 


    # --- public slots ---------------------------------------------------

    @override
    def set_settings (self, d : dict, settings_for : Airfoil|None = None, refresh=False):
        """ 
        Set self settings and all child diagram items from dictionary 

        Args:
            d (dict): settings dictionary
            settings_for (Airfoil|None): airfoil for which the settings are valid (None = all)
        """

        # update panel_settings with actual loaded airfoil
        self.panel_airfoil_settings.set_settings_loaded_for (settings_for)

        super().set_settings (d)

        if refresh:
            self.refresh()



    @override
    def refresh(self, also_viewRange=True): 

        # hide Welcome item with first refresh
        self._hide_item_welcome()

        # switch off optimize opPoint definitions
        if not self.mode_optimize and self.show_xo2_opPoint_def:
            self.set_show_xo2_opPoint_def (False) 

        super().refresh(also_viewRange=also_viewRange) 


    def on_new_airfoil (self):
        """ slot to handle new airfoil signal """

        logger.debug (f"{str(self)} on new airfoil")
        self.refresh(also_viewRange=False)


    def on_geometry_changed (self):
        """ slot to handle airfoil geometry changed signal """

        logger.debug (f"{str(self)} on airfoil changed")
        self.refresh(also_viewRange=False)


    def on_etc_changed (self):
        """ slot to handle change of ref airfoils  etc. signal """

        logger.debug (f"{str(self)} on change of ref airfoils")
        self.refresh(also_viewRange=False)


    def on_new_polars (self):
        """ slot to handle new polars loaded which were generated async by Worker """

        logger.debug (f"{str(self)} on new polars")

        for item in self._get_items (Diagram_Item_Polars):
            item.refresh ()


    def on_bezier_changed (self, aSide_type: Line.Type):
        """ slot to handle bezier changes (dureing match bezier"""

        # high speed - make direct call to artist
        item : Diagram_Item_Airfoil = self._get_first_item (Diagram_Item_Airfoil)
        item.bezier_artist.refresh_from_side (aSide_type)


    def on_polar_set_changed (self):
        """ slot to handle changed polar set signal """
        logger.debug (f"{str(self)} on polar set changed")

        self.panel_polar.refresh()                     # refresh polar panel
        for artist in self._get_artist (Polar_Artist):
            artist.refresh ()


    def on_xo2_about_to_run (self): 
        """ sot optimization will start soon ..."""

        logger.debug (f"{str(self)} on Xoptfoil2 about to run")

        # switch on opPoints 
        self.set_show_xo2_opPoint_def    (True, refresh=False)
        self.set_show_xo2_opPoint_result (True, refresh=False)

        self.refresh (also_viewRange=False)


    def on_xo2_new_state (self):
        """ slot to handle new status or result of Xoptfoil2"""

        logger.debug (f"{str(self)} on Xoptfoil2 new state")

        # airfoils (final) could have changed
        self.refresh (also_viewRange=False)


    def on_new_case_optimize (self):
        """ slot to handle new case of Xoptfoil2"""

        logger.debug (f"{str(self)} on new case optimize")

        self.refresh (also_viewRange=True)


    def on_mode_optimize (self, aBool):
        """ slot when entering / leaving mode optimze """
        if aBool: 
            self.panel_polar.set_switched_on (True)                         # switch on view polars 
            self.set_show_xo2_opPoint_def (True, refresh=False)             # show opPoint definitions
            self.set_show_xo2_opPoint_result (True,  refresh=False)         # show opPoint result

        self.section_panel.reset_show_reference_airfoils ()                 # show reference airfoils if there are
        self.section_panel.set_show_design_airfoils (not aBool)             # don't show design airfoil initially - would be too much

        self.refresh(also_viewRange=False)


    def on_xo2_opPoint_def_selected (self, ):
        """ slot opPoint def selected - highlight current"""
        artist : Xo2_OpPoint_Defs_Artist
        for artist in self._get_artist (Xo2_OpPoint_Defs_Artist):
            artist.refresh()



    def on_flap_changed (self, aBool : bool):
        """ slot flap settings changed - refresh flap artist"""
        artist : Flap_Artist
        for artist in self._get_artist (Flap_Artist):
            artist.set_show (aBool)


    def on_te_gap_changed (self, te_gap, xBlend):
        """ slot te gap changed - refresh te gap artist"""
        artist : TE_Gap_Artist
        for artist in self._get_artist (TE_Gap_Artist):
            artist.set_xBlend (xBlend)
            artist.set_show (te_gap is not None)


    def on_le_radius_changed (self, le_radius, xBlend):
        """ slot le radius changed- show le_radius artist"""
        artist : LE_Radius_Artist
        for artist in self._get_artist (LE_Radius_Artist):
            artist.set_xBlend (xBlend)
            artist.set_show (le_radius is not None)


    def on_blend_changed (self):
        """ slot to handle blending of airfoil changed signal """

        logger.debug (f"{str(self)} on blend changed")

        # swich off Line artist
        for artist in self._get_artist (Airfoil_Line_Artist):
            if artist.show: artist.set_show (False)

        # update airfoils 
        for artist in self._get_artist (Airfoil_Artist):
            artist.refresh()                          


    def on_panelling_changed (self):
        """ slot to handle blending of airfoil changed signal """

        logger.debug (f"{str(self)} on blend changed")

        # swich off Line artist
        for artist in self._get_artist (Airfoil_Line_Artist):
            if artist.show: artist.set_show (False)

        # switch on show points
        artist : Airfoil_Artist
        for artist in self._get_artist (Airfoil_Artist):
            artist.set_show_points (True)


    # --- private slots ---------------------------------------------------


    def _on_geometry_changed (self):
        """ slot to handle geometry change made in diagram """

        logger.debug (f"{str(self)} on geometry changed in diagram")
    
        self.sig_geometry_changed.emit()             # refresh app



    def _on_polars_switched (self, aBool):
        """ slot to handle polars switched on/off """

        logger.debug (f"{str(self)} on polars switched")

        self._hide_item_welcome ()
    
        for item in self._get_items (Diagram_Item_Polars):
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

        # list of airfoils will be dependend of property "show"
        for item in self.diagram_items:
            if item.isVisible(): 
                item.refresh()


    def _on_xyVars_changed (self):
        """ slot to handle change of xyVars made in diagram """

        logger.debug (f"{str(self)} on xyVars changed in diagram")

        self.panel_polar.refresh()


    def _on_opPoint_def_changed (self):
        """ slot to handle change of xo2 opPoint definition in diagram """

        if self.mode_optimize:
            logger.debug (f"{str(self)} on opPoint_def changed in diagram - save input ")

            self.panel_polar.refresh()

            for artist in self._get_artist (Xo2_OpPoint_Defs_Artist):
                artist.refresh ()
                
            self.sig_opPoint_def_changed.emit ()


    def _on_opPoint_def_selected (self):
        """ slot to handle select of xo2 opPoint definition in diagram """

        if self.mode_optimize:
            logger.debug (f"{str(self)} on opPoint_def selected in diagram")

            for artist in self._get_artist (Xo2_OpPoint_Defs_Artist):
                artist.refresh ()
                
            self.sig_opPoint_def_selected.emit ()


    def _on_opPoint_def_dblClick (self):
        """  slot to handle double click in xo2 opPoint definition in diagram"""

        parentPos=(0.03, 0.05) 
        dialogPos=(0,0)

        self.sig_opPoint_def_dblClick.emit(self, parentPos, dialogPos)
