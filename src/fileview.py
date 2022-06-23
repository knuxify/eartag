# fileview.py
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

from .file import EartagFile

from gi.repository import Adw, Gtk, GObject
from os.path import basename
import mutagen

class EartagTagListItem(Adw.ActionRow):
    __gtype_name__ = 'EartagTagListItem'

    def __init__(self, path=None):
        super().__init__(can_target=False, focusable=False, focus_on_click=False)
        self.value_entry = Gtk.Entry(valign=Gtk.Align.CENTER)
        self.add_suffix(self.value_entry)
        self.set_activatable_widget(self.value_entry)
        self.value_entry.connect('changed', self.do_notify)

    def do_notify(self, *args):
        self.notify('value')

    @GObject.Property(type=str)
    def value(self):
        return self.value_entry.get_text()

    @value.setter
    def set_value(self, value):
        self.value_entry.set_text(value)

@Gtk.Template(resource_path='/org/dithernet/Eartag/ui/fileview.ui')
class EartagFileView(Adw.Bin):
    __gtype_name__ = 'EartagFileView'

    title_entry = Gtk.Template.Child()
    comment_entry = Gtk.Template.Child()
    artist_entry = Gtk.Template.Child()
    album_entry = Gtk.Template.Child()
    albumartist_entry = Gtk.Template.Child()

    toast_overlay = Gtk.Template.Child()
    file = None

    def __init__(self, path=None):
        """Initializes the EartagFileView."""
        super().__init__()

        self.file_path = path
        if path:
            self.load_file()

    def load_file(self):
        """Reads the file path from self.file_path and loads the file."""
        self.file = EartagFile(self.file_path)
        if not self.file:
            # TODO: add some kind of user-facing warning?
            raise ValueError("File is not recognized by mutagen")

        window = self.get_native()
        window.save_button.set_visible(True)
        window.window_title.set_subtitle(basename(self.file_path))
        window.content_stack.set_visible_child(self)

        self.file.bind_property('is_modified', window.save_button, 'sensitive',
            GObject.BindingFlags.SYNC_CREATE)

        # Bind the values
        self.file.bind_property('title', self.title_entry, 'value',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)

        self.file.bind_property('artist', self.artist_entry, 'value',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)

        self.file.bind_property('album', self.album_entry, 'value',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)

        self.file.bind_property('albumartist', self.albumartist_entry, 'value',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)

        self.file.bind_property('comment', self.comment_entry, 'value',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)

    def save(self):
        """Saves changes to the file."""
        self.toast_overlay.add_toast(Adw.Toast.new(_("Saved changes to file")))
        self.file.save()
