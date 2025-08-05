
Generate F3F airfoil for fast conditions. 


Optimization Task: 

Create a fast airfoil with minimum drag at low cl range 0.3 - 0.0.
Try to achieve an acceptable glide ratio at higher cl, 
whereas flaps are mandatory.
Special care is to high cl values and a high cl-max. 
 
Thickness of the airfoil is target to ensure a minimum height. 

Hicks-Henne bump functions are taken as shape functions. 
Here we use 4 on top side and 4 on bottom side, which results 
in 24 design variables which have to optimized. 

Remarks:

This example is somehow an edge case on the number of design variables.
The optimization will take some time. As the particle swarm is random based,
it may occur, that a run doesn't find the best solution.

Run the example: 

Windows: Double click 'make.bat' 
Linux: 	 Type 'bash make.sh' (xopfoil2 must be in the search path)

-> Look at the resulting Hicks-Henne functions with the Airfoil Editor






