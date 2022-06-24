# main.py
#
# Copyright 2022 knuxify
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE X CONSORTIUM BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# Except as contained in this notice, the name(s) of the above copyright
# holders shall not be used in advertising or otherwise to promote the sale,
# use or other dealings in this Software without prior written
# authorization.

import sys
import gi
import os.path
import magic

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk, Gio

from .window import EartagWindow, AboutDialog

class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id='org.dithernet.Eartag',
                         resource_base_path='/org/dithernet/Eartag',
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.path = None
        self.connect('open', self.on_open)

    def on_open(self, window, filename, *args):
        self.path = filename[0].get_path()
        if self.path and not os.path.exists(self.path):
            self.path = None
        if self.path and not magic.Magic(mime=True).from_file(self.path).startswith('audio/'):
            self.path = None
        self.do_activate()

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = EartagWindow(application=self, path=self.path)
        self.create_action('about', self.on_about_action)
        self.create_action('open_file', self.on_open_file_action)
        win.present()

    def on_about_action(self, widget, _):
        about = AboutDialog(self.props.active_window)
        about.present()

    def on_open_file_action(self, widget, _):
        self.get_active_window().show_file_chooser()

    def create_action(self, name, callback):
        """ Add an Action and connect to a callback """
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)


def main(version):
    app = Application()
    return app.run(sys.argv)
