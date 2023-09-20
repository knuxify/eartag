# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from .config import config, DLCoverSize
from .utils.validation import is_valid_music_file, VALID_AUDIO_MIMES
from .dialogs import EartagCloseWarningDialog, EartagDiscardWarningDialog
from .musicbrainz import MusicBrainzRelease
from .fileview import EartagFileView # noqa: F401
from .filemanager import EartagFileManager
from .filelist import EartagFileList, EartagFileListItem  # noqa: F401
from .rename import EartagRenameDialog
from .identify import EartagIdentifyDialog
from .utils import find_in_model

from gi.repository import Adw, Gdk, GLib, Gtk, Gio, GObject
import os
import gettext

@Gtk.Template(resource_path='/app/drey/EarTag/ui/nofile.ui')
class EartagNoFile(Adw.Bin):
    __gtype_name__ = 'EartagNoFile'

    open_file = Gtk.Template.Child()

    def __init__(self):
        super().__init__()

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

@Gtk.Template(resource_path='/app/drey/EarTag/ui/window.ui')
class EartagWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'EartagWindow'

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

    def __init__(self, application, paths=None):
        super().__init__(application=application, title='Ear Tag')

        self.file_chooser = Gtk.FileDialog(modal=True)
        self._cancellable = Gio.Cancellable.new()

        self.audio_file_filter = Gtk.FileFilter()
        for mime in VALID_AUDIO_MIMES:
            self.audio_file_filter.add_mime_type(mime)
        self.audio_file_filter.set_name(_("All supported audio files"))

        self.file_manager = EartagFileManager(self)
        self.file_view.set_file_manager(self.file_manager)
        self.file_manager.connect('notify::is-modified', self.toggle_save_button)
        self.file_manager.connect('notify::has-error', self.toggle_save_button)
        self.file_manager.files.connect('items-changed', self.toggle_fileview)
        self.file_manager.connect('refresh-needed', self.update_state)
        self.file_manager.connect('selection-changed', self.update_state)
        self.file_manager.load_task.connect('notify::progress', self.update_loading_progress)
        self.search_bar.bind_property(
            'search-mode-enabled',
            self.sidebar_search_button, 'active',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.select_multiple_button.bind_property('active', self, 'selection-mode',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.select_multiple_button.bind_property('active', self.sidebar_action_bar, 'revealed',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )

        self.connect('close-request', self.on_close_request)

        self.drop_target = Gtk.DropTarget(
            actions=Gdk.DragAction.COPY,
            formats=Gdk.ContentFormats.new_for_gtype(Gdk.FileList)
            )
        self.drop_target.connect('accept', self.on_drag_accept)
        self.drop_target.connect('enter', self.on_drag_hover)
        self.drop_target.connect('leave', self.on_drag_unhover)
        self.drop_target.connect('drop', self.on_drag_drop)
        self.add_controller(self.drop_target)

        self.toggle_fileview()

        self.connect('realize', self._late_init)

        # Sidebar setup
        self.sidebar_file_list.set_file_manager(self.file_manager)
        self.sidebar_list_stack.set_visible_child(self.sidebar_no_files)
        self.sidebar_file_list.set_sidebar(self)

        self.search_bar.set_key_capture_widget(self)
        self.search_bar.connect_entry(self.search_entry)
        self.search_entry.connect('search-changed', self.search_changed)

        self.file_manager.connect('refresh-needed', self.refresh_actionbar_button_state)
        self.file_manager.files.connect('items-changed', self.refresh_actionbar_button_state)
        self.file_manager.connect('selection-changed', self.refresh_actionbar_button_state)
        self.file_manager.load_task.connect('notify::progress', self.update_loading_progressbar)
        self.refresh_actionbar_button_state()

        if paths:
            self.file_manager.load_files(paths, mode=EartagFileManager.LOAD_OVERWRITE)

    def _late_init(self, *args):
        self.file_view.setup_resize_handler()

    def update_loading_progress(self, task, *args):
        loading_progress = task.progress
        is_loading = loading_progress != 0
        self.sidebar_headerbar.set_sensitive(not is_loading)
        if self.file_manager.files.get_n_items() == 0 and is_loading:
            self.container_stack.set_visible_child(self.split_view)

    def update_state(self, *args):
        # Set up the active view (hide fileview if there are no selected files)
        selected_files_count = len(self.file_manager.selected_files)
        if selected_files_count <= 0:
            try:
                self.get_application().rename_action.set_enabled(False)
                self.get_application().identify_action.set_enabled(False)
            except AttributeError:
                return
            self.set_title('Ear Tag')
            self.window_title.set_subtitle('')
            if self.file_manager.files:
                self.file_view.content_stack.set_visible_child(self.file_view.select_file)

            self.run_sort()
            return False
        else:
            files = self.file_manager.selected_files

        self.file_view.content_stack.set_visible_child(self.file_view.content_scroll)

        # Set up window title and file info label
        if len(files) == 1:
            file = files[0]
            file_basename = os.path.basename(file.path)
            self.set_title('{f} — Ear Tag'.format(f=file_basename))
            self.window_title.set_subtitle(file_basename)
        else:
            # TRANSLATOR: Placeholder for file path when multiple files are selected
            _multiple_files = _('(Multiple files selected)')
            self.set_title('{f} — Ear Tag'.format(f=_multiple_files))
            self.window_title.set_subtitle(_multiple_files)

        try:
            self.get_application().rename_action.set_enabled(True)
            self.get_application().identify_action.set_enabled(True)
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
            self.sidebar_headerbar.set_sensitive(self.file_manager.load_task.progress in (0, 1))
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

    def show_file_chooser(self, folders=False):
        """Shows the file chooser."""
        if self.file_chooser_mode is not None:
            return

        if folders:
            title = _("Open Folder")
            self.file_chooser_mode = 'folders'
        else:
            title = _("Open File")
            self.file_chooser_mode = 'files'

        self.file_chooser.set_title(title)

        if not folders:
            _filters = Gio.ListStore.new(Gtk.FileFilter)
            _filters.append(self.audio_file_filter)
            self.file_chooser.set_filters(_filters)

        if folders:
            self.file_chooser.select_multiple_folders(self, self._cancellable,
                self.open_file_from_dialog)
        else:
            self.file_chooser.open_multiple(self, self._cancellable,
                self.open_file_from_dialog)

    def open_files(self, paths):
        """
        Loads the files with the given paths. Note that this does not perform
        any validation; caller functions are meant to check for this manually.
        """
        if self.open_mode != EartagFileManager.LOAD_INSERT and self.file_manager._is_modified:
            self.discard_warning = EartagDiscardWarningDialog(self, paths)
            self.discard_warning.show()
            return False

        self.file_manager.load_files(paths, mode=self.open_mode)

    def open_file_from_dialog(self, dialog, result):
        """
        Callback for a FileChooser that takes the response and opens the file
        selected in the dialog.
        """
        try:
            if self.file_chooser_mode == 'folders':
                response = dialog.select_multiple_folders_finish(result)
            elif self.file_chooser_mode == 'files':
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
            self.save_button.set_tooltip_text(_("Some of the opened files have invalid values; cannot save")) # noqa: E501
        else:
            self.save_button.set_tooltip_text('')
        self.save_button.set_sensitive(
                self.file_manager.is_modified and not self.file_manager.has_error
        )

    @Gtk.Template.Callback()
    def show_sidebar(self, *args):
        self.split_view.set_reveal_flap(True)
        self.sidebar_file_list.grab_focus()

    @Gtk.Template.Callback()
    def hide_sidebar(self, *args):
        self.split_view.set_reveal_flap(False)

    @Gtk.Template.Callback()
    def run_sort(self, *args):
        if self.file_manager.files:
            self.sidebar_file_list.sorter.changed(Gtk.SorterChange.DIFFERENT)

    @Gtk.Template.Callback()
    def on_save(self, *args):
        if not self.file_manager.save():
            return False

    @Gtk.Template.Callback()
    def insert_file(self, *args):
        self.open_mode = EartagFileManager.LOAD_INSERT
        self.show_file_chooser()

    def on_close_request(self, *args):
        if not self.force_close and list(self.file_manager.files) and \
                self.file_manager._is_modified:
            self.close_request_dialog = EartagCloseWarningDialog(self)
            self.close_request_dialog.present()
            return True

        MusicBrainzRelease.clear_tempfiles()

        for file in self.file_manager.files:
            file.on_remove()

    def show_rename_dialog(self, *args):
        self.rename_dialog = EartagRenameDialog(self)
        self.rename_dialog.present()

    def show_identify_dialog(self, *args):
        self.identify_dialog = EartagIdentifyDialog(self)
        self.identify_dialog.present()

    def show_settings_dialog(self, *args):
        self.settings_dialog = EartagSettingsWindow(self)
        self.settings_dialog.present()

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
        self.sidebar_file_list.filter.changed(Gtk.FilterChange.DIFFERENT)

        if self.sidebar_file_list.filter_model.get_n_items() == 0 and \
                self.file_manager.files.get_n_items() > 0:
            self.sidebar_list_stack.set_visible_child(self.no_results)
        else:
            self.toggle_fileview()

        selected = self.sidebar_file_list.selection_model.get_selected()
        # TODO: some weird bug where a null selected value is read as 4294967295
        # (looks like someone forgot to make an unsigned int signed...)
        has_no_selected = selected < 0 or selected >= 4294967295
        if not self.selection_mode and has_no_selected and self.file_manager.selected_files:
            new_selection = find_in_model(self.sidebar_file_list.filter_model,
                self.file_manager.selected_files[0])
            if new_selection > -1:
                self.sidebar_file_list.selection_model.set_selected(new_selection)

        # Scroll back to top of list
        vadjust = self.sidebar_file_list.get_vadjustment()
        vadjust.set_value(vadjust.get_lower())

        # Update the switcher buttons in the fileview
        self.get_native().file_view.update_buttons()

    def toggle_selection_mode(self, *args):
        self.sidebar_file_list.toggle_selection_mode()

    @Gtk.Template.Callback()
    def select_all(self, *args):
        if self.sidebar_file_list.all_selected():
            self.sidebar_file_list.unselect_all()
        else:
            self.sidebar_file_list.select_all()

    @Gtk.Template.Callback()
    def remove_selected(self, *args):
        old_selected = self.file_manager.selected_files.copy()
        self.file_manager.remove_files(old_selected)

    def refresh_actionbar_button_state(self, *args):
        if not self.file_manager.files or not self.selection_mode:
            selected_message = ''
            self.sidebar_action_bar.set_sensitive(False)
            self.sidebar_action_bar.set_revealed(False)
        else:
            self.sidebar_action_bar.set_sensitive(True)
            self.sidebar_action_bar.set_revealed(True)
            selected_file_count = len(self.file_manager.selected_files)
            if selected_file_count == 0:
                selected_message = _('No files selected')
                self.remove_selected_button.set_sensitive(False)
            else:
                selected_message = gettext.ngettext(
                    "1 file selected", "{n} files selected", selected_file_count).\
                        format(n=selected_file_count)
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
        if self.sidebar_file_list.selection_model.get_n_items() <= 1 or self.selection_mode:
            return
        selected = self.sidebar_file_list.selection_model.get_selected()
        if selected + 1 >= self.sidebar_file_list.selection_model.get_n_items():
            self.sidebar_file_list.selection_model.set_selected(0)
        else:
            self.sidebar_file_list.selection_model.set_selected(selected + 1)

    def select_previous(self, *args):
        """Selects the previous item on the sidebar."""
        if self.sidebar_file_list.selection_model.get_n_items() <= 1 or self.selection_mode:
            return
        selected = self.sidebar_file_list.selection_model.get_selected()
        if selected - 1 >= 0:
            self.sidebar_file_list.selection_model.set_selected(selected - 1)
        else:
            self.sidebar_file_list.selection_model.set_selected(
                self.sidebar_file_list.selection_model.get_n_items() - 1
            )

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

@Gtk.Template(resource_path='/app/drey/EarTag/ui/settings.ui')
class EartagSettingsWindow(Adw.PreferencesWindow):
    __gtype_name__ = 'EartagSettingsWindow'

    mb_confidence_spinbutton = Gtk.Template.Child()
    aid_confidence_spinbutton = Gtk.Template.Child()
    cover_size_comborow = Gtk.Template.Child()

    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=True)

        config.bind(
            'musicbrainz-confidence-treshold',
            self.mb_confidence_spinbutton, 'value',
            flags=Gio.SettingsBindFlags.DEFAULT
        )
        config.bind(
            'acoustid-confidence-treshold',
            self.aid_confidence_spinbutton, 'value',
            flags=Gio.SettingsBindFlags.DEFAULT
        )

        self.bind_property('cover-size-setting', self.cover_size_comborow, 'selected',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )

    @GObject.Property(type=int)
    def cover_size_setting(self):
        if config.get_enum('musicbrainz-cover-size') == 0:
            return 0
        elif config.get_enum('musicbrainz-cover-size') == 250:
            return 1
        elif config.get_enum('musicbrainz-cover-size') == 500:
            return 2
        elif config.get_enum('musicbrainz-cover-size') == 1200:
            return 3
        return 4

    @cover_size_setting.setter
    def cover_size_setting(self, value):
        config.set_enum('musicbrainz-cover-size', int(DLCoverSize.index_to_item(value)))
