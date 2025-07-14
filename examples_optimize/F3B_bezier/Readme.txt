Generate F3B/F3F airfoil for medium conditions. 

Optimization Task: 

Based on a seed airfoil which is already quite close to the desired airfoil,
fine tune the polar at RE 400.000 for 
- minimum drag at around cl=0.15,
- a good glide Ratio
- and good max lift capabilities 

Thickness of the airfoil is target to ensure a minimum height of the wing section. 

Bezier curves are used as shape functions. Only 5 control points are needed per side. 
The bottom side has a curve reversal which will lead to a rear-loaded airfoil.

 
Run the example by: 

-> Double click 'make.bat' to start the optimizer 
-> Look at the resulting Bezier curves with the Airfoil Editor

Enjoy!





