#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Case pytest classes
"""

import pytest
import os
import shutil

# -> pyproject.toml
# pythonpath = ["airfoileditor"]          # add project root to sys.path to find airfoileditor moduls

from model.case import Case_Direct_Design, Case_Abstract
from model.airfoil import Airfoil, GEO_SPLINE
from model.airfoil_examples import Root_Example

# temp_dir will be injected by pytest in the arguments of test functions
@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for test files"""
    # just a wrapper for naming
    return tmp_path


class Test_Case_Direct_Design:
    """Test suite for Case_Direct_Design class"""


    @pytest.fixture
    def seed_airfoil(self, temp_dir) -> Airfoil:
        """Create a seed airfoil for testing"""
        airfoil = Root_Example(geometry=GEO_SPLINE)
        airfoil_path = airfoil.saveAs(dir=str(temp_dir), destName="test_seed")
        return Airfoil(pathFileName=airfoil_path, workingDir=str(temp_dir))

    def test_case_creation(self, seed_airfoil: Airfoil):
        """Test basic case creation"""
        case = Case_Direct_Design(seed_airfoil)
        
        assert case.airfoil_seed == seed_airfoil
        assert case.name == seed_airfoil.fileName
        assert case.workingDir == seed_airfoil.pathName_abs
        assert os.path.isdir(case.design_dir_abs)

    def test_case_invalid_airfoil(self):
        """Test case creation with invalid airfoil"""
        with pytest.raises(ValueError):
            Case_Direct_Design("not_an_airfoil")

    def test_design_dir_creation(self, seed_airfoil : Airfoil):
        """Test design directory is created"""
        case = Case_Direct_Design(seed_airfoil)
        
        expected_dir = f"{os.path.splitext(seed_airfoil.fileName)[0]}{Case_Abstract.DESIGN_DIR_EXT}"
        assert case.design_dir == expected_dir
        assert os.path.isdir(case.design_dir_abs)

    def test_initial_airfoil_design(self, seed_airfoil):
        """Test initial airfoil design creation"""
        case = Case_Direct_Design(seed_airfoil)
        initial_design = case.initial_airfoil_design()
        
        assert initial_design is not None
        assert initial_design.isEdited
        assert len(case.airfoil_designs) == 1

    def test_add_design(self, seed_airfoil : Airfoil):
        """Test adding designs to case"""
        case = Case_Direct_Design(seed_airfoil)
        initial_design = case.initial_airfoil_design()
        
        # Modify and add as new design
        initial_design.set_isModified(True)
        case.add_design(initial_design)
        
        assert len(case.airfoil_designs) == 2
        assert case.airfoil_designs[1].fileName.startswith(Case_Abstract.DESIGN_NAME_BASE)

    def test_get_design_by_name(self, seed_airfoil : Airfoil):
        """Test retrieving design by name"""
        case = Case_Direct_Design(seed_airfoil)
        initial_design = case.initial_airfoil_design()
        
        fileName = case.airfoil_designs[0].fileName
        retrieved = case.get_design_by_name(fileName)
        
        assert retrieved is not None
        assert retrieved.fileName == fileName

    def test_get_design_by_name_not_found(self, seed_airfoil):
        """Test retrieving non-existent design"""
        case = Case_Direct_Design(seed_airfoil)
        case.initial_airfoil_design()
        
        with pytest.raises(RuntimeError):
            case.get_design_by_name("non_existent.dat")

    def test_remove_design(self, seed_airfoil):
        """Test removing a design"""
        case = Case_Direct_Design(seed_airfoil)
        initial_design = case.initial_airfoil_design()
        
        # Add second design
        case.add_design(initial_design)
        initial_count = len(case.airfoil_designs)
        
        # Remove last design
        design_to_remove = case.airfoil_designs[-1]
        next_airfoil = case.remove_design(design_to_remove)
        
        assert len(case.airfoil_designs) == initial_count - 1
        assert next_airfoil is not None

    def test_remove_last_design_protected(self, seed_airfoil):
        """Test that first design cannot be removed when it's the only one"""
        case = Case_Direct_Design(seed_airfoil)
        case.initial_airfoil_design()
        
        design_to_remove = case.airfoil_designs[0]
        result = case.remove_design(design_to_remove)
        
        # Should not remove if only one design exists
        assert result is None or len(case.airfoil_designs) >= 1

    def test_get_final_from_design(self, seed_airfoil):
        """Test creating final airfoil from design"""
        case = Case_Direct_Design(seed_airfoil)
        design = case.initial_airfoil_design()
        
        final = case.get_final_from_design(design)
        
        assert final is not None
        assert not final.isEdited
        assert "_mod" in final.name or "_Design" in final.name

    def test_set_final_from_design(self, seed_airfoil):
        """Test setting final airfoil from design"""
        case = Case_Direct_Design(seed_airfoil)
        design = case.initial_airfoil_design()
        
        case.set_final_from_design(design)
        
        assert case.airfoil_final is not None
        assert not case.airfoil_final.isEdited

    def test_design_file_name_generation(self):
        """Test design file name generation"""
        fileName_0 = Case_Abstract.design_fileName(0, ".dat")
        fileName_50 = Case_Abstract.design_fileName(50, ".dat")
        fileName_100 = Case_Abstract.design_fileName(100, ".dat")
        
        assert fileName_0 == "Design__0.dat"
        assert fileName_50 == "Design_50.dat"
        assert fileName_100 == "Design_100.dat"

    def test_get_iDesign(self, seed_airfoil: Airfoil):
        """Test extracting design number from airfoil"""
        case = Case_Direct_Design(seed_airfoil)
        design = case.initial_airfoil_design()
        
        iDesign = Case_Abstract.get_iDesign(case.airfoil_designs[0])
        assert iDesign == 0

    def test_remove_designs_on_close_flag(self, seed_airfoil):
        """Test remove_designs_on_close flag"""
        case = Case_Direct_Design(seed_airfoil)
        
        assert case.remove_designs_on_close == False
        
        case.set_remove_designs_on_close(True)
        assert case.remove_designs_on_close == True

    def test_close_removes_design_dir(self, seed_airfoil):
        """Test that close removes design directory when appropriate"""
        case = Case_Direct_Design(seed_airfoil)
        case.initial_airfoil_design()
        design_dir = case.design_dir_abs
        
        case.set_remove_designs_on_close(True)  # Should remove with only 1 design
        case.close()
        
        # Directory should be removed
        assert not os.path.isdir(design_dir)

    def test_close_preserves_design_dir(self, seed_airfoil):
        """Test that close preserves design directory with multiple designs"""
        case = Case_Direct_Design(seed_airfoil)
        initial = case.initial_airfoil_design()
        case.add_design(initial)  # Add second design
        design_dir = case.design_dir_abs
        
        case.set_remove_designs_on_close(False)
        case.close()
        
        # Directory should still exist
        assert os.path.isdir(design_dir)
        
        # Cleanup
        shutil.rmtree(design_dir, ignore_errors=True)

    def test_static_remove_design_dir(self, temp_dir, seed_airfoil):
        """Test static method to remove design directory"""
        case = Case_Direct_Design(seed_airfoil)
        case.initial_airfoil_design()
        
        pathFileName = seed_airfoil.pathFileName_abs
        design_dir = case.design_dir_abs
        
        assert os.path.isdir(design_dir)
        
        Case_Direct_Design.remove_design_dir(pathFileName)
        
        assert not os.path.isdir(design_dir)

    def test_read_existing_designs(self, seed_airfoil, temp_dir):
        """Test reading existing designs from directory"""
        # Create case and add designs
        case1 = Case_Direct_Design(seed_airfoil)
        initial = case1.initial_airfoil_design()
        case1.add_design(initial)
        case1.add_design(initial)
        
        design_count = len(case1.airfoil_designs)
        case1._remove_designs_on_close = False
        case1.close()
        
        # Create new case - should read existing designs
        case2 = Case_Direct_Design(seed_airfoil)
        
        assert len(case2.airfoil_designs) == design_count
        
        # Cleanup
        shutil.rmtree(case2.design_dir_abs, ignore_errors=True)