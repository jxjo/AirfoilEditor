![AirfoilEditor](../images/AirfoilEditor_logo.png "AirfoilEditor")

# About AirfoilEditor 5.0

The first polar appeared on screen - and "How cool is that!" just slipped out of me. That was the moment the NeuralFoil integration finally came together, and weeks of detail work later, the excitement is still there.

The AirfoilEditor already generated new polars automatically in the background whenever an airfoil was modified or a new airfoil was displayed. With NeuralFoil, however, this turns into a completely new user experience when it comes to the interplay of airfoil geometry and aerodynamic behaviour.

In version 5.0 almost everything revolves around airfoil polars. Besides calculating a polar with XFOIL, there is now a second way to determine the polar of an airfoil: NeuralFoil.

NeuralFoil is not a replacement for XFOIL. XFOIL remains the proven reference for the detailed calculation. NeuralFoil complements it where speed makes the difference: when exploring, comparing and modifying airfoils.

Two new concepts are introduced for this:

* **CST-Kulfan** describes an airfoil with a few, easily shapeable parameters.
* **NeuralFoil** predicts the polar of an airfoil described in CST-Kulfan form.

Let's have a closer look at both concepts before moving on to the practical application.


## CST-Kulfan Airfoil Parameterization

At first, CST may sound like just another file format. Behind it, however, is a very practical description of an airfoil contour. CST stands for *Class-Shape Transformation*. The class function provides the typical appearance of an airfoil with a rounded leading edge and a sharp trailing edge. The actual contour is created by a shape function whose weights define the upper and lower surface.

In simplified form, the contour can be written as: $y(x) = C(x) \cdot S(x) + y_{TE}(x)$.

The class function $C(x)$ provides the basic airfoil characteristic, $S(x)$ is formed by the shape weights, and the last term accounts for the trailing edge thickness if needed. With just a few weights, a smooth and well controllable airfoil shape can be described.

For NeuralFoil, eight shape weights are defined per side. Each weight determines the contribution of one Bernstein polynomial to the overall shape.

The advantages of CST-Kulfan based airfoils are:

1. The airfoil contour is inherently smooth and "well flowing". The underlying basis functions do not produce hard kinks.

2. Changes to individual weights can be attributed quite well to certain areas of the airfoil. Although the mathematical basis is global, this allows airfoil variants to be created in a targeted way. It makes CST particularly pleasant for prototyping, first optimizations and fine tuning.

However, the CST-Kulfan parameterization also has a fundamental limitation:

Modern airfoils often have a pronounced, tightly curved leading edge region with an asymmetric curvature distribution on the upper and lower surface. The class function fixes the behaviour at the leading edge. The additional `le_weight` - and also more shape weights - can therefore only represent this camber-induced asymmetry to a limited extent.

As a result, the CST contour occasionally ends up slightly rounder at LE. Trying to compensate for this difference with the shape weights alone may cost the desired C2 continuity of the curvature. Depending on the source airfoil, this influences the polar in the upper cl range and the predicted stall point.

CST, Bezier and B-Spline based airfoils are related: all of them describe the airfoil contour with a few parameters instead of a long list of coordinate points. They do, however, have different strengths and areas of use:

- CST-Kulfan: prototyping, first optimization, NeuralFoil
- Bezier: final optimization
- B-Spline: transition to CAD

In the AirfoilEditor, a CST-based airfoil can easily be created from an existing airfoil and saved and loaded as a new airfoil with the file extension `.cst`. The contour can be modified playfully by dragging the weight values.

![CST](../images/cst.png "CST based airfoil")

Besides this explicit CST conversion, there is also an implicit conversion in the background: whenever a NeuralFoil polar is needed for an airfoil, a temporary CST version of that airfoil is created.

Now that the airfoil is prepared in CST-Kulfan form, we can turn to the actual question:


## What is NeuralFoil?

![NeuralFoil](../images/NeuralFoil_logo_small.png "NeuralFoil")

[NeuralFoil](https://github.com/peterdsharpe/NeuralFoil) is a brilliantly developed, trained neural network by Peter Sharpe for predicting airfoil polars.
The network was trained with thousands of airfoils and nearly eight million XFOIL runs on a high performance computer. From these examples it learned how airfoil geometry, Reynolds number, Ncrit and further boundary conditions relate to the resulting polar.

An exciting and important aspect: no full XFOIL calculation is performed for a new polar. Instead, the neural network has learned from the training data to predict the results of an XFOIL run for an airfoil and the respective boundary conditions very quickly. XFOIL, now roughly 40 years old, still remains an important reference for 2D polar generation.

The NeuralFoil logo illustrates this approach nicely: from the yellow "geometry" inputs, the network produces a prediction of the blue "polar".

To determine a polar for an airfoil, the neural network receives the geometry in CST-Kulfan form together with boundary conditions such as Reynolds number, Ncrit, forced transition points and angle of attack. It returns, among others, lift cl, drag cd, moment cm and the laminar-turbulent transition points.

In contrast to XFOIL, a typical polar is available within a few milliseconds. This makes NeuralFoil particularly helpful for questions like:

* What happens if the thickness high point moves slightly aft?
* How does a small camber change affect drag at my Reynolds number?
* Is this airfoil variant worth a closer look at all, before I run a detailed calculation?

You don't wait for the answer - it is already there while you are still shaping the geometry.

### The NeuralFoil Models

NeuralFoil comes with eight models of different size - from `xxsmall` to `xxxlarge`. They differ in the number and width of their layers, and therefore in how finely the relationships from the training data are represented.

The model size can be selected in the polar definition. It is a trade-off between computing time and accuracy:

- The small models produce a complete polar in about 2 ms, the largest ones need around 15 ms. Both are very fast compared to XFOIL.
- Accuracy relative to an XFOIL calculation increases noticeably with model size. For drag, the typical deviation is in the range of a few percent for the small models, and only about two percent for the large ones.

In the AirfoilEditor, `xlarge` is preset. This model offers good accuracy for daily work without making polar generation noticeably slower.

NeuralFoil delivers very fast and often remarkably good predictions. Still, as with any data-based model: its statements are most reliable within the range the model knows from its training data. The AirfoilEditor therefore takes the prediction confidence supplied by NeuralFoil into account and hides operating points with insufficient confidence. Especially near cl_max or with unusual geometries, a comparison with an XFOIL polar remains worthwhile. NeuralFoil is a great companion for the design process, but it does not replace a critical assessment of the results.

### Limitations Compared to the XFOIL Calculation

Compared to an XFOIL polar there are some limitations in the AirfoilEditor which result directly from the way the network was trained:

- No T2 polar: NeuralFoil provides T1 polars with fixed Reynolds number only. For a T2 polar with constant lift, XFOIL is still required.
- No Mach number: the prediction applies to incompressible flow, the Mach number is fixed at 0.0. Compressibility effects are therefore not taken into account.
- No display of separation bubbles in the xtr diagram: this visualization is based on the wall shear stress of the individual XFOIL panels. NeuralFoil does not provide this quantity.

In the polar definition, the corresponding fields are therefore inactive as soon as NeuralFoil is selected as 'polar driver'.


## NeuralFoil in Action

Using NeuralFoil starts quite unspectacularly: in the 'polar definition', **NeuralFoil** is selected as 'polar driver' instead of XFOIL.

With this selection, the live update of the polars already starts within the dialog. Just use the mouse wheel to change the Reynolds number or Ncrit, for example ...

![Demo NeuralFoil polar definition](../images/demo_neuralfoil_polar_def.webp "Demo NeuralFoil polar definition")

*Note: the first time you see this, you simply rub your eyes. Magic!*

With NeuralFoil, the interaction between an airfoil modification and the corresponding polar becomes a completely new experience. You almost get the feeling you could grab the polar and bend it into shape yourself.

In this example, thickness and thickness high point of an airfoil are modified interactively.

![Demo NeuralFoil modification](../images/demo_neuralfoil_mod_airfoil.webp "Demo NeuralFoil modification")

It is helpful to define a second polar with identical settings but with XFOIL as driver alongside the NeuralFoil polar. At the end of an interactive modification, the XFOIL polar is then calculated automatically, so the current comparison of both methods is always at hand.

NeuralFoil is perfect for creating a first airfoil design or for quick comparisons between different airfoils at various Reynolds numbers or Ncrit values.

Fine tuning is then done as before, based on the XFOIL polar.


## Further Improvements in 5.0

Besides the central extensions around NeuralFoil, numerous smaller improvements and fixes were implemented in this version - many of them "behind the scenes".

One feature is remarkable from a user's point of view: the geometry of a flapped airfoil is now calculated within the AirfoilEditor itself, instead of calling the corresponding XFOIL routine. This removes the dependency on the separate Worker application for this task - and setting a flap feels noticeably smoother.

*Tip: when setting a flap, also display a NeuralFoil polar - this way the effect of the flap deflection can be followed directly.*


## Acknowledgements

Special thanks go to [Peter Sharpe](https://github.com/peterdsharpe) for NeuralFoil. In my view the project is a milestone in interactive airfoil analysis - and the fact that he makes it openly and freely available is what made the integration into the AirfoilEditor possible in the first place.


## Installation

At the time of writing, version 5.0 is available as a beta. The final version will be released once the hopefully numerous feedback items have been incorporated.

For Windows, an installer is available on the [release page of the AirfoilEditor](https://github.com/jxjo/AirfoilEditor/releases).

On Linux and macOS the beta version can be installed locally as a clone or copy. See the [Installation](https://github.com/jxjo/AirfoilEditor#installation) section in the README.

I am curious to see whether that first excitement holds up in everyday design work. On screen, airfoil and polar have certainly moved a lot closer together.

Enjoy 5.0 🚀

Jochen
