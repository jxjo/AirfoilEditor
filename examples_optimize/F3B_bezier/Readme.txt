Generate F3B/F3F airfoil for medium conditions which is quite similar to 
JX-GT3-100 - https://github.com/jxjo/Airfoils/tree/main/JX-GT
 

Optimization Task: 

Based on a dummy seed airfoil optimize the polar at RE 500.000 for 
- low drag at around cl=0.15,
- a good glide Ratio with maximum at about cl=0.6
- good max lift capabilities 

Thickness of the airfoil is a target at 7.7% to ensure a minimum height of the wing section. 

Bezier curves are used as shape functions. Just 6 control points are needed per side. 
The bottom side has a curve reversal which will lead to a rear-loaded airfoil.

Run the example: 

Windows: Double click 'make.bat' 
Linux: 	 Type 'bash make.sh' (xopfoil2 must be in the search path)

-> Look at the resulting Bezier curves with the Airfoil Editor





