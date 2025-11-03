#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

UI panels 

"""
from typing                 import TYPE_CHECKING                        # to handle circular imports

import logging

from PyQt6.QtWidgets        import QMenu
from PyQt6.QtGui            import QDesktopServices
from PyQt6.QtCore           import QUrl

from base.widgets           import * 
from base.panels            import Edit_Panel

from model.airfoil          import Airfoil
from model.airfoil_geometry import Geometry, Geometry_Bezier, Curvature_Abstract
from model.airfoil_geometry import Line, Side_Airfoil_Bezier
from model.case             import Case_Abstract, Case_Direct_Design
from model.xo2_driver       import Xoptfoil2

from airfoil_widgets        import * 
from airfoil_dialogs        import (Match_Bezier_Dialog, Matcher, LE_Radius_Dialog, TE_Gap_Dialog,
                                   Blend_Airfoil_Dialog, Flap_Airfoil_Dialog, Repanel_Airfoil_Dialog)

logger = logging.getLogger(__name__)
# logger.setLevel(logging.WARNING)


class Panel_Airfoil_Abstract (Edit_Panel):
    """ 
    Abstract superclass for Edit/View-Panels of AirfoilEditor
        - has semantics of App
        - connect / handle signals 
    """

    if TYPE_CHECKING:                                   # handle circular imports for type checking only
        from app import Main

    @property
    def app (self) -> 'Main':
        return self._app 

    @property
    def airfoil (self) -> Airfoil: 
        return self.dataObject

    @property
    def geo (self) -> Geometry:
        return self.airfoil.geo

    @property    
    def case (self) -> Case_Abstract:
        return self.app.case


    @override
    def _set_panel_layout (self ):
        """ Set layout of self._panel """
        # overridden to connect to widgets changed signal

        super()._set_panel_layout ()
        for w in self.widgets:
            w.sig_changed.connect (self._on_airfoil_widget_changed)
        for w in self.header_widgets:
            w.sig_changed.connect (self._on_airfoil_widget_changed)


    def _on_airfoil_widget_changed (self, widget):
        """ user changed data in widget"""
        logger.debug (f"{self} {widget} widget changed slot")
        self.app._on_airfoil_changed ()


    @property
    def mode_modify (self) -> bool:
        """ panel in mode_modify or disabled ? - from App """
        return self.app.mode_modify


    @property
    def mode_optimize (self) -> bool:
        """ panel in mode_modify or disabled ? - from App """
        return self.app.mode_optimize


    @property
    def mode_bezier (self) -> bool:
        """ True if self is in mode_modify and geo is Bezier """
        return self.airfoil.isBezierBased if self.airfoil else False


    @override
    @property
    def _isDisabled (self) -> bool:
        """ overloaded: only enabled in edit mode of App """
        return not self.mode_modify or (self.airfoil.isFlapped if self.airfoil else False)
    


class Panel_File_View (Panel_Airfoil_Abstract):
    """ File panel with open / save / ... """

    name = 'View Mode'

    @override
    @property
    def _isDisabled (self) -> bool:
        """ override: enabled (as parent data panel is disabled)"""
        return False
    

    def _on_airfoil_widget_changed (self, *_ ):
        """ user changed data in widget"""
        # overloaded - do not react on self widget changes 
        pass


    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""
        l_head.addStretch(1)
        ToolButton   (l_head, icon=Icon.EXPAND, set=self.app.toggle_panel_size,
                      toolTip='Minimize lower panel -<br>Alternatively, you can double click on the lower panels')


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        w =Airfoil_Select_Open_Widget (l,r,c, colSpan=4, signal=False, 
                                    textOpen="&Open", widthOpen=100, 
                                    get=lambda: self.airfoil, set=self.app.set_airfoil)
        w.sig_opened_via_button.connect (self._on_openend_via_button)

        r += 1
        Button (l,r,c, text="&Modify", width=100, 
                set=self.app.modify_airfoil, toolTip="Modify geometry, Normalize, Repanel, Set Flap",
                button_style=button_style.PRIMARY)
        MenuButton (l,r,c+2, text="More...", width=80, 
                menu=self._more_menu(), 
                toolTip="Choose further actions for this airfoil")
        r += 1
        Button (l,r,c, text="&Optimize...", width=100, 
                set=self.app.optimize_select, toolTip=self._tooltip_optimize,
                disable=lambda: not Xoptfoil2.ready)
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Button (l,r,c, text="&Exit", width=100, set=self.app.close)
        l.setColumnStretch (2,2)
        l.setColumnMinimumWidth (1,12)

        return l 
 

    def _more_menu (self) -> QMenu:
        """ create and return sub menu for 'more' actions"""

        menue = QMenu ()

        menue.addAction (MenuAction ("As Bezier based", self, set=self.app.new_as_Bezier, 
                                     disable=lambda: self.airfoil.isBezierBased,
                                     toolTip="Create new Bezier based airfoil of current airfoil"))
        menue.addSeparator ()
        menue.addAction (MenuAction ("Save as...", self, set=self.app.do_save_as,
                                     toolTip="Create a copy of the current airfoil with new name and filename"))
        menue.addAction (MenuAction ("Rename...", self, set=self.app.do_rename,
                                     toolTip="Rename name and/or filename of current airfoil"))
        menue.addAction (MenuAction ("Delete", self, set=self.app.do_delete,
                                     toolTip="Delete current airfoil including all temporary files created by the AirfoilEditor"))
        menue.addAction (MenuAction ("Delete temp files", self, set=self.app.do_delete_temp_files,
                                     toolTip="Delete all temporary files created by the AirfoilEditor just to have a clean directoy again"))
        menue.addSeparator ()
        menue.addAction (MenuAction ("Readme on Github", self, set=self._open_AE_url,
                                     toolTip="Open the Github README file of the AirfoilEditor in a browser"))
        menue.addAction (MenuAction ("Releases on Github", self, set= self._open_releases_url,
                                     toolTip="Open the Github page with the actual release of the AirfoilEditor"))

        menue.setToolTipsVisible(True)

        return menue

    def _on_openend_via_button (self):
        """ slot: airfoil opened via open button """

        # if the new airfoil has individual settings - load them now 
        if self.airfoil.get_property ('has_settings', False):
            self.app._load_airfoil_settings (self.airfoil)


    def _open_releases_url (self):
        """ open Github versions in Browser"""

        link = "https://github.com/jxjo/AirfoilEditor/releases"
        QDesktopServices.openUrl(QUrl(link))


    def _open_AE_url (self):
        """ open Github AirfoilEditor repo in Browser"""

        link = "https://github.com/jxjo/AirfoilEditor"
        QDesktopServices.openUrl(QUrl(link))


    def _tooltip_optimize (self) -> str:
        """ dynamic tooltip to handle xo2 not ready"""

        if Xoptfoil2.ready:
            return f"Optimize an airfoil with {Xoptfoil2.NAME}"
        else: 
            return f"Optimization not possible <br><br><b>{Xoptfoil2.NAME} not ready</b><br><br>{Xoptfoil2.ready_msg}"



class Panel_File_View_Small (Panel_File_View):
    """ View File panel in small version """

    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Airfoil_Select_Open_Widget (l,r,c, colSpan=4, signal=False, 
                                    textOpen="&Open", widthOpen=100, 
                                    get=lambda: self.airfoil, set=self.app.set_airfoil)
        r += 1
        Button      (l,r,c, text="&Exit", width=100, set=self.app.close)
        MenuButton  (l,r,c+2, text="More...", width=80, 
                        menu=self._more_menu(), 
                        toolTip="Choose further actions for this airfoil")
        ToolButton  (l,r,c+3, icon=Icon.COLLAPSE, set=self.app.toggle_panel_size,
                        toolTip='Maximize lower panel -<br>Alternatively, you can double click on the lower panels')

        l.setColumnMinimumWidth (1,12)
        l.setColumnStretch (2,2)
        return l 
 

    def _more_menu (self) -> QMenu:
        """ create and return sub menu for 'more' actions"""

        menue = super()._more_menu ()
        menue.insertAction (menue.actions()[0], MenuAction ("&Optimize", self, set=self.app.optimize_select,   
                                    toolTip="Modify geometry, Normalize, Repanel, Set Flap"))
        menue.insertAction (menue.actions()[0], MenuAction ("&Modify", self, set=self.app.modify_airfoil,   
                                    toolTip=self._tooltip_optimize(), disable=lambda: not Xoptfoil2.ready))
        return menue



class Panel_File_Modify (Panel_Airfoil_Abstract):
    """ File panel with open / save / ... """

    name = 'Modifiy Mode'

    @override
    def title_text (self) -> str: 
        """ returns text of title - default self.name"""
        if self.app.airfoil and self.app.airfoil.geo.isBezier:
             return 'Bezier Mode'
        else: 
            return self.name

    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""
        l_head.addStretch(1)
        ToolButton   (l_head, icon=Icon.EXPAND, set=self.app.toggle_panel_size,
                      toolTip='Minimize lower panel -<br>Alternatively, you can double click on the lower panels')


    @property
    def _isDisabled (self) -> bool:
        """ override: always enabled """
        return False
    
    @property
    def case (self) -> Case_Direct_Design:
        return self.app.case


    def _init_layout (self): 

        self.set_background_color (**mode_color.MODIFY)

        l = QGridLayout()
        r,c = 0, 0 
        Field (l,r,c, colSpan=5,  get=lambda: self.case.airfoil_seed.fileName,
                        toolTip="File name of seed airfoil for design airfoils")
        r += 1
        ComboSpinBox (l,r,c, colSpan=3, width=146, get=self.airfoil_fileName, 
                        set=self.set_airfoil_by_fileName,
                        options=self.airfoil_fileNames, signal=False,
                        toolTip="Select current design airfoil to modify")
        ToolButton   (l,r,c+3, icon=Icon.DELETE, set=self.remove_current_airfoil,
                        hide=lambda: self.case.get_iDesign (self.airfoil) == 0,  # hide Design 0 
                        toolTip="Remove current design airfoil")
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Button (l,r,c,  text="&Finish ...", width=100, 
                        set=lambda : self.app.mode_modify_finished(ok=True), 
                        toolTip="Save current airfoil, optionally modifiy name and leave edit mode")
        r += 1
        Button (l,r,c,  text="&Cancel",  width=100, 
                        set=lambda : self.app.mode_modify_finished(ok=False),
                        toolTip="Cancel modifications of airfoil and leave edit mode")
        l.setColumnMinimumWidth (1,12)
        l.setColumnStretch (4,2)

        return l


    def airfoil_fileName(self) -> list[str]:
        """ fileName of current airfoil without extension"""
        return os.path.splitext(self.airfoil.fileName)[0]


    def airfoil_fileNames(self) -> list[str]:
        """ list of design airfoil fileNames without extension"""

        fileNames = []
        if self.case:
            for airfoil in self.case.airfoil_designs:
                fileNames.append (os.path.splitext(airfoil.fileName)[0])
        return fileNames


    def set_airfoil_by_fileName (self, fileName : str):
        """ set new current design airfoil by fileName"""

        airfoil = self.case.get_design_by_name (fileName)
        self.app.set_airfoil (airfoil)


    def remove_current_airfoil (self):
        """ remove current design and set new current design airfoil by fileName"""

        next_airfoil = self.case.remove_design (self.airfoil)

        if next_airfoil: 
            self.app.set_airfoil (next_airfoil)



class Panel_File_Modify_Small (Panel_File_Modify):
    """ Modify File panel in small version """

    def _init_layout (self): 

        self.set_background_color (**mode_color.MODIFY)

        l = QGridLayout()
        r,c = 0, 0 
        ComboSpinBox (l,r,c, colSpan=3, width=146, get=self.airfoil_fileName, 
                        set=self.set_airfoil_by_fileName,
                        options=self.airfoil_fileNames, signal=False,
                        toolTip="Select current design airfoil to modify")
        ToolButton   (l,r,c+3, icon=Icon.DELETE, set=self.remove_current_airfoil,
                        hide=lambda: self.case.get_iDesign (self.airfoil) == 0,
                        toolTip="Remove current design airfoil")  
        ToolButton  (l,r,c+5, icon=Icon.COLLAPSE, set=self.app.toggle_panel_size,
                        toolTip='Maximize lower panel -<br>Alternatively, you can double click on the lower panels')
        r += 1
        Button (l,r,c,  text="&Finish ...", width=100, 
                        set=lambda : self.app.mode_modify_finished(ok=True), 
                        toolTip="Save current airfoil, optionally modifiy name and leave edit mode")
        Button (l,r,c+2,text="&Cancel",  width=80, colSpan=3,
                        set=lambda : self.app.mode_modify_finished(ok=False),
                        toolTip="Cancel modifications of airfoil and leave edit mode")
        l.setColumnMinimumWidth (1,12)
        l.setColumnStretch (4,2)
        return l



class Panel_Geometry (Panel_Airfoil_Abstract):
    """ Main geometry data of airfoil"""

    name = 'Geometry'
#    _width  = 380
    print ("geo !!")
    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        # blend with airfoil - currently Bezier is not supported
        Button (l_head, text="&Blend", width=75,
                set=self.do_blend_with, 
                hide=lambda: not self.mode_modify or self.airfoil.isBezierBased,
                toolTip="Blend original airfoil with another airfoil")


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        FieldF (l,r,c, lab="Thickness", width=75, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.max_thick,
                disable=lambda: self.airfoil.isBezierBased)
        r += 1
        FieldF (l,r,c, lab="Camber", width=75, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.max_camb,
                disable=lambda: self.airfoil.isBezierBased or self.airfoil.isSymmetrical)
        r += 1
        FieldF (l,r,c, lab="LE radius", width=75, unit="%", step=0.02,
                obj=lambda: self.geo, prop=Geometry.le_radius, disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self.do_le_radius, 
                hide=lambda: not self.mode_modify or self.mode_bezier,
                toolTip="Set leading edge radius with a flexible blending range")
        r += 1
        FieldF (l,r,c, lab="TE gap", width=75, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.te_gap, disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self.do_te_gap,
                hide=lambda: not self.mode_modify or self.mode_bezier,
                toolTip="Set trailing edge gap with a flexible blending range")
        r += 1
        SpaceR (l,r, height=5)
        r += 1
        Label  (l,r,0,colSpan=5, get=self._messageText, style=style.COMMENT, height=(None,None))
        l.setColumnMinimumWidth (c,80)
        l.setColumnMinimumWidth (c+2,30)
        l.setColumnStretch (c+3,2)

        r,c = 0,4 
        FieldF (l,r,c, lab="at", width=75, unit="%", step=0.2,
                obj=lambda: self.geo, prop=Geometry.max_thick_x,
                disable=lambda: self.airfoil.isBezierBased)
        r += 1
        FieldF (l,r,c, lab="at", width=75, unit="%", step=0.2,
                obj=lambda: self.geo, prop=Geometry.max_camb_x,
                disable=lambda: self.airfoil.isBezierBased or self.airfoil.isSymmetrical)
        r += 1
        FieldF (l,r,c, lab="LE curv", width=75, dec=0, disable=True,
                obj=lambda: self.geo.curvature, prop=Curvature_Abstract.max_around_le)
        r += 1
        FieldF (l,r,c, lab="TE curv", width=75, dec=0, disable=True,
                obj=lambda: self.geo.curvature, prop=Curvature_Abstract.max_te,
                style=lambda: style.NORMAL if self.geo.curvature.max_te <2 else style.WARNING)

        l.setColumnMinimumWidth (4,60)
        return l 


    def _messageText (self): 
        """ text to show at bottom of panel"""

        if self.geo.curvature.max_te >= 2:
            text = f"- Curvature at trailing edge is quite high"
        else:
            text = f"Geometry {self.geo.description}"
        return text 


    def do_blend_with (self): 
        """ blend with another airfoil - open blend airfoil dialog """ 

        dialog = Blend_Airfoil_Dialog (self, self.airfoil, self.app.airfoil_seed, 
                                       parentPos=(0.25, 0.75), dialogPos=(0,1))  

        dialog.sig_blend_changed.connect (self.app.sig_blend_changed.emit)
        dialog.sig_airfoil_2_changed.connect (self.app.set_airfoil_2)

        dialog.exec()     

        if dialog.airfoil2 is not None: 
            # do final blend with high quality (splined) 
            self.airfoil.geo.blend (self.app.airfoil_seed.geo, 
                                      dialog.airfoil2.geo, 
                                      dialog.blendBy) 
            self.app.set_airfoil_2 (None)
            self.app._on_airfoil_changed()



    def do_le_radius (self): 
        """ set LE radius - run set LE radius dialog""" 

        if self.airfoil.isBezierBased: return                   # not for Bezier airfoils

        dialog = LE_Radius_Dialog (self, self.airfoil, parentPos=(0.25, 0.75), dialogPos=(0,1))

        self.app.sig_le_radius_changed.emit(dialog.le_radius, dialog.xBlend)     # diagram show le radius
        dialog.sig_new_le_radius.connect    (self.app.sig_le_radius_changed.emit)

        dialog.exec()     

        if dialog.has_been_set:
            # finalize modifications 
            self.airfoil.geo.set_le_radius (dialog.le_radius, xBlend= dialog.xBlend)              

            self.app._on_airfoil_changed()

        self.app.sig_le_radius_changed.emit(None, None)                         # diagram hide le radius


    def do_te_gap (self): 
        """ set TE gap - run set TE gap dialog""" 

        if self.airfoil.isBezierBased: return                   # not for Bezier airfoils

        dialog = TE_Gap_Dialog (self, self.airfoil, parentPos=(0.25, 0.75), dialogPos=(0,1))

        self.app.sig_te_gap_changed.emit(dialog.te_gap, dialog.xBlend)     # diagram show le radius
        dialog.sig_new_te_gap.connect (self.app.sig_te_gap_changed.emit)

        dialog.exec()     

        if dialog.has_been_set:
            # finalize modifications 
            self.airfoil.geo.set_te_gap (dialog.te_gap, xBlend= dialog.xBlend)              

            self.app._on_airfoil_changed()

        self.app.sig_te_gap_changed.emit(None, None)                         # diagram hide le radius




class Panel_Geometry_Small (Panel_Geometry):
    """ Main geometry data of airfoil - small version"""

    _panel_margins = (0, 0, 0, 0)

    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        FieldF (l,r,c, lab="Thickness", width=75, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.max_thick,
                disable=lambda: self.airfoil.isBezierBased)
        r += 1
        FieldF (l,r,c, lab="Camber", width=75, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.max_camb,
                disable=lambda: self.airfoil.isBezierBased or self.airfoil.isSymmetrical)
        l.setColumnMinimumWidth (c,80)
        l.setColumnMinimumWidth (c+2,15)
        r,c = 0, 3 
        FieldF (l,r,c, lab="at", width=75, unit="%", step=0.2,
                obj=lambda: self.geo, prop=Geometry.max_thick_x,
                disable=lambda: self.airfoil.isBezierBased)
        r += 1
        FieldF (l,r,c, lab="at", width=75, unit="%", step=0.2,
                obj=lambda: self.geo, prop=Geometry.max_camb_x,
                disable=lambda: self.airfoil.isBezierBased or self.airfoil.isSymmetrical)
        l.setColumnMinimumWidth (c,20)
        c += 2
        l.setColumnMinimumWidth (c,15)
        c += 1
        r = 0
        FieldF (l,r,c, lab="LE radius", width=75, unit="%", step=0.02,
                obj=lambda: self.geo, prop=Geometry.le_radius, disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self.do_le_radius, 
                hide=lambda: not self.mode_modify or self.mode_bezier,
                toolTip="Set leading edge radius with a flexible blending range")
        r += 1
        FieldF (l,r,c, lab="TE gap", width=75, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.te_gap, disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self.do_te_gap,
                hide=lambda: not self.mode_modify or self.mode_bezier,
                toolTip="Set trailing edge gap with a flexible blending range")
        l.setColumnMinimumWidth (c,80)
        l.setColumnStretch (c+3,2)
        return l 



class Panel_Panels (Panel_Airfoil_Abstract):
    """ Panelling information """

    name = 'Panels'

    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        # repanel airfoil - currently Bezier is not supported
        Button (l_head, text="&Repanel", width=75,
                set=self.do_repanel, 
                hide=lambda: not self.mode_modify,
                disable=lambda: self.geo.isBasic or self.geo.isHicksHenne,
                toolTip="Repanel airfoil with a new number of panels" ) 


    def _init_layout (self):

        l = QGridLayout()
        r,c = 0, 0 
        FieldI (l,r,c, lab="No of panels", disable=True, width=75, style=self._style_panel,
                get=lambda: self.geo.nPanels, )
        r += 1
        FieldF (l,r,c, lab="Angle at LE", width=75, dec=1, unit="°", style=self._style_angle,
                get=lambda: self.geo.panelAngle_le)
        SpaceC (l,c+2, width=10, stretch=0)
        Label  (l,r,c+3,width=70, get=lambda: f"at index {self.geo.iLe}", style=style.COMMENT)
        r += 1
        FieldF (l,r,c, lab="Angle min", width=75, dec=1, unit="°",
                get=lambda: self.geo.panelAngle_min[0])
        Label  (l,r,c+3, get=lambda: f"at index {self.geo.panelAngle_min[1]}", style=style.COMMENT)
        r += 1
        SpaceR (l,r,height=5)
        r += 1
        Label  (l,r,0,colSpan=4, get=self._messageText, style=style.COMMENT, height=(None,None))

        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (c+4,1)    
        return l
 

    def do_repanel (self): 
        """ repanel airfoil - open repanel dialog""" 

        dialog = Repanel_Airfoil_Dialog (self, self.airfoil.geo,
                                         parentPos=(0.35, 0.75), dialogPos=(0,1))

        self.app.sig_panelling_changed.emit()                 # diagram show panelling
        dialog.sig_new_panelling.connect (self.app.sig_panelling_changed.emit)

        dialog.exec()     

        if dialog.has_been_repaneled:
            # finalize modifications 
            self.airfoil.geo.repanel (just_finalize=True)                

            self.app._on_airfoil_changed()


    def _on_panelling_finished (self, aSide : Side_Airfoil_Bezier):
        """ slot for panelling (dialog) finished - reset airfoil"""


    def _style_panel (self):
        """ returns style.WARNING if panels not in range"""
        if self.geo.nPanels < 120 or self.geo.nPanels > 260: 
            return style.WARNING
        else: 
            return style.NORMAL


    def _style_angle (self):
        """ returns style.WARNING if panel angle too blunt"""
        if self.geo.panelAngle_le > Geometry.LE_PANEL_ANGLE_TOO_BLUNT: 
            return style.WARNING
        elif self.geo.panelAngle_le < Geometry.PANEL_ANGLE_TOO_SHARP: 
            return style.WARNING
        else: 
            return style.NORMAL

    def _messageText (self): 

        text = []
        minAngle, iAngle = self.geo.panelAngle_min

        if self.geo.panelAngle_le == 180.0: 
            text.append("- Leading edge has 2 points")
        elif self.geo.panelAngle_le > Geometry.LE_PANEL_ANGLE_TOO_BLUNT: 
            text.append(f"- Panel angle at LE {self.geo.panelAngle_le:.1f}° is too blunt")

        if self.geo.panelAngle_le < Geometry.PANEL_ANGLE_TOO_SHARP: 
            text.append(f"- Panel angle at LE {self.geo.panelAngle_le:.1f}° is too sharp")
        elif minAngle < Geometry.PANEL_ANGLE_TOO_SHARP: 
            text.append(f"- Panel angle at i={iAngle} is < {Geometry.PANEL_ANGLE_TOO_SHARP}°")

        if self.geo.nPanels < 100 or self.geo.nPanels > 200: 
            text.append("- No of panels should be > 100 and < 200")
        
        text = '\n'.join(text)
        return text 



class Panel_Panels_Small (Panel_Panels):
    """ Panelling information - small version"""

    _panel_margins = (0, 0, 0, 0)

    def _init_layout (self):

        l = QGridLayout()
        r,c = 0, 0 
        FieldI (l,r,c, lab="No of panels", disable=True, width=75, style=self._style_panel,
                get=lambda: self.geo.nPanels, )
        r += 1
        Button (l,r,c+1, text="&Repanel", width=75,
                set=self.do_repanel, hide=lambda: not self.mode_modify,
                disable=lambda: self.geo.isBasic or self.geo.isHicksHenne,
                toolTip="Repanel airfoil with a new number of panels" ) 
        r += 1
        l.setRowStretch (r,2)
        l.setColumnMinimumWidth (0,80)
        return l
 


class Panel_Flap (Panel_Airfoil_Abstract):
    """ Flap information and set flap"""

    name = 'Flap'
    _width  = 240

    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is Bezier """
        isProbablyFlapped = self.airfoil.geo.isProbablyFlapped if self.airfoil else False
        return (self.mode_modify or isProbablyFlapped) and not self.mode_bezier


    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        Button (l_head, text="Set F&lap", width=75,
                set=self.do_flap, hide=lambda: not self.mode_modify,
                disable=self._set_flap_disabled,
                toolTip="Set flap at airfoil" ) 


    def _set_flap_disabled (self) -> bool:
        """ True if set flap is not possible"""

        if self.geo.isBezier or self.geo.isHicksHenne: 
            return True
        elif self.mode_modify:
            return not self.airfoil.flap_setter                       # no flapper, no set flap 
        else:
            return True


    def _init_layout (self):

        geo             = self.airfoil.geo

        l = QGridLayout()
        r,c = 0, 0 

        if self.mode_modify:

            flap_setter         = self.airfoil.flap_setter
            airfoil_flapped = flap_setter.airfoil_flapped if flap_setter else None

            if airfoil_flapped:
                FieldF (l,r,c, lab="Hinge x", width=50, get=lambda: flap_setter.x_flap, dec=1, unit="%")
                r += 1
                FieldF (l,r,c, lab="Flap Angle", width=50, dec=1, unit='°', get=lambda: flap_setter.flap_angle)
                r +=1
                Field (l,r,c, lab="Based on", width=120,
                       get=flap_setter.airfoil_base.fileName)
                r += 1
                SpaceR (l,r, stretch=2)
                r += 1
                lab =Label  (l,r,c, width=None, height=(40,None), colSpan=3, style=style.COMMENT, wordWrap=True,
                        get="As the base airfoil is still available, another flap setting can be applied.")
                lab.setAlignment (ALIGN_BOTTOM)
                l.setRowStretch (r,1)
                l.setColumnMinimumWidth (0,80)
                l.setColumnStretch (2,3)

            elif flap_setter:

                SpaceR (l,r, stretch=2)
                r += 1
                lab =Label  (l,r,c, width=None,  colSpan=3, style=style.COMMENT, wordWrap=True,
                             get="Ready to set flap")
                l.setColumnStretch (2,3)

            elif self.airfoil.isFlapped:
                FieldF (l,r,c, lab="Hinge x", width=50, get=lambda: geo.curvature.flap_kink_at, dec=1, unit="%")
                r += 1
                FieldF (l,r,c, lab="Flap Angle", width=50, dec=1, unit='°', get=lambda: geo.flap_angle_estimated)
                r +=1
                SpaceR (l,r, stretch=2)
                r += 1
                lab =Label  (l,r,c, width=None, colSpan=3, style=style.WARNING,
                             styleRole=QPalette.ColorRole.Window, 
                             get="The airfoil is already flapped.")
                r += 1
                lab =Label  (l,r,c, width=None, height=(40,None), colSpan=3, style=style.COMMENT, wordWrap=True, 
                             get="Choose a Design, which is not flapped to set a flap.")
                lab.setAlignment (ALIGN_BOTTOM)
                l.setRowStretch (r,1)
                l.setColumnMinimumWidth (0,80)
                l.setColumnStretch (2,3)

        else: 
            # mode not modify - info about a flap which is (could be) set
            
            if geo.isFlapped:
                
                FieldF (l,r,c, lab="Hinge x", width=50, get=lambda: geo.curvature.flap_kink_at, dec=1, unit="%")
                r += 1
                FieldF (l,r,c, lab="Flap Angle", width=50, dec=1, unit='°', get=lambda: geo.flap_angle_estimated)
                r +=1
                SpaceR (l,r, stretch=2)
                r += 1
                lab =Label  (l,r,c, width=None, colSpan=3, style=style.COMMENT, wordWrap=True, 
                             get="The airfoil has a set flap.")
                l.setColumnMinimumWidth (0,80)
                l.setColumnStretch (2,3)
                                
            elif geo.isProbablyFlapped:

                SpaceR (l,r, stretch=2)
                r += 1
                lab =Label  (l,r,c, width=None, height=(80,None), colSpan=3, style=style.COMMENT, wordWrap=True, 
                             get="The airfoil is probably flapped, but a kink in the contour couldn't be detected on both sides.")
                lab.setAlignment (ALIGN_BOTTOM)
                l.setColumnStretch (2,3)

        return l


    def do_flap (self): 
        """ set flaps - run set flap dialog""" 

        dialog = Flap_Airfoil_Dialog (self, self.airfoil, parentPos=(0.55, 0.80), dialogPos=(0,1))

        self.app.sig_flap_changed.emit (True)                        # diagram show flap settings
        dialog.sig_new_flap_settings.connect (self.app.sig_flap_changed.emit)

        dialog.exec()     

        if dialog.has_been_flapped:
            # finalize modifications 
            self.airfoil.do_flap ()              

            self.app._on_airfoil_changed()

        self.app.sig_flap_changed.emit (False)                       # diagram hide flap settings


    @override
    def refresh(self, reinit_layout=False):

        # force new layout to show different flpa states 
        return super().refresh(reinit_layout=True)


class Panel_Flap_Small (Panel_Flap):
    """ Flap information and set flap"""

    _width  = None
    _panel_margins = (0, 0, 0, 0)

    def _init_layout (self):

        geo             = self.airfoil.geo

        l = QGridLayout()
        r,c = 0, 0 

        if self.mode_modify:

            flap_setter         = self.airfoil.flap_setter
            airfoil_flapped = flap_setter.airfoil_flapped if flap_setter else None

            if airfoil_flapped:
                FieldF (l,r,c, lab="Flap Angle", width=75, dec=1, unit='°', get=lambda: flap_setter.flap_angle)

            elif flap_setter:
                l.setRowStretch (c,1)

            elif self.airfoil.isFlapped:
                FieldF (l,r,c, lab="Flap Angle", width=75, dec=1, unit='°', get=lambda: geo.flap_angle_estimated)
 
            r += 1
            Button (l,r,c+1, text="Set F&lap", width=75,
                    set=self.do_flap, hide=lambda: not self.mode_modify,
                    disable=self._set_flap_disabled,
                    toolTip="Set flap at airfoil" ) 
            l.setColumnMinimumWidth (0,80)

        else: 
            # mode not modify - info about a flap which is (could be) set
            
            if geo.isFlapped:
                
                FieldF (l,r,c, lab="Flap Angle", width=50, dec=1, unit='°', get=lambda: geo.flap_angle_estimated)
                r += 1
                FieldF (l,r,c, lab="Hinge x", width=50, get=lambda: geo.curvature.flap_kink_at, dec=1, unit="%")
                l.setColumnMinimumWidth (0,80)
                                
            elif geo.isProbablyFlapped:

                Label  (l,r,c, width=None, colSpan=2, style=style.COMMENT, 
                             get="The airfoil is probably flapped")
                l.setColumnMinimumWidth (0,80)
                l.setColumnMinimumWidth (1,50)
                l.setRowStretch (1,1)

        return l



class Panel_LE_TE  (Panel_Airfoil_Abstract):
    """ info about LE and TE coordinates"""

    name = 'LE, TE'

    _width  = None

    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is not Bezier """
        return not self.mode_bezier 


    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        Button (l_head, text="&Normalize", width=75,
                set=lambda : self.airfoil.normalize(), signal=True, 
                hide=lambda: not self.mode_modify,
                toolTip="Normalize airfoil to get leading edge at 0,0 and trailing edge at x=1.0")


    def _init_layout (self): 

        l = QGridLayout()     
        r,c = 0, 0 
        FieldF (l,r,c, lab="Leading edge x,y", get=lambda: self.geo.le[0], width=75, dec=7, style=lambda: self._style (self.geo.le[0], 0.0))
        r += 1
        FieldF (l,r,c, lab="  ... of spline", get=lambda: self.geo.le_real[0], width=75, dec=7, style=self._style_le_real,
                hide=lambda: not self.mode_modify)
        r += 1
        FieldF (l,r,c, lab="Trailing edge x,y", get=lambda: self.geo.te[0], width=75, dec=7, style=lambda: self._style (self.geo.te[0], 1.0))
        r += 1
        FieldF (l,r,c,lab="  ... lower", get=lambda: self.geo.te[2], width=75, dec=7, style=lambda: self._style (self.geo.te[0], 1.0))
        l.setColumnMinimumWidth (0,95)
        l.setColumnMinimumWidth (2,10)
        l.setColumnStretch (2,1)
        r,c = 0, 3 
        FieldF (l,r,c+1,get=lambda: self.geo.le[1], width=75, dec=7, style=lambda: self._style (self.geo.le[1], 0.0))
        r += 1
        FieldF (l,r,c+1,get=lambda: self.geo.le_real[1], width=75, dec=7, style=self._style_le_real,
                hide=lambda: not self.mode_modify)
        r += 1
        FieldF (l,r,c+1,get=lambda: self.geo.te[1], width=75, dec=7, style=lambda: self._style (self.geo.te[1], -self.geo.te[3]))
        r += 1
        FieldF (l,r,c+1,get=lambda: self.geo.te[3], width=75, dec=7, style=lambda: self._style (self.geo.te[3], -self.geo.te[1]))
        r += 1
        SpaceR (l,r, height=5)
        r += 1
        Label  (l,r,0,colSpan=5, get=self._messageText, style=style.COMMENT, height=(None,None))
        return l


    def _style_le_real (self):
        """ returns style.WARNING if LE spline isn't close to LE"""
        if self.geo.isLe_closeTo_le_real: 
            if self.geo.isBasic:
                return style.NORMAL
            else: 
                return style.NORMAL
        else: 
            return style.WARNING


    def _style (self, val, target_val):
        """ returns style.WARNING if val isn't target_val"""
        if val != target_val and not self.airfoil.isFlapped: 
            return style.WARNING
        else: 
            return style.NORMAL


    def _messageText (self): 

        text = []
        if not self.geo.isNormalized:
            if self.geo.isSplined and not self.geo.isLe_closeTo_le_real:
                text.append("- Leading edge of spline is not at 0,0")
            elif self.geo.le[0] != 0.0 or self.geo.le[1] != 1.0 : 
                text.append("- Leading edge is not at 0,0")
        if not self.airfoil.isFlapped:
            if self.geo.te[0] != 1.0 or self.geo.te[2] != 1.0 : 
                text.append("- Trailing edge x is not at 1.0")
            if self.geo.te[1] != -self.geo.te[3]: 
                text.append("- Trailing edge y is not symmetrical")

        if not text:
            if self.geo.isSymmetrical: 
                text.append("Airfoil is symmetrical")
            else: 
                text.append("Airfoil is normalized")

        text = '\n'.join(text)
        return text 



class Panel_LE_TE_Small  (Panel_LE_TE):
    """ info about LE and TE coordinates - small version"""

    _panel_margins = (0, 0, 0, 0)

    def _init_layout (self): 

        l = QGridLayout()     
        r,c = 0, 0 
        FieldF (l,r,c, lab="LE x,y", get=lambda: self.geo.le[0], width=75, dec=7, style=lambda: self._style (self.geo.le[0], 0.0))
        r += 1
        FieldF (l,r,c, lab="TE xm,ym",  width=75, dec=7, 
                get=lambda: (self.geo.te[0] + self.geo.te[2]) / 2, style=lambda: self._style (self.geo.te[0], 1.0))
        l.setColumnMinimumWidth (0,80)
        l.setColumnMinimumWidth (2,10)
        r,c = 0, 3 
        FieldF (l,r,c+1,get=lambda: self.geo.le[1], width=75, dec=7, style=lambda: self._style (self.geo.le[1], 0.0))
        r += 1
        FieldF (l,r,c+1,get=lambda: (self.geo.te[1] + self.geo.te[3])/2, width=75, dec=7, style=lambda: self._style (self.geo.te[1], -self.geo.te[3]))

        r,c = 1, 5 
        l.setColumnMinimumWidth (c,15)
        Button (l,r,c+1, text="&Normalize", width=75,
                set=lambda : self.airfoil.normalize(), signal=True, 
                hide=lambda: not self.mode_modify,
                toolTip="Normalize airfoil to get leading edge at 0,0 and trailing edge at x=1.0")
        return l



class Panel_Bezier (Panel_Airfoil_Abstract):
    """ Info about Bezier curves upper and lower  """

    name = 'Bezier'

    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is Bezier """
        return self.mode_bezier

    @override
    @property
    def geo (self) -> Geometry_Bezier:
        return super().geo

    @property
    def upper (self) -> Side_Airfoil_Bezier:
        if self.geo.isBezier:
            return self.geo.upper

    @property
    def lower (self) -> Side_Airfoil_Bezier:
        if self.geo.isBezier:
            return self.geo.lower


    def _init_layout (self):

        l = QGridLayout()
        r,c = 0, 0 
        Label (l,r,c, get="Bezier control Points", colSpan=4)
        r += 1
        FieldI (l,r,c,   lab="Upper side", get=lambda: self.upper.nControlPoints,  width=50, step=1, lim=(3,10),
                         set=lambda n : self.geo.set_nControlPoints_of (self.upper, n))
        r += 1
        FieldI (l,r,c,   lab="Lower side",  get=lambda: self.lower.nControlPoints,  width=50, step=1, lim=(3,10),
                         set=lambda n : self.geo.set_nControlPoints_of (self.lower, n))
        r += 1
        l.setRowStretch (r,2)
        l.setColumnMinimumWidth (0,80)
        return l
 

class Panel_Bezier_Small (Panel_Bezier):
    """ Info about Bezier curves upper and lower - small version """

    _panel_margins = (0, 0, 0, 0)

    def _init_layout (self):

        l = QGridLayout()
        r,c = 0, 0 
        FieldI (l,r,c,   lab="Bezier Upper", get=lambda: self.upper.nControlPoints,  width=50, step=1, lim=(3,10),
                         set=lambda n : self.geo.set_nControlPoints_of (self.upper, n))
        r += 1
        FieldI (l,r,c,   lab="Bezier Lower",  get=lambda: self.lower.nControlPoints,  width=50, step=1, lim=(3,10),
                         set=lambda n : self.geo.set_nControlPoints_of (self.lower, n))
        l.setColumnMinimumWidth (0,80)
        return l



class Panel_Bezier_Match (Panel_Airfoil_Abstract):
    """ Match Bezier functions  """

    name = 'Bezier Match'

    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is Bezier """
        return self.mode_bezier

    @property
    def upper (self) -> Side_Airfoil_Bezier:
        if self.geo.isBezier: return self.geo.upper

    @property
    def lower (self) -> Side_Airfoil_Bezier:
        if self.geo.isBezier: return self.geo.lower

    @property
    def curv_upper (self) -> Line:
        if self.geo.isBezier:
            return self.geo.curvature.upper

    @property
    def curv_lower (self) -> Line:
        if self.geo.isBezier:
            return self.geo.curvature.lower

    @property
    def curv (self) -> Curvature_Abstract:
        return self.geo.curvature

    @property
    def target_airfoil (self) -> Airfoil:
        return self.app.airfoil_seed

    @property
    def target_upper (self) -> Line:
        if self.target_airfoil: return self.target_airfoil.geo.upper

    @property
    def target_lower (self) -> Line:
        if self.target_airfoil: return self.target_airfoil.geo.lower

    @property
    def target_curv_le (self) -> float:
        return self.target_airfoil.geo.curvature.best_around_le

    @property
    def max_curv_te_upper (self) -> Line:
        if self.target_airfoil: return self.target_airfoil.geo.curvature.at_upper_te

    @property
    def max_curv_te_lower (self) -> Line:
        if self.target_airfoil: return self.target_airfoil.geo.curvature.at_lower_te

    def norm2_upper (self): 
        """ norm2 deviation of airfoil to target - upper side """
        if self._norm2_upper is None: 
            self._norm2_upper = Line.norm2_deviation_to (self.upper.bezier, self.target_upper) 
        return  self._norm2_upper    


    def norm2_lower (self): 
        """ norm2 deviation of airfoil to target  - upper side """
        if self._norm2_lower is None: 
            self._norm2_lower = Line.norm2_deviation_to (self.lower.bezier, self.target_lower)  
        return self._norm2_lower


    def _init_layout (self):

        self._norm2_upper = None                                # cached value of norm2 deviation 
        self._norm2_lower = None                                # cached value of norm2 deviation 
        self._target_curv_le = None 
        self._target_curv_le_weighting = None

        l = QGridLayout()

        if self.target_airfoil is not None: 

            self._target_curv_le = self.target_airfoil.geo.curvature.best_around_le 

            r,c = 0, 0 
            Label  (l,r,c+1, get="Deviation", width=70, colSpan=2)
            r += 1
            Label  (l,r,c,   get="Upper Side")
            FieldF (l,r,c+1, width=60, dec=3, unit="%", get=self.norm2_upper,
                             style=lambda: Match_Bezier_Dialog.style_deviation (self.norm2_upper()))
            r += 1
            Label  (l,r,c,   get="Lower Side")
            FieldF (l,r,c+1, width=60, dec=3, unit="%", get=self.norm2_lower,
                             style=lambda: Match_Bezier_Dialog.style_deviation (self.norm2_lower()))
            l.setColumnMinimumWidth (c,80)
            l.setColumnMinimumWidth (c+2,20)

            r,c = 0, 3 
            Label (l,r,c, colSpan=3, get="LE curvature TE")
            r += 1
            FieldF (l,r,c  , get=lambda: self.curv_upper.max_xy[1], width=40, dec=0, 
                    style=lambda: Match_Bezier_Dialog.style_curv_le(self._target_curv_le, self.curv_upper))
            FieldF (l,r,c+1, get=lambda: self.curv_upper.te[1],     width=40, dec=1, 
                    style=lambda: Match_Bezier_Dialog.style_curv_te(self.max_curv_te_upper, self.curv_upper))

            r += 1
            FieldF (l,r,c  , get=lambda: self.curv_lower.max_xy[1], width=40, dec=0, 
                    style=lambda: Match_Bezier_Dialog.style_curv_le(self._target_curv_le, self.curv_lower))
            FieldF (l,r,c+1, get=lambda: self.curv_lower.te[1],     width=40, dec=1, 
                    style=lambda: Match_Bezier_Dialog.style_curv_te(self.max_curv_te_lower, self.curv_lower))
            l.setColumnMinimumWidth (c+2,20)

            r,c = 0, 6 
            r += 1
            Button (l,r,c  , text="Match...", width=70,
                            set=lambda: self._match_bezier (self.upper, self.target_upper, 
                                                            self.target_curv_le, self.max_curv_te_upper))
            r += 1
            Button (l,r,c  , text="Match...", width=70,
                            set=lambda: self._match_bezier (self.lower, self.target_lower, 
                                                            self.target_curv_le, self.max_curv_te_lower))
            c = 0 
            r += 1
            SpaceR (l,r, height=5, stretch=2)
            r += 1
            Label  (l,r,0, get=self._messageText, colSpan=7, height=(40, None), style=style.COMMENT)
        return l
 

    def _match_bezier (self, aSide : Side_Airfoil_Bezier, aTarget_line : Line, 
                            target_curv_le: float, max_curv_te : float  ): 
        """ run match bezier (dialog) """ 

        match_bezier = Match_Bezier_Dialog (self, aSide, aTarget_line,
                                    target_curv_le = target_curv_le,
                                    max_curv_te = max_curv_te,
                                    parentPos=(0.1, 0.05), dialogPos=(0.5,1))

        match_bezier.sig_new_bezier.connect     (self.app.sig_bezier_changed.emit)
        match_bezier.sig_pass_finished.connect  (self.app.sig_geometry_changed.emit)
        match_bezier.sig_match_finished.connect (self._on_match_finished)

        # leave button press callback 
        timer = QTimer()                                
        timer.singleShot(10, lambda: match_bezier.exec())     # delayed emit 
       

    def _on_match_finished (self, aSide : Side_Airfoil_Bezier):
        """ slot for match Bezier finished - reset airfoil"""

        geo : Geometry_Bezier = self.geo
        geo.finished_change_of (aSide)              # will reset and handle changed  

        self.app._on_airfoil_changed()


    @override
    def refresh (self, reinit_layout=False):

        # reset cached deviations
        self._norm2_lower = None
        self._norm2_upper = None 
        super().refresh(reinit_layout=reinit_layout)
        

    def _messageText (self): 
        """ user warnings"""
        text = []
        r_upper_dev = Matcher.result_deviation (self.norm2_upper())
        r_lower_dev = Matcher.result_deviation (self.norm2_lower())

        r_upper_le = Matcher.result_curv_le (self._target_curv_le, self.curv_upper)
        r_lower_le = Matcher.result_curv_le (self._target_curv_le, self.curv_lower)
        r_upper_te = Matcher.result_curv_te (self.max_curv_te_upper,self.curv_upper)
        r_lower_te = Matcher.result_curv_te (self.max_curv_te_lower, self.curv_lower)

        is_bad = Matcher.result_quality.BAD
        if r_upper_dev == is_bad or r_lower_dev == is_bad:
           text.append("- Deviation is quite high")
        if r_upper_le == is_bad or r_lower_le == is_bad:
           text.append(f"- Curvature at LE differs too much from target ({int(self._target_curv_le)})")
        if r_upper_te == is_bad or r_lower_te == is_bad:
           text.append("- Curvature at TE is quite high")

        text = '\n'.join(text)
        return text 



class Panel_Bezier_Match_Small (Panel_Bezier_Match):
    """ Match Bezier functions - small version """

    _panel_margins = (0, 0, 0, 0)

    def _init_layout (self):

        self._norm2_upper = None                                # cached value of norm2 deviation 
        self._norm2_lower = None                                # cached value of norm2 deviation 
        self._target_curv_le = None 
        self._target_curv_le_weighting = None

        l = QGridLayout()

        if self.target_airfoil is not None: 

            self._target_curv_le = self.target_airfoil.geo.curvature.best_around_le 

            r,c = 0, 0 
            Label  (l,r,c,   get="Deviation Upper")
            FieldF (l,r,c+1, width=60, dec=3, unit="%", get=self.norm2_upper,
                             style=lambda: Match_Bezier_Dialog.style_deviation (self.norm2_upper()))
            r += 1
            Label  (l,r,c,   get="Deviation Lower")
            FieldF (l,r,c+1, width=60, dec=3, unit="%", get=self.norm2_lower,
                             style=lambda: Match_Bezier_Dialog.style_deviation (self.norm2_lower()))
            l.setColumnMinimumWidth (c,90)
            l.setColumnMinimumWidth (c+2,20)
            r,c = 0, 3
            Button (l,r,c  , text="Match...", width=70,
                            set=lambda: self._match_bezier (self.upper, self.target_upper, 
                                                            self.target_curv_le, self.max_curv_te_upper))
            r += 1
            Button (l,r,c  , text="Match...", width=70,
                            set=lambda: self._match_bezier (self.lower, self.target_lower, 
                                                            self.target_curv_le, self.max_curv_te_lower))
            return l
