
A little easy going example to get a first impression of the power of airfoil optimization. 


Optimization Task: 

The low reynolds airfoil SD7003 is adapted to little higher Reynolds number at 400,000.
Optimization target is to minimize drag at lower cd - while maintaining glide ration at cl = 0.7. 

The optimized airfoil should have 8% thickness.

Here shape_functions='camb-thick' will be used, where the airfoil is modified only by changing
camber, thickness, their highpoints and leading edge radius. This leads to a very fast convergence
towards the final airfoil. Only a few operting points are needed to achieve good results.


Run the example by: 

-> Double click 'make.bat' to start the optimizer 

Enjoy!





