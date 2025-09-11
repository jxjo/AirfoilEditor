#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

UI panels 

"""

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
from airfoil_dialogs        import Match_Bezier_Dialog, Matcher


logger = logging.getLogger(__name__)
# logger.setLevel(logging.WARNING)


class Panel_Airfoil_Abstract (Edit_Panel):
    """ 
    Abstract superclass for Edit/View-Panels of AirfoilEditor
        - has semantics of App
        - connect / handle signals 
    """

    from app  import Main

    @property
    def app (self) -> Main:
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
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if mode_modify """
        return not (self.mode_modify or self.mode_optimize)

    @property
    def _isDisabled (self) -> bool:
        """ override: always enabled """
        return False
    

    def _on_airfoil_widget_changed (self, *_ ):
        """ user changed data in widget"""
        # overloaded - do not react on self widget changes 
        pass


    def _init_layout (self): 

        l = QGridLayout()
        r,c = 0, 0 
        Airfoil_Select_Open_Widget (l,r,c, colSpan=4, signal=False, 
                                    textOpen="&Open", widthOpen=90, 
                                    get=lambda: self.airfoil, set=self.app.set_airfoil)
        r += 1
        Button (l,r,c, text="&Modify", width=90, 
                set=self.app.modify_airfoil, toolTip="Modify geometry, Normalize, Repanel, Set Flap",
                button_style=button_style.PRIMARY)
        MenuButton (l,r,c+2, text="More...", width=90, 
                menu=self._more_menu(), 
                toolTip="Choose further actions for this airfoil")
        # Button (l,r,c+2, text="&As Bezier", width=90, colSpan=2,
        #         set=self.app.new_as_Bezier, disable=lambda: self.airfoil.isBezierBased,
        #         toolTip="Create new Bezier airfoil based on current airfoil")
        r += 1
        SpaceR (l,r, height=10, stretch=0)
        r += 1
        Button (l,r,c, text="&Optimize...", width=90, 
                set=self.app.optimize_select, 
                toolTip=self._tooltip_optimize,
                disable=lambda: not Xoptfoil2.ready)
        r += 1
        SpaceR (l,r, stretch=1)
        r += 1
        Button (l,r,c, text="&Exit", width=90, set=self.app.close)
        r += 1
        SpaceR (l,r, height=5, stretch=0)        
        l.setColumnStretch (2,2)
        l.setColumnMinimumWidth (1,8)

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
        Field (l,r,c, colSpan=3, width=190, get=lambda: self.case.airfoil_seed.fileName)
        r += 1
        ComboSpinBox (l,r,c, colSpan=2, width=160, get=self.airfoil_fileName, 
                             set=self.set_airfoil_by_fileName,
                             options=self.airfoil_fileNames,
                             signal=False)
        ToolButton   (l,r,c+2, icon=Icon.DELETE, set=self.remove_current_airfoil,
                      hide=lambda: self.case.get_i_from_design (self.airfoil) == 0) # hide Design 0 
        r += 1
        SpaceR (l,r)
        l.setRowStretch (r,2)
        r += 1
        Button (l,r,c,  text="&Finish ...", width=90, 
                        set=lambda : self.app.mode_modify_finished(ok=True), 
                        toolTip="Save current airfoil, optionally modifiy name and leave edit mode")
        r += 1
        SpaceR (l,r, height=5, stretch=0)
        r += 1
        Button (l,r,c,  text="&Cancel",  width=90, 
                        set=lambda : self.app.mode_modify_finished(ok=False),
                        toolTip="Cancel modifications of airfoil and leave edit mode")
        r += 1
        SpaceR (l,r, height=5, stretch=0)
        l.setColumnStretch (3,2)

        return l


    def airfoil_fileName(self) -> list[str]:
        """ fileName of current airfoil without extension"""
        return os.path.splitext(self.airfoil.fileName)[0]


    def airfoil_fileNames(self) -> list[str]:
        """ list of design airfoil fileNames without extension"""

        fileNames = []
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



class Panel_Geometry (Panel_Airfoil_Abstract):
    """ Main geometry data of airfoil"""

    name = 'Geometry'
    _width  = 380

    @override
    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        # blend with airfoil - currently Bezier is not supported
        Button (l_head, text="&Blend", width=80,
                set=self.app.do_blend_with, 
                hide=lambda: not self.airfoil.isEdited or self.airfoil.isBezierBased,
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
                obj=lambda: self.geo, prop=Geometry.le_radius,
                disable=lambda: self.airfoil.isBezierBased)
        r += 1
        FieldF (l,r,c, lab="TE gap", width=75, unit="%", step=0.1,
                obj=lambda: self.geo, prop=Geometry.te_gap,
                toolTip=f"Set trailing edge gap in % of chord with a blending distance of {Geometry.TE_GAP_XBLEND:.0%}")
        ToolButton  (l,r,c+2, icon=Icon.EDIT, set=self.app.do_te_gap,
                hide=lambda: not self.mode_modify or self.mode_bezier,
                toolTip="Set trailing edge gap with a flexible blending distance")

        r += 1
        SpaceR (l,r, height=5)
        r += 1
        Label  (l,r,0,colSpan=4, get=self._messageText, style=style.COMMENT, height=(None,None))

        r,c = 0, 2 
        SpaceC (l,c, stretch=0)
        c += 1 
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

        l.setColumnMinimumWidth (0,80)
        l.setColumnMinimumWidth (2,30)
        l.setColumnMinimumWidth (3,60)
        l.setColumnStretch (5,2)
        return l 


    def _messageText (self): 
        """ text to show at bottom of panel"""

        if self.geo.curvature.max_te >= 2:
            text = f"- Curvature at trailing edge is quite high"
        else:
            text = f"Geometry {self.geo.description}"
        return text 



class Panel_Panels (Panel_Airfoil_Abstract):
    """ Panelling information """

    name = 'Panels'
    _width  =  (290, None)

    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        # repanel airfoil - currently Bezier is not supported
        Button (l_head, text="&Repanel", width=80,
                set=self.app.do_repanel, hide=lambda: not self.airfoil.isEdited,
                disable=lambda: self.geo.isBasic or self.geo.isHicksHenne,
                toolTip="Repanel airfoil with a new number of panels" ) 


    def _init_layout (self):

        l = QGridLayout()

        r,c = 0, 0 
        FieldI (l,r,c, lab="No of panels", disable=True, width=70, style=self._style_panel,
                get=lambda: self.geo.nPanels, )
        r += 1
        FieldF (l,r,c, lab="Angle at LE", width=70, dec=1, unit="°", style=self._style_angle,
                obj=lambda: self.geo, prop=Geometry.panelAngle_le)
        SpaceC (l,c+2, width=10, stretch=0)
        Label  (l,r,c+3,width=70, get=lambda: f"at index {self.geo.iLe}")
        r += 1
        FieldF (l,r,c, lab="Angle min", width=70, dec=1, unit="°",
                get=lambda: self.geo.panelAngle_min[0], )
        r += 1
        SpaceR (l,r,height=5)
        r += 1
        Label  (l,r,0,colSpan=4, get=self._messageText, style=style.COMMENT, height=(None,None))

        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (c+4,1)
        l.setRowStretch    (r-1,2)
        
        return l
 

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
        if self.geo.panelAngle_le > 175.0: 
            return style.WARNING
        else: 
            return style.NORMAL

    def _messageText (self): 

        text = []
        minAngle, _ = self.geo.panelAngle_min

        if self.geo.panelAngle_le > 175.0: 
            text.append("- Panel angle at LE (%d°) is too blunt" %(self.geo.panelAngle_le))
        if minAngle < 150.0: 
            text.append("- Min. angle of two panels is < 150°")
        if self.geo.panelAngle_le == 180.0: 
            text.append("- Leading edge has 2 points")
        if self.geo.nPanels < 100 or self.geo.nPanels > 200: 
            text.append("- No of panels should be > 100 and < 200")
        
        text = '\n'.join(text)
        return text 




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

        Button (l_head, text="Set F&lap", width=80,
                set=self.app.do_flap, hide=lambda: not self.mode_modify,
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

    @override
    def refresh(self, reinit_layout=False):

        # force new layout to show different flpa states 
        return super().refresh(reinit_layout=True)



class Panel_LE_TE  (Panel_Airfoil_Abstract):
    """ info about LE and TE coordinates"""

    name = 'LE, TE'

    _width  = 320

    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is not Bezier """
        return not self.mode_bezier 


    def _add_to_header_layout(self, l_head: QHBoxLayout):
        """ add Widgets to header layout"""

        Button (l_head, text="&Normalize", width=80,
                set=lambda : self.airfoil.normalize(), signal=True, 
                hide=lambda: not self.mode_modify,
                toolTip="Normalize airfoil to get leading edge at 0,0")


    def _init_layout (self): 

        l = QGridLayout()     
        r,c = 0, 0 
        FieldF (l,r,c, lab="Leading edge", get=lambda: self.geo.le[0], width=75, dec=7, style=lambda: self._style (self.geo.le[0], 0.0))
        r += 1
        FieldF (l,r,c, lab=" ... of spline", get=lambda: self.geo.le_real[0], width=75, dec=7, style=self._style_le_real,
                hide=lambda: not self.mode_modify)
        r += 1
        FieldF (l,r,c, lab="Trailing edge", get=lambda: self.geo.te[0], width=75, dec=7, style=lambda: self._style (self.geo.te[0], 1.0))
        r += 1
        FieldF (l,r,c+1,get=lambda: self.geo.te[2], width=75, dec=7, style=lambda: self._style (self.geo.te[0], 1.0))

        r,c = 0, 2 
        SpaceC (l,c, width=10, stretch=0)
        c += 1 
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

        l.setColumnMinimumWidth (0,80)
        l.setColumnStretch (c+3,1)
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
                text.append("- Trailing edge is not at x=1.0")
            if self.geo.te[1] != -self.geo.te[3]: 
                text.append("- Trailing edge is not at y=0.0")

        if not text:
            if self.geo.isSymmetrical: 
                text.append("Airfoil is symmetrical")
            else: 
                text.append("Airfoil is normalized")

        text = '\n'.join(text)
        return text 



class Panel_Bezier (Panel_Airfoil_Abstract):
    """ Info about Bezier curves upper and lower  """

    name = 'Bezier'
    _width  = (180, None)


    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is Bezier """
        return self.mode_bezier
    
    # ----

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
        SpaceR (l,r, height=10, stretch=2)
        l.setColumnMinimumWidth (0,70)
        l.setColumnStretch (c+2,4)
        
        return l
 


class Panel_Bezier_Match (Panel_Airfoil_Abstract):
    """ Match Bezier functions  """

    name = 'Bezier Match'
    _width  = (370, None)


    @override
    @property
    def shouldBe_visible (self) -> bool:
        """ overloaded: only visible if geo is Bezier """
        return self.mode_bezier

    # ----

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
            Label  (l,r,c+1, get="Deviation", width=70)

            r += 1
            Label  (l,r,c,   get="Upper Side")
            FieldF (l,r,c+1, width=60, dec=3, unit="%", get=self.norm2_upper,
                             style=lambda: Match_Bezier_Dialog.style_deviation (self.norm2_upper()))
            r += 1
            Label  (l,r,c,   get="Lower Side")
            FieldF (l,r,c+1, width=60, dec=3, unit="%", get=self.norm2_lower,
                             style=lambda: Match_Bezier_Dialog.style_deviation (self.norm2_lower()))

            r,c = 0, 2 
            SpaceC(l,  c, width=5)
            c += 1
            Label (l,r,c, colSpan=2, get="LE curvature TE")
    
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

            r,c = 0, 5 
            SpaceC (l,  c, width=10)
            c += 1
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
            l.setColumnMinimumWidth (0,70)
            l.setColumnStretch (c+6,2)

        else: 
            SpaceR (l,0)
            Label  (l,1,0, get="Select a target airfoil to match...", style=style.COMMENT)
            SpaceR (l,2, stretch=2)
        return l
 

    def _match_bezier (self, aSide : Side_Airfoil_Bezier, aTarget_line : Line, 
                            target_curv_le: float, max_curv_te : float  ): 
        """ run match bezier (dialog) """ 

        match_bezier = Match_Bezier_Dialog (self, aSide, aTarget_line,
                                    target_curv_le = target_curv_le,
                                    max_curv_te = max_curv_te,
                                    parentPos=(0.1, 0.1), dialogPos=(0,1))

        match_bezier.sig_new_bezier.connect     (self.app.sig_bezier_changed.emit)
        match_bezier.sig_pass_finished.connect  (self.app.sig_airfoil_changed.emit)
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

