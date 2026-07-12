![AE](https://github.com/jxjo/AirfoilEditor/blob/main/images/AirfoilEditor_logo.png?raw=true)

### Version 4.3.0

---

The **AirfoilEditor** is a fast airfoil viewer, analyzer, and advanced geometry editor with integrated Xoptfoil2-based optimization. The app provides three operating modes:

#### View
* Browse and view airfoils in subdirectories
* Analyze curvature of airfoil surface
* Show polars generated using XFOIL
* Export airfoils to DXF format

#### Modify
* Repanel and normalize airfoils
* Adjust thickness, camber, high points, and trailing edge gap
* Blend two airfoils
* Set flap
* Generate airfoil replicas using Bezier or B-Spline curves

#### Optimize
* User Interface of [Xoptfoil2](https://github.com/jxjo/Xoptfoil2)
* Graphical definition of polar-based objectives
* View results while optimizing


Install with `pip install airfoileditor`, then run `airfoileditor`.

The app, developed in Python with the Qt UI framework, runs on Windows, Linux, and MacOS. 
On Linux and macOS, View and Modify mode work after package installation. Polars and Optimize mode additionally require compiled `worker` and `xoptfoil2` binaries from the [Xoptfoil2](https://github.com/jxjo/Xoptfoil2) project.

Find more information about the **AirfoilEditor** on [GitHub](https://github.com/jxjo/AirfoilEditor).

---

Find release information in [CHANGELOG](https://github.com/jxjo/AirfoilEditor/blob/main/CHANGELOG.md).
