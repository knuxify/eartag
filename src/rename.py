# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from .backends.file import BASIC_TAGS, EXTRA_TAGS, TAG_NAMES
from .config import config
from .utils import get_readable_length
from .utils.tagsyntaxhighlight import EartagPlaceholderSyntaxHighlighter
from . import APP_GRESOURCE_PATH

from gi.repository import Adw, GLib, Gtk, Gdk, Gio, GObject
import os

def parse_placeholder_string(string, file):
    """
    Takes a string with tag placeholders and replaces them with the provided
    file's data.
    """
    output = string
    for tag in BASIC_TAGS + file.supported_extra_tags + ('length', 'bitrate'):
        if tag == 'title':
            null_value = 'Untitled'
        elif tag in file.int_properties + file.float_properties:
            null_value = 0
        else:
            null_value = 'Unknown ' + TAG_NAMES[tag]

        if tag in file.int_properties + file.float_properties + ('length', 'bitrate'):
            value = file.get_property(tag)
            if not value or value < 0:
                value = 0
            if tag == 'length':
                tag_replaced = get_readable_length(int(value))
            elif tag == 'tracknumber' or tag == 'totaltracknumber':
                tag_replaced = str(value).zfill(2)
            else:
                tag_replaced = str(value)
        else:
            value = file.get_property(tag)
            if not value:
                tag_replaced = null_value
            else:
                tag_replaced = str(value).replace('/', '_')
        output = output.replace('{' + tag + '}', tag_replaced)
    if output in (',', '.', '..'):
        output = '_'
    return output

@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/rename.ui')
class EartagRenameDialog(Adw.Window):
    __gtype_name__ = 'EartagRenameDialog'

    toast_overlay = Gtk.Template.Child()

    rename_button = Gtk.Template.Child()
    rename_progress = Gtk.Template.Child()
    error_banner = Gtk.Template.Child()

    filename_entry = Gtk.Template.Child()
    preview_entry = Gtk.Template.Child()

    _last_folder = None

    folder_selector_row = Gtk.Template.Child()
    folder_remove_button = Gtk.Template.Child()

    validation_passed = GObject.Property(type=bool, default=True)

    tag_list = Gtk.Template.Child()
    tag_list_popover = Gtk.Template.Child()
    tag_list_search_entry = Gtk.Template.Child()

    def __init__(self, window):
        super().__init__(modal=True, transient_for=window)
        self.file_manager = window.file_manager
        self._folder = None

        self.syntax_highlight = \
            EartagPlaceholderSyntaxHighlighter(self.filename_entry, "entry")

        self.folder_chooser = Gtk.FileDialog(modal=True)
        self.bind_property('folder', self.folder_selector_row, 'subtitle', GObject.BindingFlags.SYNC_CREATE)
        if EartagRenameDialog._last_folder is not None:
            self.props.folder = EartagRenameDialog._last_folder
        elif os.path.exists(config['rename-base-folder']):
            self.props.folder = config['rename-base-folder']

        self.file_manager.rename_task.bind_property(
            'progress', self.rename_progress, 'fraction'
        )
        self.file_manager.rename_task.connect('task-done', self.on_done)

        self.files = self.file_manager.selected_files_list.copy()
        config.bind('rename-placeholder',
            self.filename_entry, 'text',
            Gio.SettingsBindFlags.DEFAULT
        )

        self.connect('notify::folder', self.validate_placeholder)
        self.connect('notify::validation-passed', self.update_rename_button_sensitivity)
        self.update_rename_button_sensitivity()

        # Extra tag filter for additional tag field

        self.tag_names = dict(
            [(k, v) for k, v in TAG_NAMES.items()
            if k in BASIC_TAGS + EXTRA_TAGS + ('length', 'bitrate')]
        )
        self.tag_names_swapped = dict(
            [(v, k) for k, v in self.tag_names.items()]
        )
        tag_model_nofilter = Gtk.StringList.new(list(self.tag_names.values()))
        self.tag_model = Gtk.FilterListModel(model=tag_model_nofilter)
        self.tag_filter = Gtk.CustomFilter.new(self.tag_filter_func, self.tag_model)
        self.tag_model.set_filter(self.tag_filter)

        self.tag_selection_model = Gtk.NoSelection.new(self.tag_model)

        # "Add additional tag" field (we can reuse the factory from the "more tags" selector):
        self._ignore_tag_selector = False

        factory = Gtk.BuilderListItemFactory.new_from_resource(
            None, f'{APP_GRESOURCE_PATH}/ui/moretagsgroupfactory.ui'
        )
        self.tag_list.set_model(self.tag_selection_model)
        self.tag_list.set_factory(factory)
        self.tag_list.connect('activate', self.add_placeholder_from_selector)

        # Close popover if Escape key is pressed in search entry
        controller = Gtk.ShortcutController()
        trigger = Gtk.KeyvalTrigger.new(Gdk.keyval_from_name("Escape"), 0)
        shortcut = Gtk.Shortcut.new(trigger, Gtk.CallbackAction.new(self.close_popover))
        controller.add_shortcut(shortcut)
        self.tag_list_search_entry.add_controller(controller)

    def validate_placeholder(self, *args):
        """Validates the filename input."""
        placeholder = self.filename_entry.get_text()
        if '/' in placeholder and not self.props.folder:
            self.props.validation_passed = False
        else:
            self.props.validation_passed = True
        self.update_rename_button_sensitivity()
        self.folder_remove_button.props.sensitive = bool(self.props.folder)

    def update_rename_button_sensitivity(self, *args):
        if self.props.validation_passed:
            self.filename_entry.remove_css_class('error')
        else:
            self.filename_entry.add_css_class('error')

        self.rename_button.set_sensitive(self.props.validation_passed)

    def add_placeholder_from_selector(self, listview, position, *args):
        """Adds a new placeholder based on the tag selector."""
        if self._ignore_tag_selector:
            return

        self._ignore_tag_selector = True

        selected_item = self.tag_selection_model.get_item(position)
        if not selected_item:
            return
        if selected_item.get_string() == 'none':
            return
        tag = self.tag_names_swapped[selected_item.get_string()]

        self.filename_entry.set_text(self.filename_entry.get_text() + '{' + tag + '}')
        self.syntax_highlight.update_syntax_highlighting()
        self.tag_list_popover.popdown()

        self._ignore_tag_selector = False

    @Gtk.Template.Callback()
    def refresh_tag_filter(self, *args):
        """Refreshes the filter for the tag placeholder insert row."""
        self.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

    def close_popover(self, *args):
        self.tag_list_popover.popdown()

    def tag_filter_func(self, _tag_name, *args):
        """Filter function for the tag dropdown."""
        tag_name = _tag_name.get_string()
        query = self.tag_list_search_entry.get_text()
        if query:
            return query.lower() in tag_name.lower()
        return True

    @GObject.Property(type=str, default=None)
    def folder(self):
        """Base folder to use for the "move to folder" option."""
        return self._folder

    @folder.setter
    def folder(self, value):
        self._folder = value
        EartagRenameDialog._last_folder = value
        if not value:
            config['rename-base-folder'] = ""
        elif not value.startswith('/run/user/'):
            config['rename-base-folder'] = value

    @Gtk.Template.Callback()
    def show_folder_selector(self, *args):
        self.folder_chooser.select_folder(self, None, self.select_folder_from_selector, None)

    def select_folder_from_selector(self, source, result, data):
        try:
            response = self.folder_chooser.select_folder_finish(result)
        except GLib.GError:
            return

        if not response:
            return

        folder = response.get_path()
        try:
            assert os.path.exists(folder)
        except AssertionError:
            self.toast_overlay.add_toast(
                Adw.Toast.new(_("Selected folder does not exist"))
            )
        else:
            try:
                assert os.access(folder, os.W_OK)
            except AssertionError:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(_("Selected folder is read-only"))
                )
            else:
                self.props.folder = response.get_path()

    @Gtk.Template.Callback()
    def remove_folder(self, *args):
        self.props.folder = None

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        self.files = None
        self.close()

    @Gtk.Template.Callback()
    def do_rename(self, *args):
        self.error_banner.set_revealed(False)
        format = self.filename_entry.get_text()
        names = []
        for file in self.files:
            if self.props.folder:
                basepath = self.props.folder
            else:
                basepath = os.path.dirname(file.props.path)
            names.append(os.path.join(basepath,
                    parse_placeholder_string(format, file) + file.props.filetype)
            )

        self.set_sensitive(False)

        self.file_manager.rename_files(self.files, names)

    @Gtk.Template.Callback()
    def update_preview(self, *args):
        """Validates the input and updates the preview."""
        if self.validate_placeholder():
            return
        example_file = self.file_manager.selected_files[0]
        parsed_placeholder = parse_placeholder_string(
            self.filename_entry.get_text(),
            example_file
        )
        self.preview_entry.set_text(parsed_placeholder + example_file.props.filetype)

    def on_done(self, task, *args):
        if task.failed:
            self.set_sensitive(True)
            self.error_banner.set_revealed(True)
        else:
            self.files = None
            self.close()
