# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Adw, Gio, GObject, GLib, Gtk
import asyncio
import magic
import mimetypes
import os.path
import traceback

from .backends import (
    EartagFileMutagenVorbis,
    EartagFileMutagenID3,
    EartagFileMutagenMP4,
    EartagFileMutagenASF,
)
from .backends.file import EartagFile
from .utils.asynctask import EartagAsyncTask
from .utils.misc import find_in_model, cleanup_filename, natural_compare
from .dialogs import (
    EartagRemovalDiscardWarningDialog,
    EartagLoadingFailureDialog,
    EartagSaveFailureDialog,
    EartagRenameFailureDialog,
)


def eartagfile_from_path(path):
    """Returns an EartagFile subclass for the provided file."""
    if not os.path.exists(path):
        raise ValueError

    # We do two filetype guesses:
    # - One with mimetypes.guess_type; this only gets the type from the file
    #   extension;
    # - One with magic.from_file; this actually checks the file contents.
    # The magic guess is given a higher priority (2) than the mimetypes guess (1),
    # to avoid misdetections in cases where the file extension is incorrect.

    mimetypes_guess = mimetypes.guess_type(path)[0]
    magic_guess = magic.from_file(path, mime=True)

    def is_type_bulk(types):
        if magic_guess in types:
            return 2
        if mimetypes_guess in types:
            return 1
        return 0

    confidence = {
        "mp3": is_type_bulk(
            ("audio/mp3", "audio/mpeg", "audio/x-mpeg", "audio/wav", "audio/x-wav")
        ),
        "ogg": is_type_bulk(
            (
                "audio/flac",
                "audio/ogg",
                "application/ogg",
                "application/x-ogg",
                "audio/x-flac",
                "audio/x-vorbis+ogg",
            )
        ),
        "mp4": is_type_bulk(("audio/x-m4a", "audio/aac", "audio/mp4", "video/mp4")),
        "wma": is_type_bulk(("audio/x-ms-wma", "audio/wma", "video/x-ms-asf")),
    }

    filetype = sorted(
        confidence.keys(), key=lambda ftype: confidence[ftype], reverse=True
    )[0]

    if filetype == "mp3":
        return EartagFileMutagenID3(path)
    elif filetype == "ogg":
        return EartagFileMutagenVorbis(path)
    elif filetype == "mp4":
        return EartagFileMutagenMP4(path)
    elif filetype == "wma":
        return EartagFileMutagenASF(path)

    mimetypes_guess = mimetypes.guess_type(path)[0]
    magic_guess = magic.from_file(path, mime=True)

    raise ValueError(
        f"Unsupported file format for file {path} (mimetype: {mimetypes_guess} / {magic_guess})"
    )  # noqa: E501


class EartagFileManager(GObject.Object):
    """Contains information about the currently loaded files."""

    # Load modes
    LOAD_OVERWRITE = 0
    LOAD_INSERT = 1

    _is_modified = False
    _has_error = False

    def __init__(self, window):
        super().__init__()
        self.window = window

        # Set up models
        self.files = Gio.ListStore(item_type=EartagFile)

        # Set up sort model for sort button
        self.file_sort_model = Gtk.SortListModel(model=self.files)
        self.sorter = Gtk.CustomSorter.new(self.file_sort_func, None)
        self.file_sort_model.set_sorter(self.sorter)

        # Set up filter model for search
        self.file_filter_model = Gtk.FilterListModel(model=self.file_sort_model)
        self.filter = Gtk.CustomFilter.new(
            self.file_filter_func, self.file_filter_model
        )
        self._file_filter_str = ""
        self.file_filter_model.set_filter(self.filter)

        # Set up selection model for selected files handling
        self.selected_files = Gtk.MultiSelection.new(self.file_filter_model)

        self.file_paths = set()
        self._files_buffer = []
        self._modified_files = []
        self._error_files = []
        self._connections = {}
        self._selected_file_ids = []
        self._selection_removed = False

        # Create background task runners
        self.save_task = EartagAsyncTask(self._save)
        self.load_task = EartagAsyncTask(self._load_files)
        self.rename_task = EartagAsyncTask(self._rename_files)

        self.selected_files.connect("selection-changed", self.do_selection_changed)

    def update_modified_status(self, file, *args):
        """Responsible for setting the is_modified property."""
        if file.is_modified and file.id not in self._modified_files:
            self._modified_files.append(file.id)
        elif not file.is_modified and file.id in self._modified_files:
            self._modified_files.remove(file.id)

        self.set_property("is_modified", bool(self._modified_files))

    def update_error_status(self, file, *args):
        """Responsible for setting the has_error property."""
        if file.has_error and file.id not in self._error_files:
            self._error_files.append(file.id)
        elif not file.has_error and file.id in self._error_files:
            self._error_files.remove(file.id)

        self.set_property("has_error", bool(self._error_files))

    #
    # Saving
    #

    def save(self):
        """Saves changes in all files."""
        # self.save_task is set up in the init functions
        self.save_task.stop()
        self.save_task.run()

    async def _save(self):
        """Saves changes in all files (internal function)."""
        if not self.is_modified or self.has_error:
            return False

        task = self.save_task
        progress_step = 1 / self.get_n_files()

        for file in self.files:
            if not file.is_writable or not file.is_modified:
                task.increment_progress(progress_step)
                continue

            try:
                await asyncio.to_thread(file.save)
            except:
                traceback.print_exc()
                file_basename = os.path.basename(file.path)
                self.error_dialog = EartagSaveFailureDialog(file_basename)
                self.error_dialog.present(self.window)

                return False

            task.increment_progress(progress_step)

        self.window.toast_overlay.add_toast(Adw.Toast.new(_("Saved changes to files")))

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
        self.load_task.set_args(kwargs={"paths": paths, "mode": mode})

        if mode == self.LOAD_OVERWRITE and self.files:
            self.remove_all()

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
            EartagLoadingFailureDialog(file_basename).present(self.window)
            return False

        self._connections[_file.id] = (
            _file.connect("modified", self.update_modified_status),
            _file.connect("notify::has-error", self.update_error_status),
        )

        self._files_buffer.append(_file)

        self.file_paths.add(_file.path)

        return True

    async def _load_files(self, paths, mode=1):
        """Loads files with the provided paths."""
        task = self.load_task
        self._files_buffer = []

        if not paths:
            return True

        file_count = len(paths)
        progress_step = 1 / file_count

        for path in paths:
            if not await asyncio.to_thread(self._load_single_file, path):
                self.files.splice(0, 0, self._files_buffer)
                self._files_buffer = []

                self.refresh_state()
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
                unwritable_msg = _(
                    "Some of the opened files are read-only; changes cannot be saved"
                )  # noqa: E501
            self.window.toast_overlay.add_toast(Adw.Toast.new(unwritable_msg))

        self.files.splice(0, 0, self._files_buffer)
        first_file = None
        if self._files_buffer and mode == self.LOAD_INSERT:
            first_file = self._files_buffer[0]
        self._files_buffer = []

        self.refresh_state()
        if mode == self.LOAD_INSERT:
            if self.get_n_selected() < 2 and first_file:
                self.select_file(first_file, True)
        else:
            self.emit("select-first")

        if mode == self.LOAD_OVERWRITE:
            self.emit("refresh-needed")

    #
    # Removal
    #

    def _remove_file(self, file):
        """
        Removes a single file from the opened file list. Used internally in remove_files;
        use that function instead.
        """

        for connection in self._connections[file.id]:
            file.disconnect(connection)
        self.file_paths.remove(file.path)

        self._removed_files_buffer.append(self.files.find(file)[1])

        pos = find_in_model(self.file_filter_model, file)
        if pos >= 0:
            self._selection_removed = True
        if file.id in self._modified_files:
            self._modified_files.remove(file.id)
        if file.id in self._error_files:
            self._error_files.remove(file.id)

        file.on_remove()

        return True

    def remove_files(self, files, force_discard=False):
        """Removes files from the opened file list."""
        if not files:
            return True

        for file in files:
            if file.is_modified and not force_discard:
                EartagRemovalDiscardWarningDialog(self, files).present(self.window)
                return False

        self._selection_removed = False
        self._removed_files_buffer = []

        # Handle remove all scenario
        if len(files) == self.files.get_n_items():
            return self.remove_all()

        # Otherwise, remove all the files separately
        for file in files:
            if not self._remove_file(file):
                return False

        # If we only have one file, then just remove it manually
        if len(files) == 1:
            self.files.remove(self._removed_files_buffer[0])
        else:
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

        if self.get_n_selected() <= 0 and self.files:
            self.emit("select-first")

        self.set_property("is_modified", bool(self._modified_files))
        self.set_property("has_error", bool(self._error_files))
        self.refresh_state()

        self._selection_removed = False
        self._removed_files_buffer = []

        return True

    def remove_all(self):
        """Clear the opened file ist.."""
        for file in self.files:
            file.on_remove()

        self.files.remove_all()
        self.file_paths = set()
        self.selected_files.unselect_all()

        self._modified_files = []
        self._error_files = []
        self.set_property("is_modified", bool(self._modified_files))
        self.set_property("has_error", bool(self._error_files))

        self.refresh_state()

        return True

    #
    # Renaming
    #

    def rename_files(self, *args, **kwargs):
        self.rename_task.wait_for_completion()
        self.rename_task.set_args(args=args, kwargs=kwargs)
        self.rename_task.run()

    async def _rename_files(self, files, names):
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

            new_path = cleanup_filename(new_path, allow_path=True, full_path=True)

            if os.path.exists(new_path):
                _orig_new_path = new_path
                i = 0
                while os.path.exists(new_path):
                    i += 1
                    filler = f" ({i})"
                    path_split = os.path.splitext(_orig_new_path)
                    # Prevent the filename from becoming too long
                    if len(path_split[0]) > 249:
                        path_split = path_split[(-249 - len(filler)) :]
                    new_path = path_split[0] + filler + path_split[1]
            else:
                if not os.path.exists(os.path.dirname(new_path)):
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)

            try:
                await file.set_path_async(new_path)
            except:
                self._is_renaming_multiple_files = False

                traceback.print_exc()
                EartagRenameFailureDialog(old_path).present(self.window)

                self.failed = True
                return False

            file.notify("path")

            try:
                self.file_paths.remove(old_path)
            except KeyError:
                pass
            self.file_paths.add(new_path)

            n += 1
            task.increment_progress(progress_step)

        self.refresh_state()

    #
    # File list sort and filter
    #

    @GObject.Property(type=str, default="")
    def file_filter_str(self):
        """String for the file filter."""
        return self._file_filter_str

    @file_filter_str.setter
    def file_filter_str(self, value: str):
        self._file_filter_str = value
        self.filter.changed(Gtk.FilterChange.DIFFERENT)

    def file_filter_func(self, file, *args):
        """Custom filter for file search."""
        query = self.props.file_filter_str
        if not query:
            return True
        query = query.casefold()

        if query in file.title.casefold():
            return True

        if query in file.artist.casefold():
            return True

        if query in file.album.casefold():
            return True

        if query in os.path.basename(file.path).casefold():
            return True

        return False

    def file_sort_func(self, a, b, *args):
        """Custom sort function implementation for file sorting."""

        # Step 1. Compare album names
        a_album = GLib.utf8_casefold(a.albumsort or a.album or "", -1)
        b_album = GLib.utf8_casefold(b.albumsort or b.album or "", -1)
        collate = natural_compare(a_album, b_album)

        # Step 2. Compare track numbers
        if collate == 0:
            if (a.tracknumber or -1) > (b.tracknumber or -1):
                collate = 1
            elif (a.tracknumber or -1) < (b.tracknumber or -1):
                collate = -1

        # Step 3. If the result is inconclusive, compare filenames
        if collate == 0:
            a_filename = GLib.utf8_casefold(os.path.basename(a.path), -1)
            b_filename = GLib.utf8_casefold(os.path.basename(b.path), -1)
            collate = natural_compare(a_filename, b_filename)

        return collate

    def get_n_files(self):
        return self.files.get_n_items()

    def select_all(self, *args):
        self.selected_files.select_all()

    def unselect_all(self, *args):
        self.selected_files.unselect_all()

    def select_file(self, file, unselect_other: bool = False):
        pos = find_in_model(self.file_filter_model, file)
        if pos >= 0:
            self.selected_files.select_item(pos, unselect_other)

    def unselect_file(self, file):
        pos = find_in_model(self.file_filter_model, file)
        if pos >= 0:
            self.selected_files.unselect_item(pos)

    def is_selected(self, file):
        pos = find_in_model(self.file_filter_model, file)
        if pos >= 0:
            return self.selected_files.is_selected(pos)
        return False

    def get_n_selected(self):
        return self.selected_files.get_selection().get_size()

    def do_selection_changed(self, *args):
        if args:
            self._selected_file_ids = [file.id for file in self.selected_files]
            self.emit("selection-changed")

    def all_selected(self):
        return self.get_n_selected() == self.selected_files.get_n_items()

    @property
    def selected_files_list(self):
        out = []
        for i in range(self.file_filter_model.get_n_items()):
            if self.selected_files.is_selected(i):
                out.append(self.file_filter_model.get_item(i))
        return out

    @GObject.Signal
    def selection_changed(self):
        self.notify("is-selected-modified")

    @GObject.Signal
    def selection_override(self):
        """
        Internal signal used to communicate selection overrides to the sidebar.
        """
        pass

    @GObject.Signal
    def select_first(self):
        """See EartagFileList.handle_select_first"""
        self.selected_files.select_item(0, True)

    def get_first_selected(self):
        """Returns the position of the first selected item."""
        selected = self.selected_files.get_selection()
        if selected.get_size() < 1:
            return -1
        return selected.get_nth(0)

    def select_next(self, *args):
        """Selects the next item on the sidebar."""
        if self.selected_files.get_n_items() <= 1 or self.get_n_selected() > 1:
            return

        selected = self.get_first_selected()
        if selected < 0:
            return

        if selected + 1 >= self.selected_files.get_n_items():
            self.selected_files.select_item(0, True)
        else:
            self.selected_files.select_item(selected + 1, True)

    def select_previous(self, *args):
        """Selects the previous item on the sidebar."""
        if self.selected_files.get_n_items() <= 1 or self.get_n_selected() > 1:
            return

        selected = self.get_first_selected()
        if selected < 0:
            return

        if selected - 1 >= 0:
            self.selected_files.select_item(selected - 1, True)
        else:
            self.selected_files.select_item(self.selected_files.get_n_items() - 1, True)

    #
    # Miscelaneous
    #

    def close_dialog(self, dialog, *args):
        dialog.close()

    @GObject.Property(type=bool, default=False)
    def is_modified(self):
        return self._is_modified

    @is_modified.setter
    def is_modified(self, value):
        self._is_modified = value
        self.notify("is-selected-modified")

    @GObject.Property(type=bool, default=False)
    def is_selected_modified(self) -> bool:
        for file_id in self._modified_files:
            if file_id in self._selected_file_ids:
                return True
        return False

    @GObject.Property(type=bool, default=False)
    def has_error(self):
        return self._has_error

    @has_error.setter
    def has_error(self, value):
        self._has_error = value

    @GObject.Signal
    def refresh_needed(self):
        pass

    def refresh_state(self):
        """Convenience function to refresh the state of the UI"""
        self.emit("refresh-needed")
