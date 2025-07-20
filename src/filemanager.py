# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Gio, GObject, GLib, Gtk
import asyncio
import aiofiles
import aiofiles.os
import mimetypes
import os.path
import stat

from .backends import (
    EartagFileMutagenVorbis,
    EartagFileMutagenID3,
    EartagFileMutagenMP4,
    EartagFileMutagenASF,
)
from .backends.file import EartagFile
from .config import config
from .utils.asynctask import EartagAsyncMultitasker
from .utils.misc import find_in_model, cleanup_filename, natural_compare, iter_selection_model
from .utils.validation import (
    get_mimetype_async,
    is_valid_music_file_async,
)
from .dialogs import EartagRemovalDiscardWarningDialog


async def eartagfile_from_path(path):
    """Returns an EartagFile subclass for the provided file."""
    if not os.path.exists(path):
        raise ValueError

    # We do two filetype guesses:
    # - One with mimetypes.guess_type; this only gets the type from the file
    #   extension;
    # - One with get_mimetype; this actually checks the file contents.
    # The magic guess is given a higher priority (2) than the mimetypes guess (1),
    # to avoid misdetections in cases where the file extension is incorrect.

    mimetypes_guess = mimetypes.guess_type(path)[0]
    magic_guess = await get_mimetype_async(path, no_extension_guess=True)

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

    filetype = sorted(confidence.keys(), key=lambda ftype: confidence[ftype], reverse=True)[0]

    if filetype == "mp3":
        return await EartagFileMutagenID3.new_from_path(path)
    elif filetype == "ogg":
        return await EartagFileMutagenVorbis.new_from_path(path)
    elif filetype == "mp4":
        return await EartagFileMutagenMP4.new_from_path(path)
    elif filetype == "wma":
        return await EartagFileMutagenASF.new_from_path(path)

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
        self.filter = Gtk.CustomFilter.new(self.file_filter_func, self.file_filter_model)
        self._file_filter_str = ""
        self.file_filter_model.set_filter(self.filter)

        # Set up selection model for selected files handling
        self.selected_files = Gtk.MultiSelection.new(self.file_filter_model)

        self.file_paths = set()
        self._files_buffer = []
        self._modified_files = []
        self._error_files = []
        self._connections = {}
        self._selected_file_ids = set()
        self._selection_removed = False
        self._is_selected_cache: dict[str, bool] = {}

        # Create Multitaskers for queued operations
        self.load_task = EartagAsyncMultitasker(self._load_single_file, workers=3)
        self.load_task.connect("task-done", self.on_file_load)
        self.load_task.connect("notify::is-running", self.notify_busy)

        self.save_task = EartagAsyncMultitasker(self._save_single_file, workers=3)
        self.save_task.connect("notify::is-running", self.notify_busy)

        self.rename_task = EartagAsyncMultitasker(self._rename_single_file, workers=3)
        self.rename_task.connect("task-done", self.refresh_state)
        self.rename_task.connect("notify::is-running", self.notify_busy)

        self.selected_files.connect("selection-changed", self._on_selection_changed)

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
        if not self.is_modified or self.has_error:
            return

        # self.save_task is set up in the init functions
        self.save_task.spawn_workers()
        self.save_task.queue_put_multiple(
            [f for f in self.files if f.is_writable and f.is_modified], mark_as_done=True
        )

    async def save_async(self) -> bool:
        """
        Async wrapper for the save function, allows for waiting for
        the saving process to end.

        Returns True if there were no errors, False otherwise.
        """
        if not self.is_modified:
            return True
        if self.has_error:
            return False

        self.save_task.spawn_workers()
        self.save_task.queue_put_multiple(
            [f for f in self.files if f.is_writable and f.is_modified], mark_as_done=True
        )
        await self.save_task.wait_for_completion_async()

        if self.save_task.errors:
            return False
        return True

    async def _save_single_file(self, file):
        """Saves changes in a single file."""
        return await asyncio.to_thread(file.save)

    #
    # Loading
    #

    max_recursion_depth_reached = GObject.Signal()

    def load_files(self, paths: list, overwrite: bool = False):
        """
        Loads files or folders from the provided paths.
        """
        asyncio.create_task(self.load_files_async(paths, overwrite=overwrite))

    async def load_files_async(self, paths: list, overwrite: bool = False):
        """
        Loads files or folders from the provided paths.
        """
        # If we're doing an open-with-overwrite, clear all files first
        if overwrite:
            self._load_mode = EartagFileManager.LOAD_OVERWRITE
            self.remove_all()
        else:
            self._load_mode = EartagFileManager.LOAD_INSERT

        # Spawn file loader process
        self.load_task.spawn_workers()

        # Fill the loading queue with paths
        dirs = set()
        for path in paths:
            _stat = await aiofiles.os.stat(path)
            if stat.S_ISREG(_stat.st_mode):
                await self.load_task.queue_put_async(path)
            elif stat.S_ISDIR(_stat.st_mode):
                dirs.add(path)

        if config["open-folders-recursively"]:
            MAX_DEPTH = 10
        else:
            MAX_DEPTH = 1

        depth = 0
        while dirs and depth < MAX_DEPTH:
            new_dirs = set()

            for path in dirs:
                for file in await aiofiles.os.listdir(path):
                    fpath = os.path.join(path, file)
                    _stat = await aiofiles.os.stat(fpath)
                    if stat.S_ISDIR(_stat.st_mode):
                        new_dirs.add(fpath)
                    elif stat.S_ISREG(_stat.st_mode) and await is_valid_music_file_async(fpath):
                        await self.load_task.queue_put_async(fpath)

            dirs = new_dirs
            depth += 1

        if MAX_DEPTH != 1 and dirs and depth >= MAX_DEPTH:
            self.emit("max-recursion-depth-reached")

        # Signify that the queue is done
        self.load_task.queue_done()

    async def _load_single_file(self, path):
        """
        Loads a single file. Used internally in _load_multiple_files, which should be
        used for all file loading operations.
        """
        if path in self.file_paths:
            return True

        _file = await eartagfile_from_path(path)

        self._connections[_file.id] = (
            _file.connect("modified", self.update_modified_status),
            _file.connect("notify::has-error", self.update_error_status),
        )

        self.files.append(_file)
        self._files_buffer.append(_file)
        self.file_paths.add(_file.path)

        return True

    def on_file_load(self, *args):
        """
        Actions done after file loading is done.

        This is called automatically after the loading task is done running.
        """
        asyncio.create_task(self.on_file_load_async())

    async def on_file_load_async(self):
        """
        Actions done after file loading is done.

        This is called automatically after the loading task is done running.
        """
        has_unwritable = False
        for file in self._files_buffer:
            if not file.is_writable:
                has_unwritable = True

        if has_unwritable:
            self.emit("has-unwritable")

        first_file = None
        if self._files_buffer:
            first_file = self._files_buffer[0]
        self._files_buffer = []

        self.refresh_state()
        if self._load_mode == self.LOAD_INSERT:
            if self.get_n_selected() < 2 and first_file:
                self.select_file(first_file, True)
        else:
            self.emit("select-first")

        del first_file

        if self._load_mode == self.LOAD_OVERWRITE:
            self.emit("refresh-needed")

    has_unwritable = GObject.Signal()

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

    def rename_files(self, files, names):
        """Rename each file in the files list to the name in the names list."""
        self.rename_task.spawn_workers()
        if len(files) != len(names):
            raise ValueError("file and name lists are not of equal length")

        self.rename_task.queue_put_multiple(
            [(files[i], names[i]) for i in range(len(files))], mark_as_done=True
        )

    async def _rename_single_file(self, rename_info):
        """
        Rename a single file, with some harnesses to prevent potential
        data loss (for example due to overwriting an existing file).
        """
        file, new_path = rename_info

        old_path = file.props.path
        if old_path == new_path:
            return

        new_path = cleanup_filename(new_path, allow_path=True, full_path=True)

        def _new_path_fixups(new_path: str):
            if os.path.exists(new_path):
                orig_new_path = new_path
                i = 0
                while os.path.exists(new_path):
                    i += 1
                    filler = f" ({i})"
                    path_split = os.path.splitext(orig_new_path)
                    # Prevent the filename from becoming too long
                    if len(path_split[0]) > 249:
                        path_split = path_split[(-249 - len(filler)) :]
                    new_path = path_split[0] + filler + path_split[1]
            else:
                if not os.path.exists(os.path.dirname(new_path)):
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
            return new_path

        new_path = await asyncio.to_thread(_new_path_fixups, new_path)
        await file.set_path_async(new_path)

        file.notify("path")

        try:
            self.file_paths.remove(old_path)
        except KeyError:
            pass
        self.file_paths.add(new_path)

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
        return file.id in self._selected_file_ids

    def get_n_selected(self):
        return self.selected_files.get_selection().get_size()

    def _on_selection_changed(
        self, selection_model: Gtk.SelectionModel, position: int, n_items: int
    ):
        for i in range(position, position + n_items):
            file = self.selected_files.get_item(i)
            is_selected = self.selected_files.is_selected(i)

            if not is_selected and file.id in self._selected_file_ids:
                self._selected_file_ids.remove(file.id)
            elif is_selected:
                self._selected_file_ids.add(file.id)

        self.emit("selection-changed")

    def all_selected(self):
        return self.get_n_selected() == self.selected_files.get_n_items()

    @property
    def selected_files_list(self):
        return [file for file in iter_selection_model(self.selected_files)]

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

    @GObject.Property(type=bool, default=False)
    def is_busy(self):
        return self.load_task.is_running or self.save_task.is_running or self.rename_task.is_running

    def notify_busy(self, *args):
        self.notify("is-busy")

    @GObject.Signal
    def refresh_needed(self):
        pass

    def refresh_state(self, *args):
        """Convenience function to refresh the state of the UI"""
        self.emit("refresh-needed")
