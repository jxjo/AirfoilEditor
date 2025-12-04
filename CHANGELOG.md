# Changelog

All notable changes to this project will be documented in this file.

## 4.2.0

### Added

- Individual settings for an airfoil like polars and reference airfoils (thanks to Christian!)
- Change polar diagram variables directly in the diagram
- Maximize / minimize lower data panel
- Revised Match Bezier UI
- Now using OS dependent user data directory for settings and examples 

#### More ...
* A lot of minor improvements
* Extensive refactorings 
* Bug fixes


## 4.1.1
This is a maintenance release with some smaller features and a bunch of fixes

### Added
- LE radius - set and visualize blending range
- TE gap- set and visualize blending range (thanks to Heinz!)
- Repaneling improved, show LE panel angle 
- Optimization - improved support for flap angle optimization (thanks to Manuel!)

#### More ...
* Minor improvements and helper functions
* Bug fixes and refactorings 



## 4.1.0

This is a functional release extending version 4.0

### Added
- Show laminar separation bubbles 
  * Based on Xfoil panel negative shear stress 
  * Visualized in in xtrt/xtrb polar 

- Scale reference airfoils and their polars 
  * Used to design airfoils along the wing sections 
  * Reynolds number of polars based on scale value 

#### More ...
* Minor improvements and helper functions
* Bug fixes and refactorings 


## 4.0

This major release features ...

### Added

- Setting Flap
  * Create 'flapped' airfoil as a design in Modify mode
  * Alternatively use 'flapped' polars for ad hoc analysis and comparisons

- Airfoil Optimization 
  * Uses [Xoptfoil2 ](https://github.com/jxjo/Xoptfoil2) as optimization engine 
  * Setup optimization case with graphical operating point definition
  * Run and analyze an optimization case
  * Linux: `worker`and `xoptfoil2`have to be installed separately 

- Simplified installation
  * Now available as Python package: `pip install airfoileditor`
  * Windows: Ready-built app as attached asset

#### More ...
* Minor improvements and helper functions
* Bug fixes and refactorings 
