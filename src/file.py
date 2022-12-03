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
import threading
import time

from .backends import (
    EartagFileMutagenVorbis,
    EartagFileMutagenID3,
    EartagFileMutagenMP4,
    EartagFileMutagenASF
    )
from .backends.file import EartagFile

def is_type_bulk(path, types):
    mimetypes_guess = mimetypes.guess_type(path)[0]
    magic_guess = magic.from_file(path, mime=True)

    for type in types:
        if mimetypes_guess == type or magic_guess == type:
            return True

    return False

def eartagfile_from_path(path):
    """Returns an EartagFile subclass for the provided file."""
    if not os.path.exists(path):
        raise ValueError

    if is_type_bulk(path, ('audio/mp3', 'audio/mpeg', 'audio/wav', 'audio/x-wav')):
        return EartagFileMutagenID3(path)
    elif is_type_bulk(path, ('audio/flac', 'audio/ogg', 'application/ogg', 'application/x-ogg', 'audio/x-flac', 'audio/x-vorbis+ogg')):
        return EartagFileMutagenVorbis(path)
    elif is_type_bulk(path, ('audio/x-m4a', 'audio/aac', 'audio/mp4', 'audio/x-mpeg', 'audio/mpeg')):
        return EartagFileMutagenMP4(path)
    elif is_type_bulk(path, ('audio/x-ms-wma', 'audio/wma', 'video/x-ms-asf')):
        return EartagFileMutagenASF(path)
    raise ValueError(f"Unsupported file format for file {path}")

class EartagFileManager(GObject.Object):
    """Contains information about the currently loaded files."""

    # Load modes
    LOAD_OVERWRITE = 0
    LOAD_INSERT = 1

    _is_modified = False
    _selected_files = []
    _loading_progress = 0
    _is_loading_multiple_files = False
    _halt_loading = False

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.files = Gio.ListStore(item_type=EartagFile)
        self.file_paths = []
        self.selected_files = []
        self._files_buffer = []
        self._selection_removed = False

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

    @GObject.Signal
    def files_removed(self):
        pass

    def load_file(self, path, mode=0, emit_loaded=True, use_buffer=False):
        """Loads a file."""
        if path in self.file_paths:
            return True

        if not self._is_loading_multiple_files:
            self._loading_progress = 0
            self.notify('loading_progress')

        _selection_override = False
        file_basename = os.path.basename(path)

        try:
            _file = eartagfile_from_path(path)
        except:
            traceback.print_exc()
            self.error_dialog = Adw.MessageDialog(
                                    modal=True,
                                    transient_for=self.window,
                                    heading=_("Failed to load file"),
                                    body=_("Could not load file {f}. Check the logs for more information.").format(f=file_basename)
            )
            # TRANSLATORS: "Okay" button in the "failed to save file" dialog
            self.error_dialog.add_response("ok", _("OK"))
            self.error_dialog.connect('response', self.close_dialog)
            self.error_dialog.show()
            return False

        _file.connect('modified', self.update_modified_status)

        if mode == self.LOAD_OVERWRITE:
            self.files.remove_all()
            self.file_paths = []
            self.selected_files = []
            _selection_override = True

        if not self.selected_files:
            self.selected_files = []
            _selection_override = True

        if use_buffer:
            self._files_buffer.append(_file)
        else:
            self.files.append(_file)

        self.file_paths.append(_file.path)

        if emit_loaded:
            self.emit('files_loaded')
            self.update_modified_status()

            if _selection_override:
                self.emit('selection_override')

            if not _file.is_writable:
                self.window.toast_overlay.add_toast(
                    Adw.Toast.new(_("Opened file is read-only; changes cannot be saved."))
                )

        return True

    def _load_multiple_files(self, paths, mode=1):
        """Loads files with the provided paths."""
        self._files_buffer = []
        if not paths:
            self._loading_progress = 0
            self.notify('loading_progress')
            return True

        self._is_loading_multiple_files = True
        self._loading_progress = 0
        self.notify('loading_progress')
        if mode == self.LOAD_OVERWRITE:
            self.files.remove_all()
            self.file_paths = []
            self._selected_files = []

        file_count = len(paths)
        progress_step = 1 / file_count

        for path in paths:
            if self._halt_loading:
                # We don't emit "files-loaded" here because the only case where loading is
                # halted this way is if another load operation is about to begin
                self._is_loading_multiple_files = False
                return False
            if not self.load_file(path, mode=self.LOAD_INSERT, emit_loaded=False, use_buffer=True):
                self.files.splice(0, 0, self._files_buffer)
                self._files_buffer = []
                self.emit('files_loaded')
                self.update_modified_status()
                self._loading_progress = 0
                self.notify('loading_progress')
                self._is_loading_multiple_files = False
                return False
            self._loading_progress += progress_step
            self.notify('loading_progress')

        has_unwritable = False
        for file in self._files_buffer:
            if not file.is_writable:
                has_unwritable = True

        if has_unwritable:
            self.window.toast_overlay.add_toast(
                Adw.Toast.new(_("Some of the opened files are read-only; changes cannot be saved."))
            )

        self.files.splice(0, 0, self._files_buffer)
        self._files_buffer = []

        self.emit('files_loaded')
        self._loading_progress = 0
        self.notify('loading_progress')
        self.update_modified_status()
        if mode == self.LOAD_OVERWRITE:
            self.emit('selection_override')
        self._is_loading_multiple_files = False

    def load_multiple_files(self, *args, **kwargs):
        """Loads files with the provided paths."""
        if self._is_loading_multiple_files:
            self._halt_loading = True
            while self._is_loading_multiple_files:
                time.sleep(0.25)
            self._halt_loading = False
        thread = threading.Thread(target=self._load_multiple_files, daemon=True, args=args, kwargs=kwargs)
        thread.start()

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
                self.error_dialog = Adw.MessageDialog(
                                        modal=True,
                                        transient_for=self.window,
                                        heading=_("Failed to save file"),
                                        body=_("Could not save file {f}. Check the logs for more information.").format(f=file_basename)
                )
                # TRANSLATORS: "Okay" button in the "failed to save file" dialog
                self.error_dialog.add_response("ok", _("OK"))
                self.error_dialog.connect('response', self.close_dialog)
                self.error_dialog.show()
                return False

        self.window.toast_overlay.add_toast(
            Adw.Toast.new(_("Saved changes to files"))
        )
        return True

    def update_modified_status(self, *args):
        """Responsible for setting the is_modified property."""
        for file in self.files:
            if file.is_modified:
                self.set_property('is_modified', True)
                return
        self.set_property('is_modified', False)

    def remove(self, file, force_discard=False, no_emit=False, use_buffer=False):
        """Removes a file from the opened file list."""
        if file.is_modified and not force_discard:
            EartagRemovalDiscardWarningDialog(self, file).present()
            return False
        file.__del__()
        self.file_paths.remove(file.path)
        if use_buffer:
            self._removed_files_buffer.append(self.files.find(file)[1])
        else:
            self.files.remove(self.files.find(file)[1])
        if file in self.selected_files:
            if no_emit:
                self._selection_removed = True
            self._selected_files.remove(file)
            if not no_emit:
                if not self.selected_files and self.files:
                    self._selected_files.append(self.files.get_item(0))
                self.emit('selection-changed')
                self.emit('selection_override')
        if not no_emit:
            self.emit('files-removed')
            self.update_modified_status()
        return True

    def remove_multiple(self, files, force_discard=False):
        """Removes files from the opened file list."""
        self._removed_files_buffer = []
        file_count = len(files)
        if file_count == 0:
            return False
        elif file_count == 1:
            return self.remove(files[0], force_discard=force_discard)
        elif file_count == self.files.get_n_items():
            self.files.remove_all()
            self.file_paths = []
            self.selected_files = []
            self.emit('selection_changed')
            self.emit('selection_override')
            self.emit('files-removed')
            return True

        self._loading_progress = 0
        self.notify('loading_progress')
        self._selection_removed = False
        progress_step = 1 / file_count
        for file in files:
            if not self.remove(file, force_discard=force_discard, no_emit=True, use_buffer=True):
                self._loading_progress = 0
                self.notify('loading_progress')
                return False
            self._loading_progress += progress_step
            self.notify('loading_progress')

        # Split list into removed chunks, which will allow us to use .splice
        # (much faster than calling remove on each item individually)
        self._removed_files_buffer.sort()
        chunks = {}
        chunk_start = self._removed_files_buffer[0]
        prev_item = -1
        for item in self._removed_files_buffer:
            if item > prev_item + 1:
                chunks[chunk_start] = prev_item
                chunk_start = item
            prev_item = item
        chunks[chunk_start] = prev_item


        offset = 0
        for raw_chunk_start, chunk_end in chunks.items():
            chunk_start = raw_chunk_start - offset
            chunk_length = chunk_end - raw_chunk_start + 1
            offset += chunk_length

            self.files.splice(chunk_start, chunk_length, [])

        if self._selection_removed:
            self.emit('selection-changed')
            self.emit('selection_override')

        self._loading_progress = 0
        self.notify('loading_progress')

        self.emit('files-removed')
        self.update_modified_status()

        return True

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
        old_value = self._selected_files
        self._selected_files = value
        if old_value != value:
            self.emit('selection_changed')

    def select_all(self, *args):
        self.selected_files = list(self.files)

    @GObject.Property(type=float, default=0.0)
    def loading_progress(self):
        return self._loading_progress

@Gtk.Template(resource_path='/app/drey/EarTag/ui/removaldiscardwarning.ui')
class EartagRemovalDiscardWarningDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagRemovalDiscardWarningDialog'

    def __init__(self, file_manager, file):
        super().__init__(modal=True, transient_for=file_manager.window)
        self.file_manager = file_manager
        self.file = file

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == 'save':
            if not self.file_manager.save():
                return False
        if response != 'cancel':
            self.file_manager.remove(self.file, force_discard=True)
        self.file = None
        self.close()
