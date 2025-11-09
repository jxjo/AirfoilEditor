#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""

The different operating modes of the app like View_Mode and Modify_Mode

"""

from enum import Enum, auto

from PyQt6.QtCore           import pyqtSignal, QObject
from PyQt6.QtWidgets        import QHBoxLayout, QMessageBox, QStackedWidget

from airfoil_diagrams       import Diagram_Airfoil_Polar 
from base.diagram           import Diagram 
from base.panels            import Container_Panel, Toaster        
from base.app_utils         import Settings

from model.xo2_driver       import Worker, Xoptfoil2
from model.case             import Case_Direct_Design, Case_As_Bezier

from app_model              import App_Model
from airfoil_dialogs        import Airfoil_Save_Dialog
from airfoil_panels         import *



import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Mode_Id(Enum):
    VIEW      = auto()
    MODIFY    = auto()
    OPTIMIZE  = auto()
    AS_BEZIER = auto()


class Data_Panel (Container_Panel):
    """ Base class for data panels used in different modes. """
    
    def __init__ (self, *args, **kwargs):
        super().__init__(*args, **kwargs)


        self.set_doubleClick (self.mode.toggle_minimized)
        self.add_hint ("Double click to minimize/maximize")

        self.app_model.sig_new_airfoil.connect (self.refresh)

    @property
    def mode (self) -> 'Mode_Abstract':
        return self._app 

    @property
    def app_model (self) -> App_Model:
        return self.dataObject   

    @override
    def refresh (self, always: bool = False):
        """ refresh panels of self - only when visible  """

        if self.isVisible() or always:
            super().refresh()



class Mode_Abstract (QObject):
    """
    Abstract base class for different application modes.

    A Mode provides the lower data panel of the UI and has methods for
        - entering and exiting the mode.
        - App level functions specific to the mode.

    It is managed by the Modes_Manager.
    """

    mode_id  : Mode_Id = None                                   # the id of the mode

    sig_exit_requested          = pyqtSignal()                  # signal to request mode and app exit
    sig_leave_requested         = pyqtSignal()                  # signal to request mode leave
    sig_switch_mode_requested   = pyqtSignal(Mode_Id)           # signal to request mode switch
    sig_toggle_minimized        = pyqtSignal()                  # signal to request toggle of minimized state


    def __init__(self, app_model: App_Model):
        super().__init__()

        self._app_model = app_model

        self._panel:       Data_Panel = None
        self._panel_small: Data_Panel = None

        self._panels:      QStackedWidget  = None

    @property
    def _airfoil(self): 
        """ current airfoil from app state """
        return self._app_model.airfoil

    def _set_airfoil(self, airfoil):
        """ set current airfoil in app state """
        self._app_model.set_airfoil (airfoil)


    @property
    def _case (self):
        """ current case from app state """
        return self._app_model.case

    def _set_case (self, case):
        """ set current case in app state """
        self._app_model.set_case (case)


    def _set_current_panel (self, minimized=False, refresh=True):
        """ Apply the current minimized state to the stacked data panel. """

        if minimized:
            new_current = self.panel_small
        else:
            new_current = self.panel

        self.panels.setCurrentWidget (new_current)

        if refresh:
            new_current.refresh(always=True)


    def _toast_message (self, msg, toast_style = style.HINT):
        """ show toast message """
        
        Toaster.showMessage (self.panel, msg, corner=Qt.Corner.BottomLeftCorner, margin=QMargins(10, 10, 10, 10),
                             toast_style=toast_style)

    @property
    def panel(self):
        return self._panel

    @property
    def panel_small(self):
        return self._panel_small

    @property
    def panels(self) -> QStackedWidget:
        """ Get the stacked widget containing both data panels. """

        if self._panels is None:
            self._panels = QStackedWidget()
            self._panels.addWidget (self.panel)
            self._panels.addWidget (self.panel_small)

            # set initial visibility
            self._set_current_panel(refresh=False)

        return self._panels


    def on_enter(self):
        """ Actions to perform when entering the mode. Override in subclasses if needed. """

        logger.debug(f"Entering {self.__class__.__name__}")


    def on_leave(self):
        """ Actions to perform when exiting the mode. Override in subclasses if needed. """
        logger.debug(f"Exiting {self.__class__.__name__}")


    def check_enter_conditions(self) -> bool:
        """ Check if the mode can be entered. Override in subclasses if needed. """
        return True
    

    def set_minimized (self, minimized: bool):
        """ Set self and all modes to minimized or normal state. """

        self._set_current_panel (minimized=minimized)


    def toggle_minimized (self):
        """ Toggle the minimized state of the data panel. """
        self.sig_toggle_minimized.emit ()



    # ---- User actions ----

    def cancel (self):
        """ User action: Cancel current mode and request exit. """
        self.sig_leave_requested.emit()


    def finish (self):
        """ User action: Finish current mode and request exit. """
        self.sig_leave_requested.emit()




class Mode_View (Mode_Abstract):
    """
    Application mode for viewing airfoils without modification capabilities.
    """

    mode_id = Mode_Id.VIEW                       # the id of the mode


    @property
    def panel (self) -> Data_Panel:
        """ lower UI main panel """

        if self._panel is None: 

            l = QHBoxLayout()

            p = Panel_File_View (self, self._app_model, width=250, lazy=True)
            p.sig_toggle_panel_size.connect     (self.toggle_minimized)
            p.sig_modify.connect                (self.modify)
            p.sig_exit .connect                 (self.exit)
            l.addWidget (p)

            l.addWidget (Panel_Geometry        (self, self._app_model, lazy=True))
            l.addWidget (Panel_Panels          (self, self._app_model, lazy=True))
            l.addWidget (Panel_LE_TE           (self, self._app_model, lazy=True))
            l.addWidget (Panel_Bezier          (self, self._app_model, lazy=True))
            l.addWidget (Panel_Flap            (self, self._app_model, lazy=True))

            self._panel = Data_Panel (self, self._app_model, layout=l)

        return self._panel


    @property
    def panel_small (self) -> Data_Panel:
        """ lower UI view panel - small version with only small panels"""

        if self._panel_small is None:

            l = QHBoxLayout()

            p = Panel_File_View_Small (self, self._app_model, has_head=False, width=250, lazy=True)
            p.sig_toggle_panel_size.connect     (self.toggle_minimized)
            p.sig_modify.connect                (self.modify)
            p.sig_exit .connect                 (self.exit)
            l.addWidget (p)

            l.addWidget (Panel_Geometry_Small   (self, self._app_model, has_head=False, lazy=True))
            l.addWidget (Panel_Panels_Small     (self, self._app_model, has_head=False, lazy=True))
            l.addWidget (Panel_LE_TE_Small      (self, self._app_model, has_head=False, lazy=True))
            l.addWidget (Panel_Bezier_Small     (self, self._app_model, has_head=False, lazy=True))
            l.addWidget (Panel_Flap_Small       (self, self._app_model, has_head=False, lazy=True))

            self._panel_small = Data_Panel (self, self._app_model, layout=l)

        return self._panel_small


    # ---- User actions ----

    def modify (self): 
        """ switch to modify mode """
        self.sig_switch_mode_requested.emit (Mode_Id.MODIFY)


    def save_as (self): 
        """ save current airfoil as ..."""

        airfoil = self._app_model.airfoil

        dlg = Airfoil_Save_Dialog (parent=self, getter=airfoil)
        ok_save = dlg.exec()

        if ok_save: 
            self._set_airfoil (airfoil)                         # refresh with new

            self._toast_message (f"New airfoil {airfoil.fileName} saved", toast_style=style.GOOD)
            logger.info (f"Airfoil saved as {airfoil.fileName}")


    def rename (self): 
        """ rename current airfoil as ..."""

        airfoil = self._app_model.airfoil

        old_pathFileName = airfoil.pathFileName_abs

        dlg = Airfoil_Save_Dialog (parent=self, getter=airfoil , rename_mode=True, remove_designs=True)
        ok_save = dlg.exec()

        if ok_save: 

            # delete old one 
            if os.path.isfile (old_pathFileName):  
                os.remove (old_pathFileName)

            # a copy with new name was created 
            self._app_model.set_airfoil (airfoil)

            self._toast_message (f"Airfoil renamed to {airfoil.fileName}", toast_style=style.GOOD)
            logger.info (f"Airfoil renamed to {airfoil.fileName}")


    def delete (self): 
        """ delete current airfoil ..."""

        airfoil = self._app_model.airfoil

        if not os.path.isfile (airfoil.pathFileName_abs): return 

        text = f"Airfoil <b>{airfoil.fileName}</b> including temporary files will be deleted."
        button = MessageBox.warning (self, "Delete airfoil", text)

        if button == QMessageBox.StandardButton.Ok:

            self.delete_temp_files (silent=True)
            os.remove (airfoil.pathFileName_abs)                               # remove airfoil

            self._toast_message (f"Airfoil {airfoil.fileName} deleted", toast_style=style.GOOD)
            logger.info (f"Airfoil {airfoil.fileName} deleted")

            next_airfoil = get_next_airfoil_in_dir (airfoil, example_if_none=True)
            self._app_model.set_airfoil (next_airfoil)                           # try to set on next airfoil

            if next_airfoil.isExample:
               button = MessageBox.info (self, "Delete airfoil", "This was the last airfoil in the directory.<br>" + \
                                               "Showing Example airfoil") 


    def delete_temp_files (self, silent=False): 
        """ delete all temp files and directories of current airfoil ..."""

        airfoil = self._app_model.airfoil
        if not os.path.isfile (airfoil.pathFileName_abs): return 

        delete = True 

        if not silent: 
            text = f"All temporary files and directories of Airfoil <b>{airfoil.fileName}</b> will be deleted."
            button = MessageBox.warning (self, "Delete airfoil", text)
            if button != QMessageBox.StandardButton.Ok:
                delete = False
        
        if delete: 
            Case_Direct_Design.remove_design_dir (airfoil.pathFileName_abs)    # remove temp design files and dir 
            Worker.remove_polarDir (airfoil.pathFileName_abs)                  # remove polar dir 
            Xoptfoil2.remove_resultDir (airfoil.pathFileName_abs)              # remove Xoptfoil result dir 

            if not silent:
                self._toast_message (f"Temporary files of Airfoil {airfoil.fileName} deleted", toast_style=style.GOOD)


    def exit (self):
        """ User action: leave current mode and app. """

        self.sig_exit_requested.emit ()


    def new_as_Bezier (self):
        """ create new Bezier airfoil based on current airfoil, create Case, switch to modify mode """

        #todo
        # current airfoil should be normalized to achieve good results 


        # create new Design Case and get/create first design 

        self.set_case (Case_As_Bezier (self._airfoil))

        self.set_mode_modify (True)  
        self.set_airfoil (self.case.initial_airfoil_design() , silent=False)



class Mode_Modify (Mode_Abstract):
    """
    Application mode for modifying airfoils.
    """

    mode_id = Mode_Id.MODIFY                       # the id of the mode


    def check_enter_conditions(self) -> bool:
        """ Check if the mode can be entered. Override in subclasses if needed. """

        # info if airfoil is flapped 
        if self._airfoil.geo.isProbablyFlapped:

            text = "The airfoil is probably flapped and will be normalized.\n\n" + \
                   "Modifying the geometry can lead to strange results."
            button = MessageBox.confirm (self, "Modify Airfoil", text)
            if button == QMessageBox.StandardButton.Cancel:
                return False
        return True


    def on_enter(self):

        # ensure example airfoil is saved to file to ease consistent further handling in widgets
        if self._airfoil.isExample: 
            self._airfoil.save()

        # create new Design Case and get/create first design 

        self._set_case (Case_Direct_Design (self._airfoil))

        super().on_enter()


    def on_leave(self):
        """ Actions to perform when exiting the mode. Override in subclasses if needed. """
        self._set_case (None)
        super().on_leave()


    def cancel(self):
        """ User action: Cancel current mode and request exit. """

        self._set_airfoil (self._case.airfoil_seed)       # restore original airfoil
        self._case.close (remove_designs=False)           # shut down case  
        super().cancel()


    def finish(self):
        """ User action: Finish current mode and request exit. """

        # create new, final airfoil based on actual design and path from airfoil org 

        case : Case_Direct_Design = self._case
        new_airfoil = case.get_final_from_design (self._airfoil)

        # dialog to edit name, choose path, ..

        dlg = Airfoil_Save_Dialog (parent=self.panels, getter=new_airfoil,
                                   parentPos=(0.25,-1), dialogPos=(0,1))
        ok = dlg.exec()

        if not ok: return                                       # save was cancelled - return to modify mode 

        # close case, set new current airfoil

        self._case.close (remove_designs= dlg.remove_designs)          
        self._app_model.set_airfoil (new_airfoil)

        self._toast_message (f"New airfoil {new_airfoil.fileName} saved", toast_style=style.GOOD)
        logger.info (f"New airfoil {new_airfoil.fileName} created from {self._airfoil.fileName}")

        super().finish()
    

    @property
    def panel (self) -> Data_Panel:
        """ lower UI main panel - modify mode """

        if self._panel is None: 

            l = QHBoxLayout()

            p = Panel_File_Modify (self, self._app_model, width=250, lazy=True)
            p.sig_cancel.connect                (self.cancel)
            p.sig_finish.connect                (self.finish)
            p.sig_toggle_panel_size.connect     (self.toggle_minimized)
            l.addWidget (p)

            l.addWidget (Panel_Geometry        (self, self._app_model, lazy=True))
            l.addWidget (Panel_Panels          (self, self._app_model, lazy=True))
            l.addWidget (Panel_LE_TE           (self, self._app_model, lazy=True))
            l.addWidget (Panel_Flap            (self, self._app_model, lazy=True))
            l.addWidget (Panel_Bezier          (self, self._app_model, lazy=True))
            l.addWidget (Panel_Bezier_Match    (self, self._app_model, lazy=True))

            self._panel    = Data_Panel (self, self._app_model, layout = l)

        return self._panel


    @property
    def panel_small (self) -> Data_Panel:
        """ lower UI view panel - small version"""

        if self._panel_small is None: 

            l = QHBoxLayout()

            p = Panel_File_Modify_Small (self, self._app_model, width=250, lazy=True, has_head=False)
            p.sig_cancel.connect                (self.cancel)
            p.sig_finish.connect                (self.finish)
            p.sig_toggle_panel_size.connect     (self.toggle_minimized)
            l.addWidget (p)

            l.addWidget (Panel_Geometry_Small       (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Panels_Small         (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_LE_TE_Small          (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Bezier_Small         (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Bezier_Match_Small   (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Flap_Small           (self, self._app_model, lazy=True, has_head=False))

            self._panel_small = Data_Panel (self, self._app_model, layout=l)

        return self._panel_small



class Mode_As_Bezier (Mode_Abstract):
    """
    Application mode for create new airfoil based on Bezier curves.
    """

    mode_id = Mode_Id.AS_BEZIER                       # the id of the mode

            
    def check_enter_conditions(self) -> bool:
        """ Check if the mode can be entered. Override in subclasses if needed. """

        if not self.airfoil.isNormalized:

            text = "The airfoil is not normalized.\n\n" + \
                   "Match Bezier will not lead to the best results."
            button = MessageBox.confirm (self, "New As Bezier", text)
            if button == QMessageBox.StandardButton.Cancel:
                return False
        return True
        # info if airfoil is flapped 


    def on_enter(self):

        # ensure example airfoil is saved to file to ease consistent further handling in widgets
        if self._airfoil.isExample: 
            self._airfoil.save()

        # create new Design Case and get/create first design 
        self._set_case (Case_As_Bezier (self._airfoil))

        super().on_enter()


    def on_leave(self):
        """ Actions to perform when exiting the mode. Override in subclasses if needed. """
        self._set_case (None)
        super().on_leave()


    def cancel(self):
        """ User action: Cancel current mode and request exit. """

        self._set_airfoil (self._case.airfoil_seed)       # restore original airfoil
        self._case.close (remove_designs=True)            # shut down case and remove design dir
        super().cancel()


    def finish(self):
        """ User action: Finish current mode and request exit. """

        # create new, final airfoil based on actual design and path from airfoil org 

        case : Case_As_Bezier = self._case
        new_airfoil = case.get_final_from_design (self._airfoil)

        # dialog to edit name, choose path, ..

        dlg = Airfoil_Save_Dialog (parent=self, getter=new_airfoil)
        ok = dlg.exec()

        if not ok: return                                       # save was cancelled - return to modify mode 

        # close case, set new current airfoil

        remove_designs = dlg.remove_designs

        self._case.close (remove_designs=remove_designs)          

        self._set_airfoil (new_airfoil, silent=False)

        self._toast_message (f"New airfoil {new_airfoil.fileName} saved", toast_style=style.GOOD)
        logger.info (f"New airfoil {new_airfoil.fileName} created from {self._airfoil.fileName}")

        super().finish()
    


    @property
    def panel (self) -> Data_Panel:
        """ lower UI main panel - modify mode """

        if self._panel is None: 

            l = QHBoxLayout()
            l.addWidget (Panel_File_Modify     (self, self._app_model, width=250, lazy=True))
            l.addWidget (Panel_Geometry        (self, self._app_model, lazy=True))
            l.addWidget (Panel_Panels          (self, self._app_model, lazy=True))
            l.addWidget (Panel_Bezier          (self, self._app_model, lazy=True))
            l.addWidget (Panel_Bezier_Match    (self, self._app_model, lazy=True))

            self._panel    = Data_Panel (self, self._app_model, layout = l)

        return self._panel


    @property
    def panel_small (self) -> Data_Panel:
        """ lower UI view panel - small version"""

        if self._panel_small is None: 

            l = QHBoxLayout()
            l.addWidget (Panel_File_Modify_Small    (self, self._app_model, lazy=True, width=250, has_head=False))
            l.addWidget (Panel_Geometry_Small       (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Panels_Small         (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Bezier_Small         (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Bezier_Match_Small   (self, self._app_model, lazy=True, has_head=False))

            self._panel_small = Data_Panel (self, self._app_model, layout=l)

        return self._panel_small



class Mode_Optimize (Mode_Abstract):
    """
    Application mode for optimizing airfoils.
    """

    mode_id = Mode_Id.OPTIMIZE                       # the id of the mode


    def on_enter(self):
        super().on_enter()

    def on_leave(self):
        super().on_leave()


    @property
    def panel (self) -> Data_Panel:
        """ lower UI main panel"""

        if self._panel is None: 

            from xo2_panels import (Panel_Xo2_File, Panel_Xo2_Case, Panel_Xo2_Operating_Conditions,
                                    Panel_Xo2_Operating_Points, Panel_Xo2_Geometry_Targets,
                                    Panel_Xo2_Curvature, Panel_Xo2_Advanced)

            l = QHBoxLayout()        
            l.addWidget (Panel_Xo2_File                    (self, self._case, width=250, lazy=True))
            l.addWidget (Panel_Xo2_Case                    (self, self._case, lazy=True))
            l.addWidget (Panel_Xo2_Operating_Conditions    (self, self._case, lazy=True))
            l.addWidget (Panel_Xo2_Operating_Points        (self, self._case, lazy=True))
            l.addWidget (Panel_Xo2_Geometry_Targets        (self, self._case, lazy=True))
            l.addWidget (Panel_Xo2_Curvature               (self, self._case, lazy=True))
            l.addWidget (Panel_Xo2_Advanced                (self, self._case, lazy=True))

            self._panel = Data_Panel (self, self._app_model, layout = l)

        return self._panel


    @property
    def panel_small (self) -> Data_Panel:
        """ lower UI main panel """

        if self._panel_small is None: 

            from xo2_panels import (Panel_Xo2_File_Small, Panel_Xo2_Case_Small, Panel_Xo2_Operating_Small,
                                    Panel_Xo2_Geometry_Targets_Small)

            l = QHBoxLayout()        
            l.addWidget (Panel_Xo2_File_Small               (self, self._case, width=250, has_head=False))
            l.addWidget (Panel_Xo2_Case_Small               (self, self._case, lazy=True, has_head=False))
            l.addWidget (Panel_Xo2_Operating_Small          (self, self._case, lazy=True, has_head=False))
            l.addWidget (Panel_Xo2_Geometry_Targets_Small   (self, self._case, lazy=True, has_head=False))

            self._panel_small = Data_Panel (self, self._app_model, layout = l)

        return self._panel_small



# ------------------------------------------------------------------------------


class Modes_Manager (QObject):
    """
    Manages the different application modes.

    The Modes Manager provides a stacked data panel which presents the lower part of the UI
    according to the current mode.
    """

    sig_close_requested = pyqtSignal()                      # signal to request app close


    def __init__(self):
        super().__init__()

        self._modes_dict  = {}
        self._panels_dict = {}

        self._current_mode : Mode_Abstract = None
        self._modes_panel : QStackedWidget = None

        self._height            = 250                       # default height of modes panel
        self._height_minimized  = 150                       # default height of modes panel when minimized

        s = Settings()
        self._is_minimized = s.get('lower_panel_minimized', False)


    @property
    def modes_panel (self) -> QStackedWidget:
        """ Get the stacked widget containing the data panels of all modes. """

        if self._modes_panel is None:
            self._modes_panel = QStackedWidget()
        return self._modes_panel


    def add_mode(self, mode: Mode_Abstract):
        """ add a mode to the manager """

        mode_id = mode.mode_id

        if not mode_id in self._modes_dict:

            self._modes_dict [mode_id] = mode                        # register mode
            self._panels_dict[mode_id] = mode.panels                 # register mode's data panels
            self.modes_panel.addWidget (mode.panels)                 # add mode's data panels to stacked widget

            # connect to signals of Mode
            mode.sig_exit_requested.connect         (self.exit)
            mode.sig_leave_requested.connect        (self.leave_mode)
            mode.sig_switch_mode_requested.connect  (self.set_mode)
            mode.sig_toggle_minimized.connect       (self.toggle_minimized)


    def set_mode(self, mode_id: Mode_Id):
        """ switch to given mode """

        if mode_id in self._modes_dict:

            new_mode   : Mode_Abstract = self._modes_dict  [mode_id]
            new_panels : QWidget       = self._panels_dict [mode_id]

            if not new_mode.check_enter_conditions():
                return
            
            if self._current_mode is not None:
                self._current_mode.on_leave()

            self._current_mode = new_mode
            self.modes_panel.setCurrentWidget (new_panels)

            new_mode.on_enter()                                     # prepare enter new mode
            new_mode.set_minimized (self._is_minimized)             # apply minimized state

        else:
            logger.error(f"Mode {mode_id} not registered in Mode_Manager.")


    def leave_mode (self):
        """ leave current mode and return to view mode """

        self.set_mode (Mode_Id.VIEW)


    def exit(self, airfoil_last_opened : str = None):
        """ exit mode and close app if in view mode """

        if self._current_mode is not None:
            self._current_mode.on_leave()

        s = Settings()
        s.set('lower_panel_minimized', self._is_minimized)
        s.save()

        self.sig_close_requested.emit()             # close app if view mode finished


    def switch_to_mode_modify (self):
        """ switch to modify mode """

        self.set_mode (Mode_Id.MODIFY)


    def set_height (self, height: int, minimized: int|None = None):
        """ set height of modes panel """

        self._height = height
        self._height_minimized = minimized if minimized is not None else self._height_minimized

        self.set_minimized (self._is_minimized)                     # apply height change


    def set_minimized (self, minimized: bool):
        """ set minimized state of modes panel """

        self._is_minimized = minimized

        if self._current_mode is not None:
            self._current_mode.set_minimized (minimized)
            height = self._height_minimized if minimized else self._height
            self.modes_panel.setFixedHeight (height)    


    def toggle_minimized (self):
        """ toggle minimized state of modes panel """

        if self._current_mode is not None:
            self.set_minimized (not self._is_minimized)



