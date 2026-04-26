#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

UI panels 

"""

import logging
import numpy as np

from PyQt6.QtWidgets            import QMenu
from PyQt6.QtGui                import QDesktopServices
from PyQt6.QtCore               import QUrl

from ..base.widgets             import * 
from ..base.panels              import Edit_Panel

from ..model.airfoil            import Airfoil
from ..model.geometry   import Geometry, Curvature_Abstract, Line 
from ..model.geometry_curve     import Geometry_Curve, Side_Airfoil_Curve, Deviation_Line
from ..model.case               import Case_Abstract, Case_Direct_Design, Case_Match_Target, Match_Targets
from ..model.xo2_driver         import Xoptfoil2

from .ae_widgets                import * 
from .ae_dialogs                import (LE_Radius_Dialog, TE_Gap_Dialog, Matcher_Run_Info,
                                        Blend_Airfoil_Dialog, Flap_Airfoil_Dialog, Repanel_Airfoil_Dialog)
from ..app_model                import App_Model
from ..match_runner             import Match_Result


logger = logging.getLogger(__name__)
# logger.setLevel(logging.WARNING)


class Panel_Airfoil_Abstract (Edit_Panel):
    """ 
    Abstract superclass for Edit/View-Panels of AirfoilEditor
        - has semantics of App
        - connect / handle signals 
    """

    sig_toggle_panel_size = pyqtSignal()                # wants to toggle panel size

    MAIN_MARGINS        = (10, 5,20, 5)
    MAIN_MARGINS_MINI   = ( 0, 5,10, 5)
    MAIN_MARGINS_FILE   = (10, 5,10, 5)

    _main_margins = MAIN_MARGINS

    @property
    def app_model (self) -> App_Model:
        return self.dataObject

    @property
    def airfoil (self) -> Airfoil: 
        return self.app_model.airfoil

    @property
    def geo (self) -> Geometry:
        return self.airfoil.geo

    @property    
    def case (self) -> Case_Abstract:
        return self.app_model.case


    @property
    def is_mode_modify (self) -> bool:
        """ panel in mode_modify or disabled ? """ 
        return self.app_model.is_mode_modify 

    @property
    def is_mode_match (self) -> bool:
        """ panel in mode_match or disabled ? """ 
        return self.app_model.is_mode_as_bezier or self.app_model.is_mode_as_bspline

    @property
    def is_mode_optimize (self) -> bool:
        """ panel in mode_optimize or disabled ? """
        return self.app_model.is_mode_optimize


    @override
    @property
    def _isDisabled (self) -> bool:
        """ overloaded: only enabled in edit mode of App """
        return not self.is_mode_modify or (self.geo.isFlapped if self.geo else False)
    
    @override
    def _set_panel_layout (self ):
        """ Set layout of self._panel """
        # overridden to connect to widgets changed signal

        super()._set_panel_layout ()
        for w in self.widgets:
            w.sig_changed.connect (self._on_widget_changed)
        for w in self.header_widgets:
            w.sig_changed.connect (self._on_widget_changed)


    def _on_widget_changed (self, widget):
        """ user changed data in widget"""
        logger.debug (f"{self} {widget} widget changed slot")
        self.app_model.notify_airfoil_changed ()


# --------------------------------------------------------------------------


class Panel_File_View (Panel_Airfoil_Abstract):
    """ File panel with open / save / ... """

    name = 'View Mode'

    sig_modify = pyqtSignal()                           # wants to modify the airfoil
    sig_optimize = pyqtSignal()                         # wants to enter optimize mode
    sig_exit = pyqtSignal()                             # wants to exit the application
    sig_new_as_bezier = pyqtSignal()                    # wants to create new Bezier based airfoil
    sig_new_as_bspline = pyqtSignal()                   # wants to create new B-Spline based airfoil
    sig_save_as = pyqtSignal()                          # wants to save current airfoil as new file
    sig_rename = pyqtSignal()                           # wants to rename current airfoil
    sig_delete = pyqtSignal()                           # wants to delete current airfoil
    sig_delete_temp_files = pyqtSignal()                # wants to delete all temp files
    sig_load_airfoil_settings = pyqtSignal()            # load airfoil settings if there are any

    _main_margins = Panel_Airfoil_Abstract.MAIN_MARGINS_FILE
    
    @override
    @property
    def _isDisabled (self) -> bool:
        """ override: enabled (as parent data panel is disabled)"""
        return False
    

    def _on_widget_changed (self, *_ ):
        """ user changed data in widget"""
        # overloaded - do not react on self widget changes 
        pass


    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""
        l_head.addStretch(1)
        ToolButton   (l_head, icon=Icon.EXPAND, set=self.sig_toggle_panel_size.emit,
                      toolTip='Minimize lower panel -<br>Alternatively, you can double click on the lower panels')


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        w =Airfoil_Select_Open_Widget (l,r,c, colSpan=4, signal=False, 
                                    textOpen="&Open", widthOpen=100, 
                                    get=lambda: self.airfoil, 
                                    set=     lambda airfoil: self.app_model.set_airfoil(airfoil),
                                    set_open=lambda airfoil: self.app_model.set_airfoil(airfoil, load_settings=True))

        r += 1
        Button (l,r,c, text="&Modify", width=100, 
                set=self.sig_modify.emit, toolTip="Modify geometry, Normalize, Repanel, Set Flap",
                button_style=button_style.PRIMARY)
        MenuButton (l,r,c+2, text="More...", width=80, 
                menu=self._more_menu(), 
                toolTip="Choose further actions for this airfoil")
        r += 1
        Button (l,r,c, text="&Optimize...", width=100, 
                set=self.sig_optimize.emit, toolTip=self._tooltip_optimize,
                disable=lambda: not Xoptfoil2.ready)
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Button (l,r,c, text="&Exit", width=100, set=self.sig_exit.emit)
        l.setColumnStretch (2,2)
        l.setColumnMinimumWidth (1,12)

        return l 
 

    def _more_menu (self) -> QMenu:
        """ create and return sub menu for 'more' actions"""

        menu = QMenu ()

        menu.addAction (MenuAction ("As Bezier based", self, set=self.sig_new_as_bezier, 
                                     # disable=lambda: self.airfoil.isBezierBased,
                                     toolTip="Create new Bezier based airfoil of current airfoil"))
        menu.addAction (MenuAction ("As B-Spline based", self, set=self.sig_new_as_bspline, 
                                     # disable=lambda: self.airfoil.isBSplineBased,
                                     toolTip="Create new B-Spline based airfoil of current airfoil"))
        menu.addSeparator ()
        menu.addAction (MenuAction ("Save as...", self, set=self.sig_save_as.emit,
                                     toolTip="Create a copy of the current airfoil with new name and filename"))
        menu.addAction (MenuAction ("Rename...", self, set=self.sig_rename.emit,
                                     toolTip="Rename name and/or filename of current airfoil"))
        menu.addAction (MenuAction ("Delete", self, set=self.sig_delete.emit,
                                     toolTip="Delete current airfoil including all temporary files created by the AirfoilEditor"))
        menu.addAction (MenuAction ("Delete temp files", self, set=self.sig_delete_temp_files.emit,
                                     toolTip="Delete all temporary files created by the AirfoilEditor just to have a clean directory again"))
        menu.addSeparator ()
        menu.addAction (MenuAction ("Readme on Github", self, set=self._open_AE_url,
                                     toolTip="Open the Github README file of the AirfoilEditor in a browser"))
        menu.addAction (MenuAction ("Releases on Github", self, set= self._open_releases_url,
                                     toolTip="Open the Github page with the actual release of the AirfoilEditor"))

        menu.setToolTipsVisible(True)

        return menu


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
                                    get=lambda: self.airfoil, 
                                    set=     lambda airfoil: self.app_model.set_airfoil(airfoil),
                                    set_open=lambda airfoil: self.app_model.set_airfoil(airfoil, load_settings=True))
        r += 1
        Button      (l,r,c, text="&Exit", width=100, set=self.sig_exit.emit)
        MenuButton  (l,r,c+2, text="More...", width=80, 
                        menu=self._more_menu(), 
                        toolTip="Choose further actions for this airfoil")
        ToolButton  (l,r,c+3, icon=Icon.COLLAPSE, set=self.sig_toggle_panel_size.emit,
                        toolTip='Maximize lower panel -<br>Alternatively, you can double click on the lower panels')

        l.setColumnMinimumWidth (1,12)
        l.setColumnStretch (2,2)
        return l 
 

    def _more_menu (self) -> QMenu:
        """ create and return sub menu for 'more' actions"""

        menu = super()._more_menu ()
        menu.insertAction (menu.actions()[0], MenuAction ("&Optimize", self, set=self.sig_optimize.emit,   
                                    toolTip="Modify geometry, Normalize, Repanel, Set Flap"))
        menu.insertAction (menu.actions()[0], MenuAction ("&Modify", self, set=self.sig_modify.emit,   
                                    toolTip=self._tooltip_optimize(), disable=lambda: not Xoptfoil2.ready))
        return menu



class Panel_File_Modify (Panel_Airfoil_Abstract):
    """ File panel with open / save / ... """

    name = 'Modify'

    sig_finish   = pyqtSignal()                                 # wants to finish modify mode - ok / cancel
    sig_cancel   = pyqtSignal()                                 # wants to cancel modify mode

    _main_margins = Panel_Airfoil_Abstract.MAIN_MARGINS_FILE


    @override
    def title_text (self) -> str: 
        """ returns text of title - default self.name"""

        if self.is_mode_modify:
            if self.airfoil.geo.isCurve:
                return self.name + " " + self.airfoil.geo.CURVE_NAME
            else:
                return self.name 
        elif self.is_mode_match and self.airfoil.geo.isCurve:
            return "As " + self.airfoil.geo.CURVE_NAME 
        else:
            return self.name

    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""
        l_head.addStretch(1)
        ToolButton   (l_head, icon=Icon.EXPAND, set=self.sig_toggle_panel_size.emit,
                      toolTip='Minimize lower panel -<br>Alternatively, you can double click on the lower panels')


    @property
    def _isDisabled (self) -> bool:
        """ override: always enabled """
        return False
    
    @property
    def case (self) -> Case_Direct_Design:
        return super().case


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
        ToolButton   (l,r,c+3, icon=Icon.DELETE, set=self.app_model.remove_current_design,
                        hide=lambda: self.case.get_iDesign (self.airfoil) == 0,  # hide Design 0 
                        toolTip="Remove current design airfoil")
        r += 1
        l.setRowStretch (r,2)
        r += 1
        Button (l,r,c,  text="&Finish ...", width=100, set=self.sig_finish.emit, 
                        toolTip="Save current airfoil, optionally modify name and leave edit mode")
        r += 1
        Button (l,r,c,  text="&Cancel",  width=100, 
                        set=self.sig_cancel.emit,
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
        self.app_model.set_airfoil (airfoil)




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
        ToolButton   (l,r,c+3, icon=Icon.DELETE, set=self.app_model.remove_current_design,
                        hide=lambda: self.case.get_iDesign (self.airfoil) == 0,
                        toolTip="Remove current design airfoil")  
        ToolButton  (l,r,c+5, icon=Icon.COLLAPSE, set=self.sig_toggle_panel_size.emit,
                        toolTip='Maximize lower panel -<br>Alternatively, you can double click on the lower panels')
        r += 1
        Button (l,r,c,  text="&Finish ...", width=100, set=self.sig_finish.emit, 
                        toolTip="Save current airfoil, optionally modify name and leave edit mode")
        Button (l,r,c+2,text="&Cancel",  width=80, colSpan=3,
                        set=lambda : self.sig_cancel.emit(),
                        toolTip="Cancel modifications of airfoil and leave edit mode")
        l.setColumnMinimumWidth (1,12)
        l.setColumnStretch (4,2)
        return l



class Panel_Geometry (Panel_Airfoil_Abstract):
    """ Main geometry data of airfoil"""

    name = 'Geometry'

    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        # blend with airfoil - currently Bezier is not supported
        Button (l_head, text="&Blend", width=75,
                set=self.do_blend_with, 
                hide=lambda: not self.is_mode_modify or self.airfoil.isBezierBased,
                toolTip="Blend original airfoil with another airfoil")

    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        FieldF (l,r,c, lab="Thickness", width=75, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.max_thick,
                disable=lambda: self.geo.isCurve)
        r += 1
        FieldF (l,r,c, lab="Camber", width=75, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.max_camb,
                disable=lambda: self.geo.isCurve or self.geo.isSymmetrical)
        r += 1
        FieldF (l,r,c, lab="LE radius", width=75, unit="%", step=0.02,
                obj=lambda: self.geo, prop=Geometry.le_radius, disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self.do_le_radius, 
                hide=lambda: not self.is_mode_modify or self.geo.isCurve,
                toolTip="Set leading edge radius with a flexible blending range")
        r += 1
        FieldF (l,r,c, lab="TE gap", width=75, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.te_gap, disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self.do_te_gap,
                hide=lambda: not self.is_mode_modify or self.geo.isCurve,
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
                disable=lambda: self.geo.isCurve)
        r += 1
        FieldF (l,r,c, lab="at", width=75, unit="%", step=0.2,
                obj=lambda: self.geo, prop=Geometry.max_camb_x,
                disable=lambda: self.geo.isCurve or self.geo.isSymmetrical)
        r += 1
        FieldF (l,r,c, lab="LE curv", width=75, dec=0, disable=True,
                obj=lambda: self.geo.curvature, prop=Curvature_Abstract.at_le)
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

        dialog = Blend_Airfoil_Dialog (self, self.airfoil, self.app_model.airfoil_seed, 
                                       parentPos=(0.75, 0.2), dialogPos=(0,1))  

        dialog.sig_airfoil_2_changed.connect    (self.app_model.set_airfoil_2)
        dialog.sig_blend_changed.connect        (self.app_model.notify_airfoil_geo_changed)

        dialog.exec()     

        if dialog.airfoil2 is not None: 
            # do final blend with high quality (splined) 
            self.airfoil.geo.blend (self.app_model.airfoil_seed.geo, 
                                      dialog.airfoil2.geo, 
                                      dialog.blendBy) 
            self.app_model.set_airfoil_2 (None)
            self.app_model.notify_airfoil_changed()



    def do_le_radius (self): 
        """ set LE radius - run set LE radius dialog""" 

        if self.airfoil.isBezierBased: return                   # not for Bezier airfoils

        dialog = LE_Radius_Dialog (self, self.app_model, parentPos=(0.25, 0.75), dialogPos=(0,1))
        dialog.exec()     


    def do_te_gap (self): 
        """ set TE gap - run set TE gap dialog""" 

        if self.airfoil.isBezierBased: return                   # not for Bezier airfoils

        dialog = TE_Gap_Dialog (self, self.app_model, parentPos=(0.25, 0.75), dialogPos=(0,1))
        dialog.exec()     



class Panel_Geometry_Small (Panel_Geometry):
    """ Main geometry data of airfoil - small version"""

    _main_margins = Panel_Airfoil_Abstract.MAIN_MARGINS_MINI

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
        l.setColumnMinimumWidth (c,70)
        l.setColumnMinimumWidth (c+2,10)
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
        FieldF (l,r,c, lab="LE radius", width=60, unit="%", step=0.02,
                obj=lambda: self.geo, prop=Geometry.le_radius, disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self.do_le_radius, 
                hide=lambda: not self.is_mode_modify or self.geo.isCurve,
                toolTip="Set leading edge radius with a flexible blending range")
        r += 1
        FieldF (l,r,c, lab="TE gap", width=60, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.te_gap, disable=True)
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self.do_te_gap,
                hide=lambda: not self.is_mode_modify or self.geo.isCurve,
                toolTip="Set trailing edge gap with a flexible blending range")
        l.setColumnMinimumWidth (c,70)
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
                hide=lambda: not self.is_mode_modify,
                disable=lambda: self.geo.isBasic or self.geo.isHicksHenne,
                toolTip="Repanel airfoil with a new number of panels" ) 


    def _init_layout (self):

        l = QGridLayout()
        r,c = 0, 0 
        FieldI (l,r,c, lab="No of panels", disable=True, width=60, style=self._style_panel,
                get=lambda: self.geo.nPanels, )
        r += 1
        FieldF (l,r,c, lab="Angle at LE", width=60, dec=1, unit="°", style=self._style_angle,
                get=lambda: self.geo.panelAngle_le)
        SpaceC (l,c+2, width=10, stretch=0)
        Label  (l,r,c+3,width=70, get=lambda: f"at index {self.geo.iLe}", style=style.COMMENT)
        r += 1
        FieldF (l,r,c, lab="Angle min", width=60, dec=1, unit="°",
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

        dialog = Repanel_Airfoil_Dialog (self, self.app_model,
                                         parentPos=(0.35, 0.75), dialogPos=(0,1))
        dialog.exec()     


    def _on_panelling_finished (self, aSide):
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

    _main_margins = Panel_Airfoil_Abstract.MAIN_MARGINS_MINI

    def _init_layout (self):

        l = QGridLayout()
        r,c = 0, 0 
        FieldI (l,r,c, lab="No of panels", disable=True, width=60, style=self._style_panel,
                get=lambda: self.geo.nPanels, )
        ToolButton (l,r,c+2, icon=Icon.EDIT,
                set=self.do_repanel, hide=lambda: not self.is_mode_modify,
                disable=lambda: self.geo.isBasic or self.geo.isHicksHenne,
                toolTip="Repanel airfoil with a new number of panels" ) 
        r += 1
        l.setRowStretch (r,2)
        l.setColumnMinimumWidth (0,80)
        return l
 


class Panel_Flap (Panel_Airfoil_Abstract):
    """ Flap information and set flap"""

    name = 'Flap'
    _width  = (160,250)

    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is Bezier """
        isProbablyFlapped = self.airfoil.geo.isProbablyFlapped if self.airfoil else False
        return (self.is_mode_modify or isProbablyFlapped) and not self.geo.isCurve and not self.geo.isHicksHenne


    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        Button (l_head, text="Set F&lap", width=75,
                set=self.do_flap, hide=lambda: not self.is_mode_modify,
                disable=self._set_flap_disabled,
                toolTip="Set flap at airfoil" ) 


    def _set_flap_disabled (self) -> bool:
        """ True if set flap is not possible"""

        if self.geo.isCurve or self.geo.isHicksHenne: 
            return True
        elif self.is_mode_modify:
            return not self.airfoil.flap_setter                       # no flapper, no set flap 
        else:
            return True


    def _init_layout (self):

        geo             = self.airfoil.geo

        l = QGridLayout()
        r,c = 0, 0 

        if self.is_mode_modify:

            flap_setter         = self.airfoil.flap_setter
            airfoil_flapped = flap_setter.airfoil_flapped if flap_setter else None

            if airfoil_flapped:
                FieldF (l,r,c, lab="Hinge x", width=60, get=lambda: flap_setter.x_flap, dec=1, unit="%")
                r += 1
                FieldF (l,r,c, lab="Flap Angle", width=60, dec=1, unit='°', get=lambda: flap_setter.flap_angle)
                r +=1
                Field (l,r,c, lab="Based on", colSpan=2,
                       get=flap_setter.airfoil_base.fileName)
                r += 1
                SpaceR (l,r, stretch=2)
                r += 1
                lab =Label  (l,r,c, width=None, height=(40,None), colSpan=3, style=style.COMMENT, wordWrap=True,
                        get="As the base airfoil is available, another flap setting can be applied.")
                lab.setAlignment (ALIGN_BOTTOM)
                l.setRowStretch (r,1)
                l.setColumnMinimumWidth (0,80)
                l.setColumnStretch (2,3)

            elif flap_setter:

                SpaceR (l,r, stretch=2)
                r += 1
                lab =Label  (l,r,c, width=None,  colSpan=3, style=style.COMMENT, wordWrap=True,
                             get="No flap set")
                l.setColumnStretch (2,3)

            elif self.airfoil.isFlapped:
                FieldF (l,r,c, lab="Hinge x", width=60, get=lambda: geo.curvature.flap_kink_at, dec=1, unit="%")
                r += 1
                FieldF (l,r,c, lab="Flap Angle", width=60, dec=1, unit='°', get=lambda: geo.flap_angle_estimated)
                r +=1
                SpaceR (l,r, stretch=2)
                r += 1
                Label  (l,r,c, width=None, colSpan=3, style=style.WARNING,
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

                FieldF (l,r,c, lab="Hinge x", width=60, get=lambda: geo.curvature.flap_kink_at, dec=1, unit="%")
                r += 1
                FieldF (l,r,c, lab="Flap Angle", width=60, dec=1, unit='°', get=lambda: geo.flap_angle_estimated)
                r +=1
                SpaceR (l,r, stretch=2)
                r += 1
                lab =Label  (l,r,c, width=None, colSpan=3, style=style.COMMENT, wordWrap=True, 
                             get="The airfoil has a set flap.")
                l.setColumnMinimumWidth (0,80)
                l.setColumnStretch (2,3)
                                
            elif geo.isProbablyFlapped:

                SpaceR (l,r, stretch=2)
                Label  (l,r,c, width=160, height=(None,None), colSpan=3, style=style.COMMENT, wordWrap=True, 
                             get="The airfoil is probably flapped, but a kink in the contour couldn't be detected on both sides.")
                r += 1
                l.setRowStretch (r,1)

        return l


    def do_flap (self): 
        """ set flaps - run set flap dialog""" 

        dialog = Flap_Airfoil_Dialog (self, self.app_model, parentPos=(0.55, 0.80), dialogPos=(0,1.2))
        dialog.exec()     


    @override
    def refresh(self, reinit_layout=False):

        # force new layout to show different flap states 
        return super().refresh(reinit_layout=True)


class Panel_Flap_Small (Panel_Flap):
    """ Flap information and set flap"""

    _width  = None
    _main_margins = Panel_Airfoil_Abstract.MAIN_MARGINS_MINI

    def _init_layout (self):

        geo             = self.airfoil.geo

        l = QGridLayout()
        r,c = 0, 0 

        if self.is_mode_modify:

            flap_setter         = self.airfoil.flap_setter
            airfoil_flapped = flap_setter.airfoil_flapped if flap_setter else None

            if airfoil_flapped:
                FieldF (l,r,c, lab="Flap Angle", width=60, dec=1, unit='°', get=lambda: flap_setter.flap_angle)

            elif flap_setter:
                Label  (l,r,c, width=None,  colSpan=3, style=style.COMMENT, wordWrap=True,
                             get="No flap set")

            elif self.airfoil.isFlapped:
                FieldF (l,r,c, lab="Flap Angle", width=60, dec=1, unit='°', get=lambda: geo.flap_angle_estimated)
                r += 1
                Label  (l,r,c, width=None, colSpan=3, style=style.WARNING,
                             styleRole=QPalette.ColorRole.Window, 
                             get="The airfoil is already flapped.")
 
            ToolButton (l,0,c+2, icon=Icon.EDIT,
                    set=self.do_flap, hide=lambda: not self.is_mode_modify,
                    disable=self._set_flap_disabled,
                    toolTip="Set flap at airfoil" ) 
            l.setRowStretch (r+1,1)
            l.setColumnMinimumWidth (0,80)

        else: 
            # mode not modify - info about a flap which is (could be) set
            
            if geo.isFlapped:

                FieldF (l,r,c, lab="Flap Angle", width=60, dec=1, unit='°', get=lambda: geo.flap_angle_estimated)
                r += 1
                FieldF (l,r,c, lab="Hinge x", width=60, get=lambda: geo.curvature.flap_kink_at, dec=1, unit="%")
                l.setColumnMinimumWidth (0,80)
                                
            elif geo.isProbablyFlapped:

                Label  (l,r,c, width=None, colSpan=2, style=style.COMMENT, 
                             get="The airfoil is probably flapped")
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
        return not self.geo.isCurve 


    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        Button (l_head, text="&Normalize", width=75,
                set=self.do_normalize, 
                hide=lambda: not self.is_mode_modify,
                toolTip="Normalize airfoil to get leading edge at 0,0 and trailing edge at x=1.0")


    def _init_layout (self): 

        l = QGridLayout()     
        r,c = 0, 0 
        FieldF (l,r,c, lab="Leading edge x,y", get=lambda: self.geo.le[0], width=75, dec=7, style=lambda: self._style (self.geo.le[0], 0.0))
        r += 1
        FieldF (l,r,c, lab="  ... of spline", get=lambda: self.geo.le_real[0], width=75, dec=7, style=self._style_le_real,
                hide=lambda: not self.is_mode_modify)
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
                hide=lambda: not self.is_mode_modify)
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
        te_not_at_1 = ""
        te_not_sym  = ""
        if not self.geo.isNormalized:
            if self.geo.isSplined and not self.geo.isLe_closeTo_le_real:
                text.append("- LE of spline is not at 0,0")
            elif self.geo.le[0] != 0.0 or self.geo.le[1] != 1.0 : 
                text.append("- LE is not at 0,0")
        if not self.airfoil.isFlapped:
            if self.geo.te[0] != 1.0 or self.geo.te[2] != 1.0 : 
                te_not_at_1 = "- TE x is not at 1.0"
            if self.geo.te[1] != -self.geo.te[3]: 
                if te_not_at_1:
                    te_not_at_1 += " and y is not symmetrical"
                else:   
                    te_not_sym = "- TE y is not symmetrical"
            if te_not_at_1:
                text.append (te_not_at_1)
            if te_not_sym:
                text.append (te_not_sym)

        if not text:
            if self.geo.isSymmetrical: 
                text.append("Airfoil is symmetrical")
            else: 
                text.append("Airfoil is normalized")

        text = '\n'.join(text)
        return text 


    def do_normalize (self):
        """ normalize airfoil to LE at 0,0 and TE at x=1.0"""

        self.airfoil.normalize()
        self.app_model.notify_airfoil_changed()



class Panel_LE_TE_Small  (Panel_LE_TE):
    """ info about LE and TE coordinates - small version"""

    _main_margins = Panel_Airfoil_Abstract.MAIN_MARGINS_MINI

    def _init_layout (self): 

        l = QGridLayout()     
        r,c = 0, 0 
        FieldF (l,r,c, lab="LE x,y", get=lambda: self.geo.le[0], width=75, dec=7, style=lambda: self._style (self.geo.le[0], 0.0))
        r += 1
        FieldF (l,r,c, lab="TE xm,ym",  width=75, dec=7, 
                get=lambda: (self.geo.te[0] + self.geo.te[2]) / 2, style=lambda: self._style (self.geo.te[0], 1.0))
        l.setColumnMinimumWidth (0,70)
        l.setColumnMinimumWidth (2,10)
        r,c = 0, 3 
        FieldF (l,r,c+1,get=lambda: self.geo.le[1], width=75, dec=7, style=lambda: self._style (self.geo.le[1], 0.0))
        r += 1
        FieldF (l,r,c+1,get=lambda: (self.geo.te[1] + self.geo.te[3])/2, width=75, dec=7, style=lambda: self._style (self.geo.te[1], -self.geo.te[3]))

        r,c = 0, 5 
        ToolButton (l,r,c+1, icon=Icon.EDIT,
                set=self.do_normalize, 
                hide=lambda: not self.is_mode_modify,
                toolTip="Normalize airfoil to get leading edge at 0,0 and trailing edge at x=1.0")
        return l



class Panel_Curve (Panel_Airfoil_Abstract):
    """ Info about Bezier/B-Spline # control points upper and lower  """

    name = 'Curve'

    @override
    def title_text(self):
        return self.geo.CURVE_NAME

    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is Curve """
        return self.geo.isCurve

    @override
    @property
    def _isDisabled (self) -> bool:
        return True                             # always disabled - no change of ctrl points
    
    @override
    @property
    def geo (self) -> Geometry_Curve:
        return super().geo

    @property
    def upper (self) -> Side_Airfoil_Curve:
        return self.geo.upper

    @property
    def lower (self) -> Side_Airfoil_Curve:
        return self.geo.lower


    def _init_layout (self):

        l = QGridLayout()
        r,c = 0, 0 
        Label (l,r,c, get="# Control Points", colSpan=4)
        r += 1
        FieldI (l,r,c,   lab="Upper side", get=lambda: self.upper.ncp,  width=40, step=1, lim=lambda: self.upper.NCP_BOUNDS,
                         set=lambda n : self.geo.set_ncp_of (self.upper, n))
        r += 1
        FieldI (l,r,c,   lab="Lower side",  get=lambda: self.lower.ncp,  width=40, step=1, lim=lambda: self.lower.NCP_BOUNDS,
                         set=lambda n : self.geo.set_ncp_of (self.lower, n))
        l.setColumnMinimumWidth (0,80)

        r += 1
        l.setRowStretch (r,2)
        r += 1 
        Label  (l,r,0,colSpan=5, get=self._message, style=style.COMMENT, height=(None,None), hide=lambda: self.is_mode_modify)
        Label  (l,r,0,colSpan=5, get=self._hint, style=style.HINT, height=(None,None), 
                width=(150, 150), wordWrap=True, hide=lambda: not self.is_mode_modify)
        return l


    def _hint (self) -> str:
        return f"You may change number of control points in diagram."

    def _message (self)  -> str:

        lines = []
        for side in [self.upper, self.lower]:
            side : Side_Airfoil_Curve
            curve = side.curve
            text = f"{side.name}: degree {curve.degree}"
            if self.geo.isBSpline:
                if curve.is_uniform:
                    text += ", uniform"
                else:
                    text += ", non-uniform"
            lines.append(text)

        return '\n'.join(lines) 


class Panel_Curve_Small (Panel_Curve):
    """ Info about Bezier/B-Spline # control points upper and lower - small version """

    _main_margins = Panel_Airfoil_Abstract.MAIN_MARGINS_MINI

    def _init_layout (self):

        l = QGridLayout()
        r,c = 0, 0 
        FieldI (l,r,c,   lab=lambda: f"{self.geo.CURVE_NAME} Upper", 
                get=lambda: self.upper.ncp,  width=40, step=1, lim=lambda: self.upper.NCP_BOUNDS,
                set=lambda n : self.geo.set_ncp_of (self.upper, n))
        r += 1
        FieldI (l,r,c,   lab=lambda: f"{self.geo.CURVE_NAME} Lower",  
                get=lambda: self.lower.ncp,  width=40, step=1, lim=lambda: self.lower.NCP_BOUNDS,
                set=lambda n : self.geo.set_ncp_of (self.lower, n))
        l.setColumnMinimumWidth (0,80)
        return l



class Panel_Match_Result (Panel_Airfoil_Abstract):
    """ Match fit info like RMS deviation, curvature at LE and TE, etc"""

    name = 'Match Result'
    _small = False

    def __init__(self, *args, **kwargs):
        self._result_upper: Match_Result | None = None
        self._result_lower: Match_Result | None = None
        super().__init__(*args, **kwargs)

    @property
    def result_upper(self) -> Match_Result:
        """Match_Result: from last optimizer run if available, else rebuilt from current geo."""
        stored = self.case.match_result_upper
        if stored is not None:
            return stored
        if self._result_upper is None:
            self._result_upper = Match_Result(self.geo.upper, self.case.targets_upper,
                                              curv=self.geo.curvature.upper.y)
        return self._result_upper

    @property
    def result_lower(self) -> Match_Result:
        """Match_Result: from last optimizer run if available, else rebuilt from current geo."""
        stored = self.case.match_result_lower
        if stored is not None:
            return stored
        if self._result_lower is None:
            self._result_lower = Match_Result(self.geo.lower, self.case.targets_lower,
                                              curv=self.geo.curvature.lower.y)
        return self._result_lower

    @property
    def case (self) -> Case_Match_Target:
        return self.app_model.case


    def _init_layout (self):

        l = QGridLayout()
        r,c = 0, 0 
        Label  (l,r+1,c,   get="Upper Side")
        Label  (l,r+2,c,   get="Lower Side")
        l.setColumnMinimumWidth (c,80)

        c = 1
        Label  (l,r,c, colSpan=3, get="# Ctrl P")
        FieldI (l,r+1,c, width=40, get=lambda: self.result_upper.ncp,
                style=lambda: self.result_upper.style_ncp)
        FieldI (l,r+2,c, width=40, get=lambda: self.result_lower.ncp,
                style=lambda: self.result_lower.style_ncp)
        l.setColumnMinimumWidth (c+1,20)

        c += 2
        Label  (l,r,c, get="Δ RMS", width=70, colSpan=2)
        FieldF (l,r+1,c, width=60, dec=4, unit="%", get=lambda: self.result_upper.rms,
                style=lambda: self.result_upper.style_deviation)
        FieldF (l,r+2,c, width=60, dec=4, unit="%", get=lambda: self.result_lower.rms,
                style=lambda: self.result_lower.style_deviation)
        l.setColumnMinimumWidth (c+1,20)

        c += 2
        Label  (l,r,c, get="Δ Max", width=50)
        FieldF (l,r+1,c, width=50, dec=3, unit="%", get=lambda: self.result_upper.max_dy,
                style=lambda: self.result_upper.style_max_dy)
        FieldF (l,r+2,c, width=50, dec=3, unit="%", get=lambda: self.result_lower.max_dy,
                style=lambda: self.result_lower.style_max_dy)
        c += 1
        Label  (l,r,c, get="at", width=40)
        FieldF (l,r+1,c, width=40, dec=0, unit="%", get=lambda: self.result_upper.max_dy_position)
        FieldF (l,r+2,c, width=40, dec=0, unit="%", get=lambda: self.result_lower.max_dy_position)
        l.setColumnMinimumWidth (c+1,20)

        c += 2
        Label  (l,r,c, colSpan=2, get="LE curv")
        FieldF (l,r+1,c, get=lambda: self.result_upper.le_curvature, width=40, dec=0,
                style=lambda: self.result_upper.style_curv_le)
        FieldF (l,r+2,c, get=lambda: self.result_lower.le_curvature, width=40, dec=0,
                style=lambda: self.result_lower.style_curv_le)
        l.setColumnMinimumWidth (c+1,10)

        c += 2
        Label  (l,r,c, colSpan=2, get="Revers")
        FieldF (l,r+1,c, get=lambda: self.result_upper.nreversals, width=30, dec=0,
                style=lambda: self.result_upper.style_nreversals)
        FieldF (l,r+2,c, get=lambda: self.result_lower.nreversals, width=30, dec=0,
                style=lambda: self.result_lower.style_nreversals)
        l.setColumnMinimumWidth (c+1,10)

        c += 2
        Label  (l,r,c, colSpan=2, get="TE curv")
        FieldF (l,r+1,c, get=lambda: self.result_upper.te_curvature, width=40, dec=1,
                style=lambda: self.result_upper.style_curv_te)
        FieldF (l,r+2,c, get=lambda: self.result_lower.te_curvature, width=40, dec=1,
                style=lambda: self.result_lower.style_curv_te)
        l.setColumnMinimumWidth (c+1,10)

        c += 2
        Label  (l,r,c, colSpan=2, get="Bumps")
        FieldF (l,r+1,c, get=lambda: self.result_upper.bumps, width=40, dec=2,
                style=lambda: self.result_upper.style_bumps)
        FieldF (l,r+2,c, get=lambda: self.result_lower.bumps, width=40, dec=2,
                style=lambda: self.result_lower.style_bumps)
        l.setColumnMinimumWidth (c+1,20)

        r,c = 3,0 
        l.setRowStretch (r,1)
        r += 1
        Label  (l,r,0, colSpan=7, style=style.COMMENT, height=16,
                get=lambda: self.result_upper.name + ": " + self._remark(self.result_upper))
        r += 1
        Label  (l,r,0, colSpan=7, style=style.COMMENT, height=16,
                get=lambda: self.result_lower.name + ": " + self._remark(self.result_lower))
        return l


    def _remark (self, result : Match_Result) -> str: 

        if not result.is_optimized:
            text = f"Initial fit - run 'Match' to optimize..."
        elif result.is_perfect():
            text = f"Match is perfect"
            if not result.is_ncp_good():
                text += " but more control points were needed."
            else:
                text += "!"
        elif result.is_good_enough():
            text = f"Match is quite good for this difficult target."
        else:
            text = f"Match is not too good. Maybe tweak LE or TE curvature or Reversals"
        return text



    @override
    def refresh(self, reinit_layout=False):
        """Override to clear cached results on refresh."""
        self._result_upper = None
        self._result_lower = None
        return super().refresh(reinit_layout)





class Panel_Match_Result_Small (Panel_Match_Result):
    """ Match fit info like RMS deviation, curvature at LE and TE, etc - small version"""

    _main_margins = Panel_Airfoil_Abstract.MAIN_MARGINS_MINI

    def _init_layout (self):

        l = QGridLayout()
        r = 0

        Label  (l, r, 0, get="Result Upper Side", width=100)
        FieldI (l, r, 1, width=40, get=lambda: self.result_upper.ncp,
                style=lambda: self.result_upper.style_ncp)
        FieldF (l, r, 3, width=60, dec=4, unit="%", get=lambda: self.result_upper.rms,
                style=lambda: self.result_upper.style_deviation)
        Label  (l, r, 5, style=style.COMMENT, get=lambda: self._remark(self.result_upper))

        r += 1
        Label  (l, r, 0, get="Result Lower Side", width=100)
        FieldI (l, r, 1, width=40, get=lambda: self.result_lower.ncp,
                style=lambda: self.result_lower.style_ncp)
        FieldF (l, r, 3, width=60, dec=4, unit="%", get=lambda: self.result_lower.rms,
                style=lambda: self.result_lower.style_deviation)
        Label  (l, r, 5, style=style.COMMENT, get=lambda: self._remark(self.result_lower))

        l.setColumnMinimumWidth (2, 20)
        l.setColumnMinimumWidth (4, 20)
        l.setColumnStretch (5, 1)
        return l



class Panel_Match_Curve (Panel_Airfoil_Abstract):
    """ Match BezCurveier functions  """

    name = 'Match'

    _small = False

    @override
    def title_text(self):
        if self.geo.isCurve:
            return self.name + " " + self.geo.CURVE_NAME
        else:
             return super().title_text()

    @override
    @property
    def _isDisabled (self) -> bool:
        return not self.is_mode_match
    
    @override
    def _on_widget_changed (self, widget):
        """ user changed data in widget"""
        # just refresh - no airfoil changed
        self.refresh()

    @property
    def case (self) -> Case_Match_Target:
        return self.app_model.case

    @property
    def geo (self) -> Geometry_Curve:
        return super().geo
    
    @property
    def upper (self) -> Side_Airfoil_Curve:
        return self.geo.upper

    @property
    def lower (self) -> Side_Airfoil_Curve:
        return self.geo.lower
    
    @property
    def curv_upper_nreversals (self) -> int:
        return self.target_airfoil.geo.curvature.upper.nreversals()

    @property
    def curv_lower_nreversals (self) -> int:
        return self.target_airfoil.geo.curvature.lower.nreversals()

    @property
    def target_airfoil (self) -> Airfoil:
        return self.app_model.airfoil_target
    
    @property
    def targets_upper (self) -> Match_Targets:
        return self.case.targets_upper
    
    @property
    def targets_lower (self) -> Match_Targets:
        return self.case.targets_lower

    @property
    def target_curv_le (self) -> float:
        return self.target_airfoil.geo.curvature.at_le


    def _init_layout (self):

        l = QGridLayout()

        r,c = 0, 0 
        Label  (l,r+1,c,   get="Upper Side")
        Label  (l,r+2,c,   get="Lower Side")
        l.setColumnMinimumWidth (c,80)

        c += 1
        Label  (l,r,c, colSpan=3, get="# Ctrl Points", hide=self._small)
        c +=1
        _tip = "Auto will find the optimal minimum number of control points for a good match"
        CheckBox (l,r+1,c, text="Auto", get=lambda: self.targets_upper.ncp_auto,
                set=lambda b: self.set_ncp_auto(self.upper, self.targets_upper, b),
                toolTip=_tip)
        CheckBox (l,r+2,c, text="Auto", get=lambda: self.targets_lower.ncp_auto,
                set=lambda b: self.set_ncp_auto(self.lower, self.targets_lower, b),
                toolTip=_tip)
        c += 1
        _tip = "Number of control points, the matching curve will have.\n"+ \
               "A higher number may allow a better fit, but could cause undesired bumps. "
        FieldI (l,r+1,c, width=40, step=1, lim =lambda: self.upper.NCP_BOUNDS,
                get=lambda: self.targets_upper.ncp, 
                set=lambda n: self.set_ncp(self.upper, self.targets_upper, n),
                hide=lambda: self.targets_upper.ncp_auto,
                toolTip=_tip)
        FieldI (l,r+2,c, width=40, step=1, lim =lambda: self.lower.NCP_BOUNDS,
                get=lambda: self.targets_lower.ncp, 
                set=lambda n: self.set_ncp(self.lower, self.targets_lower, n),
                hide=lambda: self.targets_lower.ncp_auto,
                toolTip=_tip)
        l.setColumnMinimumWidth (c+1,10)

        c += 2
        _tip = "Curvature at leading edge which is essential for a good fit.\n" + \
               "Have a look at the curvature comb of the airfoil at leading edge,\n" + \
               "if the match doesn't find a good result."
        Label  (l,r,c, colSpan=3, get="LE curv", hide=self._small)
        FieldF (l,r+1,c, rowSpan=2, width=45, dec=0, step=1, lim =(50,800),
                get=lambda: self.le_curv, set=self.set_le_curv, toolTip=_tip)
        l.setColumnMinimumWidth (c+1,5)

        c += 2
        Label  (l,r,c, colSpan=3, get="Revers", hide=self._small)
        _tip = "Maximum number of curvature reversals allowed for the matched airfoil.\n" + \
               "A normal airfoil has 0 reversals.\n" + \
               "A reflexed airfoil has 1 reversal on the upper side,\n" + \
               "an airfoil with rear loading has 1 reversal on the lower side."
        FieldI (l,r+1,c, width=40, step=1, lim =(0,2),
                get=lambda: self.targets_upper.max_nreversals, 
                set=lambda n: self.targets_upper.set_max_nreversals(n), toolTip=_tip)
        FieldI (l,r+2,c, width=40, step=1, lim =(0,2),
                get=lambda: self.targets_lower.max_nreversals, 
                set=lambda n: self.targets_lower.set_max_nreversals(n), toolTip=_tip)
        l.setColumnMinimumWidth (c+1,5)

        c += 2
        _tip = "Maximum curvature at TE allowed for the matched side.\n" + \
               "A higher value may allow a better fit, \nbut could cause an undesired artefact at TE."
        Label  (l,r,c, colSpan=3, get="TE curv", hide=self._small)
        FieldF (l,r+1,c, width=45, dec=1, step=0.1, lim =(-9,9),
                get=lambda: self.targets_upper.max_te_curvature, 
                set=lambda c: self.targets_upper.set_max_te_curvature(c), toolTip=_tip)
        FieldF (l,r+2,c, width=45, dec=1, step=0.1, lim =(-9,9),
                get=lambda: self.targets_lower.max_te_curvature, 
                set=lambda c: self.targets_lower.set_max_te_curvature(c), toolTip=_tip)
        l.setColumnMinimumWidth (c+1,5)

        c += 2
        _tip = "Suppress bumps of curvature to get a smooth airfoil.\n" + \
               "Bumps are controlled by limiting the derivate of curvature.\n" + \
               "Show 'Derivative of curvature' in the Curvature diagram to watch the effect."
        Label  (l,r,c, colSpan=2, get="Bumps", hide=self._small)
        CheckBox (l,r+1,c, text="No", get=lambda: self.targets_upper.bump_control,
                set=lambda b: self.targets_upper.set_bump_control(b),
                toolTip=_tip)
        CheckBox (l,r+2,c, text="No", get=lambda: self.targets_lower.bump_control,
                set=lambda b: self.targets_lower.set_bump_control(b),
                toolTip=_tip)
        l.setColumnMinimumWidth (c+1,20)

        c += 2
        _tip = "Run the matching optimizer to find\nthe best fitting curve to the target side."
        Button (l,r+1,c  , text="Match", width=80, button_style = button_style.PRIMARY,
                        set=lambda: self._match (self.upper.type), toolTip=_tip)
        Button (l,r+2,c  , text="Match", width=80, button_style = button_style.PRIMARY,
                        set=lambda: self._match (self.lower.type), toolTip=_tip)

        r,c = 3,0 
        l.setRowStretch (r,2)
        r += 1
        Label  (l,r,0, get=self._messageText, colSpan=10, height=(None, None), hide=self._small, style=style.COMMENT)
    
        return l


    def _match (self, side_type : Line.Type): 
        """ run match (dialog) """ 

        matcher = self.app_model.run_match (side_type)    # run match - will update airfoil and targets with results

        if matcher:
            diag = Matcher_Run_Info (self, matcher, parentPos=(0.7, 0.0), dialogPos=(0,1))
            diag.show()


    def set_ncp_auto (self, aSide : Side_Airfoil_Curve, targets : Match_Targets, auto: bool):
        """ set ncp auto mode of a side and update targets with new auto mode"""
        targets.set_ncp_auto(auto)
        if not auto:
            # set ncp to current value of geo 
            targets.set_ncp (aSide.curve.ncp)


    def set_ncp (self, aSide : Side_Airfoil_Curve, targets : Match_Targets, ncp: int):
        """ set ncp of a side and update targets with new ncp"""                
        self.geo.set_ncp_of (aSide, ncp)                # show updated airfoil with new ncp - will reset and handle changed
        targets.set_ncp (ncp)
        self.app_model.notify_airfoil_changed()         # notify change of airfoil - new design


    @property
    def le_curv (self) -> float:
        upper_curv =self.targets_upper.le_curvature
        lower_curv =self.targets_lower.le_curvature
        return round((upper_curv + lower_curv) / 2, 0)


    def set_le_curv (self, le_curv: float):

        self.targets_upper.set_le_curvature (le_curv)
        self.targets_lower.set_le_curvature (le_curv)


    def _messageText (self):
        """ user info"""
        text = f"Have a look at Curvature (comb) to tune target values."
        return text



class Panel_Match_Curve_Small (Panel_Match_Curve):
    """ Match Bezier functions - small version """

    _main_margins = Panel_Airfoil_Abstract.MAIN_MARGINS_MINI
    _small = True



class Panel_Target_Curv (Panel_Airfoil_Abstract):
    """ Curvature values of target airfoil (Match)  """

    name = 'Target Curvature'

    @property
    def target_airfoil (self) -> Airfoil:
        return self.app_model.airfoil_target

    @property
    def shouldBe_visible(self):
        return self.target_airfoil is not None

    @property
    def curv_upper (self) -> Line:
        return self.target_airfoil.geo.curvature.upper

    @property
    def curv_lower (self) -> Line:
        return self.target_airfoil.geo.curvature.lower

    @property
    def target_curv_le (self) -> float:
        return self.target_airfoil.geo.curvature.at_le


    def _init_layout (self):

        self._target_curv_le = None 
        self._target_curv_le_weighting = None

        l = QGridLayout()

        r,c = 0, 0 
        Label  (l,r+1,c,   get="Upper Side")
        Label  (l,r+2,c,   get="Lower Side")
        l.setColumnMinimumWidth (c,80)

        c += 1
        Label  (l,r,c, colSpan=3, get="LE curv  Max")
        FieldF (l,r+1,c  , get=lambda: self.curv_upper.y[0],  width=40, dec=0,
                style=lambda: self._style_curv_le(self.curv_upper.y[0], self.curv_lower.y[0]))
        FieldF (l,r+2,c  , get=lambda: self.curv_lower.y[0],  width=40, dec=0,
                style=lambda: self._style_curv_le(self.curv_upper.y[0], self.curv_lower.y[0]))
        
        c += 1
        # Label  (l,r,c, colSpan=1, get="Max")
        FieldF (l,r+1,c  , get=lambda: self.curv_upper.max_xy[1],  width=40, dec=0,
                style=lambda:self._style_max_curv(self.curv_upper.max_xy[1], self.target_curv_le))
        FieldF (l,r+2,c  , get=lambda: self.curv_lower.max_xy[1],  width=40, dec=0,
                style=lambda: self._style_max_curv(self.curv_lower.max_xy[1], self.target_curv_le))
        l.setColumnMinimumWidth (c+1,10)

        c += 2
        Label  (l,r,c, colSpan=2, get="Revers")
        FieldF (l,r+1,c, get=lambda: self.curv_upper.nreversals(), width=30, dec=0,
                style=lambda: self._style_nreversals(self.curv_upper))
        FieldF (l,r+2,c, get=lambda: self.curv_lower.nreversals(), width=30, dec=0,
                style=lambda: self._style_nreversals(self.curv_lower))
        l.setColumnMinimumWidth (c+1,10)

        c += 2
        Label  (l,r,c, colSpan=2, get="TE curv")
        FieldF (l,r+1,c, get=lambda: self.curv_upper.y[-1], width=40, dec=1,
                style=lambda: self._style_curv_te(self.curv_upper.y[-1]))
        FieldF (l,r+2,c, get=lambda: self.curv_lower.y[-1], width=40, dec=1,
                style=lambda: self._style_curv_te(self.curv_lower.y[-1]))

        r,c = 3,0 
        l.setRowStretch (r,2)
        r += 1
        Label  (l,r,0, get=self._message, colSpan=7, height=(None, None), style=style.COMMENT)

        return l


    def _style_curv_le (self, curv_le_upper : float, curv_le_lower : float):
        """ returns style.WARNING if curvature at LE differs too much"""
        return style.WARNING if abs(curv_le_upper - curv_le_lower) > 0.5 else style.NORMAL

    def _style_max_curv (self, max_curv: float, curv_le: float):
        """ returns style.WARNING if max_curv is not equal curv_le"""
        return style.WARNING if not np.isclose(max_curv, curv_le) else style.NORMAL

    def _style_nreversals (self, curv : Line):
        """ returns style.WARNING if nreversals > 1"""   

        reversals = curv.reversals()
        if len(reversals) == 0:
            return style.NORMAL
        else: 
            if reversals[-1] > 0.95:
                return style.WARNING
            elif len(reversals) > 1:
                return style.WARNING
            else:
                return style.NORMAL

    def _style_curv_te (self, curv_te: float):
        """ returns style.WARNING if curvature at TE is quite high"""
        return style.WARNING if abs(curv_te) > 5 else style.NORMAL


    def _message (self) -> str: 
        """ user warnings"""
        text = []

        for curv in [self.curv_upper, self.curv_lower]:

            if not np.isclose(curv.max_xy[1], self.target_curv_le):
                text.append(f"- {curv.name}: Max curvature is not at LE. ")

            nreversals = curv.nreversals()
            if nreversals > 1 and nreversals <= 3:
                text.append(f"- {curv.name}: Curvature has bumps.")
            elif nreversals > 3:
                text.append(f"- {curv.name}: Curvature has many bumps!")
            elif nreversals == 1 and curv.reversals()[-1] > 0.95:
                text.append(f"- {curv.name}: Reversal is very close to LE. Artefact?")

            if abs(curv.y[-1]) > 5:
                text.append(f"- {curv.name}: Curvature at TE is quite high.")     

        if len(text) < 2:
            if "_norm" in self.target_airfoil.name:
                text.insert(0, "Target airfoil has been repaneled and normalized.")
            else:
                text.insert(0, "Target airfoil has been repaneled")

        text = '\n'.join(text[:3])
        return text 

