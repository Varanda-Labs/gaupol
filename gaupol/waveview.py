# -*- coding: utf-8 -*-

# Copyright (C) 2023 Varanda Labs Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""User interface container and controller for :class:`aeidon.Project`."""

import aeidon
import gaupol
import os
import sys
import cairo
import traceback
import argparse

from aeidon.i18n   import _
from gi.repository import Gtk, GObject, Gst

# gi.require_version('Gst', '1.0')
# from gi.repository import Gst, GObject

__all__ = ("Waveview",)

TMP_PATH = "/tmp/"
TMP_EXT = ".gaupol.$$$"

"""
for 16 bits in 16 bits, signed, little endian:

gst-launch-1.0 filesrc location=filename ! \ 
 decodebin ! audioconvert ! audioresample ! \
 audio/x-raw, channels=1, rate=16000, format=S16LE ! \
 filesink location=out.raw

for 8 bits, 8K/sec:

gst-launch-1.0 filesrc location=filename ! \
    decodebin ! audioconvert ! \
    audioresample ! \
    audio/x-raw, channels=1, rate=8000, format=S8 ! \
    filesink location=fileout.raw
"""

AUDIO_SAMPLES_PER_SECOND = 8000
DECIMATE_FACTOR = 80
DISP_SAMPLES_PER_SECOND = AUDIO_SAMPLES_PER_SECOND / DECIMATE_FACTOR
DISP_SPAM_IN_SECONDS = 10
DISP_SPAM_IN_SAMPLES = DISP_SPAM_IN_SECONDS * DISP_SAMPLES_PER_SECOND

#ref: https://github.com/jackersson/gst-python-tutorials/blob/master/launch_pipeline/pipeline_with_parse_launch.py

class CreateCache():
    def __init__(self, file_in, file_out, progress):
        super(CreateCache,self).__init__()
        self.progress = progress

        DEFAULT_PIPELINE = "filesrc location=FILEIN ! decodebin ! progressreport update-freq=1 silent=true ! audioconvert ! audioresample ! audio/x-raw, channels=1, rate=8000, format=S8 ! filesink location=FILEOUT"
        default_pipeline = DEFAULT_PIPELINE.replace("FILEIN", file_in)
        default_pipeline = default_pipeline.replace("FILEOUT", file_out)

        ap = argparse.ArgumentParser()
        ap.add_argument("-p", "--pipeline", required=False,
                        default=default_pipeline, help="Gstreamer pipeline without gst-launch")

        args = vars(ap.parse_args())

        command = args["pipeline"]

        pipeline = Gst.parse_launch(command)
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        pipeline.set_state(Gst.State.PLAYING)

        # Init GObject loop to handle Gstreamer Bus Events
        loop = GObject.MainLoop()

        bus.connect("message", self.on_message, loop)

        try:
            loop.run()
        except Exception:
            traceback.print_exc()
            loop.quit()

        # Stop Pipeline
        pipeline.set_state(Gst.State.NULL)


    def on_message(self, bus: Gst.Bus, message: Gst.Message, loop: GObject.MainLoop):
        mtype = message.type
        """
            Gstreamer Message Types and how to parse
            https://lazka.github.io/pgi-docs/Gst-1.0/flags.html#Gst.MessageType
        """
        if mtype == Gst.MessageType.EOS:
            print("End of stream")
            loop.quit()

        elif mtype == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(err, debug)
            loop.quit()

        elif mtype == Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            print(err, debug)

        elif mtype == Gst.MessageType.ELEMENT:
            b,p = message.get_structure().get_int("percent")
            print("Progress message " + str(p) + "%")
            self.progress.set_fraction(p/100)

        else:
            print(mtype)

        return True


class GraphicArea(Gtk.DrawingArea):
    """ This class is a Drawing Area"""
    def __init__(self):
        super(GraphicArea,self).__init__()
        ## Connect to the "draw" signal
        self.connect("draw", self.on_draw)
        ## This is what gives the animation life!
        GObject.timeout_add(50, self.tick) # Go call tick every 50 whatsits.


        ## x,y is where I'm at
        self.x, self.y = 25, -25
        ## rx,ry is point of rotation
        self.rx, self.ry = -10, -25
        ## rot is angle counter
        self.rot = 0
        ## sx,sy is to mess with scale
        self.sx, self.sy = 1, 1
        self.data = None
        self.sample_pos = -1

    def set_data(self, data):
        self.data = data

    def set_position(self, pos):
        if self.data == None:
            return
        # pos is fraction of the total duration
        self.sample_pos = int(len(self.data) * pos)

    def tick(self):
        ## This invalidates the graphic area, causing the "draw" event to fire.
        rect = self.get_allocation()
        #self.get_window().invalidate_rect(rect, True)
        #w = self.get_window()
        #w.invalidate_rect(rect, True)
        #self.gtk_widget_queue_draw_area()
        self.queue_draw()
        return True # Causes timeout to tick again.

    ## When the "draw" event fires, this is run
    def on_draw(self, widget, event):
        self.cr = self.get_window().cairo_create()
        geom = self.get_window().get_geometry()
        self.draw_wave(geom.width, geom.height)
    
    def draw_wave(self, width, height):
        self.drawcross(self.cr)
        ctx = self.cr
        ctx.set_source_rgb(0, 0, 0)

        if self.data == None:
            return
        max_y = DISP_SPAM_IN_SAMPLES
        if max_y > len(self.data):
            max_y = len(self.data)
        offset_x = width/max_y
        x = 0
        i = 0

        self.cr.set_source_rgb(0, 0, 0)
        #self.cr.set_line_width(0.02)
        self.cr.move_to(x, 0)
        while x <= width:
            self.cr.move_to(x, height)
            self.cr.line_to(x, height - self.data[i] * height)
            self.cr.stroke()
            i += 1
            x += offset_x
        if self.sample_pos >= 0 and self.sample_pos < max_y:
            self.cr.set_source_rgb(255, 0, 0)
            x = self.sample_pos * offset_x
            self.cr.move_to(x, height)
            self.cr.line_to(x, 0)
            self.cr.stroke()

class Progress(Gtk.Window):
    def __init__(self):
        super(Progress, self).__init__()
        self.set_default_size(400,200)
        self.set_title("Gaupol Progress")
        vbox = Gtk.VBox()
        label = Gtk.Label("Loading/Parsing Video File")
        vbox.pack_start(label, expand = True, fill = True, padding = 10)
        self.progress = Gtk.ProgressBar()
        vbox.pack_start(self.progress, expand = True, fill = True, padding = 10)
        self.add(vbox)
        self.show_all()

    def get_progress(self):
        return self.progress
    

class Waveview():
    """ This class is a Drawing Area"""
    def __init__(self):
        super(Waveview,self).__init__()
        self.graphic_area = GraphicArea()
        self.top_container = Gtk.HBox(spacing=6)

        self.vbox = Gtk.VBox(spacing=6)
        b = Gtk.Button("Dummy 1")
        self.vbox.pack_start(b, True, True, 0)
        b = Gtk.Button("Dummy 2")
        self.vbox.pack_start(b, True, True, 0)

        self.top_container.pack_start(self.graphic_area, True, True, 0)
        self.top_container.pack_start(self.vbox, True, True, 0)
        self.top_container.show_all()


    def getWidget(self):
        return self.top_container

    def create_data(self, path):
        tmp_name = TMP_PATH + os.path.basename(path) + TMP_EXT
        p = Progress()
        CreateCache(path, tmp_name, p.get_progress())
        p.hide()
        f = open(tmp_name, 'rb')
        d = bytearray(f.read())  # maybe save d as self.audio_samples for scrubbing
        f.close()

        # maybe run an IIR low pass before decimation?

        # decimate date
        i = 0
        _len = len(d)
        samples = []
        max = 0

        while (i < _len):
            b = d[i]
            if b > 127:
                b = 256 - b
            samples.append(b)
            if b > max:
                max = b
            i += DECIMATE_FACTOR
        #print("n samples = " + str(len(samples)))
        #print ("DISP_SAMPLES_PER_SECOND = " + str(DISP_SAMPLES_PER_SECOND))

        ## normalize
        _len = len(samples)
        i = 0
        f = 1.0 / max
        #print("max = " + str(max) + ", f = " + str(f))
        while (i < _len):
            samples[i] *= f
            i += 1
        self.data = samples
        self.graphic_area.set_data(samples)
        print(samples)




