#!/usr/bin/env pythonnowfinished
# -*- coding: utf-8 -*-
"""  

    Part of Optimizer Model to handle Xoptfoil2 result files 

    |-- Case                        - a single optimization case, define specs for an optimization 
        |-- Results                 - proxy of the Xoptfoil2 result files 
            |-- Reader_Airfoils     - read airfoil designs of optimization 
            |-- Reader ...

                                          
"""

import os
import shutil
from datetime import datetime

from base.common_utils      import * 
from base.spline            import HicksHenne
from .airfoil               import Airfoil, Airfoil_Bezier, Airfoil_Hicks_Henne, usedAs
from .airfoil               import GEO_BASIC, Line
from .polar_set             import * 
from .xo2_driver            import Xoptfoil2
from .xo2_input             import GEO_OPT_VARS

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.WARNING)


#-------------------------------------------------------------------------------
# Results - holds the different Result classes 
#-------------------------------------------------------------------------------


class Xo2_Results:

    TIME_REF_FILE   = 'Optimization_History.csv' 

    def __init__(self, workingDir, outName, remove_result_dir = False, remove_airfoil = False ):

        self._outName       = outName                                           # xo2 result airfoil fielName (withput extension) 
        self._workingDir    = workingDir                                        # working dir of optimizer

        resultDir_rel       = outName + Xoptfoil2.RESULT_DIR_POSTFIX            # directory where the designs are generated
        self._resultDir     = os.path.join (workingDir, resultDir_rel)          # directory where the designs are generated

        # optionally remove existing result_dir 

        if remove_result_dir and os.path.isdir (self.resultDir):
            shutil.rmtree(self.resultDir, ignore_errors=True)

        # optionally remove out airfoil (avoid race conditions as xo2 is slow in deleting at a new optimization) 

        if remove_airfoil:
            pathfileName = os.path.join (workingDir, outName + Airfoil.Extension)
            if os.path.isfile (pathfileName): os.remove (pathfileName)
            pathfileName = os.path.join (workingDir, outName + Airfoil_Bezier.Extension)
            if os.path.isfile (pathfileName): os.remove (pathfileName)
            pathfileName = os.path.join (workingDir, outName + Airfoil_Hicks_Henne.Extension)
            if os.path.isfile (pathfileName): os.remove (pathfileName)

        # results reader  

        self._reader_airfoils              = Reader_Airfoils (self.resultDir)        
        self._reader_airfoils_hh           = Reader_Airfoils_HH (self.resultDir)        
        self._reader_airfoils_bezier       = Reader_Airfoils_Bezier (self.resultDir)    
        self._reader_opPoints              = Reader_OpPoints (self.resultDir)            
        self._reader_geoTargets            = Reader_GeoTargets (self.resultDir)          
        self._reader_optimization_history  = Reader_Optimization_History (self.resultDir) 

        # final airfoils 

        self._airfoil_final         = None
        self._airfoil_final_bezier  = None
        self._airfoil_final_hh      = None


    @property
    def workingDir (self): 
        """ working dir of optimizer - absolut"""
        return self._workingDir

    @property
    def resultDir (self): 
        """ directory with optimizer results - absolut"""
        return self._resultDir

    @property 
    def airfoil_final (self) -> Airfoil | None:
        """ the final airfoil as result of optimization - None if not generated """

        if self._airfoil_final is None:
            self._airfoil_final = self._get_airfoil_final (self.workingDir, self._outName, Airfoil.Extension)
        return self._airfoil_final


    @property 
    def airfoil_final_bezier (self) -> Airfoil | None:
        """ the final airfoil Bezier as result of optimization - None if not generated """

        if self._airfoil_final_bezier is None:
            self._airfoil_final_bezier = self._get_airfoil_final (self.workingDir, self._outName, Airfoil_Bezier.Extension)
        return self._airfoil_final_bezier


    @property 
    def airfoil_final_hh (self) -> Airfoil | None:
        """ the final airfoil Hicks Henneas result of optimization - None if not generated """

        if self._airfoil_final_hh is None:
            self._airfoil_final_hh = self._get_airfoil_final (self.workingDir, self._outName, Airfoil_Hicks_Henne.Extension)
        return self._airfoil_final_hh


    def _get_airfoil_final (self, workingDir : str, outName: str, extension : str) -> Airfoil | None:
        """ if exists return final airfoil for extension .dat or .bez or .hh"""

        fileName = outName + extension
        if os.path.isfile (os.path.join (workingDir, fileName)):
            airfoil =  Airfoil.onFileType (fileName, workingDir=workingDir)
            airfoil.load()
            airfoil.set_usedAs (usedAs.FINAL)
            return airfoil 



    @property
    def nSteps (self) -> int:
        """ number of optimization steps imported (up to now) - "0" excluded""" 
        nSteps = len(self._reader_optimization_history.steps)
        return nSteps if nSteps == 0 else nSteps - 1


    @property
    def nDesigns (self) -> int:
        """ number of Designs steps imported (up to now) - "0" excluded""" 
        nDesigns = 0 
        for step in self._reader_optimization_history.steps [::-1]:
            if step.design != -1: 
                nDesigns = step.design
                break
        return nDesigns 


    @property 
    def improvement (self):
        """ improvement in fraction of 1.0 reached up to now - else 0.0 """
        steps = self._reader_optimization_history.steps
        if steps: 
            improvement = steps[-1].improvement / 100.0                     # xoptfoil2 returns % 
        else: 
            improvement = 0.0 
        return improvement


    @property
    def hasProbablyResults (self) -> bool:
        """ does result dir exist? or isRunning? Then there *should* be results"""

        hasResults = False
        if os.path.isdir(self.resultDir):
            hasResults = True 
        return hasResults


    @property 
    def isFinished (self) -> bool:
        """ is optimization finished - performance summary will exist"""

        return self.hasProbablyResults and os.path.isfile (os.path.join (self.resultDir, self.TIME_REF_FILE)) 


    def time_elapsed (self) -> str:
        """ returns hours, minutes, seconds how long self was running as string hh:mm:ss"""

        last_write_dt  = self._get_dateTime_last_write() 
        first_write_dt = self._get_dateTime_first_write()

        if last_write_dt and first_write_dt:
            delta = last_write_dt - first_write_dt
            hours, remainder = divmod(delta.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
        else:
            hours, minutes, seconds = 0, 0, 0 

        if hours > 0:
            return f"{int(hours)}:{int(minutes)}:{int(seconds):02d}"
        else: 
            return f"{int(minutes)}:{int(seconds):02d}"

    @property
    def date_time_last_write (self) -> datetime:
        """ youngest date of written results"""
        return self._get_dateTime_last_write()        

    @property
    def steps (self) -> list ['Optimization_History_Entry']:
        """ optimization steps imported (up to now)""" 
        return self._reader_optimization_history.steps


    @property
    def designs_opPoints (self):        
        """ op point results of the designs """
        return self._reader_opPoints.designs


    @property
    def designs_geoTargets (self):        
        """ geo targets results of the designs """
        return self._reader_geoTargets.designs

    @property
    def designs_airfoil (self):        
        """ airfoil of the designs either HicksHenne or Bezier """

        if self._reader_airfoils_hh.hasResults:
            return self._reader_airfoils_hh.designs
        elif self._reader_airfoils_bezier.hasResults:
            return self._reader_airfoils_bezier.designs
        elif self._reader_airfoils.hasResults:
            return self._reader_airfoils.designs
        else: 
            return []


    # ---- Methods -------------------------------------------


    def set_results_could_be_dirty (self): 
        """ mark results of Reader as dirty so they will be re-read at next access"""

        self._reader_airfoils.set_results_could_be_dirty(True)
        self._reader_airfoils_hh.set_results_could_be_dirty(True)
        self._reader_airfoils_bezier.set_results_could_be_dirty(True)
        self._reader_opPoints.set_results_could_be_dirty(True)
        self._reader_geoTargets.set_results_could_be_dirty(True)
        self._reader_optimization_history.set_results_could_be_dirty(True)


    def remove_resultDir (self):
        """ 
        removes result directory - handle with care ...
        """ 

        shutil.rmtree(self.resultDir, ignore_errors=True)


    def _get_dateTime_last_write (self) -> datetime:
        """" dateTime of reference file in result dir if it exists - else None"""
        ref_file = os.path.join (self.resultDir, self.TIME_REF_FILE)  
        if os.path.isfile (ref_file):    
            ts = os.path.getmtime(ref_file)                 # file modification timestamp of a file
            dt = datetime.fromtimestamp(ts)                 # convert timestamp into DateTime object
        else:
            dt = None
        return dt


    def _get_dateTime_first_write (self) -> datetime:
        """" dateTime of file first written which is Xo2 seed airfoil (normalized)"""

        files = os.listdir(self.resultDir) if os.path.isdir (self.resultDir) else []
        if files:
            path_files = [os.path.join(self.resultDir, f) for f in files]
            oldest_file = min(path_files, key=os.path.getctime)
            ts = os.path.getmtime (oldest_file)             # file modification timestamp of a file
            dt = datetime.fromtimestamp(ts)                 # convert timestamp into DateTime object
        else: 
            dt = None
        return dt  

#-------------------------------------------------------------------------------
# Optimization History step entry  
#-------------------------------------------------------------------------------


class Optimization_History_Entry:
    """ 
    An entry in the optimization hostory    
    """
    def __init__(self):
        """
        New entry in the optimization history with Xoptfoil2 data 
        """

        self.step           = 0                # step number in optimization 
        self.improvement    = None             # % improvement to prior design 
        self.objective      = 1.0              # value of objective function 
        self.design_radius  = 0.0              # the design radius of the particles 
        self.design         = -1               # number of new design if achieved in this step 



#-------------------------------------------------------------------------------
# Geometry target Result  
#-------------------------------------------------------------------------------


class GeoTarget_Result:
    """ 
    optimization result of a geometry target  
    """

    def __init__(self):

        self.optVar         = None             # either CAMBER or THICKNESS 
        self.value          = 0.0 
        self.deviation      = 0.0              # deviation from target / improvement to seed 
        self.distance       = 0.0              # distance from target  / distance from seed 
        self.weighting      = 1.0              # actual weighting during optimization 
        self.is_new_weighting = False          # flag if weighting changed to previous design



#-------------------------------------------------------------------------------
# OpPoint Result  
#-------------------------------------------------------------------------------


class OpPoint_Result (Polar_Point):
    """ 
    The optimization result of Xoptfoil2 for single op point - inherits from opPoint   
    """
    def __init__(self):
        """
        New operating point result  from optimization 
        """

        super().__init__()
        
        self.idesign        = None             # belongs to Design i 
        self.iopPoint       = None             # is opPoint i 

        self.distance       = 0.0              # distance from target  / distance from seed 
        self.deviation      = 0.0              # deviation from target / improvement to seed 
        self.flap           = 0.0              # flap angle (optimzation with flaps)
        self.weighting      = 1.0              # actual weighting during optimization 
        self.is_new_weighting = False          # flag if weighting changed to previous design




#-------------------------------------------------------------------------------
# Result Handler - read the various results vom Xoptfoil2
#-------------------------------------------------------------------------------


class Reader_Abstract:
    """ 
    Abstract superclass    
    """

    filename = None 
    objects_text  = ('','')

    DESIGN_DIR_EXT = "_designs"
    DESIGN_NAME_BASE = "Design"

    @classmethod
    def design_fileName (cls, iDesign : int, extension : str) -> str:
        """ returns fileName of design iDesign"""

        postfix = str(iDesign).rjust(4,'_') if iDesign < 1000 else "_"+str(iDesign)

        return f"{cls.DESIGN_NAME_BASE}{postfix}{extension}"  
    
      
    # ----------------------------------


    def __init__(self, resultDir):
        """Superclass for the different Result Handlers for reading results

        Arguments:
            resultDir -- directory where designs with 'filename' can be found    
        """

        self._results   = []                    # list of designs red 
        self._resultDir = resultDir             # directory where the designs are generated
        self._resultFile_lastDate = None        # last file modification date   
        self._results_could_be_dirty = False    # flag that _results could be outdated 

        # read and load results the first time 

        self.read_results()


    def __repr__(self) -> str:
        """ nice print string"""
        return f"<{type(self).__name__}>"


    @property
    def resultPathFile (self): 
        """ the file path of the file with designs """
        if self.filename is None:
            raise ValueError ("Filename for design file not set") 
        return os.path.join(self._resultDir, self.filename)

    @property 
    def results (self): 
        """ list of (abstract) results - could be designs or steps"""

        # re-read results if dirty flag set 
        if self._results_could_be_dirty: 

            n = self.read_results ()

            logger.debug (f"read {n} results after dirty in {self.__class__.__name__}")
            self._results_could_be_dirty = False
        return self._results 

    
    @property 
    def designs (self): 
        """ List of designs of type Airfoil or Polar or ..."""
        return self.results

    @property 
    def hasResults (self) -> bool: 
        """ are there results? will read if dirty """
        return len(self.results) > 0 

    @property 
    def nResults (self) -> int: 
        """ number of result objects already red in"""
        return len(self._results)


    def set_results_could_be_dirty (self, aBool: bool):
        """ set the dirty flag for self.results - will be re-read when accessed next time"""
    
        self._results_could_be_dirty = aBool


    def read_results (self) -> int:
        """ Reads new design, create objects and add them to 'designs' 

        Returns:
            n_new -- number of new results added
        """    

        n_new = 0                                           # n new results red

        # read only if file changed since last time 
        if self._is_younger_than_last_read (self._resultFile_lastDate, self.resultPathFile):

            from timeit import default_timer as timer
            start = timer()
            # ...
            # print("Time ", timer() - start)  

            try: 
                f = open(self.resultPathFile, 'r')
            except:
                logger.error (f"Couldn't read '{self.resultPathFile}' to get designs")
                return n_new

            # read complete file 
                      
            file_lines = f.readlines()
            f.close()

            time_read = timer() - start 

            # save current file date

            ts = os.path.getmtime(self.resultPathFile)                       # file modification timestamp of a file
            self._resultFile_lastDate = datetime.fromtimestamp(ts)      # convert timestamp into DateTime object

            n_before = self.nResults

            # parse line, create objects, add to result list 
            start = timer()

            n_new = self._load_results(file_lines)          # overloaded in sub classes

            time_load = timer() - start 

            # nice message print 
            if n_new > 0: 
                if n_new == 1:
                    object_name = self.objects_text[0]
                else: 
                    object_name = self.objects_text[1]
                if n_before == 0: 
                    new_text = ''
                else:
                    new_text = 'new '
                if time_load < 0.01 and time_read < 0.005:
                    logger.debug (f"{self} imported {n_new} {new_text}{object_name}  (Time read: {time_read:.4f}s, load: {time_load:.4f}s)")
                elif n_new == 1: 
                    logger.warning (f"{self} importing {len(file_lines)} lines takes too long (Time read: {time_read:.4f}s, load: {time_load:.4f}s)")
            else: 
                logger.warning (f"{self} nothing to import")

        return n_new


    def _load_results (self, file_lines): 
        """ parse new lines and create design results """
        return 0                                           # must be over loaded 


    def _is_younger_than_last_read (self, lastDate, aResultFile):
        """ checks if the current file is younger than the version at last read"""

        if  aResultFile is None or not os.path.isfile (aResultFile):
            return False                                # no valid file to check
        
        if lastDate is None:
            return True                                 # first time - no last date available

        ts = os.path.getmtime(aResultFile)              # file modification timestamp of a file
        current = datetime.fromtimestamp(ts)            # convert timestamp into DateTime object

        if lastDate != current:
            return True
        else:
            return False                                # file didn't change

 

class Reader_Optimization_History (Reader_Abstract):
    """
    The Xoptfoil2 optimization history with steps, objective function, design radius 
    """

    filename = 'Optimization_History.csv'
    objects_text  = ('optimization step', 'optimization steps')

    @property
    def steps (self) -> list [Optimization_History_Entry]:
        """ no of steps - will re-read if dirty!"""
        return self.results 


    def _load_results (self, file_lines):
        """ Parse file_lines and create new history objects  

        Arguments:
            file_lines -- (new) lines of the file 
        """
        # File format 
        #
        #   Iter;Design;  Objective;  % Improve; Design rad
        #      0;      ;  1.0000000;  0.0000000;  0.1459420
        #      1;     1;  0.9729227;  2.7077310;  0.1433520

        n_new = 0 
        for i, line in enumerate(file_lines):

            vals = [val.strip() for val in line.split(';')]             # will remove all extra spaces

            if vals[0] == 'Iter' and vals[1] == 'Design':               # Header 
                pass
            else:
                istep = int (vals[0])
                if vals[1] != '':
                    idesign = int(vals[1])                              # step with new design
                else: 
                    idesign = -1                                        # step with no new design                    
                data =  [float(i) for i in vals[2:]]               
                n_new += self.add_history_entry (istep, idesign, data)
        return n_new


    def add_history_entry (self, istep, idesign, data):
        """ add a Optimization_Step to steps  """

        n_new = 0 
        if  istep == self.nResults:             # steps start with istep=0

            history_entry = Optimization_History_Entry()

            history_entry.objective     = data[0]
            history_entry.improvement   = data[1]
            history_entry.design_radius = data[2]
            history_entry.step          = istep
            history_entry.design        = idesign
            
            self._results.append(history_entry) 
            n_new += 1           

        elif istep < self.nResults:              # we have it already 
            pass                                     
        else:                                       #  there would be a gap in design list
            raise ValueError ("Add new history step: Index %i doesn't fit" %istep)
        return n_new
        



class Reader_OpPoints (Reader_Abstract):
    """
    The Xoptfoil2 results for the operating points during an optimization 
    """

    filename = 'Design_OpPoints.csv'
    objects_text  = ('set of op results', 'sets of op results')

    def _load_results (self, file_lines):
        """ Parse file_lines and create new design objects lines of the file freshly red into 

        Arguments:
            file_lines -- (new) lines of the file 
        """
        # File format 
        #
        #    No; iOp;      alpha;         cl;         cd;         cm;       xtrt;       xtrb;       dist;        dev;     flap;   weight
        #     0;   1;  -3.713445;  -0.250000;   0.012932;  -0.037740;   0.982203;   0.026582;  -0.001832; -16.507213;   0.0000;     1.0
        #     0;   2;  -2.236515;  -0.050000;   0.008851;  -0.046911;   0.956186;   0.533244;  -0.001791; -25.370629;   0.0000;     0.5

        n_new = 0 
        idesign_old = len (self._results) 
        ops_results = []

        for i, line in enumerate(file_lines):

            vals = [val.strip() for val in line.split(';')]             # will remove all extra spaces

            if vals[0] == 'No' and vals[1] == 'iOp':   # Header 
                pass
            else:
                idesign = int (vals[0])

                if idesign == idesign_old: 
                    # same design group - add sub object to list 
                    ops_results.append ([float(i) for i in vals[2:]])   # convert list to float

                if idesign > idesign_old :  
                    # new design group - flush old one 
                    n_new += self.add_opPoints_result (idesign_old, ops_results)
                    # start new one with current sub object
                    idesign_old = idesign 
                    ops_results = [[float(i) for i in vals[2:]]]   

                if i == (len(file_lines)-1):
                    # last record - flush current design group 
                    n_new += self.add_opPoints_result (idesign, ops_results)               
      
        return n_new


    def add_opPoints_result (self, idesign, ops_results_list):
        """ add array of OpPoint_Result to designs """

        n_new = 0 
        if idesign == len (self._results):          # new, next design in list 

            ops      = []

            for iop, op_result_list in enumerate (ops_results_list): 

                if len(op_result_list) >= 10: 
                    op = OpPoint_Result ()

                    op.idesign   = idesign 
                    op.iopPoint  = iop 

                    op.alpha     = op_result_list[0]
                    op.cl        = op_result_list[1]
                    op.cd        = op_result_list[2]
                    op.cm        = op_result_list[3]
                    op.xtrt      = op_result_list[4]
                    op.xtrb      = op_result_list[5]
                    op.distance  = op_result_list[6]
                    op.deviation = op_result_list[7]
                    op.flap      = op_result_list[8]
                    op.weighting = op_result_list[9]
                    ops.append(op)
                else: 
                    logger.error (f"Format of '{self.filename}' doesn't fit. Skipping op point data...")       

            # compare weighting to previous design and set flag if changed (dynamic weighting)
            self._set_is_new_weighting (ops, self._results[-1] if self._results else [])

            self._results.append(ops)   

            n_new += 1  

        elif idesign < len (self._results):         # we have it already 
            pass                                     
        elif len (self._results) == 0:              # we are already in error mode
            pass
        else:                                       #  there would be a gap in design list
            raise ValueError ("Add new design: Index %i doesn't fit" %idesign)
        return n_new


    def _set_is_new_weighting (self, new_ops : list [OpPoint_Result], prev_ops : list [OpPoint_Result]):
        """ set new weighting flag if new weighting of op point is different to previous one """

        if len(new_ops) != len(prev_ops): return  

        for new_op, prev_op in zip (new_ops, prev_ops):
            if abs (new_op.weighting - prev_op.weighting) > 1e-6:
                new_op.is_new_weighting = True 



class Reader_GeoTargets (Reader_Abstract):
    """
    The results for the geometry targets during an optimization 
    """

    filename = 'Design_GeoTargets.csv'
    objects_text  = ('set of geo target results', 'sets of geo target results')

    def _load_results (self, file_lines):
        """ Parse file_lines and create new design objects lines of the file freshly red into 

        Arguments:
            file_lines -- (new) lines of the file 
        """
        # File format 
        #
        #    No; iGeo;        type;       val;        dev;   weight 
        #     0;    1;    'Camber';   0.01711; -16.507213;      1.0   
        #     0;    2; 'Thickness';   0.08201; -16.507213;      1.0     

        n_new = 0 
        idesign_old = 0 
        geo_results = []

        for i, line in enumerate(file_lines):

            vals = [val.strip() for val in line.split(';')]             # will remove all extra spaces

            if vals[0] == 'No' and vals[1] == 'iGeo':   # Header 
                pass
            else:
                idesign = int (vals[0])

                if idesign == idesign_old: 
                    # same design group - add sub object to list 
                    geo_results.append ([vals[2]] + [float(i) for i in vals[3:]]) 

                if idesign != idesign_old :  
                    # new design group - flush old one 
                    n_new += self.add_geoTarget_result (idesign_old, geo_results)
                    # start new one with current sub object
                    idesign_old = idesign 
                    geo_results = [[vals[2]] + [float(i) for i in vals[3:]]]

                if i == (len(file_lines)-1):
                    # last record - flush current design group 
                    n_new += self.add_geoTarget_result (idesign, geo_results)               

        return n_new


    def add_geoTarget_result (self, idesign, geos_results_list):
        """ add array of GeoTarget_Result to designs """

        n_new = 0 
        if idesign == len (self._results):          # new, next design in list 

            geos = []
            for geo_result_list in geos_results_list: 

                if len(geo_result_list) >= 2: 
                    geo = GeoTarget_Result ()

                    optVar_result : str = geo_result_list[0]
                    for optVar in GEO_OPT_VARS:                         # support "thickness" and "Thickness"
                        if optVar_result.lower() == optVar.lower():
                            geo.optVar    = optVar
                            geo.value     = geo_result_list[1]
                            geo.distance  = geo_result_list[2]
                            geo.deviation = geo_result_list[3]
                            geo.weighting = geo_result_list[4]
                            geos.append(geo)
                else: 
                    logger.error (f"Format of '{self.filename}' doesn't fit. Skipping op point data...")       

            # compare weighting to previous design and set flag if changed (dynamic weighting)  
            self._set_is_new_weighting (geos, self._results[-1] if self._results else [])

            self._results.append(geos)  
            n_new += 1  

        elif idesign < len (self._results):         # we have it already 
            pass                                     
        elif len (self._results) == 0:              # we are already in error mode
            pass
        else:                                       #  there would be a gap in design list
            raise ValueError ("Add new design: Index %i doesn't fit" %idesign)
        return n_new


    def _set_is_new_weighting (self, new_geos : list [GeoTarget_Result], prev_geos : list [GeoTarget_Result]):
        """ set new weighting flag if new weighting of op point is different to previous one """

        if len(new_geos) != len(prev_geos): return  

        for new_geo, prev_geo in zip (new_geos, prev_geos):
            if abs (new_geo.weighting - prev_geo.weighting) > 1e-6:
                new_geo.is_new_weighting = True 




class Reader_Airfoils (Reader_Abstract):
    """
    The airfoils generated during an optimization 
    """
    filename = 'Design_Coordinates.csv'
    objects_text  =('airfoil', 'airfoils')

    def _load_results (self, file_lines : list[str]):
        """ Parse file_lines and create new design objects lines of the file freshly red into 

        Arguments:
            file_lines -- (new) lines of the file 
        """
        # File format 
        #
        #    No;           Name; Coord;         1;         2;         3;     
        #     0;JX-Seed-Reflexed;    x; 1.0000000; 0.9905321; 0.9797401; 0.96
        #     0;JX-Seed-Reflexed;    y; 0.0001498; 0.0003774; 0.0007564; 0.00

        x,y = [], []
        n_new = 0 
        for i, line in enumerate(file_lines):

            vals = [val.strip() for val in line.split(';')]             # will remove all extra spaces

            if vals[0] == 'No' and vals[1] == 'Name':                   # Header 
                pass

            elif vals[2] == 'x' or vals[2] =='y':                       # a valid line 
                idesign = int (vals[0])

                name    = vals[1]
                coord   = vals[2]
                if coord == 'x':
                    x = [float(i) for i in vals[3:]] 
                else: 
                    y = [float(i) for i in vals[3:]] 
                if x and y: 
                    n_new += self.add_airfoil_design (idesign, name, x, y) 
                    x, y = [], []

            else:
                logger.error ("Invalid coordinates file format for designs - skipped.")
                break 
        return n_new


    def add_airfoil_design (self, idesign, name, x, y):
        """ add a new airfoil design to my designs """

        n_new = 0 
        if idesign == len (self._results):          # new, next design in list 

            # create airfoil - set its file path to resultDir for lazy save to generate polar
            #                  use basic Geometry (not splined) for faster evaluation
            fileName = self.design_fileName (idesign, Airfoil.Extension )

            airfoil = Airfoil (name=name, workingDir=self._resultDir, geometry=GEO_BASIC)

            airfoil.set_xy (x,y)
            airfoil.set_pathFileName (fileName, noCheck=True)               # no check - it doesn't exist
            airfoil.set_usedAs (usedAs.DESIGN)

            # if airfoil file not was already created before, set modify for lazy write 
            if os.path.isfile (airfoil.pathFileName):
                airfoil.set_isModified (False)
            else: 
                airfoil.set_isModified (True)             # up to now airfoil file doesn't exist  

            self._results.append(airfoil)

            n_new = 1           

        elif idesign < len (self._results):         # we have it already 
            pass                                     
        else:                                       #  there would be a gap in design list
            raise ValueError ("Add new design airfoil: Index %i doesn't fit" %idesign)

        return n_new



# -----------------------------------------


class Reader_Airfoils_Bezier (Reader_Abstract):
    """
    The airfoils as bezier definitions generated durng an optimization 
    """

    filename = 'Design_Beziers.csv'
    objects_text  =('bezier airfoil', 'bezier airfoils')

    def _load_results (self, file_lines):
        """ Parse file_lines and create new design objects lines of the file freshly red into 

        Arguments:
            file_lines -- (new) lines of the file 
        """
        # File format 
        #
        #    No;           Name; Side;         p1x;         p1y;         p2x;         p2y;         p3x;         p3y;         
        #     0;JX-Seed-Reflexed_bezier;  Top;  0.00000000;  0.00000000;  0.00000000;  0.02508150;  0.12899340;  0.10043424
        #     0;JX-Seed-Reflexed_bezier;  Bot;  0.00000000;  0.00000000;  0.00000000; -0.01452336;  0.09103726; -0.03561080       #    No; Side;         p1x;         p1y;         p2x;         p2y;     

        pxy_top, pxy_bot = [], []
        n_new = 0 

        for i, line in enumerate(file_lines):

            vals = [val.strip() for val in line.split(';')]             # will remove all extra spaces

            if vals[0] == 'No' and vals[1] == 'Name':   # Header 
                pass

            elif vals[2] == 'Top' or vals[2] =='Bot':  # a valid line 
                idesign = int (vals[0])
                side = vals[2]
                if side == 'Top':
                    pxy_top = [float(i) for i in vals[3:]] 
                else: 
                    pxy_bot = [float(i) for i in vals[3:]] 
                if pxy_top and pxy_bot: 
                    n_new += self.add_airfoil_design (idesign, vals[1], pxy_top, pxy_bot) 
                    pxy_top, pxy_bot = [], []
            else:
                logger.error ("Invalid Bezier file format for designs - skipped.")
                break 
        return n_new


    def add_airfoil_design (self, idesign, name, pxy_top, pxy_bot):
        """ add a new bezier based airfoil design to my designs """

        n_new = 0 
        if idesign == len (self._results):          # new, next design in list 

            # create bezier airfoil out of bezier upper and lower 
            #  - set its file path to resultDir for lazy save to generate polar
            airfoil = Airfoil_Bezier (name=name, workingDir=self._resultDir, )

            fileName = self.design_fileName (idesign, Airfoil_Bezier.Extension )

            airfoil.set_pathFileName (fileName, noCheck=True)

            px, py = [], []
            for i, x_or_y in enumerate(pxy_top):
                if i % 2 == 0: px.append(x_or_y)
                else:          py.append(x_or_y)
            airfoil.set_newSide_for (Line.Type.UPPER, px, py)

            px, py = [], []
            for i, x_or_y in enumerate(pxy_bot):
                if i % 2 == 0: px.append(x_or_y)
                else:          py.append(x_or_y)
            airfoil.set_newSide_for (Line.Type.LOWER, px, py)

            airfoil.set_usedAs (usedAs.DESIGN)
            airfoil.set_isLoaded (True)
            airfoil.set_isModified (True)             # up to now airfoil file doesn't exist  

            self._results.append(airfoil)

            n_new = 1           

        elif idesign < len (self._results):         # we have it already 
            pass                                     
        else:                                       #  there would be a gap in design list
            raise ValueError ("Add new design airfoil: Index %i doesn't fit" %idesign)

        return n_new




class Reader_Airfoils_HH (Reader_Abstract):
    """
    The airfoils as Hicks Henne definitions generated during an optimization 
    """

    filename = 'Design_Hicks.csv'
    objects_text  = ('hh airfoil', 'hh airfoils')

    def __init__(self, *args, **kwargs):

        self._seed_x = None                             # x,y coordinates of seed 
        self._seed_y = None 
        self._seed_name = None

        super().__init__(*args,  **kwargs)


    def _load_results (self, file_lines):
        """ Parse file_lines and create new design objects lines of the file freshly red into 
        """

        # File format 
        #
        #    No;           Name; Coord;         1;         2;         3;         4;         5;         6;         
        #     0;X2-Seed-Rearload-repan-preset;    x; 1.0000000; 0.9930137; 0.9830685; 0.9688287; 0.9539262; 0.9386
        #     0;X2-Seed-Rearload-repan-preset;    y; 0.0001545; 0.0010889; 0.0024129; 0.0042939; 0.0062408; 0.0082
        #    No;           Name; Side;     hh1_str;     hh1_loc;     hh1_wid;     hh2_str;     hh2_loc;     hh2_wi
        #     1;JX-GT-10v3~1;  Top;  0.00026016;  0.19854563;  0.99892745;  0.00044837;  0.40176901;  0.99883876; 
        #     1;JX-GT-10v3~1;  Bot; -0.00018333;  0.24907524;  1.00275824;  0.00036286;  0.49963857;  1.00189794; 

        hhs_top, hhs_bot = [], []
        n_new = 0 

        for i, line in enumerate(file_lines):

            if i == 0 or i == 3:                                        # Header 
                continue
            if i == 1 and self._seed_x :                                # seed coordinates already read
                continue 
            if i == 2 and self._seed_y :                                # seed coordinates already read
                continue 

            vals = [val.strip() for val in line.split(';')]             # will remove all extra spaces

            if i == 1: 
                self._seed_x = [float(i) for i in vals[3:]] 
                self._seed_name = vals[1]
            elif i == 2: 
                self._seed_y = [float(i) for i in vals[3:]] 
                n_new += self.add_airfoil_design (0)                    # add design 0 = seed airfoil

            elif vals[2] == 'Top' or vals[2] =='Bot':                   # a valid line with hhs
                idesign, name, side = int (vals[0]), vals[1], vals[2]
                if side == 'Top':
                    hhs_top = [float(i) for i in vals[3:]] 
                else: 
                    hhs_bot = [float(i) for i in vals[3:]] 

                n_new += self.add_airfoil_design (idesign, name, hhs_top, hhs_bot)  # hh can be []
                hhs_top, hhs_bot = [], []

            else:
                logger.error ("Invalid Hicks Henne file format for designs - skipped.")
                break 
        return n_new


    def add_airfoil_design (self, idesign, name=None, top_hh_vals=None, bot_hh_vals=None):
        """ add a new Hicks Henne based airfoil design to my designs """

        n_new = 0 

        #  design #0 is the seed airfoil 

        if idesign == 0  and len (self._results) == 0: 

            airfoil = Airfoil (name=self._seed_name, geometry=GEO_BASIC)
            airfoil.set_xy (self._seed_x,self._seed_y)
            airfoil.set_pathFileName (os.path.join(self._resultDir, self._seed_name + '.dat'), noCheck=True)
            airfoil.set_isModified (True)             # up to now airfoil file doesn't exist  
            airfoil.set_usedAs (usedAs.DESIGN)
            self._results.append(airfoil)

        # create hicks henne airfoil out of upper and lower hh functions 
        #  - set its file path to resultDir for lazy save to generate polar

        elif idesign == len (self._results):          # new, next design in list 

            top_hhs = self._get_hhs (top_hh_vals)
            bot_hhs = self._get_hhs (bot_hh_vals)

            airfoil = Airfoil_Hicks_Henne (name=name, workingDir=self._resultDir)

            fileName = self.design_fileName (idesign, Airfoil_Hicks_Henne.Extension )
            airfoil.set_pathFileName (fileName, noCheck=True)
            airfoil.set_hh_data (name, self._seed_name, self._seed_x, self._seed_y, top_hhs, bot_hhs)
            airfoil.set_usedAs (usedAs.DESIGN)
            airfoil.set_isModified (True)             # up to now airfoil file doesn't exist  
            self._results.append(airfoil)
            n_new += 1           

        elif idesign < len (self._results):         # we have it already 
            pass                                     
        else:                                       #  there would be a gap in design list
            raise ValueError ("Add new design airfoil: Index %i doesn't fit" %idesign)

        return n_new


    def _get_hhs (self, hh_vals): 
        """ extract hh function out of array of hh values """

        if len(hh_vals)%3 != 0: 
            raise ValueError ("no valid Hicks Henne data array")

        hhs = []
        nhh = int(len(hh_vals) / 3)
        for ihh in range(nhh):
                strength = hh_vals[ihh*3] 
                location = hh_vals[ihh*3 + 1] 
                width    = hh_vals[ihh*3 + 2] 
                hhs.append (HicksHenne (strength, location, width ))
        return hhs
