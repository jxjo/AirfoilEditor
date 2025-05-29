
Generate F3B/F3F airfoil for medium conditions. 


Optimization Task: 

The use case is already close to a final state. All operating points are defined by targets 
to fine tune the polar at Re 400000. 

Special care is to high cl values and a high cl-max. 

Thickness of the airfoil is tagret to ensure a minimum height. 
Camber target is set to have a constant camber of the other airfoils of the wing strak. 

Bezier curves are taken as shape functions. Only 5 control points are needed per side. 
The bottom side has a curve reversal which will lead to a rear-loaded airfoil.


Remarks:

The defined operating point targets are already close to or at the aerodynamic limits.
So improvement at a certian operating point can only be achieved by reducing the target
at other operating points.

 
Run the example by: 

-> Double click 'make.bat' to start the optimizer 

-> Look at the resulting Bezier curves with the Airfoil Editor

Enjoy!





