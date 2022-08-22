# file.py
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

from gi.repository import Adw, Gio, Gtk, GObject
import magic
import mimetypes
import os.path
import traceback

from .backends import EartagFileEyed3, EartagFileTagLib, EartagFileMutagenVorbis
from .backends.file import EartagFile

def eartagfile_from_path(path):
    """Returns an EartagFile subclass for the provided file."""
    if not os.path.exists(path):
        raise ValueError

    mimetypes_guess = mimetypes.guess_type(path)[0]
    magic_guess = magic.Magic(mime=True).from_file(path)

    is_type = lambda type: mimetypes_guess == type or magic_guess == type

    if is_type('audio/mpeg'):
        return EartagFileEyed3(path)
    elif is_type('audio/flac') or is_type('audio/ogg'):
        try:
            import mutagen
        except ImportError:
            print("mutagen unavailable, using taglib to handle ogg/flac!")
        else:
            return EartagFileMutagenVorbis(path)
    return EartagFileTagLib(path)

class EartagFileManager(GObject.Object):
    """Contains information about the currently loaded files."""

    # Load modes
    LOAD_OVERWRITE = 0
    LOAD_INSERT = 1

    _is_modified = False
    _selected_files = []

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.files = Gio.ListStore(item_type=EartagFile)
        self.selected_files = []

    @GObject.Signal
    def files_loaded(self):
        pass

    @GObject.Signal
    def selection_changed(self):
        pass

    @GObject.Signal
    def selection_override(self):
        """
        Internal signal used to communicate selection overrides to the sidebar.
        """
        pass

    def load_file(self, path, mode=0, emit_loaded=True):
        """Loads a file."""
        _selection_override = False
        file_basename = os.path.basename(path)

        try:
            _file = eartagfile_from_path(path)
        except:
            traceback.print_exc()
            self.error_dialog = Gtk.MessageDialog(
                                    transient_for=self.window,
                                    buttons=Gtk.ButtonsType.OK,
                                    message_type=Gtk.MessageType.ERROR,
                                    text=_("Failed to load file"),
                                    secondary_text=_("Could not load file {f}. Check the logs for more information.").format(f=file_basename)
            )
            self.error_dialog.connect('response', self.close_dialog)
            self.error_dialog.show()
            return False

        _file.connect('modified', self.update_modified_status)

        if mode == self.LOAD_OVERWRITE:
            self.files.remove_all()
            self.selected_files = [_file]
            _selection_override = True
            self.emit('selection_override')

        if not self.selected_files:
            self.selected_files = [_file]
            _selection_override = True

        self.files.append(_file)

        if emit_loaded:
            self.emit('files_loaded')
            self.update_modified_status()

        if _selection_override:
            self.emit('selection_override')

        return True

    def load_multiple_files(self, paths, mode=1):
        """Loads files with the provided paths."""
        if mode == self.LOAD_OVERWRITE:
            self.files.remove_all()
            self._selected_files = []

        for path in paths:
            if not self.load_file(path, mode=self.LOAD_INSERT, emit_loaded=False):
                self.emit('files_loaded')
                self.update_modified_status()
                return False

        self.emit('files_loaded')
        self.update_modified_status()

    def save(self):
        """Saves changes in all files."""
        for file in self.files:
            if not file.is_writable or not file.is_modified:
                continue

            try:
                file.save()
            except:
                traceback.print_exc()
                file_basename = os.path.basename(file.path)
                self.error_dialog = Gtk.MessageDialog(
                                        transient_for=self.window,
                                        buttons=Gtk.ButtonsType.OK,
                                        message_type=Gtk.MessageType.ERROR,
                                        text=_("Failed to save file"),
                                        secondary_text=_("Could not save file {f}. Check the logs for more information.").format(f=file_basename)
                )
                self.error_dialog.connect('response', self.close_dialog)
                self.error_dialog.show()
                return False
            else:
                self.window.toast_overlay.add_toast(
                    Adw.Toast.new(_("Saved changes to file"))
                )

    def update_modified_status(self, *args):
        """Responsible for setting the is_modified property."""
        for file in self.files:
            if file.is_modified:
                self.set_property('is_modified', True)
                return
        self.set_property('is_modified', False)

    def remove(self, file):
        """Removes a file from the opened file list."""
        self.files.remove(self.files.find(file)[1])
        if file in self.selected_files:
            self._selected_files.remove(file)
            if not self.selected_files and self.files:
                self.selected_files.append(self.files.get_item(0))
            self.emit('selection-changed')
            self.emit('selection_override')

    def close_dialog(self, dialog, *args):
        dialog.close()

    @GObject.Property(type=bool, default=False)
    def is_modified(self):
        return self._is_modified

    @is_modified.setter
    def is_modified(self, value):
        self._is_modified = value

    @GObject.Property
    def selected_files(self):
        return self._selected_files

    @selected_files.setter
    def selected_files(self, value):
        self._selected_files = value
        self.emit('selection_changed')
