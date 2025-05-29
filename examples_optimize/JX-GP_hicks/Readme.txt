
Generate F3B/F3F airfoil for medium conditions. 


Optimization Task: 

The use case is already close to a final state. All operating points are defined by targets 
to fine tune the polar at Re 400000. 

Special care is to high cl values and a high cl-max. 

Thickness of the airfoil is tagret to ensure a minimum height. 
Camber target is set to have a constant camber of the other airfoils of the wing strak. 

Hicks-Henne bump functions are taken as shape functions. Only 3 for top and 4 for bottom side are needed. 
The bottom side has a curve reversal which will lead to a rear-loaded airfoil.

This task is exactly the same as the exmaple with bezier curves.
Compare the results of both optimizations ...


Remarks:

The defined operating point targets are already close to or at the aerodynamic limits.
So improvement at a certian operating point can only be achieved by reducing the target
at other operating points.

 
Run the example by: 

-> Double click 'make.bat' to start the optimizer 

-> Look at the resulting Hicks-Henne functions with the Airfoil Editor

Enjoy!





