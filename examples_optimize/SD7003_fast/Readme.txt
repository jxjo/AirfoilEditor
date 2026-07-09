An easy going example to get a first impression of airfoil optimization. 

Optimization Task: 

The low reynolds airfoil SD7003 is adapted to little higher Reynolds number at 400,000.
Optimization target is to minimize drag at lower cd - while maintaining a good glide ration at cl = 0.7. 

The optimized airfoil should have 8% thickness.

Shape_functions 'bezier' with just 5 control points on top and bot side.

This results in a total of just 9 design variables leading to a fast convergence towards the 
final airfoil. 

As there is no danger of geometry artefacts only a few operating points are needed to achieve good results.

Run the example: 

Windows: Double click 'make.bat' 
Linux: 	 Type 'bash make.sh' (xopfoil2 must be in the search path)

Enjoy!





