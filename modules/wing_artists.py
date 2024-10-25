#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  

The "Artists" to plot a wing object on a matplotlib axes

"""
import numpy as np

from common_utils import *
from artist     import *
from wing_model import Wing, Planform, WingSection, Planform_DXF, Flap, Planform_Bezier, Planform_Paneled
from airfoil    import Airfoil

cl_planform         = 'whitesmoke'
cl_quarter          = 'lightgrey'
cl_pureElliptical   = 'dodgerblue'
cl_dxf              = 'tomato'
cl_wingSection_fix  = 'deeppink'
cl_wingSection_flex = 'mediumvioletred'
cl_paneled          = 'steelblue'



# -------- concrete sub classes ------------------------



class CurrentSection_Artist (Artist):
    """Plot a Marker Symbol at the current (selected) wing sections.
       May plot in real coordinates and normed

    Keyword Arguments:
        norm --   True: plot in a normed coordinate system
    """    
    def __init__ (self, axes, modelFn, **kwargs):
        super().__init__ (axes, modelFn, **kwargs)

        # limits for movement of section 
        self._limits_pos   = None
        self._limits_chord = None

        # show mouse helper / allow drag of points 
        self.section_line_artist = None
        self.chord_marker_artist = None
        self.chord_marker_anno   = None
        self.pos_marker_artist   = None
        self.pos_marker_anno     = None

        self.outline_artist      = None

        self._userInfo_shown     = False


    @property   
    def wing (self) -> Wing:
        return self.model

    @property
    def wingSections (self): 
        return self.wing.wingSections

    @property 
    def curSection (self) -> WingSection: 
        # find current section based on name 
        sectionName = self._curLineLabel
        sec : WingSection
        for sec in self.wingSections:
            if sec.name() == sectionName:
                return sec
        return None


    def set_current (self, aLineLabel, figureUpdate=False):
        """ tries to set a Marker to a line with Label aLabel 
        """
        if (not aLineLabel is None and aLineLabel != self._curLineLabel):    # only when changed do something
            self._curLineLabel = aLineLabel
            if self.show and figureUpdate:                       # view is switched on by user? 
                self.plot (figureUpdate=figureUpdate)


    def _plot (self): 
        """ do plot of wing sections in the prepared axes   
        """ 

        if self.curSection is None: return

        # coordinates of line and limits for movement by mouse 
        if self._norm: 
            y_sec, x_sec =  self.curSection.norm_line()
            self._limits_pos = self.curSection.limits_norm_yPos ()
        else:
            y_sec, x_sec =  self.curSection.line()
            self._limits_pos = self.curSection.limits_yPos ()

        # plot animated planform outline for trapezoid planform when changing section
        if self.curSection.hasFixPosChord():
            if self._norm: 
                y, x = self.wing.planform.norm_chord_line () 
                self._limits_chord = self.curSection.limits_normChord ()
            else: 
                y, x = self.wing.planform.linesPolygon()
                self._limits_chord = self.curSection.limits_chord ()
            p = self.ax.plot(y, x, 'None', color=cl_planform, animated=True)
            self.outline_artist = self._add(p) 


        # plot current section as a thick line 
        p = self.ax.plot(y_sec, x_sec, '-', color=cl_wingSection_fix,  linewidth=2.5)
        self._add (p)              # remind plot to delete 

        if self.mouseActive and not self.curSection.isRootOrTip:        # don't move root or tip

            self.show_mouseHelper (self.curSection, y_sec, x_sec)
            self.show_mouseUserInfo ()

            # make section points draggable - install callback when move is finished
            self._dragManagers.append (DragManager (self.ax, self.chord_marker_artist, 
                                        callback_draw_animated = self.draw_animated_byChord,
                                        callback_on_moved=self._moveCallback))
            self._dragManagers.append (DragManager (self.ax, self.pos_marker_artist, 
                                        callback_draw_animated = self.draw_animated_byPos,
                                        callback_on_moved=self._moveCallback))

            # connect to draw event for initial plot of the animated artists all together
            self._connectDrawEvent()


    def show_mouseUserInfo (self):
        # show info for section select #

        if self.mouseActive and not self._userInfo_shown:      
            text = 'click to on section to select, move at helper points'
            p = self.ax.text (0.50, 0.05, text, color=cl_userHint, fontsize = 'small',
                              zorder=9, transform=self.ax.transAxes, 
                              horizontalalignment='center', verticalalignment='bottom')
            self._add(p)
            self._userInfo_shown = True 



    def show_mouseHelper (self, section, y_sec, x_sec): 
        """ show the helper points for section movement"""

        # ! animated=True must be set for all artists moving around !

        # highlight section
        p = self.ax.plot (y_sec, x_sec, '--', linewidth=0.5, color= cl_wingSection_fix, animated=True) 
        
        self.section_line_artist = self._add(p) 

        # upper marker at le - move "chord"
        p = self.ax.plot(y_sec [0], x_sec[0],  markersize=6, clip_on=False, 
                         marker='o', color = cl_userHint, animated=True, pickradius=10)
        
        self.chord_marker_artist= self._add(p) 

        if self.curSection.hasFixPosChord():
            text = 'change chord'
        else: 
            text = 'move by chord'

        p = self.ax.annotate(text, color=cl_userHint, backgroundcolor= cl_background,
                        xy=(y_sec [0], x_sec[0]), ha='left', va= 'top', fontsize = 'small',
                        xytext=(8, -5), textcoords='offset points', animated=True)
        self._add(p)
        self.chord_marker_anno = p 

        # lower marker at te - move "pos"
        x = y_sec[1]
        if self.norm:
            y = 0.015
            xytext=(8, 0)
            va = 'bottom'
            ha = 'left'
        else:
            y = x_sec[1]
            xytext= (8, -12)
            va= 'top'
            ha='left'

        p = self.ax.plot(x, y,  markersize=6, clip_on=False, 
                         marker='o', color = cl_userHint, 
                         animated=True, pickradius=10)   
        self.pos_marker_artist = self._add(p)

        if self.curSection.hasFixPosChord():
            text = 'change pos'
        else: 
            text = 'move by pos'

        p = self.ax.annotate(text, color=cl_userHint, backgroundcolor= cl_background,
                        xy=(x, y), ha=ha, va= va, fontsize = 'small', annotation_clip=False,
                        xytext=xytext, textcoords='offset points', animated=True)
        self.pos_marker_anno = self._add(p)


    def draw_animated_byPos(self, **_ ): 
        """ call back when point for new position was moved"""
        # get new coordinates (when dragged) 
        xm,ym = self.pos_marker_artist.get_xydata()[0]

        # is new pos between left and right section? 
        new_yPos = xm
        new_yPos = max (self._limits_pos[0], new_yPos)
        new_yPos = min (self._limits_pos[1], new_yPos)
        # new_yPos = round(new_yPos,1)

        # update new section pos
        if self.norm: 
            self.curSection.set_norm_yPos (new_yPos)
            y_sec, x_sec =  self.curSection.norm_line()
        else:
            self.curSection.set_yPos (new_yPos)
            y_sec, x_sec =  self.curSection.line()

        # draw new section line 
        self.section_line_artist.set_xdata(y_sec)
        self.section_line_artist.set_ydata(x_sec)

        # draw marker - keep marker on trailing 
        if self.norm: 
            x, y =  y_sec[1], 0.022
        else:
            x, y =  y_sec[1],x_sec[1]
        self.pos_marker_artist.set_xdata(x)
        self.pos_marker_artist.set_ydata(y)

        self.pos_marker_anno.xy =  (x,y)
        if self.norm: 
            text = "%.3f" % x
        else: 
            text = "%.1f" % x
        self.pos_marker_anno.set ( text=text)

        # plot animated planform outline for trapezoid planform when changing section
        if self.curSection.hasFixPosChord():
            if self._norm: 
                y, x = self.wing.planform.norm_chord_line () 
            else: 
                y, x = self.wing.planform.linesPolygon()
            self.outline_artist.set_xdata(y)
            self.outline_artist.set_ydata(x)
            self.outline_artist.set_linestyle(':')

        self.draw_animated_artists()


    def draw_animated_byChord(self, **_): 
        """ call back when point for new chord length was moved"""

        # get new coordinates (when dragged) 
        xm,ym = self.chord_marker_artist.get_xydata()[0]

        if self.curSection.hasFixPosChord():

            # trapezoid planform: "by Chord" changes diredctly the chord length of this section
            if self.norm: 
                new_norm_chord = ym
                new_norm_chord = max (self._limits_chord[0], new_norm_chord)
                new_norm_chord = min (self._limits_chord[1], new_norm_chord)

                self.curSection.set_norm_chord (new_norm_chord)
            else: 
                y_sec, x_sec =  self.curSection.line()
                new_chord = x_sec[1] - ym
                new_chord = max (self._limits_chord[0], new_chord)
                new_chord = min (self._limits_chord[1], new_chord)
                self.curSection.set_chord (new_chord)

            # plot animated planform outline for trapezoid planform when changing section
            if self._norm: 
                y, x = self.wing.planform.norm_chord_line () 
            else: 
                y, x = self.wing.planform.linesPolygon()
            self.outline_artist.set_xdata(y)
            self.outline_artist.set_ydata(x)
            self.outline_artist.set_linestyle(':')

        else:

            # normal planform -  "by Chord" moves the section to a new chord position 

            # is new pos between left and right section 
            new_yPos = xm
            new_yPos = max (self._limits_pos[0], new_yPos)
            new_yPos = min (self._limits_pos[1], new_yPos)

            # get chord at this position 
            if self.norm: 
                new_yPos_norm = new_yPos
            else:
                new_yPos_norm = new_yPos / self.wing.halfwingspan
            new_norm_chord = self.wing.planform.norm_chord_function(new_yPos_norm, fast=False) 
            # update new section pos
            self.curSection.set_norm_chord (new_norm_chord)


        # draw new section line 
        if self.norm: 
            y_sec, x_sec =  self.curSection.norm_line()
        else:
            y_sec, x_sec =  self.curSection.line()

        self.section_line_artist.set_xdata(y_sec)
        self.section_line_artist.set_ydata(x_sec)

        # draw marker - keep marker on leading edge 
        self.chord_marker_artist.set_xdata(y_sec[0])
        self.chord_marker_artist.set_ydata(x_sec[0])

        self.chord_marker_anno.xy =  (y_sec[0],x_sec[0])
        if self.norm: 
            self.chord_marker_anno.set ( text="%.3f" % self.curSection.norm_chord)
        else:
            self.chord_marker_anno.set ( text="%.1f" % self.curSection.chord)


        self.draw_animated_artists()

# ----------------------------------


class Planform_Artist (Artist):
    """Plot the outline of the wing planform.
    """

    def __init__ (self, axes, modelFn, planform=None, **kwargs):
        super().__init__ (axes, modelFn, **kwargs)

        # an alternative planform - not taken from Wing
        self._planform = planform

        self._halfwingspan_sav = None                   # keep original span for mouse modifications

        # show mouse helper / allow drag of points 
        self.p1_marker_artist = None
        self.p1_marker_anno = None
        self.p1_line_artist = None
        self.banana_line_artist = None 
        self.planform_line_artist = None 

        self.hinge_line_artist = None
        self.hinge_marker_artist = None
        self.hinge_marker_anno = None

        self.root_marker_artist = None
        self.root_marker_anno = None
        
        self.flap_marker_artist = None
        self.flap_marker_anno = None
        

    @property
    def planform (self) -> Planform:
        if self._planform is None:
            return self.model.planform
        else:
            return self._planform


    def _plot(self):
    
        self._halfwingspan_sav = self.planform.halfwingspan

        # planform outline 
        y, x = self.planform.linesPolygon()
        p = self.ax.plot(y, x,  '-', color=cl_planform, label= "Planform")  
        self._add (p)
        # planform outline for movement
        p = self.ax.plot(y, x,'None', color=cl_planform, animated=True)  
        self.planform_line_artist = self._add (p)

        p = self.ax.fill(y, x, linewidth=0.8, color=cl_planform, alpha=0.1)    
        self._add(p)

        # hinge line
        yh, hinge = self.planform.hingeLine()
        p = self.ax.plot(yh, hinge,   '-', linewidth=0.8, label="Hinge line", color='springgreen')
        self._add (p)
        # hinge line animated for movement
        p = self.ax.plot(yh, hinge,'None', color='springgreen', animated=True)
        self.hinge_line_artist = self._add (p) 

        if self.mouseActive: 

            # plot root chord  helper
            self.show_mouseHelper_root(self.planform)
            bounds_y = (self.planform.rootchord/10, self.planform.rootchord * 4)
            self._dragManagers.append (DragManager (self.ax, self.root_marker_artist, 
                                        bounds=[(0,0), bounds_y], 
                                        callback_draw_animated = self.draw_animated_root,
                                        callback_on_moved=self._moveCallback))

            # plot root flap depth helper
            self.show_mouseHelper_flap(self.planform)
            bounds_y = (self.planform.rootchord/3, self.planform.rootchord * 0.95)
            self._dragManagers.append (DragManager (self.ax, self.flap_marker_artist, 
                                        bounds=[(0,0), bounds_y], 
                                        callback_draw_animated = self.draw_animated_flap,
                                        callback_on_moved=self._moveCallback))

            # plot hinge line helper
            self.show_mouseHelper_hinge(self.planform)
            self._dragManagers.append (DragManager (self.ax, self.hinge_marker_artist, 
                                        callback_draw_animated = self.draw_animated_hinge,
                                        callback_on_moved=self._moveCallback))

            if self.planform.planformType == "Bezier": 

                # plot banana line with mouse helper 
                self.show_mouseHelper_banana (self.planform)
                # make p1,2 of Bezier draggable - install callback when move is finished
                bounds_x = ( 0.1 * self.planform.halfwingspan, 0.9 * self.planform.halfwingspan)
                bounds_y = (-0.2 * self.planform.rootchord,    0.2 * self.planform.rootchord)
                self._dragManagers.append (DragManager (self.ax, self.p1_marker_artist, 
                                            bounds=[bounds_x, bounds_y], 
                                            typeTag = 'banana', 
                                            callback_draw_animated = self.draw_animated_banana,
                                            callback_on_moved=self._moveCallback))
                
        # connect to draw event for initial plot of the animated artists all together
        self._connectDrawEvent()

        # set ticks 
        self._add_xticks ([0, self.planform.halfwingspan])
        self._add_yticks ([0, self.planform.rootchord])


    def show_mouseHelper_banana (self, planform: Planform_Bezier): 
        """ show the helper points and lines for bezier curve definition """

        # ! animated=True must be set for all artists moving around !
        x, y = planform.banana_line()
        p = self.ax.plot (x,y , '--', linewidth=0.5, color= cl_userHint, animated=True) 
        self.banana_line_artist = self._add(p) 

        # drag marker 
        x = planform.banana_p1y * planform.halfwingspan
        y = planform.banana_p1x * planform.rootchord
        p = self.ax.plot (x, y, marker='o', color=cl_userHint, markersize=6, animated=True )
        self.p1_marker_artist = self._add(p) 

        p = self.ax.annotate('banana', color=cl_userHint, backgroundcolor= cl_background, fontsize = 'small',
                            xy=(x, y), ha='left', va= 'bottom',
                            xytext=(7, 3), textcoords='offset points', animated=True)
        self.p1_marker_anno = self._add(p) 


    def show_mouseHelper_root (self, planform: Planform_Bezier): 
        """ show the helpe point  for root chord definition """

        # drag marker 
        x = 0
        y = planform.rootchord
        p = self.ax.plot (x, y, marker='o', color=cl_userHint, markersize=6, animated=True )
        self.root_marker_artist = self._add(p) 

        # ... and its annotation 
        p = self.ax.annotate('chord', color=cl_userHint, backgroundcolor= cl_background, fontsize = 'small',
                            xy=(x, y), ha='right', va= 'top', multialignment='left',
                            xytext=(-6, -3), textcoords='offset points', animated=True)
        self.root_marker_anno = self._add(p)


    def show_mouseHelper_flap (self, planform: Planform_Bezier): 
        """ show the helpe point for root flap depth definition """

        # drag marker 
        x = 0
        y = planform.rootchord * (1 - planform.flapDepthRoot / 100.0)
        p = self.ax.plot (x, y, marker='o', color=cl_userHint, markersize=6, animated=True )
        self.flap_marker_artist = self._add(p) 

        # ... and its annotation 
        p = self.ax.annotate('flap', color=cl_userHint, backgroundcolor= cl_background, fontsize = 'small',
                            xy=(x, y), ha='right', va= 'top', multialignment='left',
                            xytext=(-6, -3), textcoords='offset points', animated=True)
        self.flap_marker_anno = self._add(p) 


    def show_mouseHelper_hinge (self, planform: Planform_Bezier): 
        """ show the helper points for hinge line modification """

        # drag marker 
        xl, yl = planform.hingeLine()
        x = xl[1]
        y = yl[1]
        p = self.ax.plot (x, y, marker='o', color=cl_userHint, markersize=6, animated=True )
        self.hinge_marker_artist = self._add(p) 

        p = self.ax.annotate('hinge\nspan', color=cl_userHint, backgroundcolor= cl_background, fontsize = 'small',
                            xy=(x, y), ha='right', va= 'top', multialignment='left',
                            xytext=(-4, -6), textcoords='offset points', animated=True)
        self.hinge_marker_anno = self._add(p) 

    #-----------------

    def draw_animated_root(self, **_): 
        """ call back when root point was moved"""
        # draw marker and get new coordinates (when dragged) 
        self.ax.draw_artist (self.root_marker_artist)
        x1,y1 = self.root_marker_artist.get_xydata()[0]

        # update planform rootchoord with y coordinate  
        self.planform.wing.set_rootchord (y1)  
        root_new = self.planform.rootchord
 
        # update planform outline  
        y, x = self.planform.linesPolygon()
        self.planform_line_artist.set_xdata(y)
        self.planform_line_artist.set_ydata(x)
        self.planform_line_artist.set_linestyle(':')

        # update annotation text   
        self.root_marker_anno.xy =  (x1,y1)
        self.root_marker_anno.set ( text="%.0fmm" % (root_new))

        self.draw_animated_artists()


    def draw_animated_flap(self, **_): 
        """ call back when flap marker was moved"""
        # draw marker and get new coordinates (when dragged) 
        x1,y1 = self.flap_marker_artist.get_xydata()[0]

        # update wing flap depth root with y coordinate  
        flapdepth_new = round (100 * (self.planform.rootchord - y1) / self.planform.rootchord, 1) 
        self.planform.wing.set_flapDepthRoot (flapdepth_new)  
 
        # update planform outline  
        y, x = self.planform.linesPolygon()
        self.planform_line_artist.set_xdata(y)
        self.planform_line_artist.set_ydata(x)
        self.planform_line_artist.set_linestyle(':')

        # update dotted hinge line   
        y, x = self.planform.hingeLine()
        self.hinge_line_artist.set_xdata(y)
        self.hinge_line_artist.set_ydata(x)
        self.hinge_line_artist.set_linestyle(':')

        # update annotation text   
        self.flap_marker_anno.xy =  (x1,y1)
        self.flap_marker_anno.set ( text="%.1f%%" % (flapdepth_new))

        self.draw_animated_artists()


    def draw_animated_hinge(self, **_): 
        """ call back when hinge point was moved"""
        # draw marker and get new coordinates (when dragged) 
        self.ax.draw_artist (self.hinge_marker_artist)
        x1,y1 = self.hinge_marker_artist.get_xydata()[0]

        # when span should be increased take square of delta span
        dx = x1 - self._halfwingspan_sav
        if dx > 0: dx = dx **2 / 10
        span_new = self._halfwingspan_sav + dx

        # update planform span with x coordinate  
        self.planform.wing.set_wingspan (span_new * 2)  
        span_new = self.planform.halfwingspan

        # update hinge angle
        xl, yl = self.planform.hingeLine()
        dx = xl[1] - xl[0]
        dy = y1    - yl[0]
        angle = np.arctan (dy/dx) * 180 / np.pi
        self.planform.wing.set_hingeAngle (angle)  
 
        # update planform outline  
        y, x = self.planform.linesPolygon()
        self.planform_line_artist.set_xdata(y)
        self.planform_line_artist.set_ydata(x)
        self.planform_line_artist.set_linestyle(':')

        # update dotted hinge line   
        y, x = self.planform.hingeLine()
        self.hinge_line_artist.set_xdata(y)
        self.hinge_line_artist.set_ydata(x)
        self.hinge_line_artist.set_linestyle(':')

        # update annotation text   
        self.hinge_marker_anno.xy =  (x1,y1)
        self.hinge_marker_anno.set ( text="hinge %.1f°\nhalf  %.0fmm" % (angle, span_new))

        self.draw_animated_artists()


    def draw_animated_banana(self, **_): 
        """ call back when bezier point 1 was moved"""

        # draw marker and get new coordinates (when dragged) 
        self.ax.draw_artist (self.p1_marker_artist)
        x1,y1 = self.p1_marker_artist.get_xydata()[0]

        # update planform banana - ! wing coordinate system
        norm_y1 = x1 / self.planform.halfwingspan
        norm_x1 = y1 / self.planform.rootchord

        self.planform : Planform_Bezier
        self.planform.set_banana_p1x (norm_x1)  
        self.planform.set_banana_p1y (norm_y1)  

        # because of animate=True the artist has to be provided with actual data...
        y, banana_x = self.planform.banana_line()
        self.banana_line_artist.set_xdata(y)
        self.banana_line_artist.set_ydata(banana_x)

        # update planform outline  
        y, x = self.planform.linesPolygon()
        self.planform_line_artist.set_xdata(y)
        self.planform_line_artist.set_ydata(x)
        self.planform_line_artist.set_linestyle(':')

        # update annotation text   
        self.p1_marker_anno.xy =  (x1,y1)
        self.p1_marker_anno.set ( text="height %.2f  pos %.2f" % (norm_x1, norm_y1))
        self.ax.draw_artist (self.p1_marker_anno)

        self.draw_animated_artists()


# ----------------------------------


class Wing_Artist (Artist):
    """Plot the outline of the wing planform.
    """

    def __init__ (self, axes, modelFn, planform=None, **kwargs):
        super().__init__ (axes, modelFn, **kwargs)

        self.set_showLegend (False)

    @property
    def wing (self) -> Wing:
        return self.model

    @property
    def planform (self) -> Planform:
        return self.model.planform


    def _plot(self):
    
        # planform outline 
        x, y = self.planform.linesPolygon()
        area, aspectRatio = self.planform.calc_area_AR (x,y)

        # hinge line
        yh, hinge = self.planform.hingeLine()

        # flaaps
        flaps = self.planform.wing.getFlaps()

        for mirror in [1, -1]:

            p = self.ax.plot(mirror * x, y,  '-', linewidth=0.8, color=cl_planform, label= "Planform")  
            self._add (p)
            p = self.ax.fill(mirror * x, y, linewidth=0, color=cl_planform, alpha=0.08)    
            self._add(p)

            flap : Flap
            for flap in flaps:   

                p = self.ax.plot(mirror * flap.y, flap.x, color = cl_planform, linewidth=0.5)
                self._add(p)

                p = self.ax.fill(mirror * flap.y, flap.x, color = cl_planform, linewidth=3, alpha=0.05)   # color from cycler 
                self._add(p)

            p = self.ax.plot(mirror * yh, hinge,   '-', linewidth=0.5, label="Hinge line", color='springgreen')
            self._add (p)

        # print data 
        self._print_title()
        self._print_wingData(area, aspectRatio)
        # airfoil names          
        section : WingSection
        for section in self.wing.wingSections:
            if not section.airfoil.isStrakAirfoil:
                self._print_airfoil_names (section)


        # set ticks 
        self._add_xticks ([-self.planform.halfwingspan, 0, self.planform.halfwingspan])
        self._add_yticks ([0, self.planform.rootchord])



    def _print_title (self):
        """ wing name as title"""

        yText = 0.90
        va = 'top'
        p = self.ax.text (0.045, yText, self.planform.wing.name, color=cl_labelGrid, fontsize = 'xx-large',
                          transform=self.ax.transAxes, horizontalalignment='left', verticalalignment=va)
        self._add (p)   


    def _print_wingData (self, area, aspectRatio):
        """ print wing data """
 
        xa = 0.088

        if self.wing.hingeAngle > 5: 
            ya= 0.7
        else: 
            ya = 0.08 

        self._add (print_text (self.ax,    'Wing span','right',(xa,ya),( 0,36), cl_textHeader, xycoords='axes fraction'))
        data = "%.0f mm" % (self.wing.halfwingspan * 2) 
        self._add (print_text (self.ax,           data,'left' ,(xa,ya),(10,36), cl_text, xycoords='axes fraction'))

        self._add (print_text (self.ax,    'Wing area','right',(xa,ya),( 0,24), cl_textHeader, xycoords='axes fraction'))
        data = "%.1f dm²" % (area * 2 / 10000)
        self._add (print_text (self.ax,           data,'left', (xa,ya),(10,24), cl_text, xycoords='axes fraction'))

        self._add (print_text (self.ax, 'Aspect ratio','right',(xa,ya),( 0,12), cl_textHeader, xycoords='axes fraction'))
        data = "%.1f" % (aspectRatio)
        self._add (print_text (self.ax,           data,'left', (xa,ya),(10,12), cl_text, xycoords='axes fraction'))

        self._add (print_text (self.ax,  'Hinge angle','right',(xa,ya),( 0, 0), cl_textHeader, xycoords='axes fraction'))
        data = "%.1f °" % (self.wing.hingeAngle)
        self._add (print_text (self.ax,           data,'left', (xa,ya),(10, 0), cl_text, xycoords='axes fraction'))



    def _print_airfoil_names (self, section: WingSection): 
        """ print airfoil name and nickname below the planform """

        y, le_to_te = section.line()

        marker_y = 0.04                         # in axis coordinates
        marker_x = y[0]                         # in data coordinates
        if section.airfoilNick():
            nickname = "'"+ section.airfoilNick() + "'" + "\n"
        else:
            nickname = ''

        text = nickname + section.airfoil.name

        p = self.ax.text (marker_x, marker_y, text, color=cl_textHeader, backgroundcolor= cl_background,
                          transform=self.ax.get_xaxis_transform(), fontsize='small',
                          horizontalalignment='left', verticalalignment='bottom',
                          rotation=90)
        self._add (p)   

      

# ----------------------------------


class ChordLines_Artist (Artist):
    """Plot the chordlines t/2 t/4 3t/4 of the wing planform and chord distribution.
    """
    @property
    def planform (self) -> Planform:
        return self.model.planform
    
    def _plot(self):

        if self._norm: 
            y, chord = self.planform.norm_chord_line ()
            quarterChord = chord/4
        else:
            y, leadingEdge, trailingEdge = self.planform.lines()
            quarterChord = leadingEdge + (trailingEdge - leadingEdge)/4

        p = self.ax.plot(y, quarterChord, '--', color= cl_quarter, linewidth=0.7, label="Chord lines")
        self._add (p)

        if self._norm: 
            halfChord = chord/2
        else:
            halfChord = leadingEdge + (trailingEdge - leadingEdge)/2
        p = self.ax.plot(y, halfChord, '--', color= cl_quarter, linewidth=0.7)
        self._add (p)

        if self._norm: 
            threeQuarterChord = chord * 3 / 4
        else:
            threeQuarterChord = leadingEdge + (trailingEdge - leadingEdge) * 3/4
        p = self.ax.plot(y, threeQuarterChord, '--', color= cl_quarter, linewidth=0.7)
        self._add (p)



class RefPlanform_Artist (Planform_Artist):
    """Plot the outline of the wing reference planform 'PureElliptical'
    """
    color = cl_pureElliptical 

    @property
    def refPlanform (self) -> Planform :
        return self.model.refPlanform

    def _plot(self):
        y, leadingEdge, trailingEdge = self.refPlanform.lines()
        p = self.ax.plot(y, leadingEdge,  color=self.color, label=self.refPlanform.planformType)
        self._add (p)              # remind plot to delete 
        p = self.ax.plot(y, trailingEdge, color=self.color)
        self._add (p)              # remind plot to delete 

 


class RefPlanform_DXF_Artist (Planform_Artist):
    """Plot the outline of the dxf reference planform 
    """

    def __init__ (self, axes, modelFn, showDetail=False, **kwargs):
        super().__init__ (axes, modelFn, **kwargs)

        self._showDetail = showDetail               # show TE, LE, hinge seperate 

        if showDetail: 
            self._set_colorcycle (8)         

    @property
    def refPlanform_DXF (self) -> Planform_DXF :
        if self._planform is None:
            return self.model.refPlanform_DXF
        else:
            return self._planform

    def _nextColor(self):
        # overloaded to switch between 'details' and dxf in sinle color  

        if self._showDetail: 
            return self._cycle_color ()
        else: 
            return cl_dxf
              

    def _plot(self):

        # is there a DXF planform? 
        if (self.refPlanform_DXF): 
            y, leadingEdge, trailingEdge = self.refPlanform_DXF.lines ()
            if len(y) > 0: 

                # leading edge 
                color = self._nextColor()
                if self._showDetail:    label='Leading edge'
                else:                   label= self.refPlanform_DXF.dxf_filename() 
                p = self.ax.plot(y, leadingEdge, label=label, color=color)
                self._add (p)  
                            
                # trailing edge 
                color = self._nextColor()
                if self._showDetail:    label='Trailing edge'
                else:                   label= ''
                p = self.ax.plot(y, trailingEdge, label=label,color=color)
                self._add (p)              

                # rootline 
                yr = [y[0],y[0]]
                xr = [leadingEdge[0],trailingEdge[0]]
                color = self._nextColor()
                if self._showDetail:    label='Root'
                p = self.ax.plot(yr, xr,label=label, color=color)
                self._add (p)              

                # hinge line? 
                yh, xh = self.refPlanform_DXF.hingeLine_dxf()
                if self._showDetail:    label='Hinge line'
                if len(yh) > 0:
                    color = self._nextColor()
                    p = self.ax.plot(yh, xh,  label=label, color=color)
                    self._add (p)              


class PaneledPlanform_Artist (Planform_Artist):
    """Plot the outline of the paneled planform for Xflr5 or FLZ export
    """
    color = cl_paneled 

    def __init__ (self, axes, dataModel, paneledPlanform, **kwargs):
        super().__init__ (axes, dataModel, **kwargs)

        self._paneledPlanform = paneledPlanform

    @property
    def planform (self) -> Planform :
        return self.model.planform
    @property
    def paneledPlanform (self) -> Planform_Paneled :
        return self._paneledPlanform
    @property
    def wingSections (self): 
        return self.model.wingSections

    def _plot(self):

        # le and te of the original planform 
        y, leadingEdge, trailingEdge = self.planform.lines()
        lw = 0.7
        p = self.ax.plot(y, leadingEdge,  '--', lw=lw, color=cl_planform)
        self._add (p)
        p = self.ax.plot(y, trailingEdge, '--', lw=lw, color=cl_planform)
        self._add (p)

        # y-panel lines 
        lw = 0.7
        ls ='-'
        lines_y, lines_le_to_te, deviations = self.paneledPlanform.y_panel_lines()

        for iLine in range(len(lines_y)):
            y = lines_y[iLine]
            le_to_te = lines_le_to_te [iLine]
            if deviations[iLine] > 5:            # highlight y with too much deviation from actual 
                lw = 1.5
                color = cl_userHint
            else:
                lw = 0.7
                color = self.color
            p = self.ax.plot(y, le_to_te, color=color, linewidth=lw)
            self._add (p)              # remind plot to delete 

        # x-panel lines 
        lines_y, lines_panels_x = self.paneledPlanform.x_panel_lines()

        for iLine in range(len(lines_y)):
            y = lines_y[iLine]
            line_x = lines_panels_x [iLine]
            p = self.ax.plot(y, line_x, color=self.color, linewidth=lw)
            self._add (p)              # remind plot to delete 

        # wing sections
        section : WingSection
        lw = 1
        ls ='-'

        for section in self.wingSections:
            y, le_to_te = section.line()
            p = self.ax.plot(y, le_to_te, color=cl_wingSection_fix, linestyle=ls, linewidth=lw)
            self._add (p)              # remind plot to delete 
            self.plot_markers (y, le_to_te, section)


    def plot_markers (self, y, le_to_te, section: WingSection): 

        # plot section name 
        offset = 10
        top_y = y[0] 
        if section.isTip: 
            top_x = le_to_te[0] - 4 * offset
        else: 
            top_x = le_to_te[0] - offset

        if section.isRoot:
            label = "Root"
        elif section.isTip:
            label = "Tip"
        else:
            label = str(section.wing.wingSections.index_of (section))

        p = self.ax.text (top_y, top_x, "%s" % label, ha='center', va='bottom',
                          color = cl_wingSection_fix )
        self._add (p)   


class Chord_Artist (Artist):
    """Plot the chord distribution of a planform.
    """
    color = cl_planform  
    name  = 'Normalized chord distribution'   

    def __init__ (self, axes, modelFn, **kwargs):
        super().__init__ (axes, modelFn, **kwargs)

        # show mouse helper / allow drag of points 
        self.p1_marker_artist  = None
        self.p1_marker_anno    = None
        self.p1_line_artist    = None
        self.p2_marker_artist  = None
        self.p2_marker_anno    = None
        self.p2_line_artist    = None
        self.chord_line_artist = None 

    
    @property
    def planform (self) -> Planform :
        return self.model.planform
    
    def chord_line (self):
        return self.planform.norm_chord_line ()  

    def label (self):
        return 'Normalized chord distribution'

    def _plot (self): 


        if not self.planform.isValid: return                # e.g. dxf could be invalid 

        y, chord = self.chord_line ()

        # chord distribution 
        p = self.ax.plot(y, chord, '-', color=self.color, label=self.label())
        self._add(p) 
        # chord distribution for bezier movement 
        p = self.ax.plot(y, chord, 'None', color=self.color, animated=True)
        self.chord_line_artist = self._add(p) 


        if self.mouseActive and isinstance(self.planform, Planform_Bezier): 

            self.create_artists_bezier (self.model.planform)

            # make p1,2 of Bezier draggable - install callback when move is finished
            self._dragManagers.append (DragManager (self.ax, self.p1_marker_artist, 
                                        bounds=[(0.1, 0.95),(0.6, 1.0)], 
                                        callback_draw_animated = self.draw_animated_p1,
                                        callback_on_moved      = self._moveCallback))
            self._dragManagers.append (DragManager (self.ax, self.p2_marker_artist, 
                                        bounds=[(1, 1),(0.05, 0.95)], 
                                        callback_draw_animated = self.draw_animated_p2,
                                        callback_on_moved      = self._moveCallback))

            self.show_mouseHelper ()

        # connect to draw event for initial plot of the animated artists all together
        self._connectDrawEvent()

        # set ticks 
        self._add_xticks ([0, 1])
        self._add_yticks ([0, 1])


    def show_mouseHelper (self):
        # show info for section select #
        text = 'move bezier control points with the mouse '
        p = self.ax.text (0.50, 0.05, text, color=cl_userHint, fontsize = 'small',
                    transform=self.ax.transAxes, horizontalalignment='center', verticalalignment='bottom')
        self._add(p)


    def create_artists_bezier (self, planform: Planform): 
        """ show the helper points and lines for bezier curve definition """

        # ! animated=True must be set for all artists moving around !

        # Bezier p1 tangent line
        p = self.ax.plot (planform._py[0:2], planform._px[0:2], '--', linewidth=0.5, 
                          color= cl_userHint, animated=True) 
        self.p1_line_artist = self._add(p) 
        p = self.ax.plot (planform._py[0]+0.002, planform._px[0], marker=(3, 0, 0), fillstyle='none', 
                          color=cl_userHint, markersize=8, animated=True )
        self._add(p)

        # Bezier p1 marker and annotation
        p = self.ax.plot (planform._py[1], planform._px[1], marker='o', 
                          color=cl_userHint, markersize=6, animated=True )
        self.p1_marker_artist = self._add(p) 
        p = self.ax.annotate('root tangent', color=cl_userHint, fontsize='small',
                            xy=(planform._py[1], planform._px[1]), ha='left', va='center',
                            xytext=(8, 0), textcoords='offset points', animated=True)
        self.p1_marker_anno = self._add(p) 

        # Bezier p2 tangent line
        p = self.ax.plot (planform._py[2:], planform._px[2:], '--', linewidth=0.5, 
                          color= cl_userHint, animated=True)    
        self.p2_line_artist = self._add(p) 
        p = self.ax.plot (planform._py[3], planform._px[3],marker=(3, 0, 0), fillstyle='none', 
                          color=cl_userHint, animated=True, markersize=8 )
        self._add(p)

        # Bezier p2 marker and annotation
        p = self.ax.plot (planform._py[2], planform._px[2], marker='o', 
                          color=cl_userHint, markersize=6, animated=True)
        self.p2_marker_artist = self._add(p) 
        p = self.ax.annotate('tip tangent', color=cl_userHint, fontsize='small',
                            xy=(planform._py[2], planform._px[2]), ha='center', va= 'bottom',
                            xytext=(0, 5), textcoords='offset points', animated=True)
        self.p2_marker_anno = self._add(p) 



    def draw_animated_p1(self, **_): 
        """ call back when bezier point 1 was moved"""

        # draw marker and get new coordinates (when dragged) 
        x1,y1 = self.p1_marker_artist.get_xydata()[0]

        # set new endpoint for tangent line and draw line 
        x = self.p1_line_artist.get_xdata()
        y = self.p1_line_artist.get_ydata()
        x[-1] = x1
        y[-1] = y1
        self.p1_line_artist.set_xdata(x)
        self.p1_line_artist.set_ydata(y)

        # update planform - ! wing coordinate system
        self.planform : Planform_Bezier
        self.planform.set_p1x (y1)  
        self.planform.set_p1y (x1)  

        y, chord = self.chord_line ()
        self.chord_line_artist.set_xdata(y)
        self.chord_line_artist.set_ydata(chord)
        self.chord_line_artist.set_linestyle(':')

        # update annotation
        angle  = self.planform.tangentAngle_root
        length = self.planform.tangentLength_root
        self.p1_marker_anno.xy =  (x1,y1)
        self.p1_marker_anno.set ( text="angle %.1f  length %.2f" % (angle, length))

        # now draw all animated artists 
        self.draw_animated_artists ()

        # reset to the static values 
        self.p1_marker_anno.set ( text='root tangent')
        self.chord_line_artist.set_linestyle('-')


    def draw_animated_p2(self, **_): 
        """ call back when bezier point 2 was moved"""

        # draw marker and get new coordinates (when dragged) 
        x2,y2 = self.p2_marker_artist.get_xydata()[0]

        # set new endpoint for tangent line and draw line 
        x = self.p2_line_artist.get_xdata()
        y = self.p2_line_artist.get_ydata()
        x[0] = x2
        y[0] = y2
        self.p2_line_artist.set_xdata(x)
        self.p2_line_artist.set_ydata(y)

        # update planform - ! wing coordinate system
        self.planform.set_p2x (y2)

        y, chord = self.chord_line ()
        self.chord_line_artist.set_xdata(y)
        self.chord_line_artist.set_ydata(chord)
        self.chord_line_artist.set_linestyle(':')

        # update annotation
        angle  = self.planform.tangentAngle_tip
        length = self.planform.tangentLength_tip
        self.p2_marker_anno.xy =  (x2,y2)
        self.p2_marker_anno.set ( text="angle %.1f  length %.2f" % (angle, length))

        # now draw all animated artists 
        self.draw_animated_artists ()

        # reset to the static values 
        self.p2_marker_anno.set ( text='tip tangent')
        self.chord_line_artist.set_linestyle('-')





# ----------------------------------


class RefChord_Artist (Chord_Artist):
    """Plot the reference chord distribution of a planform.
    """
    color = cl_pureElliptical

    @property
    def planform (self) -> Planform :
        return self.model.refPlanform

    def label (self):
        return 'Elliptical chord distribution'



class RefChord_DXF_Artist (Chord_Artist):
    """Plot the chord distribution of a planform.
    """
    color = cl_dxf

    @property
    def planform (self) -> Planform :
        return self.model.refPlanform_DXF


    def label (self):
        return self.model.refPlanform_DXF.dxf_filename()


class Sections_Artist (Artist):
    """Plot the wing sections as a vertical line. Add markers and text etc.
    May plot in real coordinates and normed

    Arguments:
        norm --   True: plot in a normed coordinate system
    """
   
    def _plot (self): 
        """ do plot of wing sections in the prepared axes   
        """
        wing : Wing = self.model
        section : WingSection

        # now plot each single section
        for section in wing.wingSections:
            if self._norm: 
                y, le_to_te = section.norm_line()
            else:
                y, le_to_te = section.line()

            color = cl_wingSection_fix
            linewidth= 1.0
            linestyle='solid'

            label = '_' + section.name()                # add '_' to not appear in legend          

            # if not (section.isRootOrTip and self._norm): 
            p = self.ax.plot(y, le_to_te, color=color, label=label, linestyle=linestyle, 
                            linewidth=linewidth)
            self._add (p)                               # remind plot to delete 

            if self._pickActive: 
                # if not (self.mouseActive and section.isRootOrTip):  # avoid conflict with drag hinge line
                if self.mouseActive:  # avoid conflict with drag hinge line
                    self._makeObjectPickable (p)

            self.plot_markers (y, le_to_te, section)

        # activate event for clicking on line 
        if self._pickActive: 
            self._connectPickEvent ()


    def plot_markers (self, y, le_to_te, section: WingSection): 

        sectionFix = section.hasFixedPosition()

        # section chord - print along chord
        if self._norm:
            # if section.isRoot: return               # no norm_chord for root
            text = "%.3f" % (section.norm_chord)
            marker_x = (le_to_te[0] + le_to_te[1]) * 0.40
            marker_y = y[0] + 0.007
        else: 
            text = "%.0f" % section.chord
            marker_x = le_to_te[1] - (le_to_te[1] - le_to_te[0]) * 0.40
            marker_y = y[0] + 6

        if not sectionFix:                          # fixed chord 
            text = text + " fix"

        color = cl_wingSection_fix

        p = self.ax.text (marker_y, marker_x, text, ha='left',color = color, rotation=90 )
        self._add (p)   

        # section pos at bottom  
        if not section.isRootOrTip: 

            # add position as xtick 
            self._add_xticks ([y[0]])

            # add fixed Position info 
            if self._norm:
                marker_x = round(y[0],2)                    # in data coordinates
                marker_y = 0.06                             # in axis coordinates
            else: 
                marker_x = y[0]                             # in data coordinates
                marker_y = 0.02                             # in axis coordinates

            if sectionFix:
                p = self.ax.text (marker_x, marker_y, "fix", color=cl_wingSection_fix, backgroundcolor= cl_background, 
                                transform=self.ax.get_xaxis_transform(), 
                                horizontalalignment='center', verticalalignment='bottom')
                self._add (p)   

        # section name above le
        marker_top_y = y[0] 
        if self._norm:
            offset = - 0.03
        else:
            offset = 10
        marker_top_x = le_to_te[0] - offset

        if section.isRoot:
            label = "Root"
        elif section.isTip:
            label = "Tip"
            marker_top_x = le_to_te[0] - 4 * offset
        else:
            label = str(section.wing.wingSections.index_of (section))

        p = self.ax.text (marker_top_y, marker_top_x, "%s" % label, ha='center', va='bottom',
                          color = cl_wingSection_fix, fontsize = 'medium')   
        self._add (p)   



#-----------------------------------------------

class Flap_Artist (Artist):
    """Plot the flaps as a filley polygon. Add markers and text etc.
       May plot in real coordinates 
    """
    def wing (self) -> Wing:
        return self.model

    def _plot (self): 
        """ do plot of wing sections in the prepared axes   
        """

        flaps = self.wing().getFlaps()

        n = len(flaps)                   # Number of colors
        if n < 2: n= 2
         # create cycled colors 
        self._set_colorcycle (n, colormap='summer')                # no of cycle colors - extra color for each airfoil

        flap : Flap
        for flap in flaps:   

            p = self.ax.plot(flap.y, flap.x, color = cl_planform, linewidth=0.5)
            self._add(p)

            p = self.ax.fill(flap.y, flap.x, linewidth=3, alpha=0.3)   # color from cycler 
            self._add(p)

            self._plot_markers (flap)


        
    def  _plot_markers (self, flap : Flap): 

        # show xtick of flap left end - exclude most left flap as it would be tip 
        if flap.lineRight [0][1] != self.wing().halfwingspan: 
            self._add_xticks ([round(flap.lineRight [0][1], 0)])

        # show ytick of flap at root
        if flap.lineLeft [0][0] == 0.0: 
            self._add_yticks ([round(flap.lineLeft [1][1], 0)])

        # flapDepth
        self._text_flapDepth (flap.lineLeft, flap.depthLeft)
        if flap.lineRight [0][1] == self.wing().halfwingspan:    
            # plot extra depth at tip
            self._text_flapDepth (flap.lineRight, flap.depthRight)

        # flapGroup
        yBase = (flap.lineLeft [0][0] + flap.lineRight [0][1]) / 2  # middle of flap span
        xBase = (flap.lineLeft [1][0] + flap.lineRight [1][1]) / 2  # middle of flap chord
        p = self.ax.text (yBase, xBase, "%d" % (flap.flapGroup) , 
                          color = cl_text, fontsize = 'x-large' )
        self._add(p)

    def _text_flapDepth (self, line, flapDepth):
        yBase = line [0][0]
        xBase = (line [1][0] + line [1][1]) / 2  # middle of flap chord
        p = self.ax.text (yBase + 5, xBase, "%.1f %%" % (flapDepth * 100) , 
                        color = cl_text, fontsize = 'small' )
        self._add(p)



class Airfoil_Artist (Artist):
    """Plot the airfoils of the wing sections 
    May plot in real coordinates and normed

    Additional arguments:
        strak --   True: also show straked airfoils 
    """
    def __init__ (self, axes, dataModel, strak=False, **kwargs):
        super().__init__ (axes, dataModel, **kwargs)

        self._strak = strak
        self.set_showLegend('extended')         # show  legend with airfoil data 


    def set_current (self, aLineLabel, figureUpdate=False):
        """ tries to set a highlighted airfoil  to section with name ''aLineLabel' 
        """
        if (not aLineLabel is None and aLineLabel != self._curLineLabel):    # only when changed do something
            self._curLineLabel = aLineLabel
            if self.show:                       # view is switched on by user? 
                self.plot (figureUpdate=figureUpdate)

    def set_strak (self, aBool):
        """ show straked airfoils """
        self._strak = aBool
        if self.show:                       # view is switched on by user? 
            self.plot(figureUpdate=True)

    
    def _plot (self): 
        """ do plot of wing sections in the prepared axes   
        """

        wing = self.model 

        n = 0                                       
        for section in wing.wingSections:
            airfoil = section.airfoil
            if (airfoil.isLoaded) and not (not self._strak and airfoil.isStrakAirfoil): n += 1
        if not n: return 

        # create cycled colors 
        self._set_colorcycle (8, colormap="Set2")    # extra color for each airfoil

        # plot title
        if not self._norm: 
            text = "Airfoils in wing sections"
            self._add(self.ax.text(.05,.9, text, fontsize ='large', ha='left', transform=self.ax.transAxes))

        section : WingSection
        iair = 0 

        # now plot each single section
        for section in wing.wingSections:
            airfoil = section.airfoil
            if (airfoil.isLoaded) and not (not self._strak and airfoil.isStrakAirfoil):

                label = ("%s  @ %s" % (airfoil.name, section.name() ))  

                if self._norm:
                    x = airfoil.x
                    y = airfoil.y
                else:
                    # x = 0 at root LE
                    le = section.line ()[1][0]
                    x = airfoil.x * section.chord + le 
                    y = airfoil.y * section.chord 

                color = self._cycle_color()

                if self._curLineLabel == label:
                    if not self._norm:                     # for norm it would be too much color confusion
                        p = self.ax.fill (x, y, facecolor=color, alpha=0.1)
                        self._add(p)
                    linewidth=1.6
                    self._plot_marker (x,y, color, section)
                else:
                    linewidth=0.8

                p = self.ax.plot (x, y, '-', color = color, label=label, linewidth= linewidth)
                self._add(p)

                if self._pickActive: 
                    self._makeObjectPickable (p)

                # print a table for the max values 
                if self.showLegend == 'extended':
                    if self.norm: 
                        self._print_values (iair, airfoil, section, color)
                    else: 
                        self._print_size   (iair, airfoil, section, color)
                    iair += 1


        # activate event for clicking on line 
        if self._pickActive: 
            self._connectPickEvent ()
            self.show_mouseHelper ()



    def show_mouseHelper (self):
        """ show info for section select"""

        p = self.ax.text (0.40, 0.05, 'click airfoil to select', color=cl_userHint, fontsize = 'small',
                    transform=self.ax.transAxes, horizontalalignment='left', verticalalignment='bottom')
        self._add(p)


    def _plot_marker (self, x,y, color, section: WingSection):
        # annotate airfoil with name etc. 

        # section data  
        if section.airfoilNick():
            nickname = " - '"+ section.airfoilNick() 
        else:
            nickname = ''
        name = section.airfoil.name + nickname + "  @ " + section.name() 
        y = np.amin(y) * 0.3
        x = np.amax(x) 

        p = self.ax.annotate(name, color=color, 
                xy=(x, y), xycoords='data', ha='right', va= 'top',
                xytext=(0, -50), textcoords='offset points')
        self._add(p)


    def _print_values (self, iair, airfoil: Airfoil, section: WingSection, color):
         # print thickness, camber in a little table in upper left corner , position relative in pixel 
 
        sc = get_font_size() / 10                    # scale pos depending on font size 
        xa = 0.84 - (sc - 1.0) / 4
        ya = 0.96 

        # header 
        if iair == 0: 
            self._add (print_text (self.ax, 'Thickness', 'right', (xa,ya), ( 15*sc, 0), cl_textHeader, xycoords='axes fraction'))
            self._add (print_text (self.ax,    'Camber', 'right', (xa,ya), ( 75*sc, 0), cl_textHeader, xycoords='axes fraction'))
            self._add (print_text (self.ax,   'Section',  'left', (xa,ya), (115*sc, 0), cl_textHeader, xycoords='axes fraction'))

        # section data  
        if section.airfoilNick():
            nickname = " - '"+ section.airfoilNick() 
        else:
            nickname = ''
        name = section.airfoil.name + nickname
        sect = section.name() 

        geo = airfoil.geo
        xt, t = geo.maxThickX, geo.maxThick 
        xc, c = geo.maxCambX,  geo.maxCamb

        yoff = - iair * (12*sc) - (12*sc)
        self._add (print_text   (self.ax, name, 'right', (xa,ya), (-35*sc, yoff), color, xycoords='axes fraction'))
        self._add (print_number (self.ax,  t, 2, (xa,ya), (  0, yoff), cl_text, asPercent=True))
        self._add (print_number (self.ax, xt, 1, (xa,ya), ( 30*sc, yoff), cl_text, asPercent=True))
        self._add (print_number (self.ax,  c, 2, (xa,ya), ( 70*sc, yoff), cl_text, asPercent=True))
        self._add (print_number (self.ax, xc, 1, (xa,ya), (100*sc, yoff), cl_text, asPercent=True))
        self._add (print_text   (self.ax, sect,  'left', (xa,ya), (115*sc, yoff), cl_text, xycoords='axes fraction'))



    def _print_size (self, iair, airfoil: Airfoil, section: WingSection, color):
         # print section sizes in a little table in upper right corner , position relative in pixel 
 
        sc = get_font_size() / 10                    # scale pos depending on font size 
        xa = 0.84 - (sc - 1.0) / 4
        ya = 0.96 

        # header 
        if iair == 0: 
            self._add (print_text (self.ax,   'Width', 'right', (xa,ya), ( 20*sc, 0), cl_textHeader, xycoords='axes fraction'))
            self._add (print_text (self.ax,  'Height', 'right', (xa,ya), ( 70*sc, 0), cl_textHeader, xycoords='axes fraction'))
            self._add (print_text (self.ax, 'Section',  'left', (xa,ya), ( 90*sc, 0), cl_textHeader, xycoords='axes fraction'))

        # section data  
        if section.airfoilNick():
            nickname = " - '"+ section.airfoilNick() 
        else:
            nickname = ''
        name = section.airfoil.name + nickname

        geo = airfoil.geo
        height = f"{geo.maxThick * section.chord:.1f}mm"
        width  = f"{section.chord:.1f}mm"
        sect   = section.name() 

        yoff = - iair * (12*sc) - (12*sc)
        self._add (print_text   (self.ax,   name, 'right', (xa,ya),(-35*sc, yoff),   color, xycoords='axes fraction'))
        self._add (print_text   (self.ax,  width, 'right', (xa,ya), (20*sc, yoff), cl_text, xycoords='axes fraction'))
        self._add (print_text   (self.ax, height, 'right', (xa,ya), (70*sc, yoff), cl_text, xycoords='axes fraction'))
        self._add (print_text   (self.ax,   sect,  'left', (xa,ya), (90*sc, yoff), cl_text, xycoords='axes fraction'))




class AirfoilName_Artist (Artist):
    """shows the airfoil name in planform view """

    @property   
    def wing (self) -> Wing:
        return self.model
    @property
    def wingSections (self): 
        return self.wing.wingSections
    
    def _plot (self): 
        """ do plot of wing sections in the prepared axes   
        """
        if self.norm: return                    # normalized view not supported 

         # create cycled colors 
        n= len(self.wing.wingSections)
        self._set_colorcycle (n)                # no of cycle colors - extra color for each airfoil

        section : WingSection
        for section in self.wingSections:
            if not section.airfoil.isStrakAirfoil:
                y, le_to_te = section.line()
                self.plot_markers (y, le_to_te, section)
            

    def plot_markers (self, y, le_to_te, section: WingSection): 
        # print airfoil name and nickname below the planform 

        marker_y = 0.87                         # in axis coordinates
        marker_x = y[0]                         # in data coordinates
        if section.airfoilNick():
            nickname = "'"+ section.airfoilNick() + "'" + "\n"
        else:
            nickname = ''

        text = nickname + section.airfoil.name

        color = self._cycle_color()
        p = self.ax.text (marker_x, marker_y, text, color=color, backgroundcolor= cl_background,
                          transform=self.ax.get_xaxis_transform(), fontsize='small',
                          horizontalalignment='center', verticalalignment='top')
        self._add (p)   
