#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""

    Airfoil and operations on it 

"""
import os
import ast
import logging
from datetime               import datetime, timedelta
from copy                   import copy
from typing                 import Type, override
from enum                   import StrEnum
from pathlib                import Path

import numpy as np

from ..base.common_utils      import fromDict, toDict, clip 
from ..base.spline            import HicksHenne

from .airfoil_geometry      import (Geometry_Splined, Geometry, Geometry_Bezier, Geometry_HicksHenne,
                                    Line, Side_Airfoil_Bezier, GeometryException)

from .xo2_driver            import Worker

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)



#-------------------------------------------------------------------------------
# enums   
#-------------------------------------------------------------------------------

class usedAs (StrEnum):
    """ airfoil types for some usage semantics in application """
    NORMAL      = ""
    SEED        = "Seed"
    SEED_DESIGN = "Seed of design"
    REF         = "Reference" 
    DESIGN      = "Design"
    TARGET      = "Target"
    SECOND      = "Airfoil 2"
    FINAL       = "Final"


# geometry specification 

GEO_BASIC  = Geometry
GEO_SPLINE = Geometry_Splined




#--------------------------------------------------------------------------

class Airfoil:
    """ 

    Airfoil object to handle a airfoil direct related things  

    """
    isBlendAirfoil      = False
    isEdited            = False
    isExample           = False                      # vs. Example_Airfoil 
    isBezierBased       = False
    isHicksHenneBased   = False
    isDatBased          = not isBezierBased and not isHicksHenneBased

    Extension           = '.dat'

    def __init__(self, x= None, y = None, name = None,
                 geometry : Type[Geometry]  = None, 
                 pathFileName = None,  workingDir= None):
        """
        Main constructor for new Airfoil

        Args:
            pathFileName: optional - string of existinng airfoil path and name 
            name: optional         - name of airfoil - no checks performed 
            x,y: optional          - the coordinates of airfoil 
            geometry: optional     - the geometry staretegy either GEO_BASIC, GEO_SPLNE...
            workingDir: optional   - base directoty where pathFileName is relative 
        """

        self._pathFileName = None
        if workingDir is not None:
            self._workingDir = os.path.normpath (workingDir)
        else: 
            self._workingDir = ''
        self._name          = name if name is not None else ''

        if x is not None: 
            x = x if isinstance(x,np.ndarray) else np.asarray (x)
        self._x     = x
        if y is not None: 
            y = y if isinstance(y,np.ndarray) else np.asarray (y)
        self._y     = y  

        self._isModified     = False
        self._isEdited       = False 
        self._isBlendAirfoil = False                        # is self blended from two other airfoils 

        if geometry is None: 
            self._geometry_class  = GEO_SPLINE              # geometry startegy 
        else:
            self._geometry_class  = geometry                # geometry startegy 
        self._geo            = None                         # selfs instance of geometry

        self._polarSet       = None                         # polarSet which is defined from outside 
        self._scale_factor   = None                         # scale factor of airfoil e.g. for polars

        self._usedAs         = usedAs.NORMAL                # usage type of airfoil used by app <- AIRFOIL_TYPES
        self._propertyDict   = {}                           # multi purpose extra properties for an Airfoil
        self._file_datetime  = None                         # modification datetime of file 

        self._flap_setter    = None                         # proxy controller to flap self using Worker

        # pathFileName must exist if no coordinates were given 

        if (pathFileName is not None) and  (x is None or y is None): 
            pathFileName = os.path.normpath(pathFileName)   # ensure correct format
            if os.path.isabs (pathFileName):
                checkPath = pathFileName
            else:
                checkPath = os.path.join(self.workingDir, pathFileName)
            if not os.path.isfile(checkPath):
                self._name = "-- Error --"
                raise ValueError (f"Airfoil '{checkPath}' does not exist.")
            else:
                self._pathFileName = pathFileName
                self._name = self.fileName_stem             # load will get the real name

        elif (pathFileName is not None) : 
                self._pathFileName = pathFileName

        elif (not name):
            self._name = "-- ? --"

        self._name_org      = self._name                    # original name for modification label
        self._fileName_org  = None                          # will hold original fileName 


    @classmethod
    def onDict(cls, dataDict, workingDir = None, geometry : Type[Geometry]  = None):
        """
        Alternate constructor for new Airfoil based on dictionary 

        Args:
            :dataDict: dictionary with "name" and "file" keys
            :workingDir: home of dictionary (paramter file) 
        """
        pathFileName  = fromDict(dataDict, "file", None)
        name          = fromDict(dataDict, "name", None)
        return cls(pathFileName = pathFileName, name = name, 
                   geometry = geometry, workingDir = workingDir)
        

    @classmethod
    def onFileType(cls, pathFileName, workingDir = None, geometry : Type[Geometry]  = None):
        """
        Alternate constructor for new Airfoil based on its file type retrieved from pathFileName

            '.dat'      - returns Airfoil 
            '.bez'      - returns Airfoil_Bezier 
            '.hicks'    - returns Airfoil_Hicks_Henne 

        Args:
            pathFileName: string of existinng airfoil path and name
            workingDir: optional working dir (if path is relative)
            geometry : geometry tyoe - only for .dat files 
        """

        ext : str = os.path.splitext(pathFileName)[1]
        ext = ext.lower() if ext else None

        if ext == Airfoil.Extension: 
            return Airfoil (pathFileName=pathFileName, workingDir=workingDir, geometry=geometry)

        elif ext == Airfoil_Bezier.Extension: 
            return Airfoil_Bezier (pathFileName=pathFileName, workingDir=workingDir)

        elif ext == Airfoil_Hicks_Henne.Extension: 
            return Airfoil_Hicks_Henne (pathFileName=pathFileName, workingDir=workingDir)
        else:
            raise ValueError (f"Unknown file extension '{ext}' for new airfoil")



    def _save (self, airfoilDict):
        """ stores the variables into the dataDict - returns the filled dict"""
        
        if self.isBlendAirfoil:
            toDict (airfoilDict, "name", self.name) 
        else:
            toDict (airfoilDict, "file", self.pathFileName) 
        return airfoilDict
 

    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        info = f"'{self.fileName}'" if self.fileName else self.name
        return f"<{type(self).__name__} {info}>"


    def _handle_geo_changed (self, geo : Geometry = None):
        """ 
        callback from geometry when it was changed (by user) 
        
        Args:
            geo: optional alternative geometry which will be taken 
        """

        # load new coordinates from modified geometry 
        if geo is None: 
            self._x = self.geo.x
            self._y = self.geo.y
            modifications = self.geo.modification_dict
        else: 
            self._x = geo.x
            self._y = geo.y
            modifications = geo.modification_dict

        # set new name
        if not self._name_org: 
            self._name_org = self.name

        self.set_name (f"{self._name_org}_mods:{str(modifications)}")

        # if not DESIGN set new filename - take original filename if possible (without ...mod...)
        if not self.usedAsDesign:
            if self._fileName_org is None: 
                self._fileName_org = self.fileName

            fileName_stem = os.path.splitext(self._fileName_org)[0]
            fileName_ext  = os.path.splitext(self._fileName_org)[1]
            mod_string    = "_mod" if modifications else ""
            self.set_fileName (fileName_stem + mod_string + fileName_ext)

        self.set_isModified (True)
        logger.debug (f"{self} - geometry changed: {modifications} ")


    # ----------  Properties ---------------

    @property
    def x (self): 
        """ x coordinates of self """
        return self._x

    @property
    def y (self): 
        """ y coordinates of self """
        return self._y


    @property
    def geo (self) -> Geometry:
        """ the geometry of self"""
        if self._geo is None: 
            if self.isLoaded:
                self._geo = self._geometry_class (self.x, self.y, onChange = self._handle_geo_changed)
            else:
                raise GeometryException (f"Airfoil '{self.name}' not loaded - cannot create geometry.")
        return self._geo
    

    def set_xy (self, x, y):
        """ set new coordinates """

        if not x is None: 
            x = x if isinstance(x,np.ndarray) else np.asarray (x)
            x = np.round(x,7)
        if not y is None: 
            y = y if isinstance(y,np.ndarray) else np.asarray (y)
            y = np.round(y,7)

        self._x     = x
        self._y     = y  
        self._geo    = None

        self.set_isModified (True)


    @property
    def workingDir (self) -> str: 
        """ working directory which is added to pathFileName"""
        return self._workingDir 
    
    def set_workingDir (self, aDir : str):
        self._workingDir = aDir


    @property
    def name (self) -> str: 
        """ name of airfoil"""

        return self._name 

    @property
    def name_to_show (self) -> str: 
        """ public name of airfoil - use fileName.stem - limited to 47 chars"""

        name = self.fileName_stem
        return name if len(name) <= 47 else f"{name[:47]}..."


    def set_name (self, newName, reset_original=False):
        """  Set name of the airfoil. 'reset_original' will also overwrite original name  
        Note:  This will not rename an existing airfoil (file)...
        """
        self._name = newName

        if not self._name_org or reset_original: 
            self._name_org = self.name

        self.set_isModified (True)

    @property
    def name_short (self):
        """ name of airfoil shortend at the beginning to 23 chars"""
        if len(self.name) <= 23:    return self.name
        else:                       return "..." + self.name[-20:]


    def info_short_as_html (self, thickness_color = None, camber_color = None) -> str:
        """ comprehensive info about self as formatted html string"""

        info = "<p style='white-space:pre'>"                                # no word wrap 

        thickness_color = thickness_color if thickness_color else ''
        camber_color    = camber_color    if camber_color    else ''

        if self.isLoaded and self.geo and self.geo.max_thick:          # could be strak airfoil
            info += f"<table>" + \
                    f"<tr>" + \
                        f"<td>Thickness  </td>" + \
                        f"<td style='color: {thickness_color}'>{self.geo.max_thick:.2%}  </td>" + \
                        f"<td>at  </td>" + \
                        f"<td>{self.geo.max_thick_x:.2%}  </td>" + \
                    f"</tr>" + \
                    f"<tr>" + \
                        f"<td>Camber  </td>" + \
                        f"<td style='color: {camber_color}'>{self.geo.max_camb:.2%}  </td>" + \
                        f"<td>at  </td>" + \
                        f"<td>{self.geo.max_camb_x:.2%}  </td>" + \
                    f"</tr>" + \
                    f"<tr>" + \
                        f"<td>Curvature LE  </td>" + \
                        f"<td>{self.geo.curvature.max_around_le:.0f}  </td>" + \
                        f"<td>TE    </td>" + \
                        f"<td>{self.geo.curvature.max_te:.0f}  </td>" + \
                    f"</tr>" + \
                f"</table>"
        else:
            info += f"No geometry info available"

        info += "</p>"
        return info 


    @property
    def info_as_html (self) -> str:
        """ comprlonger  info about self as formatted html string"""

        info = "<p style='white-space:pre'>"                     # no word wrap 

        if self.isLoaded:
            used_as = f"{self.usedAs}: " if self.usedAs != usedAs.NORMAL else ""
            info += f"{used_as}{self.fileName}" 
            info += f"<br><br>in {self.pathName_abs}" 

        info += self.info_short_as_html()

        return info 


    @property
    def polarSet (self):
        """ Property which is set from outside - Airfoil doesn't know about it... """ 
        return self._polarSet 
    def set_polarSet (self, aPolarSet):
        self._polarSet = aPolarSet

    @property
    def scale_factor (self):
        """ scale factor of airfoil e.g. for polars - default is 1.0 """
        return self._scale_factor if self._scale_factor is not None else 1.0
    
    def set_scale_factor (self, aScale):
        if aScale == 1.0 or aScale is None:
            self._scale_factor = None
        else:
            self._scale_factor = clip (aScale, 0.01, 100.0)
 
    @property
    def isScaled (self) -> bool:
        """ True if airfoil is scaled (scale != 1.0)"""
        return self._scale_factor is not None 


    @property
    def isEdited (self) -> bool: 
        """ True if airfoil is being edited, modified, ..."""
        return self._isEdited
    def set_isEdited (self, aBool): 
        self._isEdited = bool(aBool)  


    @property
    def isModified (self) -> bool: 
        """ True if airfoil is being modified, ..."""
        return self._isModified
    def set_isModified (self, aBool): 
        self._isModified = aBool 

    @property
    def isExisting (self) -> bool:
        return not self.pathFileName is None


    @property
    def isLoaded (self) -> bool:
        """ true if airfoil has coordinates loaded"""
        if self._x is None or self._y is None:
            return False
        if isinstance(self._x, np.ndarray) and isinstance(self._y, np.ndarray):
            if self._x.size < 2 or self._y.size < 2:
                return False
            return True
        return bool(self._x)
    
    @property
    def isNormalized (self) -> bool:
        """ is LE at 0,0 and TE at 1,.. ?"""
        return self.geo.isNormalized
    
    @property
    def isBlendAirfoil (self) -> bool:
        """ is self blended out of two other airfoils"""
        return self._isBlendAirfoil
    def set_isBlendAirfoil (self, aBool): 
        self._isBlendAirfoil = aBool
    
    @property
    def nPanels (self) -> int: 
        """ number of panels """
        return self.geo.nPanels
      
    @property
    def nPoints (self) -> int: 
        """ number of coordinate points"""
        return self.geo.nPoints 

        
    @property
    def isSymmetrical(self) -> bool:
        """ true if max camber is 0.0 - so it's a symmetric airfoil"""
        return self.geo.isSymmetrical


    @property
    def isFlapped (self) -> bool:
        """ true if self is probably flapped"""
        return self.geo.isFlapped


    @property
    def isReflexed (self) -> bool:
        """ True if there is just one reversal on upper side"""
        return self.geo.curvature.isReflexed


    @property
    def isRearLoaded (self) -> bool:
        """ True if there is just one reversal on lower side"""
        return self.geo.curvature.isRearLoaded


    @property
    def isUpToDate (self) -> bool:
        """ true if the loaded airfoil is up to date with its file - none if no answer"""

        if os.path.isfile (self.pathFileName_abs) and self._file_datetime is not None:
            ts = os.path.getmtime(self.pathFileName_abs)                       # file modification timestamp of a file
            file_datetime = datetime.fromtimestamp(ts)                  # convert timestamp into DateTime object

            # add safety seconds (async stuff?) 
            if (self._file_datetime >= (file_datetime - timedelta(seconds=1))):
                return True
            else: 
                return False
        return None  


    @property
    def usedAs (self):
        """ usage type (enum usedAs) of self like DESIGN"""
        return self._usedAs
    def set_usedAs (self, aType): 
        if aType in usedAs:
            self._usedAs = aType

    @property
    def usedAsDesign (self): 
        """ short for self used as DESIGN """ 
        return self._usedAs == usedAs.DESIGN

    def useAsDesign (self, aBool=True): 
        """ set usedAs property to DESIGN"""
        if aBool: 
            self.set_usedAs (usedAs.DESIGN)
        else: 
            self.set_usedAs (usedAs.NORMAL)
            return

        # Design: get modifications dict from name

        if aBool: 
            try: 
                name_org, mods = self._name.split ("_mods:", 1)
                if mods and name_org:
                    self.geo._modification_dict = ast.literal_eval (mods)
                    self._name_org = name_org 
            except ValueError:
                self._name_org = self.name
                pass

    def usedAs_i_Ref (self, airfoils : list['Airfoil']) -> tuple[int,int]:
        """ if self is usedAs REF returns index i and no of all REF airfoils"""

        if self.usedAs == usedAs.REF:
            iRef, nRef = 0, 0                                       # get the how many reference 
            for a in airfoils:
                if a == self: iRef = nRef 
                if a.usedAs == usedAs.REF: nRef += 1
            return iRef, nRef
        else:
            None, None     


    def get_property (self, name, default):
        """ returns free style property of self"""
        return fromDict (self._propertyDict, name, default )

    def set_property (self, name, aVal):
        """ set free style property of self"""
        return toDict (self._propertyDict, name, aVal )

    #-----------------------------------------------------------

    @property
    def pathFileName (self) -> str:
        """ path and filename of airfoil like './examples/JX-GT-15.dat' """
        return self._pathFileName


    def set_pathFileName (self, pathfileName : str, noCheck=False):
        """
        Set fullpaths of airfoils location and file  
        ! This will not move or copy the airfoil physically - use copyAs instead
        """
        if noCheck:
            self._pathFileName = pathfileName
        elif os.path.isfile(pathfileName):
            self._pathFileName = pathfileName
        elif self.workingDir and os.path.isfile(self.pathFileName_abs):
            self._pathFileName = pathfileName
        else:
            raise ValueError (f"Airfoil {pathfileName} does not exist. Couldn\'t be set")

    @property
    def pathFileName_abs (self) -> str:
        """ path including working dir and filename of airfoil like '/root/examples/JX-GT-15.dat' """

        if self.workingDir:
            pathFileName_abs =  os.path.join(self.workingDir, self.pathFileName)
        else: 
            pathFileName_abs =  self._pathFileName
        
        if not os.path.isabs (pathFileName_abs):
            pathFileName_abs = os.path.abspath(pathFileName_abs)       # will insert cwd 
        return pathFileName_abs


    def set_pathName (self, aDir : str, noCheck=False):
        """
        Set fullpaths of airfoils directory  
            ! This will not move or copy the airfoil physically
        """
        aDir_abs = os.path.join (self.workingDir, aDir)
        if noCheck or (os.path.isdir(aDir_abs)) or aDir == '':
            self._pathFileName = os.path.join (aDir, self.fileName)
        else:
            raise ValueError ("Directory \'%s\' does not exist. Couldn\'t be set" % aDir)

    @property
    def fileName (self):
        """ filename of airfoil like 'JX-GT-15.dat' """
        return os.path.basename(self.pathFileName) if self.pathFileName else ''
    
    @property
    def fileName_stem (self):
        """ stem of fileName like 'JX-GT-15' """
        return Path(self.fileName).stem if self.fileName else ''

    @property
    def fileName_ext (self):
        """ extension of fileName like '.dat'"""
        return os.path.splitext(self.fileName)[1] if self.fileName else ''


    def set_fileName (self, aFileName : str):
        """ set new fileName """
        if not aFileName: return 
        self._pathFileName = os.path.join (self.pathName, aFileName)

    def set_name_from_fileName (self):
        """ set current fileName as name of airfoil """
        self.set_name (self.fileName_stem)

    def set_fileName_from_name (self):
        """ set current fileName as name of airfoil """
        self.set_fileName (self.name + self.fileName_ext) 

    def set_fileName_add_suffix (self, aSuffix : str):
        """ extend current fileName_stem with suffix """
        self.set_fileName (self.fileName_stem + aSuffix + self.fileName_ext)


    @property
    def pathName (self):
        """
        directory pathname of airfoil like '..\\myAirfoils\\'
        """
        if not self.pathFileName is None: 
            return os.path.dirname(self.pathFileName) 
        else:
            return ''

    @property
    def pathName_abs (self):
        """
        absolute directory pathname of airfoil like '\\root\\myAirfoils\\'
        """
        if not self.pathFileName_abs is None: 
            return os.path.dirname(self.pathFileName_abs)
        else:
            # fallback - current python working dir
            logger.warning (f"{self} has not pathFileName")
            return os.path.dirname(os.getcwd())


    def load (self, fromPath = None):
        """
        Loads airfoil coordinates from file. 
        pathFileName must be set before or fromPath must be defined.
        Load doesn't change self pathFileName
        """    

        if fromPath:
            sourcePathFile = fromPath
        else:
            sourcePathFile = self.pathFileName_abs

        if os.path.isfile (sourcePathFile):

            try:
                # read airfoil file into x,y 

                f = open(sourcePathFile, 'r')
                file_lines = f.readlines()
                f.close()
                self._name, self._x, self._y = self._loadLines(file_lines)

                self._geo = None                                            # reset geometry 

                # get modfication datetime of file 

                ts = os.path.getmtime(sourcePathFile)                       # file modification timestamp of a file
                self._file_datetime = datetime.fromtimestamp(ts)            # convert timestamp into DateTime object

            except ValueError as e:
                logger.error (f"{self} {e}")
                raise

            # first geometry check
            
            if self.isLoaded:
                try:
                    self.geo.thickness
                except GeometryException as e:
                    logger.error (f"{self} {e}")
                    raise

            logger.debug (f"{self} loaded from {sourcePathFile} with {len(self._x)} points.")


    def _loadLines (self, file_lines : list[str]):
        """ extract name, x, y from file_lines"""
        # returns the name and x,y (np array) of the airfoil file 

        name = ''
        x = []
        y = []
        xvalPrev = -9999.9
        yvalPrev = -9999.9

        for i, line in enumerate(file_lines):
            if (i > 0): 
                splitline = line.strip().split()               # will remove all extra spaces
                if len(splitline) == 1:                        # couldn't split line - try tab as separator
                    splitline = line.strip().split("\t",1)
                if len(splitline) >= 2:                     
                    xval = float(splitline[0].strip())
                    yval = float(splitline[1].strip())
                    if xval == xvalPrev and yval == yvalPrev:   # avoid duplicate, dirty coordinates
                        logger.warning ("Airfoil '%s' has duplicate coordinates - skipped." % self._name)
                    else: 
                        x.append (xval)
                        y.append (yval) 
                    xvalPrev = xval 
                    yvalPrev = yval 
            else: 
                name = line.strip()
        
        if not name or not x or not y:
            raise ValueError ("Invalid .dat file")
        
        x, y = self._ensure_counter_clockwise (np.asarray (x), np.asarray (y))

        # test orientation 
        # x2, y2 = self._ensure_counter_clockwise (np.flip(np.copy (x)), np.flip(np.copy (y)))

        return name, x, y


    def _ensure_counter_clockwise (self, x : np.ndarray, y : np.ndarray):
        """ ensure x,y coordinates are counter clockwise ordered"""

        # sanity 

        if len(x) != len(y) or len(x) == 0:
            raise ValueError ("Invalid coordinates")

        # using shoelace formula to get signed area 
        #   A = 0.5 * sum (xi * yi+1 - xi+1 * yi )

        x_plus = np.append (x[1:], x[0])                            # shift index plus 1
        y_plus = np.append (y[1:], y[0])

        a = np.sum (x*y_plus) - np.sum(x_plus*y)

        if a < 0:                                                   # clockwise is negative 
            x, y = np.flip(x), np.flip(y)  
            logger.warning (f"{self} coordinates flipped to become counter clockwise")

        return x, y


    def save (self, onlyShapeFile=False):
        """
        Basic save of self to its pathFileName_abs
            for Hicks-Henne and Bezier 'onlyShapeFile' will write no .dat file 
        """
        if self.isLoaded: 
            self._write_dat_to_file ()
            self.set_isModified (False)

            logger.debug (f"{self} save to {self.fileName}")


    def saveAs (self, dir : str = None, destName : str = None, isWorkingDir = False):
        """
        save self to dir and destName and set new values to self
        if both dir and name are not set, it's just a save to current directory

        If workingDir is set, the saved airfoil will be relative to workingDir

        Returns: 
            newPathFileName from dir and destName 
        """     
        if destName: 
            self.set_name (destName)
            fileName = destName +  Airfoil.Extension
        else: 
            fileName = self.fileName  

        # create dir if not exist - build new airfoil filename
        if dir: 
            if not os.path.isdir (dir):
                os.mkdir(dir)
            if isWorkingDir:
                self.set_pathFileName (self.fileName, noCheck=True)
                self.set_workingDir   (dir)
            else:
                self.set_pathFileName (os.path.join (dir, fileName), noCheck=True)

        self.save()
        self.set_isModified (False)
        return self.pathFileName


    def asCopy (self, pathFileName = None, 
                name=None, nameExt=None,
                geometry=None) -> 'Airfoil':
        """
        returns a copy of self 

        Args:
            pathFileName: optional - string of existing (relative) airfoil path and name 
            name: optional         - name of airfoil - no checks performed 
            nameExt: -optional     - will be appended to self.name (if name is not provided)
            geometry: optional     - the geometry staretegy either GEO_BASIC, GEO_SPLNE...
        """
        if pathFileName is None and name is None: 
            pathFileName = self.pathFileName

        if os.path.isabs (pathFileName):
            workingDir = None
        else: 
            workingDir = self.workingDir 

        if name is None:
            name = self.name + nameExt if nameExt else self.name

        geometry = geometry if geometry else self._geometry_class

        airfoil =  Airfoil (x = np.copy (self.x), y = np.copy (self.y), 
                            name = name, pathFileName = pathFileName, 
                            workingDir = workingDir,
                            geometry = geometry )
        return airfoil 


    def asCopy_design (self, pathFileName = None) -> 'Airfoil':
        """
        returns a copy of self - same as asCopy with additional properties
            of a DESIGN airfoil

        Args:
            pathFileName: optional - string new fileName
        """
        pathFileName = pathFileName if pathFileName else self.pathFileName 
        name         = self.name 
        geometry     = self._geometry_class

        airfoil = self.asCopy (pathFileName=pathFileName, name=name, geometry=geometry)

        airfoil.set_usedAs (self.usedAs)
        airfoil.set_isEdited (self.isEdited)
        airfoil.geo._modification_dict = copy (self.geo._modification_dict)
        airfoil._name_org = self._name_org
        
        return airfoil 


    def _write_dat_to_file (self):
        """ writes .dat file of to self.pathFileName"""

        # ensure extension .dat (in case of Bezier) 
        pathFileName_abs =  os.path.splitext(self.pathFileName_abs)[0] + Airfoil.Extension

        with open(pathFileName_abs, 'w+') as file:
            file.write("%s\n" % self.name)
            for i in range (len(self.x)):
                file.write("%.7f %.7f\n" %(self.x[i], self.y[i]))
            file.close()


    def normalize (self, 
                   just_basic=False, 
                   mod_string=None):
        """
        Shift, rotate, scale airfoil so LE is at 0,0 and TE is symmetric at 1,y
        Returns True/False if normalization was done 

        Args:
            just_basic: will only normalize coordinates - not based on spline 
            mod_string: alternate modification identifier for fileName and name 
        """
        normalize_done = self.geo.normalize(just_basic=just_basic)

        if normalize_done: 

            if mod_string:
                fileName_stem = os.path.splitext(self._fileName_org)[0]
                fileName_ext  = os.path.splitext(self._fileName_org)[1]
                self.set_fileName (fileName_stem + mod_string + fileName_ext)  
                self.set_name     (self._name_org + mod_string)

        return normalize_done  


    def do_blend (self, 
                  airfoil1 : 'Airfoil', airfoil2 : 'Airfoil', 
                  blendBy : float,
                  geometry_class = None ):
        """ 
        Blends self out of two airfoils to the left and right
            depending on the blendBy factor
        
        Args: 
            airfoil1, airfoil2: Airfoils to the left and right 
            blendBy: 0.0 equals to the left, 1.0 equals to the right airfoil  
            geometry_class: optional - geo strategy for blend - either GEO_BASIC or GEO_SPLINE
        """
    
        blendBy = clip (blendBy, 0.0, 1.0)

        # other geo strategy - change geometry_class of self 
        if not geometry_class is None and geometry_class != self._geometry_class:
            self._geometry_class = geometry_class
            self._geo = None                                            # reset geometry

        # allow self is dummy airfoil with no coordinates (normally exception)
        if self._geo is None:
            self._geo = self._geometry_class (self.x, self.y, onChange = self._handle_geo_changed)

        self.geo.blend (airfoil1.geo, airfoil2.geo, blendBy)

        self.set_isBlendAirfoil (True)


    @property
    def flap_setter (self) -> 'Flap_Setter':
        """ proxy controller to flap self using Worker"""

        if self._flap_setter is None and not self.isFlapped: 
            self._flap_setter = Flap_Setter (self)
        return self._flap_setter 


    def do_flap (self, flap_def = None):
        """ 
        flap self based on current 'flap_setter' data

        Args:
            flap_def: optional new flap definition to be applied
        """

        if flap_def is not None:                                 # set new flap definition
            self.flap_setter.set_flap_definition (flap_def)
        elif self._flap_setter is None: 
            return 

        # run worker - read flapped airfoil 
        self.flap_setter.set_flap ()

        if self.flap_setter.airfoil_flapped:

            # flapping was successful - update geometry - will update self
            x,y        = self.flap_setter.airfoil_flapped.x, self.flap_setter.airfoil_flapped.y
            flap_angle = self.flap_setter.flap_angle
            x_flap     = self.flap_setter.x_flap

            self.geo.set_flapped_data (x,y, flap_angle, x_flap)


#------------------------------------------------------

class Airfoil_Bezier(Airfoil):
    """ 

    Airfoil based on Bezier curves for upper and lower side 

    """

    isBezierBased       = True

    Extension           = ".bez"


    def __init__(self, name = None, pathFileName=None, workingDir= None,
                 cp_upper = None,
                 cp_lower = None):
        """
        Main constructor for new Bezier Airfoil

        Args:
            pathFileName: optional - string of existinng airfoil path and name 
            name: optional - name of airfoil - no checks performed 
        """
        super().__init__( name = name, pathFileName=None, workingDir=workingDir)

        self._pathFileName   = pathFileName         # after super() as checks would hit 
        self._geometry_class = Geometry_Bezier      # geometry startegy 
        self._isLoaded       = False                # bezier definition loaded? 

        if cp_upper is not None: 
            self.geo.upper.set_controlPoints (cp_upper)
        if cp_lower is not None: 
            self.geo.lower.set_controlPoints (cp_lower)

        # pathFileName must exist if no coordinates were given 

        if (pathFileName is not None) and  (cp_upper is None or cp_lower is None): 
            pathFileName = os.path.normpath(pathFileName)       # make all slashes to double back
            if os.path.isabs (pathFileName):
                checkPath = pathFileName
            else:
                checkPath = self.pathFileName_abs
            if not os.path.isfile(checkPath):
                raise ValueError (f"Airfoil '{checkPath}' does not exist.")


    @staticmethod
    def onAirfoil (anAirfoil : Airfoil):
        """
        Alternate constructor for new Airfoil based on another airfoil 

        The new Bezier airfoil will just have a rough estimation for the Bezier curves,
        which have to be optimized with 'match bezier'
        """

        # new name and filename
        name = anAirfoil.name + '_bezier'
 
        # get estimated controlpoints for upper and lower 
        cp_upper = Side_Airfoil_Bezier.estimated_controlPoints (anAirfoil.geo.upper, 5)
        cp_lower = Side_Airfoil_Bezier.estimated_controlPoints (anAirfoil.geo.lower, 5)

        airfoil_new =  Airfoil_Bezier (name=name, cp_upper=cp_upper, cp_lower=cp_lower)

        # new pathFileName
        fileName_stem = anAirfoil.fileName_stem
        # fileName_ext  = anAirfoil.fileName_ext
        pathFileName  = os.path.join (anAirfoil.pathName, fileName_stem + '_bezier' + Airfoil_Bezier.Extension)
        airfoil_new.set_pathFileName (pathFileName, noCheck=True)
        airfoil_new.set_workingDir   (anAirfoil.workingDir)

        airfoil_new.set_isLoaded (True)

        return airfoil_new 


    @property
    def pathFileName_shape (self) -> str: 
        """ abs pathfileName of the Bezier definition file """
        if self.pathFileName_abs:  
            return os.path.splitext(self.pathFileName_abs)[0] + Airfoil_Bezier.Extension
        else: 
            return None 

    @property
    def isLoaded (self): 
        # overloaded
        return self._isLoaded
    def set_isLoaded (self, aBool: bool):
        self._isLoaded = aBool

    @property
    def geo (self) -> Geometry_Bezier:
        """ the geometry strategy of self"""
        if self._geo is None: 
            self._geo = self._geometry_class (onChange = self._handle_geo_changed)
        return self._geo

    @override
    @property
    def flap_setter (self) -> 'Flap_Setter':
        """ proxy controller to flap self using Worker"""
        # do not flap Bezier
        return None 


    def set_xy (self, x, y):
        """ Bezier - do nothing """

        # overloaded - Bezier curve in Geometry is master of data 
        pass


    def set_newSide_for (self, curveType, px,py): 
        """creates either a new upper or lower side in self"""
        self.geo.set_newSide_for (curveType, px,py)
        self.set_isModified (True)

    @property
    def x (self):
        # overloaded  - take from bezier 
        return self.geo.x

    @property
    def y (self):
        # overloaded  - take from bezier 
        return self.geo.y

    # -----------------

    def reset (self): 
        """ make child curves like thickness or camber invalid """
        self.geo._reset_lines()


    def load (self):
        """
        Overloaded: Loads bezier definition instead of .dat from file" 
        """    

        if os.path.isfile (self.pathFileName_abs):

            self.load_bezier(fromPath=self.pathFileName_abs)

            # first geometry check
            
            try:
                self.geo.thickness
            except GeometryException as e:
                logger.error (f"{self} {e}")
                raise
        
            # get modfication datetime of file 

            ts = os.path.getmtime(self.pathFileName_abs)                # file modification timestamp of a file
            self._file_datetime = datetime.fromtimestamp(ts)            # convert timestamp into DateTime object


    def load_bezier (self, fromPath=None):
        """
        Loads bezier definition from file. 
        pathFileName must be set before or fromPath must be defined.
        Load doesn't change self pathFileName
        """    

        with open(fromPath, 'r') as file:            

            file_lines = file.readlines()

        # format of bezier airfoil file 
        # <airfoil name> 
        # Top Start
        # 0.0000000000000000 0.0000000000000000
        # ...
        # 1.0000000000000000 0.0000000000000000
        # Top End
        # Bottom Start
        # ...
        # Bottom End

        new_name = 'Bezier_Airfoil'                             # default name 
        self._geo = None                                        # reset geometry 

        try: 
            px, py = [], []
            for i, line in enumerate(file_lines):
                if i == 0:
                    new_name = line.strip()
                else: 
                    line = line.lower()
                    if "start" in line:
                        if "top" in line: 
                            side = Line.Type.UPPER
                        else:
                            side = Line.Type.LOWER 
                        px, py = [], []
                    elif "end" in line:
                        if not px : raise ValueError("Start line missing")
                        if "top"    in line and side == Line.Type.LOWER: raise ValueError ("Missing 'Bottom End'")  
                        if "bottom" in line and side == Line.Type.UPPER: raise ValueError ("Missing 'Bottom Top'") 
                        self.set_newSide_for (side, px,py)
                    else:     
                        splitline = line.strip().split()
                        if len(splitline) == 1:                        # couldn't split line - try tab as separator
                            splitline = line.strip().split("\t")
                        if len(splitline) >= 2:                     
                            px.append (float(splitline[0].strip()))
                            py.append (float(splitline[1].strip()))
        except ValueError as e:
            logger.error ("While reading Bezier file '%s': %s " %(fromPath,e )) 
            return  
         
        self._name = new_name
        self._isLoaded = True 

        logger.debug (f"Bezier definition for {self.name} loaded")

        return   


    @override
    def save (self, onlyShapeFile=False):
        """
        Basic save of self to its pathFileName
            for Hicks-Henne and Bezier 'onlyShapeFile' will write no .dat file 
        """
        if self.isLoaded: 
            self._write_bez_to_file ()
            if not onlyShapeFile:
                self._write_dat_to_file ()

            self.set_isModified (False)

            logger.debug (f"{self} save to {self.fileName}")



    def _write_bez_to_file (self):
        """ write Bezier data to bez file """
        #  .bez-format for CAD etc and 

        with open(self.pathFileName_shape, 'w+') as file:

            # airfoil name 
            file.write("%s\n" % self.name)

            file.write("Top Start\n" )
            for p in self.geo.upper.controlPoints:
                file.write("%13.10f %13.10f\n" %(p[0], p[1]))
            file.write("Top End\n" )

            file.write("Bottom Start\n" )
            for p in self.geo.lower.controlPoints:
                file.write("%13.10f %13.10f\n" %(p[0], p[1]))
            file.write("Bottom End\n" )

            file.close()


    def asCopy (self, pathFileName = None, 
                name=None, nameExt=None,
                geometry=None) -> 'Airfoil':
        """
        returns a copy of self 

        Args:
            pathFileName: optional - string of existinng airfoil path and name 
            name: optional         - name of airfoil - no checks performed 
            nameExt: -optional     - will be appended to self.name (if name is not provided)
            geometry: - not supported - 
        """
        # overloaded as Bezier needs a special copy, no other geometry supported

        if pathFileName is None and name is None: 
            pathFileName = self.pathFileName

        if os.path.isabs (pathFileName):
            workingDir = None
        else: 
            workingDir = self.workingDir 

        if name is None:
            name = self.name + nameExt if nameExt else self.name

        if geometry is not None and geometry != Geometry_Bezier: 
            raise ValueError (f"Airfoil_Bezier does not support new geometry {geometry}")

        airfoil =  Airfoil_Bezier (name = name, pathFileName = pathFileName,
                                   workingDir=workingDir, 
                                   cp_upper = self.geo.upper.controlPoints,
                                   cp_lower = self.geo.lower.controlPoints)
        airfoil.set_isLoaded (True)

        return airfoil 


#------------------------------------------------------

class Airfoil_Hicks_Henne(Airfoil):
    """ 

    Airfoil based on a seed airfoil and hicks henne bump (hh) functions for upper and lower side 

    """

    isHicksHenneBased  = True

    Extension           = ".hicks"


    def __init__(self, name = None, pathFileName=None, workingDir= None):
        """
        Main constructor for new Airfoil

        Args:
            pathFileName: optional - string of existinng airfoil path and name \n
            name: optional - name of airfoil - no checks performed 
        """
        super().__init__( name = name, pathFileName=pathFileName, workingDir=workingDir)

        self._geometry_class  = Geometry_HicksHenne  # geometry strategy 
        self._isLoaded       = False                # hicks henne definition loaded? 

    @property
    def pathFileName_shape (self) -> str: 
        """ abs pathfileName of the hh definition file """
        if self.pathFileName_abs:  
            return os.path.splitext(self.pathFileName_abs)[0] + Airfoil_Hicks_Henne.Extension
        else: 
            return None 

    @property
    def isLoaded (self): 
        # overloaded
        return self._isLoaded
    def set_isLoaded (self, aBool: bool):
        self._isLoaded = aBool


    @property
    def geo (self) -> Geometry_HicksHenne:
        """ the geometry strategy of self"""
        if self._geo is None: 
            self._geo = self._geometry_class (onChange = self._handle_geo_changed)
        return self._geo

    @override
    @property
    def flap_setter (self) -> 'Flap_Setter':
        """ proxy controller to flap self using Worker"""
        # do not flap Hicks-Henne
        return None 


    def set_xy (self, x, y):
        """ hh - do nothing """
        # overloaded - hh geometry is master of data 
        pass

    @property
    def x (self):
        # overloaded  - take from geometry hh 
        return self.geo.x

    @property
    def y (self):
        # overloaded  - take from geometry hh  (seed airfoil and hicks henne are added)
        return self.geo.y

    # -----------------

    def reset (self): 
        """ make child curves like thickness or camber invalid """
        self.geo._reset_lines()


    def load (self):
        """
        Overloaded: Loads hicks henne definition instead of .dat from file" 
        """    

        if os.path.isfile (self.pathFileName_abs):

            self.load_hh(fromPath=self.pathFileName_abs)

            # first geometry check
            
            try:
                self.geo.thickness
            except GeometryException as e:
                logger.error (f"{self} {e}")
                raise

            # get modfication datetime of file 

            ts = os.path.getmtime(self.pathFileName_abs)                       # file modification timestamp of a file
            self._file_datetime = datetime.fromtimestamp(ts)            # convert timestamp into DateTime object


    def load_hh (self, fromPath=None):
        """
        Loads hicks henne definition from file. 
        """    

        name, seed_name, seed_x, seed_y, top_hhs, bot_hhs = self._read_hh_file (fromPath)

        self.set_hh_data (name, seed_name, seed_x, seed_y, top_hhs, bot_hhs)



    def set_hh_data (self, name, seed_name, seed_x, seed_y, top_hhs, bot_hhs): 
        """ set all data needed for a Hicks Henne airfoil"""

        self._name = name                       # don't use set_ (isModified)

        if seed_name and len(seed_x) and len(seed_y): 

            seed_foil = Airfoil (x=seed_x, y=seed_y, name=seed_name)

            if seed_foil.isLoaded: 
                self._geo = Geometry_HicksHenne (seed_foil.x, seed_foil.y)
                self._geo.upper.set_hhs (top_hhs)
                self._geo.lower.set_hhs (bot_hhs)

                self._isLoaded = True 
                logger.debug (f"Hicks Henne definition for {self.name} loaded")
            else: 
                logger.error (f"Hicks Henne seed airfoil {seed_name} couldn't be loaded ")
        else: 
            raise ValueError (f"Hicks Henne seed airfoil data missing for {name}")



    def _read_hh_file (self, fromPath):
        """
        reads hicks henne definition from file. 
        """    

        with open(fromPath, 'r') as file:            

            file_lines = file.readlines()

        
        # format of bezier airfoil file 

        # <airfoil name> 
        # Top Start
        # 0.000strength000000000 0.0000location0000000  0.0000width0000000
        # ...
        # Top End
        # Bottom Start
        # ... 
        # Bottom End
        # Seedfoil Start 
        # 'seed airfoil name'
        #  1.000000 0.000000
        #  ...      ...

        name = ''                                # name of airfoil  
        seed_name = ''                           # name of seed airfoil 
        x,y = [], []                             # x,y of sedd
        top_hhs = []                             # array of hh functions 
        bot_hhs = []
        side = None

        try: 
            hhs = []
            for i, line in enumerate(file_lines):

                line_low = line.lower()

                if i == 0: 

                    name = line.strip()

                elif "seedfoil start" in line_low:

                    seed_name, x, y = self._loadLines (file_lines [i+1:])

                elif "start" in line_low:

                    if "top" in line_low: 
                        side = Line.Type.UPPER
                    else:
                        side = Line.Type.LOWER 
                    hhs = []

                elif "end" in line_low:

                    if not side : raise ValueError("Start line missing")
                    if "top"    in line_low and side == Line.Type.LOWER: raise ValueError ("Missing 'Bottom End'")  
                    if "bottom" in line_low and side == Line.Type.UPPER: raise ValueError ("Missing 'Bottom Top'") 

                    if side == Line.Type.LOWER:
                        bot_hhs = hhs
                    else: 
                        top_hhs = hhs 
                    side = None

                else:     

                    splitline = line.split()
                    if len(splitline) == 3:                     
                        strength = float(splitline[0].strip())
                        location = float(splitline[1].strip())
                        width    = float(splitline[2].strip())
                        hhs.append (HicksHenne (strength, location, width ))
        except ValueError as e:
            logger.error ("While reading Hicks Henne file '%s': %s " %(fromPath,e ))   
         
        return name, seed_name, x, y, top_hhs, bot_hhs   



#--------------------------------------------------------------------------


class Flap_Definition:
    """ 

    Defines the geometry of a flap 

    With set_flap a flapped version of the original airfoil is returned   

    """

    @staticmethod
    def have_same_hinge (flap_def1 : 'Flap_Definition', flap_def2 : 'Flap_Definition') -> bool:
        """
        Compare 2 flap definitions if they have the same hinge definition
        Return True if they are the same or both have no flap_def1
        """
        if flap_def1 and flap_def2:
            return  flap_def1.x_flap == flap_def2.x_flap and \
                    flap_def2.y_flap == flap_def2.y_flap and \
                    flap_def1.y_flap_spec == flap_def2.y_flap_spec
        elif flap_def1 is None and flap_def2 is None:
            return True
        else: 
            return False
        

    def __init__(self, dataDict : dict = None):
        """
        """

        self._x_flap        = fromDict (dataDict, "x_flap", 0.75)
        self._y_flap        = fromDict (dataDict, "y_flap", 0.0) 
        self._y_flap_spec   = fromDict (dataDict, "y_flap_spec", 'y/t')
        self._flap_angle    = fromDict (dataDict, "flap_angle", 0.0) 


    def _as_dict (self):
        """ returns a data dict with the parameters of self """

        d = {}
        toDict (d, "x_flap",        self.x_flap)                  
        toDict (d, "y_flap",        self.y_flap) 
        toDict (d, "y_flap_spec",   self.y_flap_spec) 
        toDict (d, "flap_angle",    self.flap_angle) 
        return d

    @property
    def name_suffix (self) -> str:
        """ 
        fileName suffix for being flapped like 
            '_f5.1' for defaults or 
            '_f-1.4_xf0.72_yf0.5_yspecYC' for non default values
        """

        return Worker.flapped_suffix (self.flap_angle, self.x_flap, self.y_flap, self.y_flap_spec)


    @property
    def x_flap (self) -> float: 
        return self._x_flap

    def set_x_flap (self, aVal : float):
        self._x_flap = clip (aVal, 0.02, 0.98)

    @property
    def y_flap (self) -> float: 
        return self._y_flap

    def set_y_flap (self, aVal : float):
        self._y_flap = clip (aVal, 0.0, 1.0)

    @property
    def y_flap_spec (self) -> str: 
        return self._y_flap_spec

    def set_y_flap_spec (self, aVal : str):
        self._y_flap_spec = aVal if aVal in ['y/c', 'y/t'] else self._y_flap_spec

    @property
    def flap_angle (self) -> float: 
        return self._flap_angle

    def set_flap_angle (self, aVal : float):
        self._flap_angle = clip (aVal, -20.0, 20.0)



class Flap_Setter (Flap_Definition):
    """ 

    Proxy to flap an airfoil using Worker 

    With set_flap a flapped version of the original airfoil is returned   

    """

    def __init__(self, airfoil_base : Airfoil):
        """
        constructor for new Flapper to handle flapping of an airfoil

        Args:
            airfoil_base:   an unflapped airfoil to flap 
        """

        super().__init__()
        
        if airfoil_base.isBezierBased or airfoil_base.isHicksHenneBased:
            raise ValueError ("Only .dat files can be flapped")
        
        if airfoil_base.isFlapped:
            raise ValueError ("A flapped airfoil cannot be flapped")
        
        self._worker_workingDir  = airfoil_base.pathName_abs        # working dir of Worker!
        self._base_copy          = airfoil_base.asCopy ()           # copy as parent will change!

        self._airfoil_flapped    = None                             # flapped version of airfoil_org 


    @property
    def airfoil_base (self) -> Airfoil:
        """ the initial, unflapped airfoil"""
        return self._base_copy

    @property
    def airfoil_flapped (self) -> Airfoil:
        """ airfoil org being flapped - None if not """
        return self._airfoil_flapped


    def set_flap_definition (self, flap_def : 'Flap_Definition'):
        """ set new flap definition from another flap_def """
        self.set_x_flap (flap_def.x_flap)
        self.set_y_flap (flap_def.y_flap)
        self.set_y_flap_spec (flap_def.y_flap_spec)
        self.set_flap_angle (flap_def.flap_angle)


    def set_flap (self, flap_angle=None, outname : str=None) -> Airfoil:
        """ 
        flap the base airfoil using worker - an optional flap angle can be submitted
        If successful, airfoil_flapped is available 
        """

        airfoil_base_saved = False

        self._airfoil_flapped = None                        # reset flapped airfoil 

        if not Worker.ready:
            raise RuntimeError ("Worker is not ready to flap airfoil") 

        # don't do anything for flap angle = 0 

        if flap_angle is not None: 
            self.set_flap_angle (flap_angle)
        if self.flap_angle == 0.0: return

        # ensure airfoil_base is (temporarly) saved

        if not os.path.isfile (self.airfoil_base.pathFileName_abs):
            self.airfoil_base.save()
            airfoil_base_saved = True

        # run Worker 

        worker = Worker(self._worker_workingDir)

        flapped_fileName = worker.set_flap (self.airfoil_base.fileName, 
                                        x_flap = self.x_flap, y_flap = self.y_flap, y_flap_spec = self.y_flap_spec,
                                        flap_angle = self.flap_angle,
                                        outname = outname )
        # delete base airfoil file if it was just saved

        if airfoil_base_saved: 
            try: 
                os.remove(self.airfoil_base.pathFileName_abs) 
            except OSError as exc: 
                logger.error (f"{self.airfoil_base.pathFileName_abs} couldn't be removed")

        # load flapped airfoil if successful
        
        if flapped_fileName: 

            # load new airfoil 
            self._airfoil_flapped = Airfoil (pathFileName=flapped_fileName, workingDir=self._worker_workingDir)
            self._airfoil_flapped.load()

            # ... and delete immediatly its file to have a clean directory  
            try: 
                os.remove(self._airfoil_flapped.pathFileName_abs) 
            except OSError as exc: 
                logger.error (f"{self._airfoil_flapped.pathFileName_abs} couldn't be removed")




# ------------ test functions - to activate  -----------------------------------

if __name__ == "__main__":

    # # test flap set 

    # from airfoil_examples import Example

    # Worker().isReady (Path.cwd(), min_version='1.0.5')

    # airfoil = Example(geometry = GEO_SPLINE) 
    # # airfoil.geo.repanel (nPanels=300)
    # airfoil.save() 

    # flapper = Flap_Setter (airfoil)
    # for angle in np.arange (-10,10, 1.0):
    #     flapper.set_flap (angle) 
    # for y in np.arange (0,1, 0.1):
    #     flapper.set_y_flap (y)
    #     flapper.set_flap (15, outname=f"{airfoil.fileName}_y{y:.1f}") 
    # for x in np.arange (0,1, 0.1):
    #     flapper.set_x_flap (x)
    #     flapper.set_flap (15, outname=f"{airfoil.fileName}_x{x:.1f}") 
    
    pass  
