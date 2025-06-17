# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from .config import config, DLCoverSize
from .utils.asynctask import EartagAsyncTask
from .utils.validation import is_valid_music_file, VALID_AUDIO_MIMES
from .dialogs import (
    EartagErrorType,
    EartagErrorDialog,
    EartagCloseWarningDialog,
    EartagDiscardWarningDialog,
    EartagTagDeleteWarningDialog,
)
from .musicbrainz import EartagCAACover
from .fileview import EartagFileView  # noqa: F401
from .filemanager import EartagFileManager
from .filelist import EartagFileList, EartagFileListItem  # noqa: F401
from .rename import EartagRenameDialog
from .identify import EartagIdentifyDialog
from .extract import EartagExtractTagsDialog
from . import APP_GRESOURCE_PATH, DEVEL

import asyncio
from gi.repository import Adw, Gdk, GLib, Gtk, Gio, GObject
import os
import gettext
from enum import Flag


class EartagFileDialogType(Flag):
    """Types of file opening dialogs."""

    # Dialog type - file or folder
    TYPE_FILE = 1
    TYPE_FOLDER = 2

    # Load mode - overwrite (clear all and load) or insert (append to current)
    MODE_OVERWRITE = 4
    MODE_INSERT = 8


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
        window.show_file_chooser(
            EartagFileDialogType.TYPE_FILE | EartagFileDialogType.MODE_OVERWRITE
        )

    @Gtk.Template.Callback()
    def on_add_folder(self, *args):
        window = self.get_native()
        window.show_file_chooser(
            EartagFileDialogType.TYPE_FOLDER | EartagFileDialogType.MODE_OVERWRITE
        )


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
        super().__init__(application=application, title=_("Ear Tag"))
        self._undo_all_data = {}
        self.error_dialog = None

        if devel:
            self.add_css_class("devel")

        self.set_icon_name(application.get_application_id())

        self.file_chooser = Gtk.FileDialog(modal=True)

        self.audio_file_filter = Gtk.FileFilter()
        for mime in VALID_AUDIO_MIMES:
            self.audio_file_filter.add_mime_type(mime)
        self.audio_file_filter.set_name(_("All supported audio files"))

        # File manager setup
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
        self.file_manager.connect("notify::is-busy", self.update_busy)
        self.file_manager.connect("refresh-needed", self.refresh_actionbar_button_state)
        self.file_manager.files.connect(
            "items-changed", self.refresh_actionbar_button_state
        )
        self.file_manager.connect("has-unwritable", self.show_unwritable_toast)
        self.file_manager.connect(
            "selection-changed", self.refresh_actionbar_button_state
        )

        self.file_manager.load_task.connect(
            "progress-pulse", self.loading_progressbar_pulse
        )
        self.file_manager.load_task.connect(
            "notify::progress", self.update_loading_progressbar
        )
        self.file_manager.load_task.connect(
            "task-done", self.task_done_handler, EartagErrorType.ERROR_LOAD
        )

        self.file_manager.save_task.connect(
            "notify::progress", self.update_loading_progressbar
        )
        self.file_manager.save_task.connect(
            "task-done", self.task_done_handler, EartagErrorType.ERROR_SAVE
        )

        self.file_manager.rename_task.connect(
            "task-done", self.task_done_handler, EartagErrorType.ERROR_RENAME
        )

        self.show_error_action = Gio.SimpleAction.new(
            "show-error-dialog", GLib.VariantType.new("(is)")
        )
        self.show_error_action.connect("activate", self._show_error_action)
        self.add_action(self.show_error_action)

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
        self.undo_all_task = EartagAsyncTask(self._undo_all)
        self.undo_all_task.connect("task-done", self._undo_all_done)

        self._redo_all_count = 0
        self.redo_all_task = EartagAsyncTask(self._redo_all)
        self.redo_all_task.connect("task-done", self._redo_all_done)

        # Task for delete all tags option
        self._delete_all_tags_count = 0
        self.delete_all_tags_task = EartagAsyncTask(self._delete_all_tags)
        self.delete_all_tags_task.connect("task-done", self._delete_all_tags_done)

        self._undo_delete_all_count = 0
        self.undo_delete_all_tags_task = EartagAsyncTask(self._undo_delete_all_tags)
        self.undo_delete_all_tags_task.connect(
            "task-done", self._undo_delete_all_tags_done
        )

        # Sidebar setup
        self.sidebar_file_list.set_file_manager(self.file_manager)
        self.sidebar_list_stack.set_visible_child(self.sidebar_no_files)

        self.search_bar.set_key_capture_widget(self)
        self.search_bar.connect_entry(self.search_entry)
        self.search_entry.connect("search-changed", self.search_changed)

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
        self.sidebar_file_list.connect(
            "notify::selection-mode", self.update_selection_mode
        )

        self.refresh_actionbar_button_state()

        if paths:
            self.file_manager.load_files(paths, mode=EartagFileManager.LOAD_OVERWRITE)

    def update_busy(self, task, *args):
        """
        Mark the window as busy or not busy based on whether the file manager
        is currently processing a long operation (opening/saving/renaming files).

        Also handles showing error dialogs.
        """
        busy = self.file_manager.is_busy

        self.sidebar_headerbar.set_sensitive(not busy)
        self.loading_progressbar_revealer.set_reveal_child(busy)
        self.sidebar_file_list.set_sensitive(not busy)
        self.file_view.content_clamp.set_sensitive(not busy)

        if self.file_manager.load_task.is_running:
            self.file_view.set_visible_child(self.file_view.loading)
        else:
            self.file_view.set_visible_child(self.file_view.content_stack)

        if self.file_manager.files.get_n_items() == 0:
            if busy:
                self.container_stack.set_visible_child(self.split_view)
            else:
                self.container_stack.set_visible_child(self.no_file)

    def show_error_dialog(self, error_type: EartagErrorType, error_message: str):
        """Show an error dialog with logs."""
        error_dialog = EartagErrorDialog(error_type, error_message)
        error_dialog.present(self)

    def _show_error_action(self, action: Gio.Action, data: GLib.Variant):
        """Wrapper around show_error_dialog for the win.show-error-dialog option."""
        error_type_int = data.get_child_value(0).get_int32()
        error_message = data.get_child_value(1).get_string()
        return self.show_error_dialog(EartagErrorType(error_type_int), error_message)

    def task_done_handler(self, task, error_type: EartagErrorType):
        """
        Handle a long file manager task (opening, saving or renaming) being done.

        The type of task that finished can be derived from the error_type parameter.
        """

        # If the task encountered an error, show an error dialog
        if task.errors:
            error_message = "\n---\n".join(task.errors)
            if self.file_manager.files.get_n_items() == 0:
                self.show_error_dialog(error_type, error_message)
            else:
                param = GLib.Variant.new_tuple(
                    GLib.Variant.new_int32(int(error_type)),
                    GLib.Variant.new_string(error_message),
                )
                toast = Adw.Toast.new(_("Some files failed to load"))
                toast.props.button_label = _("More Information")
                toast.props.action_name = "win.show-error-dialog"
                toast.props.action_target = param
                self.toast_overlay.add_toast(toast)

        # Handle file loading not detecting any supported files
        if error_type == EartagErrorType.ERROR_LOAD:
            if self.file_manager.load_task.n_items == 0:
                toast = Adw.Toast.new(_("No supported files found in opened folder"))
                self.toast_overlay.add_toast(toast)

        # Handle saving being done
        if error_type == EartagErrorType.ERROR_SAVE:
            saved_file_count = self.file_manager.save_task.n_items - len(
                self.file_manager.load_task.errors
            )
            save_message = ngettext(
                "Saved changes to 1 file",
                "Saved changes to {n} files",
                saved_file_count,
            ).format(n=saved_file_count)

            self.window.toast_overlay.add_toast(
                Adw.Toast.new(_("Saved changes to {n} files"))
            )

    def show_unwritable_toast(self, *args):
        """Show a toast saying that some files are read-only."""
        unwritable_msg = _(
            "Some of the opened files are read-only; changes cannot be saved"
        )  # noqa: E501
        self.window.toast_overlay.add_toast(Adw.Toast.new(unwritable_msg))

    def update_state(self, *args):
        app = self.get_application()

        # Set up the active view (hide fileview if there are no selected files)
        selected_files_count = self.file_manager.get_n_selected()

        if selected_files_count == self.file_manager.get_n_files():
            self.select_all_button.set_icon_name("edit-select-none-symbolic")
            self.select_all_button.set_tooltip_text(_("Unselect all files"))
        else:
            self.select_all_button.set_icon_name("edit-select-all-symbolic")
            self.select_all_button.set_tooltip_text(_("Select all files"))

        if selected_files_count <= 0:
            try:
                for action in (
                    app.sort_action,
                    app.rename_action,
                    app.extract_action,
                    app.identify_action,
                    app.undo_all_action,
                    app.delete_all_tags_action,
                ):
                    action.set_enabled(False)
            except AttributeError:
                return
            self.set_title(_("Ear Tag"))
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
        _title = _("Ear Tag")
        if len(files) == 1:
            file = files[0]
            file_basename = os.path.basename(file.path)
            self.set_title("{f} — {title}".format(f=file_basename, title=_title))
            self.window_title.set_subtitle(file_basename)
        else:
            # TRANSLATORS: Placeholder for file path when multiple files are selected.
            # Shows up in the titlebar of the application.
            _multiple_files = _("(Multiple files selected)")
            self.set_title("{f} — {title}".format(f=_multiple_files, title=_title))
            self.window_title.set_subtitle(_multiple_files)

        is_modified = False
        for file in files:
            if file.is_modified:
                is_modified = True
                break

        try:
            app.undo_all_action.set_enabled(is_modified)
            for action in (
                app.sort_action,
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
            if not os.path.isdir(path) and not is_valid_music_file(path):
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
        self.file_manager.load_files([f.get_path() for f in files], overwrite=False)
        self.on_drag_unhover()

    @Gtk.Template.Callback()
    def drop_highlight_autohide(self, revealer, *args):
        """Sets the drop highlight to be invisible."""
        revealer.set_visible(revealer.props.child_revealed)

    async def show_file_chooser_async(self, chooser: EartagFileDialogType):
        """Show the file chooser dialog and get files from it."""

        # Set up title and check for chooser type validity
        if chooser & EartagFileDialogType.TYPE_FILE:
            if chooser & EartagFileDialogType.MODE_OVERWRITE:
                #: TRANSLATORS: Title of the popup for opening a file
                self.file_chooser.props.title = _("Open File")
            elif chooser & EartagFileDialogType.MODE_INSERT:
                self.file_chooser.props.title = _("Add File")
            else:
                raise ValueError

        elif chooser & EartagFileDialogType.TYPE_FOLDER:
            if chooser & EartagFileDialogType.MODE_OVERWRITE:
                self.file_chooser.props.title = _("Open Folder")
            else:
                raise ValueError

        else:
            raise ValueError

        # Set up filters for file selectors
        if chooser & EartagFileDialogType.TYPE_FILE:
            _filters = Gio.ListStore.new(Gtk.FileFilter)
            _filters.append(self.audio_file_filter)
            self.file_chooser.set_filters(_filters)
        else:
            self.file_chooser.set_filters(None)

        # If we're doing an overwrite load, warn about discarding changes
        if (
            chooser & EartagFileDialogType.MODE_OVERWRITE
            and self.file_manager._is_modified
        ):
            self.discard_warning = EartagDiscardWarningDialog()
            self.discard_warning.present(self)
            response = await self.discard_warning.wait_for_response()

            if response == "cancel":
                del self.discard_warning
                return
            elif response == "save":
                self.file_manager.save()

            del self.discard_warning

        # Display the dialog
        try:
            if chooser & EartagFileDialogType.TYPE_FOLDER:
                gfiles = await self.file_chooser.select_multiple_folders(self, None)
            else:
                gfiles = await self.file_chooser.open_multiple(self, None)
        except GLib.GError:
            return

        await self.file_manager.load_files_async(
            [f.get_path() for f in gfiles],
            overwrite=bool(chooser & EartagFileDialogType.MODE_OVERWRITE),
        )

    def show_file_chooser(self, chooser: EartagFileDialogType):
        """Non-async wrapper around show_file_chooser_async."""
        asyncio.create_task(self.show_file_chooser_async(chooser))

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

    def run_sort(self, *args):
        if self.file_manager.files.get_n_items():
            self.file_manager.sorter.changed(Gtk.SorterChange.DIFFERENT)

    @Gtk.Template.Callback()
    def on_save(self, *args):
        if not self.file_manager.save():
            return False

    @Gtk.Template.Callback()
    def insert_file(self, *args):
        self.show_file_chooser(
            EartagFileDialogType.TYPE_FILE | EartagFileDialogType.MODE_INSERT
        )

    def on_close_request(self, *args):
        if (
            not self.force_close
            and list(self.file_manager.files)
            and self.file_manager._is_modified
        ):
            self.close_request_dialog = EartagCloseWarningDialog(
                self, self.file_manager
            )
            self.close_request_dialog.present(self)
            return True

        EartagCAACover.clear_tempfiles()

        for file in self.file_manager.files:
            file.on_remove()

        self.clear_redo_data()
        self.clear_delete_all_tags_undo_data()

        self.file_view.on_close()

    def show_rename_dialog(self, *args):
        self.rename_dialog = EartagRenameDialog(self)
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
        """Updates the loading progressbar's position."""
        self.loading_progressbar.set_fraction(task.progress)

    def loading_progressbar_pulse(self, task, *args):
        """Updates the loading progressbar's pulse."""
        self.loading_progressbar.pulse()

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
                selected_message = ngettext(
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

    def update_selection_mode(self, filelist, *args):
        self.notify("selection-mode")
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
        self.sidebar_list_scroll.get_vadjustment().set_value(0)

    def scroll_to_index(self, index):
        """Scrolls to file at the specified index."""
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
        self.undo_all_task.run()

    async def _undo_all(self, *args):
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

            file.undo_all()

    def _undo_all_done(self, *args):
        self.file_view.more_tags_group.slow_refresh_entries()
        self.set_sensitive(True)

        toast = Adw.Toast.new(
            # TRANSLATORS: {n} is a placeholder for the amount of files.
            # **Do not change the letter between the curly brackets!**
            ngettext(
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
        self.redo_all_task.run()

    async def _redo_all(self, *args):
        """Reverses undo_all."""
        self._redo_all_count = 0
        for file in self.file_manager.files:
            if file.id in self._undo_all_data:
                self._redo_all_count += 1
                for tag, value in self._undo_all_data[file.id].items():
                    if tag in file.int_properties + file.float_properties and not value:
                        file.set_property(tag, 0)
                    else:
                        file.set_property(tag, value)

    def _redo_all_done(self, *args):
        self.file_view.more_tags_group.slow_refresh_entries()
        self.set_sensitive(True)
        toast = Adw.Toast.new(
            # TRANSLATORS: {n} is a placeholder for the amount of files.
            # **Do not change the letter between the curly brackets!**
            ngettext(
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
        self.delete_all_tags_task.run()

    async def _delete_all_tags(self, *args):
        """Undo all changes and add the option to re-do them."""
        self._delete_all_tags_undo_data = {}
        files = self.file_manager.selected_files_list.copy()
        self._delete_all_tags_count = len(files)
        for file in files:
            self._delete_all_tags_undo_data[file.id] = {}
            for prop in file.modified_tags:
                self._delete_all_tags_undo_data[file.id][prop] = file.get_property(prop)
            file.delete_all_raw()

    def _delete_all_tags_done(self, *args):
        self.file_view.more_tags_group.slow_refresh_entries()
        self.set_sensitive(True)

        toast = Adw.Toast.new(
            # TRANSLATORS: {n} is a placeholder for the amount of files
            # that tags have been removed from.
            # **Do not change the letter between the curly brackets!**
            ngettext(
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
        self.undo_delete_all_tags_task.run()

    async def _undo_delete_all_tags(self, *args):
        """Reverses undo_all."""
        self._undo_delete_all_count = 0
        for file in self.file_manager.files:
            if file.id in self._delete_all_tags_undo_data:
                self._undo_delete_all_count += 1
                await file.reload()
                for prop, value in self._delete_all_tags_undo_data[file.id].items():
                    file.set_property(prop, value)

    def _undo_delete_all_tags_done(self, *args):
        self.file_view.more_tags_group.slow_refresh_entries()
        self.set_sensitive(True)

        toast = Adw.Toast.new(
            # TRANSLATORS: {n} is a placeholder for the amount of files.
            # **Do not change the letter between the curly brackets!**
            ngettext(
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
