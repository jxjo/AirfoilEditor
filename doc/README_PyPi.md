![AE](https://github.com/jxjo/AirfoilEditor/blob/main/images/AirfoilEditor_logo.png?raw=true)

### Version 4.2.4

---

The **AirfoilEditor** serves as a fast airfoil viewer and an advanced geometry editor including Xoptfoil2-based optimization. The App provides three operating modes:

#### View
* Browse and view airfoils in subdirectories
* Analyse curvature of airfoil surface
* Show polars generated using XFOIL

#### Modify
* Repanel and normalize airfoils
* Adjust thickness, camber, high points, and trailing edge gap
* Blend two airfoils
* Set flap
* Generate airfoil replicas using Bezier curves.

#### Optimize
* User Interface of [Xoptfoil2](https://github.com/jxjo/Xoptfoil2)
* Graphical definition of polar based objectives
* View results while optimizing


The app was initially developed to address artefacts found in other tools like Xflr5 when using xfoil geometry routines. The aim has been an intuitive, user-friendly experience that encourages exploration.

The app, developed in Python with the Qt UI framework, runs on Windows, Linux, and MacOS. 
Linux and MacOS users are required to compile Xoptfoil2 (airfoil optimization) and Worker (polar generation) from the [Xoptfoil2](https://github.com/jxjo/Xoptfoil2) project.

Find more info about the **AirfoilEditor** on [Github](https://github.com/jxjo/AirfoilEditor).

---

Find Release Information in [CHANGELOG](https://github.com/jxjo/AirfoilEditor/blob/main/CHANGELOG.md).
