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

from gi.repository import Adw, Gio, GObject, GLib
import magic
import mimetypes
import os.path
import traceback

from .backends import (
    EartagFileMutagenVorbis,
    EartagFileMutagenID3,
    EartagFileMutagenMP4,
    EartagFileMutagenASF
    )
from .backends.file import EartagFile
from .common import EartagBackgroundTask
from .dialogs import (EartagRemovalDiscardWarningDialog,
    EartagLoadingFailureDialog, EartagRenameFailureDialog)

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
    elif is_type_bulk(path, ('audio/flac', 'audio/ogg', 'application/ogg', 'application/x-ogg',
            'audio/x-flac', 'audio/x-vorbis+ogg')):
        return EartagFileMutagenVorbis(path)
    elif is_type_bulk(path, ('audio/x-m4a', 'audio/aac', 'audio/mp4', 'audio/x-mpeg',
            'audio/mpeg', 'video/mp4')):
        return EartagFileMutagenMP4(path)
    elif is_type_bulk(path, ('audio/x-ms-wma', 'audio/wma', 'video/x-ms-asf')):
        return EartagFileMutagenASF(path)

    mimetypes_guess = mimetypes.guess_type(path)[0]
    magic_guess = magic.from_file(path, mime=True)
    raise ValueError(f"Unsupported file format for file {path} (mimetype: {mimetypes_guess} / {magic_guess})") # noqa: E501

class EartagFileManager(GObject.Object):
    """Contains information about the currently loaded files."""

    # Load modes
    LOAD_OVERWRITE = 0
    LOAD_INSERT = 1

    _is_modified = False
    _has_error = False
    _selected_files = []

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.files = Gio.ListStore(item_type=EartagFile)
        self.file_paths = []
        self.selected_files = []
        self._files_buffer = []
        self._modified_files = []
        self._error_files = []
        self._selection_removed = False

        # Create background task runners
        self.load_task = EartagBackgroundTask(self._load_files)
        self.rename_task = EartagBackgroundTask(self._rename_files)

    def save(self):
        """Saves changes in all files."""
        if not self.is_modified or self.has_error:
            return False

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
                                        body=_("Could not save file {f}. Check the logs for more information.").format(f=file_basename) # noqa: E501
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

    def update_modified_status(self, file, *args):
        """Responsible for setting the is_modified property."""
        if file.is_modified and file.id not in self._modified_files:
            self._modified_files.append(file.id)
        elif not file.is_modified and file.id in self._modified_files:
            self._modified_files.remove(file.id)

        self.set_property('is_modified', bool(self._modified_files))

    def update_error_status(self, file, *args):
        """Responsible for setting the has_error property."""
        if file.has_error and file.id not in self._error_files:
            self._error_files.append(file.id)
        elif not file.has_error and file.id in self._error_files:
            self._error_files.remove(file.id)

        self.set_property('has_error', bool(self._error_files))

    #
    # Loading
    #

    def load_files(self, paths, mode):
        """
        Loads files with the provided paths. This is the recommended way for
        users to load files.
        """
        # self.load_task is set up in the init functions
        self.load_task.stop()
        self.load_task.reset(kwargs={'paths': paths, 'mode': mode})

        if mode == self.LOAD_OVERWRITE and self.files:
            self.files.remove_all()
            self.file_paths = []
            self._selected_files = []

        self.load_task.run()

    def _load_single_file(self, path):
        """
        Loads a single file. Used internally in _load_multiple_files, which should be
        used for all file loading operations.
        """
        if path in self.file_paths:
            return True

        file_basename = os.path.basename(path)

        try:
            _file = eartagfile_from_path(path)
        except:
            traceback.print_exc()
            GLib.idle_add(lambda *args:
                EartagLoadingFailureDialog(self.window, file_basename).present()
            )
            return False

        _file.connect('modified', self.update_modified_status)
        _file.connect('notify::has-error', self.update_error_status)

        if not self.selected_files:
            self.selected_files = []

        self._files_buffer.append(_file)

        self.file_paths.append(_file.path)

        return True

    def _load_files(self, paths, mode=1):
        """Loads files with the provided paths."""
        task = self.load_task
        self._files_buffer = []

        if not paths:
            task.emit_task_done()
            return True

        file_count = len(paths)
        progress_step = 1 / file_count

        for path in paths:
            if task.halt:
                # We don't emit "task-done" here because the only case where loading is
                # halted this way is if another load operation is about to begin
                task.emit_task_done()
                return False

            if not self._load_single_file(path):
                self.files.splice(0, 0, self._files_buffer)
                self._files_buffer = []

                task.emit_task_done()
                GLib.idle_add(lambda *args: self.refresh_state())
                self.failed = True
                return False

            task.increment_progress(progress_step)

        has_unwritable = False
        for file in self._files_buffer:
            if not file.is_writable:
                has_unwritable = True

        if has_unwritable:
            if file_count == 1:
                unwritable_msg = _("Opened file is read-only; changes cannot be saved")
            else:
                unwritable_msg = _("Some of the opened files are read-only; changes cannot be saved") # noqa: E501
            GLib.idle_add(lambda *args: self.window.toast_overlay.add_toast(
                Adw.Toast.new(unwritable_msg)
            ))

        self.files.splice(0, 0, self._files_buffer)
        self._files_buffer = []

        task.emit_task_done()
        GLib.idle_add(lambda *args: self.refresh_state())
        if mode == self.LOAD_OVERWRITE:
            GLib.idle_add(lambda *args: self.emit('selection_override'))

    #
    # Removal
    #

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
                    self.emit('select-first')
                self.emit('selection-changed')
                self.emit('selection-override')
        if file.id in self._modified_files:
            self._modified_files.remove(file.id)
        if file.id in self._error_files:
            self._error_files.remove(file.id)
        if not no_emit:
            self.set_property('is_modified', bool(self._modified_files))
            self.set_property('has_error', bool(self._error_files))
            self.refresh_state()
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

            self.refresh_state()
            self.emit('selection-override')
            return True

        self._selection_removed = False
        for file in files:
            if not self.remove(file, force_discard=force_discard, no_emit=True, use_buffer=True):
                return False

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
            for file in self.files:
                file.setup_present_extra_tags()
            self.emit('selection-override')

        if not self.selected_files and self.files:
            self.emit('select-first')

        self.set_property('is_modified', bool(self._modified_files))
        self.set_property('has_error', bool(self._error_files))
        self.refresh_state()

        return True

    #
    # Renaming
    #

    def rename_files(self, *args, **kwargs):
        self.rename_task.wait_for_completion()
        self.rename_task.reset(args=args, kwargs=kwargs)
        self.rename_task.run()

    def _rename_files(self, files, names):
        """
        Renames multiple files and adds some harnesses to prevent potential
        data loss (for example due to overwriting an existing file).
        """
        task = self.rename_task

        progress_step = 1 / len(files)
        n = 0
        for file in files:
            old_path = file.props.path
            new_path = names[n]
            if old_path == new_path:
                n += 1
                continue

            if os.path.exists(new_path):
                _orig_new_path = new_path
                i = 0
                while os.path.exists(new_path):
                    i += 1
                    path_split = os.path.splitext(_orig_new_path)
                    new_path = path_split[0] + f' ({i})' + path_split[1]

            try:
                file.props.path = new_path
            except:
                self._is_renaming_multiple_files = False

                traceback.print_exc()
                GLib.idle_add(lambda *args:
                    EartagRenameFailureDialog(self.window, old_path).present()
                )

                task.emit_task_done()
                self.failed = True
                return False
            n += 1
            task.increment_progress(progress_step)

        task.emit_task_done()
        GLib.idle_add(lambda *args: self.refresh_state())

    def close_dialog(self, dialog, *args):
        dialog.close()

    @GObject.Property(type=bool, default=False)
    def is_modified(self):
        return self._is_modified

    @is_modified.setter
    def is_modified(self, value):
        self._is_modified = value

    @GObject.Property(type=bool, default=False)
    def has_error(self):
        return self._has_error

    @has_error.setter
    def has_error(self, value):
        self._has_error = value

    @GObject.Property
    def selected_files(self):
        return self._selected_files

    @selected_files.setter
    def selected_files(self, value):
        old_value = self._selected_files
        self._selected_files = value
        if old_value != value:
            self.emit('selection-changed')

    def select_all(self, *args):
        self.selected_files = list(self.files)

    @GObject.Signal
    def refresh_needed(self):
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
    def select_first(self):
        """See EartagFileList.handle_select_first"""
        pass

    def refresh_state(self):
        """Convenience function to refresh the state of the UI"""
        self.emit('refresh-needed')
        self.emit('selection-changed')
        self.emit('select-first')
