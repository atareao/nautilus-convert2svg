#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This file is part of nautilus-convert2svg
#
# Copyright (C) 2016 Lorenzo Carbonell
# lorenzo.carbonell.cerezo@gmail.com
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
#
import gi
try:
    gi.require_version('Gtk', '3.0')
    gi.require_version('Nautilus', '3.0')
except Exception as e:
    print(e)
    exit(-1)
import os
import subprocess
import shlex
import tempfile
import shutil
from threading import Thread
from urllib import unquote_plus
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Nautilus as FileManager

EXTENSIONS_FROM = ['.bmp', '.eps', '.gif', '.jpg', '.pcx', '.png', '.ppm',
                   '.tif', '.tiff', '.webp']
SEPARATOR = u'\u2015' * 10

_ = str


class IdleObject(GObject.GObject):
    """
    Override GObject.GObject to always emit signals in the main thread
    by emmitting on an idle handler
    """
    def __init__(self):
        GObject.GObject.__init__(self)

    def emit(self, *args):
        GLib.idle_add(GObject.GObject.emit, self, *args)


class DoItInBackground(IdleObject, Thread):
    __gsignals__ = {
        'started': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (int,)),
        'ended': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (bool,)),
        'start_one': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (str,)),
        'end_one': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (float,)),
    }

    def __init__(self, elements):
        IdleObject.__init__(self)
        Thread.__init__(self)
        self.elements = elements
        self.stopit = False
        self.ok = True
        self.daemon = True
        self.process = None

    def stop(self, *args):
        self.stopit = True

    def ejecuta(self, rutine):
        args = shlex.split(rutine)
        self.process = subprocess.Popen(args, stdout=subprocess.PIPE)
        out, err = self.process.communicate()
        print(out, err)

    def convert2svg(self, file_in):
        tmp_file_out_1 = tempfile.NamedTemporaryFile(
            prefix='tmp_2svg_file_step1_',
            dir='/tmp/').name+'.bmp'
        tmp_file_out_2 = tempfile.NamedTemporaryFile(
            prefix='tmp_2svg_file_step2_',
            dir='/tmp/').name+'.bmp'
        tmp_file_out_3 = get_output_filename(tmp_file_out_2)
        rutine2 = 'mkbitmap "%s" -o "%s"' % (tmp_file_out_1, tmp_file_out_2)
        rutine3 = 'potrace -s "%s"' % (tmp_file_out_2)
        if os.path.exists((tmp_file_out_1)):
            os.remove(tmp_file_out_1)
        if os.path.exists((tmp_file_out_2)):
            os.remove(tmp_file_out_2)
        if os.path.exists((tmp_file_out_3)):
            os.remove(tmp_file_out_3)
        convertImage2Bmp(file_in, tmp_file_out_1)
        # ejecuta(rutine1)
        self.ejecuta(rutine2)
        self.ejecuta(rutine3)
        file_out = get_output_filename(file_in)
        if os.path.exists(file_out):
            os.remove(file_out)
        shutil.copyfile(tmp_file_out_3, file_out)
        if os.path.exists((tmp_file_out_1)):
            os.remove(tmp_file_out_1)
        if os.path.exists((tmp_file_out_2)):
            os.remove(tmp_file_out_2)
        if os.path.exists((tmp_file_out_3)):
            os.remove(tmp_file_out_3)

    def run(self):
        total = 0
        for element in self.elements:
            total += get_duration(element)
        self.emit('started', total)
        try:
            total = 0
            for element in self.elements:
                if self.stopit is True:
                    self.ok = False
                    break
                self.emit('start_one', element)
                self.convert2svg(element)
                self.emit('end_one', get_duration(element))
        except Exception as e:
            self.ok = False
        try:
            if self.process is not None:
                self.process.terminate()
                self.process = None
        except Exception as e:
            print(e)
        self.emit('ended', self.ok)


class Progreso(Gtk.Dialog, IdleObject):
    __gsignals__ = {
        'i-want-stop': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
    }

    def __init__(self, title, parent):
        Gtk.Dialog.__init__(self, title, parent,
                            Gtk.DialogFlags.MODAL |
                            Gtk.DialogFlags.DESTROY_WITH_PARENT)
        IdleObject.__init__(self)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_size_request(330, 30)
        self.set_resizable(False)
        self.connect('destroy', self.close)
        self.set_modal(True)
        vbox = Gtk.VBox(spacing=5)
        vbox.set_border_width(5)
        self.get_content_area().add(vbox)
        #
        frame1 = Gtk.Frame()
        vbox.pack_start(frame1, True, True, 0)
        table = Gtk.Table(2, 2, False)
        frame1.add(table)
        #
        self.label = Gtk.Label()
        table.attach(self.label, 0, 2, 0, 1,
                     xpadding=5,
                     ypadding=5,
                     xoptions=Gtk.AttachOptions.SHRINK,
                     yoptions=Gtk.AttachOptions.EXPAND)
        #
        self.progressbar = Gtk.ProgressBar()
        self.progressbar.set_size_request(300, 0)
        table.attach(self.progressbar, 0, 1, 1, 2,
                     xpadding=5,
                     ypadding=5,
                     xoptions=Gtk.AttachOptions.SHRINK,
                     yoptions=Gtk.AttachOptions.EXPAND)
        button_stop = Gtk.Button()
        button_stop.set_size_request(40, 40)
        button_stop.set_image(
            Gtk.Image.new_from_stock(Gtk.STOCK_STOP, Gtk.IconSize.BUTTON))
        button_stop.connect('clicked', self.on_button_stop_clicked)
        table.attach(button_stop, 1, 2, 1, 2,
                     xpadding=5,
                     ypadding=5,
                     xoptions=Gtk.AttachOptions.SHRINK)
        self.stop = False
        self.show_all()
        self.max_value = float(max_value)
        self.value = 0.0

    def set_max_value(self, anobject, max_value):
        self.max_value = float(max_value)

    def get_stop(self):
        return self.stop

    def on_button_stop_clicked(self, widget):
        self.stop = True
        self.emit('i-want-stop')

    def close(self, *args):
        self.destroy()

    def increase(self, anobject, value):
        self.value += float(value)
        fraction = self.value/self.max_value
        self.progressbar.set_fraction(fraction)
        if self.value >= self.max_value:
            self.hide()

    def set_element(self, anobject, element):
        self.label.set_text(_('Converting: %s') % element)


def convertImage2Bmp(file_in, file_out):
        img = Image.open(file_in)
        img.save(file_out)


def get_output_filename(file_in):
    head, tail = os.path.split(file_in)
    root, ext = os.path.splitext(tail)
    file_out = os.path.join(head, root+'.svg')
    return file_out


def get_duration(file_in):
    return os.path.getsize(file_in)


def get_files(files_in):
    files = []
    for file_in in files_in:
        print(file_in)
        file_in = unquote_plus(file_in.get_uri()[7:])
        if os.path.isfile(file_in):
            files.append(file_in)
    return files


class SVGConvereterMenuProvider(GObject.GObject, FileManager.MenuProvider):

    def __init__(self):
        pass

    def all_files_are_images(self, items):
        for item in items:
            fileName, fileExtension = os.path.splitext(unquote_plus(
                item.get_uri()[7:]))
            if fileExtension.lower() not in EXTENSIONS_FROM:
                return False
        return True

    def convert(self, menu, selected):
        files = get_files(selected)
        diib = DoItInBackground(files)
        progreso = Progreso(_('Convert to svg'), window, len(files))
        diib.connect('started', progreso.set_max_value)
        diib.connect('start_one', progreso.set_element)
        diib.connect('end_one', progreso.increase)
        diib.connect('ended', progreso.close)
        progreso.connect('i-want-stop', diib.stop)
        diib.start()
        progreso.run()

    def get_file_items(self, window, sel_items):
        if self.all_files_are_images(sel_items):
            top_menuitem = FileManager.MenuItem(
                name='SVGConverterMenuProvider::Gtk-svg-tools',
                label=_('Convert to svg'),
                tip=_('Tool to convert to svg'))
            top_menuitem.connect('activate', self.convert, sel_items)
            #
            return top_menuitem,
        return
if __name__ == '__main__':
    print(tempfile.NamedTemporaryFile(prefix='tmp_convert2svg_file',
                                      dir='/tmp/').name)
    print(get_output_filename('ejemplo.ext'))
    convert2svg('/home/lorenzo/Escritorio/last-sample.png')
