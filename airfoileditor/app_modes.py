#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""

The different operating modes of the app like View_Mode and Modify_Mode

The modes are controlled by the Modes_Manager 

"""

from PyQt6.QtCore           import pyqtSignal, QObject, QTimer
from PyQt6.QtWidgets        import QHBoxLayout, QMessageBox, QStackedWidget, QDialog

from base.panels            import Container_Panel, Toaster        
from base.app_utils         import Settings

from model.xo2_driver       import Worker, Xoptfoil2
from model.case             import Case_Direct_Design, Case_As_Bezier

from ui.ae_dialogs          import Airfoil_Save_Dialog
from ui.ae_panels           import *

from ui.xo2_dialogs         import Xo2_Select_Dialog, Xo2_New_Dialog
from ui.xo2_panels          import *

from app_model              import App_Model, Mode_Id


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# ------------------------------------------------------------------------------


class Data_Panel (Container_Panel):
    """ 
    Base class for data panels used in different modes. 
    - support double click to minimize/maximize
    - ensure refresh when visible
    """
    
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


# ------------------------------------------------------------------------------


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
    sig_switch_mode_requested   = pyqtSignal(Mode_Id, object)   # signal to request mode switch
    sig_toggle_minimized        = pyqtSignal()                  # signal to request toggle of minimized state


    def __init__(self, app_model: App_Model):
        super().__init__()

        self._app_model = app_model

        self._panel:       Data_Panel = None
        self._panel_small: Data_Panel = None

        self._stacked_panel:  QStackedWidget  = None


    def __repr__(self):
        """ nice representation of self """
        return f"<{self.__class__.__name__}>"


    @property
    def _airfoil(self): 
        """ current airfoil from app state """
        return self._app_model.airfoil


    def _toast_message (self, msg, toast_style = style.HINT):
        """ show toast message """
        
        Toaster.showMessage (self.stacked_panel, msg, corner=Qt.Corner.BottomLeftCorner, margin=QMargins(10, 10, 10, 5),
                             toast_style=toast_style)

    @property
    def panel(self):
        return self._panel

    @property
    def panel_small(self):
        return self._panel_small

    @property
    def stacked_panel(self) -> QStackedWidget:
        """ Get the stacked widget containing both data panels. """

        if self._stacked_panel is None:
            self._stacked_panel = QStackedWidget()
            self._stacked_panel.addWidget (self.panel)
            self._stacked_panel.addWidget (self.panel_small)

            # set initial visibility
            self.set_current_panel(refresh=False)

        return self._stacked_panel


    def on_enter(self, initial_arg: Airfoil | str = None):
        """ 
        Actions to perform when entering the mode. 
            Override in subclasses if needed. 
            Call super().on_enter() to ensure mode_id is set in app_model.
        """

        on_str = f" with arg {initial_arg}" if initial_arg is not None else ""   
        logger.debug(f"Entering {self.__class__.__name__} {on_str}")


    def on_leave(self):
        """ Actions to perform when exiting the mode. Override in subclasses if needed. """
        logger.debug(f"Exiting {self.__class__.__name__}")


    def prepare_check_enter(self, on_arg=None) -> Airfoil | str:
        """ Check if the mode can be entered. Prepare and Return initial object. """
        # to be overridden in subclasses if needed.
        return on_arg
    
    @property
    def current_panel(self) -> Data_Panel:
        """ Get the currently visible data panel. """
        return self.stacked_panel.currentWidget() 


    def set_current_panel (self, minimized: bool = False, refresh=True):
        """ Set self and all modes to minimized or normal state. """

        if minimized:
            new_current = self.panel_small
        else:
            new_current = self.panel

        self.stacked_panel.setCurrentWidget (new_current)

        if refresh:
            new_current.refresh(always=True)


    def toggle_minimized (self):
        """ Toggle the minimized state of the data panel. """
        self.sig_toggle_minimized.emit ()



    # ---- User actions ----

    def cancel (self):
        """ User action: Cancel current mode and request exit. """
 
        QTimer.singleShot (0, self.sig_leave_requested.emit)    # leave after current events processed


    def finish (self):
        """ User action: Finish current mode and request exit. """

        QTimer.singleShot (0, self.sig_leave_requested.emit)    # leave after current events processed


    def switch_mode (self, mode_id: Mode_Id, on_arg=None):
        """ User action: Switch to another mode. """
         
        QTimer.singleShot (0, lambda: self.sig_switch_mode_requested.emit (mode_id, on_arg))



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
            p.sig_optimize.connect              (self.optimize)
            p.sig_new_as_bezier.connect         (self.new_as_Bezier)
            p.sig_save_as.connect               (self.save_as)
            p.sig_rename.connect                (self.rename)
            p.sig_delete.connect                (self.delete)
            p.sig_delete_temp_files.connect     (self.delete_temp_files)
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
            p.sig_optimize.connect              (self.optimize)
            p.sig_new_as_bezier.connect         (self.new_as_Bezier)
            p.sig_save_as.connect               (self.save_as)
            p.sig_rename.connect                (self.rename)
            p.sig_delete.connect                (self.delete)
            p.sig_delete_temp_files.connect     (self.delete_temp_files)
            p.sig_exit .connect                 (self.exit)
            l.addWidget (p)

            l.addWidget (Panel_Geometry_Small   (self, self._app_model, has_head=False, lazy=True))
            l.addWidget (Panel_Panels_Small     (self, self._app_model, has_head=False, lazy=True))
            l.addWidget (Panel_LE_TE_Small      (self, self._app_model, has_head=False, lazy=True))
            l.addWidget (Panel_Bezier_Small     (self, self._app_model, has_head=False, lazy=True))
            l.addWidget (Panel_Flap_Small       (self, self._app_model, has_head=False, lazy=True))

            self._panel_small = Data_Panel (self, self._app_model, layout=l)

        return self._panel_small

    def prepare_check_enter(self, initial_airfoil: Airfoil | None) -> Airfoil:
        """ Check if the mode can be entered. Prepare and Return initial object. """

        if isinstance (initial_airfoil, Airfoil):
            return initial_airfoil
        else:
            return self._airfoil


    def on_enter(self, airfoil: Airfoil):

        self._app_model.set_airfoil (airfoil, silent=True, load_settings=True)

        # switch app_model to this mode - remove any case
        self._app_model.set_mode_and_case (self.mode_id, None)

        super().on_enter()

    # ---- User actions ----

    def modify (self): 
        """ switch to modify mode """
        self.switch_mode (Mode_Id.MODIFY)


    def optimize (self): 
        """ switch to optimize mode """
        self.switch_mode (Mode_Id.OPTIMIZE)


    def save_as (self): 
        """ save current airfoil as ..."""

        airfoil = self._app_model.airfoil

        dlg = Airfoil_Save_Dialog (self.stacked_panel, airfoil)
        ok_save = dlg.exec()

        if ok_save: 
            self._app_model.set_airfoil (airfoil)                         # refresh with new

            self._toast_message (f"New airfoil {airfoil.fileName} saved", toast_style=style.GOOD)
            logger.info (f"Airfoil saved as {airfoil.fileName}")


    def rename (self): 
        """ rename current airfoil as ..."""

        airfoil = self._app_model.airfoil

        old_pathFileName = airfoil.pathFileName_abs

        dlg = Airfoil_Save_Dialog (self.stacked_panel, airfoil , rename_mode=True, remove_designs=True)
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
        button = MessageBox.warning (self.stacked_panel, "Delete airfoil", text)

        if button == QMessageBox.StandardButton.Ok:

            self.delete_temp_files (silent=True)
            os.remove (airfoil.pathFileName_abs)                               # remove airfoil

            self._toast_message (f"Airfoil {airfoil.fileName} deleted", toast_style=style.GOOD)
            logger.info (f"Airfoil {airfoil.fileName} deleted")

            next_airfoil = get_next_airfoil_in_dir (airfoil, example_if_none=True)
            self._app_model.set_airfoil (next_airfoil)                           # try to set on next airfoil

            if next_airfoil.isExample:
               button = MessageBox.info (self.stacked_panel, "Delete airfoil", "This was the last airfoil in the directory.<br>" + \
                                               "Showing Example airfoil") 


    def delete_temp_files (self, silent=False): 
        """ delete all temp files and directories of current airfoil ..."""

        airfoil = self._app_model.airfoil
        if not os.path.isfile (airfoil.pathFileName_abs): return 

        delete = True 

        if not silent: 
            text = f"All temporary files and directories of Airfoil <b>{airfoil.fileName}</b> will be deleted."
            button = MessageBox.warning (self.stacked_panel, "Delete airfoil", text)
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

        self.switch_mode (Mode_Id.AS_BEZIER)




class Mode_Modify (Mode_Abstract):
    """
    Application mode for modifying airfoils.
    """

    mode_id = Mode_Id.MODIFY                       # the id of the mode


    def prepare_check_enter(self, on_arg = None ) -> Airfoil | None:
        """ Check if the mode can be entered. Override in subclasses if needed. """

        # info if airfoil is flapped 
        if self._airfoil.geo.isProbablyFlapped:

            text = "The airfoil is probably flapped and will be normalized.\n\n" + \
                   "Modifying the geometry can lead to strange results."
            button = MessageBox.confirm (self.stacked_panel, "Modify Airfoil", text)
            if button == QMessageBox.StandardButton.Cancel:
                return None
        return self._airfoil


    def on_enter(self, airfoil: Airfoil):
        """ Actions to perform when entering the mode. """
        # ensure example airfoil is saved to file to ease consistent further handling in widgets
        if airfoil.isExample:
            airfoil.save()

        # switch app_model to this mode with new Design Case - will get/create first design
        self._app_model.set_mode_and_case (self.mode_id, Case_Direct_Design (airfoil))

        # show airfoil design initially
        self._app_model.set_show_airfoil_design (True)

        super().on_enter()


    def on_leave(self):
        """ Actions to perform when exiting the mode.  """

        super().on_leave()

        if self._app_model.case.airfoil_final:
            next_airfoil = self._app_model.case.airfoil_final       # final airfoil created in finish
        else:
            next_airfoil = self._app_model.case.airfoil_seed
        next_airfoil.set_usedAs (usedAs.NORMAL)                     # normal AE color 

        self._app_model.case.close()                                # shut down case
        self._app_model.set_case (None)
        self._app_model.set_airfoil (next_airfoil, silent=True)     # we'll continue with set airfoil to final or seed


    def cancel(self):
        """ User action: Cancel current mode and request exit. """

        self._app_model.case.set_airfoil_final (None)                 # just sanity

        # rest will be done in on_leave
        super().cancel()


    def finish(self):
        """ User action: Finish current mode and request exit. """

        # create new, final airfoil based on actual design and path from airfoil org 

        case : Case_Direct_Design = self._app_model.case
        new_airfoil = case.get_final_from_design (self._airfoil)

        # dialog to edit name, choose path, ..

        dlg = Airfoil_Save_Dialog (parent=self.stacked_panel, getter=new_airfoil,
                                   parentPos=(0.25,-1), dialogPos=(0,1))
        ok = dlg.exec()
        if not ok: return                                       # save was cancelled - return to modify mode 

        # set final airfoil in case - rest will be done in on_leave
        self._app_model.case.set_remove_designs_on_close (dlg.remove_designs)
        self._app_model.case.set_airfoil_final (new_airfoil)

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

            
    def prepare_check_enter(self, on_arg = None) -> Airfoil | None:
        """ Check if the mode can be entered. Override in subclasses if needed. """

        if not self._airfoil.isNormalized:

            text = "The airfoil is not normalized.\n\n" + \
                   "Match Bezier will not lead to the best results."
            button = MessageBox.confirm (self.stacked_panel, "New As Bezier", text)
            if button == QMessageBox.StandardButton.Cancel:
                return None
        return self._airfoil


    def on_enter(self, airfoil: Airfoil):

        # ensure example airfoil is saved to file to ease consistent further handling in widgets
        if airfoil.isExample:
            airfoil.save()

        # switch app_model to this mode with new Design Case - will get/create first design
        self._app_model.set_mode_and_case (self.mode_id, Case_As_Bezier (airfoil))

        # show airfoil design initially
        self._app_model.set_show_airfoil_design (True)

        super().on_enter()


    def on_leave(self):
        """ Actions to perform when exiting the mode. Override in subclasses if needed. """

        if self._app_model.case.airfoil_final:
            next_airfoil = self._app_model.case.airfoil_final       # final airfoil created in finish
        else:
            next_airfoil = self._app_model.case.airfoil_seed

        self._app_model.case.close()                                 # shut down case
        self._app_model.set_case (None)
        self._app_model.set_airfoil (next_airfoil, silent=True)      # we'll continue with set airfoil to final or seed

        super().on_leave()


    def cancel(self):
        """ User action: Cancel current mode and request exit. """

        self._app_model.case.set_airfoil_final (None)                 # just sanity

        # rest will be done in on_leave
        super().cancel()


    def finish(self):
        """ User action: Finish current mode and request exit. """

        # create new, final airfoil based on actual design and path from airfoil org 

        case : Case_As_Bezier = self._app_model.case
        new_airfoil = case.get_final_from_design (self._airfoil)

        # dialog to edit name, choose path, ..

        dlg = Airfoil_Save_Dialog (parent=self.stacked_panel, getter=new_airfoil,
                                   parentPos=(0.25,-1), dialogPos=(0,1))
        ok = dlg.exec()
        if not ok: return                                       # save was cancelled - return to modify mode 

        # set final airfoil in case - rest will be done in on_leave
        self._app_model.case.set_remove_designs_on_close (dlg.remove_designs)
        self._app_model.case.set_airfoil_final (new_airfoil)

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
            # p.sig_cancel.connect                (self.cancel)
            p.sig_finish.connect                (self.finish)
            p.sig_toggle_panel_size.connect     (self.toggle_minimized)
            l.addWidget (p)

            l.addWidget (Panel_Geometry_Small       (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Panels_Small         (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Bezier_Small         (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Bezier_Match_Small   (self, self._app_model, lazy=True, has_head=False))

            self._panel_small = Data_Panel (self, self._app_model, layout=l)

        return self._panel_small


# ------------------------------------------------------------------------------


class Mode_Optimize (Mode_Abstract):
    """
    Application mode for optimizing airfoils.
    """

    mode_id = Mode_Id.OPTIMIZE                       # the id of the mode


    def _save_input_file (self, ask = False, toast=True): 
        """ save xo2 input options - optionally ask user"""

        case: Case_Optimize = self._app_model.case

        # check if changes were made in current case 

        if case and case.input_file.isChanged:
            if ask: 
                text = f"Save changes made for <b>{case.name}</b>?"
                button = MessageBox.save (self.stacked_panel, "Save Case", text,
                                          buttons = QMessageBox.StandardButton.Save | 
                                                    QMessageBox.StandardButton.Discard)
                if button == QMessageBox.StandardButton.Discard:
                    return 
                
            saved = case.input_file.save_nml()

            if toast and saved:
                self._toast_message (f"Options saved to Input file", toast_style=style.GOOD)


    def on_enter(self, pathFileName: str):
        """ Actions to perform when entering the mode. """

        # switch app_model to this mode with new Optimize Case - will get/create first design
        self._app_model.set_mode_and_case (self.mode_id, Case_Optimize (pathFileName))

        # don't show airfoil design initially
        self._app_model.set_show_airfoil_design(False)

        super().on_enter()


    def on_leave(self):
        """ Actions to perform when exiting the mode """

        super().on_leave()

        # set next airfoil to final or seed
        if self._app_model.case:
            if self._app_model.case.airfoil_final:
                next_airfoil = self._app_model.case.airfoil_final       # final airfoil created in finish
            else:
                next_airfoil = self._app_model.case.airfoil_seed
            next_airfoil.set_usedAs (usedAs.NORMAL)                     # normal AE color 

            self._app_model.case.close()                                # shut down case
            self._app_model.set_airfoil (next_airfoil, silent=True)     # we'll continue with set airfoil to final or seed
    
        self._app_model.set_case (None)
    

    def prepare_check_enter(self, on_arg=None) -> str:
        """ Check / prepare if the mode can be entered. Get/Create input file for xo2 """

        if not Xoptfoil2.ready : return False

        # an input file is already set - check existence

        if on_arg and Input_File.is_xo2_input(on_arg): 
                return on_arg
        elif on_arg:
            logger.error (f"Cannot enter Optimize mode - provided input file is not xo2 input: {on_arg}")
            return None
            
        # no xo2 file as argument - ask user to select existing or create new one

        diag = Xo2_Select_Dialog (self.stacked_panel, self._airfoil, parentPos=(0.4,-0.5), dialogPos=(0,1))
        rc = diag.exec()

        if rc == QDialog.DialogCode.Accepted:

            if diag.input_fileName:                                     
                # existing xo2 file selected (or new version)
                return os.path.join(diag.workingDir, diag.input_fileName)
            else: 
                # create new xo2 file based on current airfoil
                seed_airfoil = self._airfoil
                workingDir   = seed_airfoil.pathName_abs

                diag = Xo2_New_Dialog (self.stacked_panel, workingDir, seed_airfoil, parentPos=(0.5,0.0), dialogPos=(0,1.1))
                rc = diag.exec()

                if rc == QDialog.DialogCode.Accepted:
                    return os.path.join(diag.workingDir, diag.input_fileName)
        return None                             


    @property
    def panel (self) -> Data_Panel:
        """ lower UI main panel"""

        if self._panel is None: 

            l = QHBoxLayout()  

            p = Panel_Xo2_File (self, self._app_model, width=250, lazy=True)
            p.sig_toggle_panel_size.connect     (self.toggle_minimized)
            p.sig_open_next.connect             (self.open_next)
            p.sig_new_version.connect           (self.new_version)
            p.sig_finish.connect                (self.finish)
            l.addWidget (p)
            # p.sig_cancel.connect                (self.cancel)

            l.addWidget (Panel_Xo2_Case                    (self, self._app_model, lazy=True))
            l.addWidget (Panel_Xo2_Operating_Conditions    (self, self._app_model, lazy=True))
            l.addWidget (Panel_Xo2_OpPoint_Defs            (self, self._app_model, lazy=True))
            l.addWidget (Panel_Xo2_Geometry_Targets        (self, self._app_model, lazy=True))
            l.addWidget (Panel_Xo2_Curvature               (self, self._app_model, lazy=True))
            p = Panel_Xo2_Advanced              (self, self._app_model, lazy=True)
            p.sig_edit_input_file.connect       (self.edit_input_file)
            l.addWidget (p)

            self._panel = Data_Panel (self, self._app_model, layout = l)

            self._app_model.sig_xo2_input_changed.connect (self._panel.refresh)

        return self._panel


    @property
    def panel_small (self) -> Data_Panel:
        """ lower UI main panel """

        if self._panel_small is None: 

            l = QHBoxLayout()        

            p = Panel_Xo2_File_Small (self, self._app_model, width=250, lazy=True, has_head=False)
            p.sig_toggle_panel_size.connect     (self.toggle_minimized)
            p.sig_finish.connect                (self.finish)
            l.addWidget (p)

            l.addWidget (Panel_Xo2_Case_Small               (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Xo2_Operating_Small          (self, self._app_model, lazy=True, has_head=False))
            l.addWidget (Panel_Xo2_Geometry_Targets_Small   (self, self._app_model, lazy=True, has_head=False))

            self._panel_small = Data_Panel (self, self._app_model, layout = l)

            self._app_model.sig_xo2_input_changed.connect (self._panel_small.refresh)

        return self._panel_small


    # ---- User actions ----


    def run_xo2 (self): 
        """ run optimizer"""

        self._app_model.run_xo2 ()


    def edit_input_file (self):
        """ slot user action - edit xo2 input file """

        self._save_input_file (ask=False, toast=True)

        case : Case_Optimize = self._app_model.case
        diag = Xo2_Input_File_Dialog (self.stacked_panel, case.input_file, parentPos=(0.8,0,9), dialogPos=(1,1))
        diag.exec () 

        if diag.result() == QDialog.DialogCode.Accepted:
            msg = "Input file successfully checked and saved"
            self._toast_message (msg, toast_style=style.GOOD)
            self._app_model.notify_xo2_input_changed()


    def open_next (self, pathFileName: str):
        """ slot user action - open next xo2 input file """

        self._save_input_file (ask=True)

        # set next file to open
        self.switch_mode (Mode_Id.OPTIMIZE, pathFileName)        


    def new_version (self):
        """ slot user action - create new version of xo2 input file """

        self._save_input_file (ask=True)

        case : Case_Optimize = self._app_model.case

        workingDir   = case.input_file.workingDir
        cur_fileName = case.input_file.fileName
        new_fileName = Input_File.new_fileName_version (cur_fileName, workingDir)

        if new_fileName:

            copyfile (os.path.join (workingDir,cur_fileName), os.path.join (workingDir,new_fileName))
            self.switch_mode (Mode_Id.OPTIMIZE, os.path.join (workingDir,new_fileName))

            self._toast_message (f"New version {new_fileName} created", toast_style=style.GOOD) 
        else: 
            MessageBox.error   (self.stacked_panel,'Create new version', f"New Version of {cur_fileName} could not be created.",
                                min_width=350)


    def finish (self):
        """ slot user action - finish optimize airfoil - switch back to view mode """ 

        # be sure input file data is written to file 
        self._save_input_file (ask=True)

        # rest will be done in on_leave
        super().finish()




# ------------------------------------------------------------------------------


class Modes_Manager (QObject):
    """
    Manages the different application modes.

    The Modes Manager provides a stacked data panel which presents the lower part of the UI
    according to the current mode.
    """

    sig_close_requested = pyqtSignal()                      # signal to request app close


    def __init__(self, app_model: App_Model):
        super().__init__()

        self._modes_dict  = {}
        self._app_model   = app_model

        self._modes_panel : QStackedWidget = None

        self._height            = 250                       # default height of modes panel
        self._height_minimized  = 150                       # default height of modes panel when minimized

        s = Settings()
        self._is_minimized = s.get('lower_panel_minimized', False)


    def _switch_mode_panel (self, mode: Mode_Abstract):
        """ switch stacked widget to panel of mode """

        if not (mode.mode_id in self._modes_dict):
            logger.error (f"Mode {mode} not registered in Mode_Manager.")

        # set small oder normal  
        mode.set_current_panel (self._is_minimized, refresh=True)

        # switch stacked widget to new mode panel
        self._modes_panel.setCurrentWidget (mode.stacked_panel)

        # setting of the actual width of the modes panel after switching needs to be done
        # after all current events are processed so that the size hint of the new panel is valid
        QTimer.singleShot (100, self._set_min_width)        # set min width after current events processed


    def _set_min_width (self):
        """ set minimum width of modes panel according to current mode panel """

        # because QStackedWidget takes the width of the widest widget of all its children,
        # we need to set the minimum width of the stacked widget to the minimum width of the current mode panel

        if self.current_mode is not None:
            self._modes_panel.setMinimumWidth (0)
            self._modes_panel.adjustSize()
            min_width = self.current_mode.current_panel.calc_min_width()
            self._modes_panel.setMinimumWidth (min_width)


    @property
    def current_mode (self) -> Mode_Abstract:
        """ Get the current active mode. """

        mode_id = self._app_model.mode_id
        if mode_id is None:
            return None
        elif mode_id in self._modes_dict:
            return self._modes_dict[mode_id]
        else:
            logger.warning(f"Mode {mode_id} not registered in Mode_Manager.")
            return None     
       

    def add_mode(self, mode: Mode_Abstract):
        """ add a mode to the manager """

        mode_id = mode.mode_id

        if not mode_id in self._modes_dict:

            self._modes_dict [mode_id] = mode                        # register mode

            # connect to signals of Mode
            mode.sig_exit_requested.connect         (self.exit)
            mode.sig_leave_requested.connect        (self.leave_mode)
            mode.sig_switch_mode_requested.connect  (self.switch_mode)
            mode.sig_toggle_minimized.connect       (self.toggle_minimized)


    def set_mode (self, mode_id: Mode_Id, on_arg=None):
        """ set initial mode """

        if not mode_id in self._modes_dict:
            logger.error(f"Mode {mode_id} not registered in Mode_Manager.")
            return

        if self._app_model.mode_id is not None:
            logger.error("Initial mode already set in App_Model.")
            return

        mode : Mode_Abstract = self._modes_dict [mode_id]

        # prepare new mode and argument to work on
        arg =  mode.prepare_check_enter (on_arg)

        mode.on_enter(arg)                                              # set mode
        mode.set_current_panel (self._is_minimized)                     # select the right panels small or not



    def stacked_modes_panel (self) -> QStackedWidget:
        """ build all modes panels and return them as stacked widget """

        if self._modes_panel is not None:
            return self._modes_panel
        
        self._modes_panel = QStackedWidget()

        # collect all modes and their panels
        mode : Mode_Abstract
        for mode_id, mode in self._modes_dict.items():
            self._modes_panel.addWidget (mode.stacked_panel)                 # add mode's data panels to stacked widget

        # switch stacked widget to current mode panel
        if self.current_mode is not None:
            self._modes_panel.setCurrentWidget (self.current_mode.stacked_panel)

        return self._modes_panel


    def switch_mode (self, new_mode_id: Mode_Id, on_arg=None):
        """ switch to given mode """

        if not new_mode_id in self._modes_dict:
            logger.error(f"Mode {new_mode_id} not registered in Mode_Manager.")
            return

        if self._app_model.mode_id is None:
            logger.error("Cannot switch modes: No initial mode set")
            return

        # leave current mode
        self.current_mode.on_leave()

        # prepare new mode and argument to work on
        new_mode   : Mode_Abstract = self._modes_dict [new_mode_id]
        new_arg =  new_mode.prepare_check_enter (on_arg)
        if new_arg is None:  return                                         # cannot enter mode         
        
        # enter new mode, switch data panels
        new_mode.on_enter(new_arg)                                          # prepare enter new mode
        self._switch_mode_panel (new_mode)                                  # switch stacked widget - make visible



    def leave_mode (self):
        """ leave current mode and return to view mode """

        self.switch_mode (Mode_Id.VIEW)


    def exit(self):
        """ exit mode and close app if in view mode """

        if self.current_mode is not None:
            self.current_mode.on_leave()

        s = Settings()
        s.set('lower_panel_minimized', self._is_minimized)
        s.save()

        self.sig_close_requested.emit()             # close app if view mode finished


    def set_height (self, height: int, minimized: int|None = None):
        """ set height of modes panel """

        self._height = height
        self._height_minimized = minimized if minimized is not None else self._height_minimized

        self._set_minimized (self._is_minimized)                     # apply height change


    def _set_minimized (self, minimized: bool):
        """ set minimized state of modes panel """

        self._is_minimized = minimized

        if self.current_mode is not None:
            self.current_mode.set_current_panel (minimized)         # set panel small or normal

        # set to predefined height
        height = self._height_minimized if minimized else self._height
        self._modes_panel.setFixedHeight (height)    


    def toggle_minimized (self):
        """ toggle minimized state of modes panel """

        if self.current_mode is not None:
            self._set_minimized (not self._is_minimized)

            # adjust new min with of data panel
            self._set_min_width()        


