# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from .config import config, DLCoverSize
from .utils.bgtask import EartagBackgroundTask, run_threadsafe
from .utils.validation import is_valid_music_file, VALID_AUDIO_MIMES
from .dialogs import (
    EartagCloseWarningDialog,
    EartagDiscardWarningDialog,
    EartagTagDeleteWarningDialog,
)
from .musicbrainz import MusicBrainzRelease
from .fileview import EartagFileView  # noqa: F401
from .filemanager import EartagFileManager
from .filelist import EartagFileList, EartagFileListItem  # noqa: F401
from .rename import EartagRenameDialog
from .identify import EartagIdentifyDialog
from .extract import EartagExtractTagsDialog
from . import APP_GRESOURCE_PATH, DEVEL

from gi.repository import Adw, Gdk, GLib, Gtk, Gio, GObject
import os
import gettext


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/nofile.ui")
class EartagNoFile(Adw.Bin):
    __gtype_name__ = "EartagNoFile"

    nofile_status = Gtk.Template.Child()
    open_file = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        if DEVEL:
            self.nofile_status.set_icon_name("app.drey.EarTag.Devel")

    def grab_button_focus(self, *args):
        self.open_file.grab_focus()

    @Gtk.Template.Callback()
    def on_add_file(self, *args):
        window = self.get_native()
        window.open_mode = EartagFileManager.LOAD_OVERWRITE
        window.show_file_chooser(folders=False)

    @Gtk.Template.Callback()
    def on_add_folder(self, *args):
        window = self.get_native()
        window.open_mode = EartagFileManager.LOAD_OVERWRITE
        window.show_file_chooser(folders=True)


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/window.ui")
class EartagWindow(Adw.ApplicationWindow):
    __gtype_name__ = "EartagWindow"

    save_button = Gtk.Template.Child()
    window_title = Gtk.Template.Child()
    container_stack = Gtk.Template.Child()
    split_view = Gtk.Template.Child()

    sidebar_view = Gtk.Template.Child()
    sidebar_headerbar = Gtk.Template.Child()
    sidebar_search_button = Gtk.Template.Child()
    select_multiple_button = Gtk.Template.Child()
    sort_button = Gtk.Template.Child()

    no_file = Gtk.Template.Child()
    file_view = Gtk.Template.Child()

    no_file_widget = Gtk.Template.Child()

    toast_overlay = Gtk.Template.Child()
    overlay = Gtk.Template.Child()
    drop_highlight_revealer = Gtk.Template.Child()

    primary_menu_button = Gtk.Template.Child()
    empty_primary_menu_button = Gtk.Template.Child()

    force_close = False
    file_chooser_mode = None

    open_mode = EartagFileManager.LOAD_OVERWRITE

    # Sidebar
    sidebar_list_stack = Gtk.Template.Child()
    sidebar_list_scroll = Gtk.Template.Child()
    sidebar_file_list = Gtk.Template.Child()
    sidebar_no_files = Gtk.Template.Child()

    search_bar = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    no_results = Gtk.Template.Child()

    sidebar_action_bar = Gtk.Template.Child()
    select_all_button = Gtk.Template.Child()
    remove_selected_button = Gtk.Template.Child()
    selected_message_label = Gtk.Template.Child()

    loading_progressbar = Gtk.Template.Child()
    loading_progressbar_revealer = Gtk.Template.Child()

    def __init__(self, application, paths=None, devel=False):
        super().__init__(application=application, title="Ear Tag")
        self._undo_all_data = {}

        if devel:
            self.add_css_class("devel")

        self.file_chooser = Gtk.FileDialog(modal=True)
        self._cancellable = Gio.Cancellable.new()

        self.audio_file_filter = Gtk.FileFilter()
        for mime in VALID_AUDIO_MIMES:
            self.audio_file_filter.add_mime_type(mime)
        self.audio_file_filter.set_name(_("All supported audio files"))

        self.file_manager = EartagFileManager(self)
        self.file_view.set_file_manager(self.file_manager)
        self.file_manager.connect("notify::is-modified", self.toggle_save_button)
        self.file_manager.connect("notify::has-error", self.toggle_save_button)
        self.file_manager.connect(
            "notify::is-selected-modified", self.toggle_undo_all_action
        )
        self.file_manager.files.connect("items-changed", self.toggle_fileview)
        self.file_manager.connect("refresh-needed", self.update_state)
        self.file_manager.connect("selection-changed", self.update_state)
        self.file_manager.load_task.connect(
            "notify::progress", self.update_loading_progress
        )
        self.search_bar.bind_property(
            "search-mode-enabled",
            self.sidebar_search_button,
            "active",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )
        self.select_multiple_button.bind_property(
            "active",
            self,
            "selection-mode",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )
        self.select_multiple_button.bind_property(
            "active",
            self.sidebar_action_bar,
            "revealed",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )

        self.connect("close-request", self.on_close_request)

        self.drop_target = Gtk.DropTarget(
            actions=Gdk.DragAction.COPY,
            formats=Gdk.ContentFormats.new_for_gtype(Gdk.FileList),
        )
        self.drop_target.connect("accept", self.on_drag_accept)
        self.drop_target.connect("enter", self.on_drag_hover)
        self.drop_target.connect("leave", self.on_drag_unhover)
        self.drop_target.connect("drop", self.on_drag_drop)
        self.add_controller(self.drop_target)

        self.toggle_fileview()

        # Tasks for undo/redo all option
        self._undo_all_count = 0
        self.undo_all_task = EartagBackgroundTask(self._undo_all)
        self.undo_all_task.connect("task-done", self._undo_all_done)

        self._redo_all_count = 0
        self.redo_all_task = EartagBackgroundTask(self._redo_all)
        self.redo_all_task.connect("task-done", self._redo_all_done)

        # Task for delete all tags option

        self._delete_all_tags_count = 0
        self.delete_all_tags_task = EartagBackgroundTask(self._delete_all_tags)
        self.delete_all_tags_task.connect("task-done", self._delete_all_tags_done)

        self._undo_delete_all_count = 0
        self.undo_delete_all_tags_task = EartagBackgroundTask(
            self._undo_delete_all_tags
        )
        self.undo_delete_all_tags_task.connect(
            "task-done", self._undo_delete_all_tags_done
        )

        # Sidebar setup
        self.sidebar_file_list.set_file_manager(self.file_manager)
        self.sidebar_list_stack.set_visible_child(self.sidebar_no_files)

        self.search_bar.set_key_capture_widget(self)
        self.search_bar.connect_entry(self.search_entry)
        self.search_entry.connect("search-changed", self.search_changed)

        self.file_manager.connect("refresh-needed", self.refresh_actionbar_button_state)
        self.file_manager.files.connect(
            "items-changed", self.refresh_actionbar_button_state
        )
        self.file_manager.connect(
            "selection-changed", self.refresh_actionbar_button_state
        )
        self.file_manager.load_task.connect(
            "notify::progress", self.update_loading_progressbar
        )
        self.refresh_actionbar_button_state()

        if paths:
            self.file_manager.load_files(paths, mode=EartagFileManager.LOAD_OVERWRITE)

    def update_loading_progress(self, task, *args):
        loading_progress = task.progress
        is_loading = loading_progress != 0
        self.sidebar_headerbar.set_sensitive(not is_loading)
        if self.file_manager.files.get_n_items() == 0 and is_loading:
            self.container_stack.set_visible_child(self.split_view)

    def update_state(self, *args):
        app = self.get_application()

        # Set up the active view (hide fileview if there are no selected files)
        selected_files_count = self.file_manager.get_n_selected()
        if selected_files_count <= 0:
            try:
                for action in (
                    app.rename_action,
                    app.extract_action,
                    app.identify_action,
                    app.undo_all_action,
                    app.delete_all_tags_action,
                ):
                    action.set_enabled(False)
            except AttributeError:
                return
            self.set_title("Ear Tag")
            self.window_title.set_subtitle("")
            if self.file_manager.files:
                self.file_view.content_stack.set_visible_child(
                    self.file_view.select_file
                )

            self.run_sort()
            return False
        else:
            files = self.file_manager.selected_files_list

        self.file_view.content_stack.set_visible_child(self.file_view.content_scroll)

        # Set up window title and file info label
        if len(files) == 1:
            file = files[0]
            file_basename = os.path.basename(file.path)
            self.set_title("{f} — Ear Tag".format(f=file_basename))
            self.window_title.set_subtitle(file_basename)
        else:
            # TRANSLATORS: Placeholder for file path when multiple files are selected.
            # Shows up in the titlebar of the application.
            _multiple_files = _("(Multiple files selected)")
            self.set_title("{f} — Ear Tag".format(f=_multiple_files))
            self.window_title.set_subtitle(_multiple_files)

        is_modified = False
        for file in files:
            if file.is_modified:
                is_modified = True
                break

        try:
            app.undo_all_action.set_enabled(is_modified)
            for action in (
                app.rename_action,
                app.extract_action,
                app.identify_action,
                app.delete_all_tags_action,
            ):
                action.set_enabled(True)
        except AttributeError:
            pass

        self.toggle_save_button()

        self.file_view.update_binds()

    def toggle_fileview(self, *args):
        """
        Shows/hides the fileview/"no files" message depending on opened files.
        """
        if self.file_manager.files.get_n_items() > 0:
            self.container_stack.set_visible_child(self.split_view)
            self.sidebar_headerbar.set_sensitive(
                self.file_manager.load_task.progress in (0, 1)
            )
            self.sidebar_list_stack.set_visible_child(self.sidebar_list_scroll)
        else:
            self.container_stack.set_visible_child(self.no_file)
            self.no_file_widget.grab_button_focus()
            self.sidebar_headerbar.set_sensitive(False)
            self.sidebar_list_stack.set_visible_child(self.sidebar_no_files)
            if self.selection_mode:
                self.select_multiple_button.set_active(False)

    def on_drag_accept(self, target, drop, *args):
        drop.read_value_async(Gdk.FileList, 0, None, self.verify_files_valid)
        return True

    def verify_files_valid(self, drop, task, *args):
        try:
            files = drop.read_value_finish(task).get_files()
        except GLib.GError:
            self.drop_target.reject()
            self.on_drag_unhover()
            return False
        for file in files:
            path = file.get_path()
            if not is_valid_music_file(path):
                self.drop_target.reject()
                self.on_drag_unhover()

    def on_drag_hover(self, *args):
        self.drop_highlight_revealer.set_visible(True)
        self.drop_highlight_revealer.set_reveal_child(True)
        self.drop_highlight_revealer.set_can_target(True)
        return Gdk.DragAction.COPY

    def on_drag_unhover(self, *args):
        self.drop_highlight_revealer.set_reveal_child(False)
        self.drop_highlight_revealer.set_can_target(False)

    def on_drag_drop(self, drop_target, value, *args):
        files = value.get_files()
        paths = []
        for file in files:
            paths.append(file.get_path())
        self.open_mode = EartagFileManager.LOAD_INSERT
        self.open_files(paths)
        self.open_mode = EartagFileManager.LOAD_OVERWRITE
        self.on_drag_unhover()

    @Gtk.Template.Callback()
    def drop_highlight_autohide(self, revealer, *args):
        """Sets the drop highlight to be invisible."""
        revealer.set_visible(revealer.props.child_revealed)

    def show_file_chooser(self, folders=False):
        """Shows the file chooser."""
        if self.file_chooser_mode is not None:
            return

        if folders:
            title = _("Open Folder")
            self.file_chooser_mode = "folders"
        else:
            title = _("Open File")
            self.file_chooser_mode = "files"

        self.file_chooser.set_title(title)

        if not folders:
            _filters = Gio.ListStore.new(Gtk.FileFilter)
            _filters.append(self.audio_file_filter)
            self.file_chooser.set_filters(_filters)

        if folders:
            self.file_chooser.select_multiple_folders(
                self, self._cancellable, self.open_file_from_dialog
            )
        else:
            self.file_chooser.open_multiple(
                self, self._cancellable, self.open_file_from_dialog
            )

    def open_files(self, paths):
        """
        Loads the files with the given paths. Note that this does not perform
        any validation; caller functions are meant to check for this manually.
        """
        if (
            self.open_mode != EartagFileManager.LOAD_INSERT
            and self.file_manager._is_modified
        ):
            self.discard_warning = EartagDiscardWarningDialog(self.file_manager, paths)
            self.discard_warning.present(self)
            return False

        self.file_manager.load_files(paths, mode=self.open_mode)

    def open_file_from_dialog(self, dialog, result):
        """
        Callback for a FileChooser that takes the response and opens the file
        selected in the dialog.
        """
        try:
            if self.file_chooser_mode == "folders":
                response = dialog.select_multiple_folders_finish(result)
            elif self.file_chooser_mode == "files":
                response = dialog.open_multiple_finish(result)
            else:
                self.file_chooser_mode = None
                return False
        except GLib.GError:
            self.file_chooser_mode = None
            return False

        self.file_chooser_mode = None

        if not response:
            return

        paths = []
        for file in response:
            _path = file.get_path()
            if os.path.isdir(_path):
                for _file in os.listdir(_path):
                    _fpath = os.path.join(_path, _file)
                    if os.path.isfile(_fpath) and is_valid_music_file(_fpath):
                        paths.append(_fpath)
            else:
                paths.append(_path)
        if not paths:
            toast = Adw.Toast.new(_("No supported files found in opened folder"))
            self.toast_overlay.add_toast(toast)
            return
        return self.open_files(paths)

    def toggle_save_button(self, *args):
        if self.file_manager.has_error:
            self.save_button.set_tooltip_text(
                _("Some of the opened files have invalid values; cannot save")
            )  # noqa: E501
        else:
            self.save_button.set_tooltip_text("")

        self.save_button.set_sensitive(
            self.file_manager.is_modified and not self.file_manager.has_error
        )

    @Gtk.Template.Callback()
    def show_sidebar(self, *args):
        self.split_view.set_show_sidebar(True)
        self.sidebar_file_list.grab_focus()

    @Gtk.Template.Callback()
    def hide_sidebar(self, *args):
        self.split_view.set_show_sidebar(False)

    @Gtk.Template.Callback()
    def run_sort(self, *args):
        if self.file_manager.files.get_n_items():
            self.file_manager.sorter.changed(Gtk.SorterChange.DIFFERENT)

    @Gtk.Template.Callback()
    def on_save(self, *args):
        if not self.file_manager.save():
            return False

    @Gtk.Template.Callback()
    def insert_file(self, *args):
        self.open_mode = EartagFileManager.LOAD_INSERT
        self.show_file_chooser()

    def on_close_request(self, *args):
        if (
            not self.force_close
            and list(self.file_manager.files)
            and self.file_manager._is_modified
        ):
            self.close_request_dialog = EartagCloseWarningDialog(self.file_manager)
            self.close_request_dialog.present(self)
            return True

        MusicBrainzRelease.clear_tempfiles()

        for file in self.file_manager.files:
            file.on_remove()

        self.clear_redo_data()
        self.clear_delete_all_tags_undo_data()

        self.file_view.on_close()

    def show_rename_dialog(self, *args):
        self.rename_dialog = EartagRenameDialog(self.file_manager)
        self.rename_dialog.present(self)

    def show_identify_dialog(self, *args):
        self.identify_dialog = EartagIdentifyDialog(self)
        self.identify_dialog.present(self)

    def show_preferences_dialog(self, *args):
        self.preferences_dialog = EartagPreferencesDialog()
        self.preferences_dialog.present(self)

    def show_extract_dialog(self, *args):
        self.extract_dialog = EartagExtractTagsDialog(self)
        self.extract_dialog.present(self)

    def show_delete_all_tags_dialog(self, *args):
        self.delete_all_tags_dialog = EartagTagDeleteWarningDialog(self)
        self.delete_all_tags_dialog.present(self)

    # Sidebar

    def update_loading_progressbar(self, task, *args):
        """
        Updates the loading progressbar's position.
        """
        loading_progress = task.progress
        self.loading_progressbar_revealer.set_reveal_child(not loading_progress == 0)
        self.set_sensitive(loading_progress == 0)
        self.sidebar_file_list.set_visible(loading_progress == 0)
        self.loading_progressbar.set_fraction(loading_progress)

    def search_changed(self, search_entry, *args):
        """Emitted when the search has changed."""
        self.file_manager.props.file_filter_str = search_entry.get_text()
        n_results = self.file_manager.file_filter_model.get_n_items()

        if n_results == 0 and self.file_manager.files.get_n_items() > 0:
            self.sidebar_list_stack.set_visible_child(self.no_results)
        else:
            self.toggle_fileview()

        if (
            not self.selection_mode
            and not self.file_manager.get_n_selected()
            and n_results
        ):
            self.file_manager.select_file(self.file_manager.file_filter_model[0])

        # Scroll back to top of list
        vadjust = self.sidebar_file_list.get_vadjustment()
        vadjust.set_value(vadjust.get_lower())

        # Update the switcher buttons in the fileview
        self.get_native().file_view.update_buttons()

    def toggle_selection_mode(self, *args):
        self.sidebar_file_list.toggle_selection_mode()

    @Gtk.Template.Callback()
    def select_all(self, *args):
        if self.file_manager.all_selected() and self.file_manager.get_n_selected() != 1:
            self.file_manager.unselect_all()
        else:
            self.file_manager.select_all()

    @Gtk.Template.Callback()
    def remove_selected(self, *args):
        self.sidebar_file_list.remove_selected()

    def refresh_actionbar_button_state(self, *args):
        if not self.file_manager.files or not self.selection_mode:
            selected_message = ""
            self.sidebar_action_bar.set_sensitive(False)
            self.sidebar_action_bar.set_revealed(False)
        else:
            self.sidebar_action_bar.set_sensitive(True)
            self.sidebar_action_bar.set_revealed(True)
            selected_file_count = self.file_manager.get_n_selected()
            if selected_file_count == 0:
                selected_message = _("No files selected")
                self.remove_selected_button.set_sensitive(False)
            else:
                # TRANSLATORS: {n} is a placeholder for the amount of files.
                # **Do not change the letter between the curly brackets!**
                selected_message = gettext.ngettext(
                    "1 file selected", "{n} files selected", selected_file_count
                ).format(n=selected_file_count)
                self.remove_selected_button.set_sensitive(True)

        self.selected_message_label.set_label(selected_message)

    @GObject.Property(type=bool, default=False)
    def selection_mode(self):
        """Whether the sidebar is in selection mode or not."""
        return self.sidebar_file_list.selection_mode

    @selection_mode.setter
    def selection_mode(self, value):
        self.sidebar_file_list.selection_mode = value
        # Workaround for the text not showing up on initial load
        self.refresh_actionbar_button_state()

    def select_next(self, *args):
        """Selects the next item on the sidebar."""
        return self.file_manager.select_next()

    def select_previous(self, *args):
        """Selects the previous item on the sidebar."""
        return self.file_manager.select_previous()

    def scroll_to_top(self):
        """Scrolls to the top of the file list."""
        GLib.idle_add(self._scroll_to_top)

    def _scroll_to_top(self):
        self.sidebar_list_scroll.get_vadjustment().set_value(0)

    def scroll_to_index(self, index):
        """Scrolls to file at the specified index."""
        GLib.idle_add(self._scroll_to_index, index)

    def _scroll_to_index(self, index):
        item_height = self.sidebar_file_list.get_first_child().get_height()
        vadjust = self.sidebar_list_scroll.get_vadjustment()
        new_value = item_height * (index + 1)
        if new_value <= vadjust.get_upper():
            vadjust.set_value(new_value)
        else:
            vadjust.set_value(vadjust.get_upper())

    # Undo all option

    def undo_all(self, *args):
        self.set_sensitive(False)
        self.undo_all_task.reset()
        self.undo_all_task.run()

    def _undo_all(self, *args):
        """Undo all changes and add the option to re-do them."""
        self._undo_all_data = {}
        self._undo_all_count = 0
        for file in self.file_manager.selected_files_list:
            if not file.is_modified:
                continue
            self._undo_all_count += 1

            self._undo_all_data[file.id] = {}
            for tag in file.modified_tags:
                self._undo_all_data[file.id][tag] = file.get_property(tag)

            run_threadsafe(file.undo_all)

        if self._undo_all_count == 0:
            self.undo_all_task.emit_task_done()
            return

        self.undo_all_task.emit_task_done()

    def _undo_all_done(self, *args):
        self.file_view.more_tags_group.slow_refresh_entries()
        self.set_sensitive(True)

        toast = Adw.Toast.new(
            # TRANSLATORS: {n} is a placeholder for the amount of files.
            # **Do not change the letter between the curly brackets!**
            gettext.ngettext(
                "Undid changes in 1 file",
                "Undid changes in {n} files",
                self._undo_all_count,
            ).format(n=self._undo_all_count)
        )
        toast.props.button_label = _("Redo")
        toast.connect("button-clicked", self.redo_all)
        # toast.connect('dismissed', self.clear_redo_data)
        self.toast_overlay.add_toast(toast)

    def redo_all(self, *args):
        self.set_sensitive(False)
        self.redo_all_task.reset()
        self.redo_all_task.run()

    def _redo_all(self, *args):
        """Reverses undo_all."""
        self._redo_all_count = 0
        for file in self.file_manager.files:
            if file.id in self._undo_all_data:
                self._redo_all_count += 1
                for tag, value in self._undo_all_data[file.id].items():
                    if tag in file.int_properties + file.float_properties and not value:
                        run_threadsafe(file.set_property, tag, 0)
                    else:
                        run_threadsafe(file.set_property, tag, value)

        self.redo_all_task.emit_task_done()

    def _redo_all_done(self, *args):
        self.file_view.more_tags_group.slow_refresh_entries()
        self.set_sensitive(True)
        toast = Adw.Toast.new(
            # TRANSLATORS: {n} is a placeholder for the amount of files.
            # **Do not change the letter between the curly brackets!**
            gettext.ngettext(
                "Redid changes in 1 file",
                "Redid changes in {n} files",
                self._redo_all_count,
            ).format(n=self._redo_all_count)
        )
        self.toast_overlay.add_toast(toast)

    def clear_redo_data(self, *args):
        """Clears the redo data for the "undo all" option."""
        self._undo_all_data = {}

    def toggle_undo_all_action(self, *args):
        app = self.get_application()
        try:
            app.undo_all_action.set_enabled(
                self.file_manager.props.is_selected_modified
            )
        except AttributeError:
            pass

    # "Delete all tags" option
    def do_delete_all_tags(self, *args):
        self.set_sensitive(False)
        self.delete_all_tags_task.reset()
        self.delete_all_tags_task.run()

    def _delete_all_tags(self, *args):
        """Undo all changes and add the option to re-do them."""
        self._delete_all_tags_undo_data = {}
        files = self.file_manager.selected_files_list.copy()
        self._delete_all_tags_count = len(files)
        for file in files:
            self._delete_all_tags_undo_data[file.id] = {}
            for prop in file.modified_tags:
                self._delete_all_tags_undo_data[file.id][prop] = file.get_property(prop)
            run_threadsafe(file.delete_all_raw)

        self.delete_all_tags_task.emit_task_done()

    def _delete_all_tags_done(self, *args):
        self.file_view.more_tags_group.slow_refresh_entries()
        self.set_sensitive(True)

        toast = Adw.Toast.new(
            # TRANSLATORS: {n} is a placeholder for the amount of files
            # that tags have been removed from.
            # **Do not change the letter between the curly brackets!**
            gettext.ngettext(
                "Removed tags from 1 file",
                "Removed tags from {n} files",
                self._delete_all_tags_count,
            ).format(n=self._delete_all_tags_count)
        )
        toast.props.button_label = _("Undo")
        toast.connect("button-clicked", self.undo_delete_all_tags)
        # toast.connect('dismissed', self.clear_delete_all_tags_undo_data)
        self.toast_overlay.add_toast(toast)

    def undo_delete_all_tags(self, *args):
        self.set_sensitive(False)
        self.undo_delete_all_tags_task.reset()
        self.undo_delete_all_tags_task.run()

    def _undo_delete_all_tags(self, *args):
        """Reverses undo_all."""
        self._undo_delete_all_count = 0
        for file in self.file_manager.files:
            if file.id in self._delete_all_tags_undo_data:
                self._undo_delete_all_count += 1
                file.reload(thread_safe=True)
                for prop, value in self._delete_all_tags_undo_data[file.id].items():
                    run_threadsafe(file.set_property, prop, value)

        self.undo_delete_all_tags_task.emit_task_done()

    def _undo_delete_all_tags_done(self, *args):
        self.file_view.more_tags_group.slow_refresh_entries()
        self.set_sensitive(True)

        toast = Adw.Toast.new(
            # TRANSLATORS: {n} is a placeholder for the amount of files.
            # **Do not change the letter between the curly brackets!**
            gettext.ngettext(
                "Undid tag removal in 1 file",
                "Undid tag removal in {n} files",
                self._undo_delete_all_count,
            ).format(n=self._undo_delete_all_count)
        )
        self.toast_overlay.add_toast(toast)

    def clear_delete_all_tags_undo_data(self, *args):
        self._delete_all_tags_undo_data = {}


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/settings.ui")
class EartagPreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = "EartagPreferencesDialog"

    mb_confidence_spinbutton = Gtk.Template.Child()
    aid_confidence_spinbutton = Gtk.Template.Child()
    cover_size_comborow = Gtk.Template.Child()

    def __init__(self):
        super().__init__()

        config.bind(
            "musicbrainz-confidence-treshold",
            self.mb_confidence_spinbutton,
            "value",
            flags=Gio.SettingsBindFlags.DEFAULT,
        )
        config.bind(
            "acoustid-confidence-treshold",
            self.aid_confidence_spinbutton,
            "value",
            flags=Gio.SettingsBindFlags.DEFAULT,
        )

        self.bind_property(
            "cover-size-setting",
            self.cover_size_comborow,
            "selected",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )

    @GObject.Property(type=int)
    def cover_size_setting(self):
        if config.get_enum("musicbrainz-cover-size") == 0:
            return 0
        elif config.get_enum("musicbrainz-cover-size") == 250:
            return 1
        elif config.get_enum("musicbrainz-cover-size") == 500:
            return 2
        elif config.get_enum("musicbrainz-cover-size") == 1200:
            return 3
        return 4

    @cover_size_setting.setter
    def cover_size_setting(self, value):
        config.set_enum("musicbrainz-cover-size", int(DLCoverSize.index_to_item(value)))
