# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import GObject, Gtk, GLib, Gdk
import os.path

from .utils import find_in_model
from . import APP_GRESOURCE_PATH

@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/filelistitem.ui')
class EartagFileListItem(Gtk.Box):
    __gtype_name__ = 'EartagFileListItem'

    status_icon_stack = Gtk.Template.Child()
    modified_icon = Gtk.Template.Child()
    error_icon = Gtk.Template.Child()

    coverart_image = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    filename_label = Gtk.Template.Child()

    cover_edit_stack = Gtk.Template.Child()
    select_button = Gtk.Template.Child()
    remove_button = Gtk.Template.Child()
    suffixes = Gtk.Template.Child()

    def __init__(self, filelist):
        super().__init__()
        self.file = None
        self._title = None
        self._selected = None
        self.filelist = filelist
        if self.filelist.selection_mode:
            self.show_selection_button()
        self.file_manager = filelist.file_manager
        self.file_manager.connect('selection-changed', self.update_selected_status)
        self.filelist.connect('notify::selection-mode', self.toggle_selection_mode)
        self.connect('destroy', self.on_destroy)
        self._selected_bind = self.bind_property(
            'selected', self.select_button, 'active',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.bindings = []

    def bind_to_file(self, file):
        if self.bindings:
            for b in self.bindings:
                b.unbind()
        self.file = file

        self.bindings.append(self.file.bind_property('title', self, 'title',
            GObject.BindingFlags.SYNC_CREATE))
        self.bindings.append(self.file.bind_property('path', self,
            'filename', GObject.BindingFlags.SYNC_CREATE))
        self.bindings.append(self.file.bind_property('is-modified', self.modified_icon,
            'visible', GObject.BindingFlags.SYNC_CREATE))
        self.bindings.append(self.file.bind_property('has-error', self.error_icon,
            'visible', GObject.BindingFlags.SYNC_CREATE))
        self._error_connect = self.file.connect('notify::has-error', self.handle_error)
        self.filename_label.set_label(os.path.basename(file.path))
        self.coverart_image.bind_to_file(file)
        self.update_selected_status()

    def on_destroy(self, *args):
        if self.bindings:
            for b in self.bindings:
                b.unbind()
        self._selected_bind.unbind()
        self.file.disconnect(self._error_connect)
        self.file = None

    def handle_error(self, *args):
        if self.file.has_error:
            self.status_icon_stack.set_visible_child(self.error_icon)
        else:
            self.status_icon_stack.set_visible_child(self.modified_icon)

    def add_suffix(self, widget):
        """Adds a suffix widget."""
        self.suffixes.append(widget)

    @GObject.Property(type=bool, default=False)
    def selected(self):
        return self._selected

    @selected.setter
    def selected(self, value):
        self._selected = value
        if value and not self.file_manager.is_selected(self.file):
            self.file_manager.select_file(self.file)
        elif not value and self.file_manager.is_selected(self.file):
            self.file_manager.unselect_file(self.file)

    def update_selected_status(self, *args):
        self._selected = self.file_manager.is_selected(self.file)
        self.notify("selected")

    @Gtk.Template.Callback()
    def remove_item(self, *args):
        if self.file_manager.remove_files([self.file]):
            self.on_destroy()

    @GObject.Property(type=str)
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        # TRANSLATORS: Placeholder for file sidebar items with no title set
        self.title_label.set_label(value or _('(No title)'))

    @GObject.Property(type=str)
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        self.filename_label.set_label(os.path.basename(value))
        self._filename = os.path.basename(value)

    def show_selection_button(self, *args):
        self.cover_edit_stack.set_visible_child(self.select_button)

    def hide_selection_button(self, *args):
        self.cover_edit_stack.set_visible_child(self.coverart_image)

    def toggle_selection_mode(self, *args):
        if self.filelist.selection_mode:
            self.show_selection_button()
        else:
            self.hide_selection_button()

class EartagFileList(Gtk.ListView):
    """List of opened tracks."""
    __gtype_name__ = 'EartagFileList'

    def __init__(self):
        super().__init__()
        self.sidebar_factory = Gtk.SignalListItemFactory()
        self.sidebar_factory.connect('setup', self.setup)
        self.sidebar_factory.connect('bind', self.bind)
        self.sidebar_factory.connect('unbind', self.bind)
        self.set_factory(self.sidebar_factory)
        self._selection_mode = False
        self._ignore_unselect = False
        self.file_manager = None
        self._widgets = {}

        # See on_activate function for explaination
        self.connect("activate", self.on_activate)
        self.key_controller = Gtk.EventControllerKey.new()
        self.key_controller.connect('key-pressed', self.shift_key_pressed)
        self.key_controller.connect('key-released', self.shift_key_released)
        self.add_controller(self.key_controller)
        self.shift_state = False

    def set_file_manager(self, file_manager):
        self.file_manager = file_manager
        self.set_model(self.file_manager.selected_files)
        self.file_manager.connect('selection-changed', self.switch_into_selection_mode)

    def setup(self, factory, list_item):
        list_item.set_child(EartagFileListItem(self))

    def bind(self, factory, list_item):
        child = list_item.get_child()
        file = list_item.get_item()
        child.bind_to_file(file)
        self._widgets[file.id] = child

    def unbind(self, factory, list_item):
        file = list_item.get_item()
        del self._widgets[file.id]

    @GObject.Property(type=bool, default=False)
    def selection_mode(self):
        """Whether the sidebar is in selection mode or not."""
        return self._selection_mode

    @selection_mode.setter
    def selection_mode(self, value):
        self._selection_mode = value
        if not self.file_manager:
            return
        if value is True:
            self.action_set_enabled('list.select-item', False)
            self.props.single_click_activate = True
        else:
            self.action_set_enabled('list.select-item', True)
            self.props.single_click_activate = False
            selection = self.file_manager.selected_files.get_selection()
            if selection.get_size() > 1:
                self.file_manager.selected_files.select_item(selection.get_nth(0), True)

    def toggle_selection_mode(self):
        self.props.selection_mode = not self.props.selection_mode

    def switch_into_selection_mode(self, *args):
        """
        If multiple files have been selected (by holding down Ctrl or Shift) and
        we're not in multiple selection mode, toggle it on.
        """
        if self.file_manager.get_n_selected() >= 2 and not self.props.selection_mode:
            self.props.selection_mode = True

    def on_activate(self, list, index):
        if self.props.selection_mode:
            # Gtk.MultiSelection doesn't have a way to force every click
            # to count a selection - instead, a single click unselects
            # all other items. This isn't the behavior we want, so instead:
            # - We switch into single_click_activate (which makes selections
            # happen on hover, and activations on a single click, instead
            # of selections happening on a single-click and activations on
            # double-click)
            # - Then, we disable the list.select-item action to prevent the
            # items from being selected on hover. Instead:
            # - We re-implement the default selection behavior manually,
            # here in on_activate. We still call the underlying action so
            # that we don't have to re-write all the code for handling
            # "extend" selections (when Shift is pressed).

            extend = self.shift_state

            self.action_set_enabled('list.select-item', True)
            self.activate_action('list.select-item', GLib.Variant('(ubb)', (index, not extend, extend)))
            self.action_set_enabled('list.select-item', False)

    def shift_key_pressed(self, controller, keyval, keycode, state):
        """
        Checks if the Shift key is pressed and sets the internal shift state
        variable accordingly.
        """
        if state & Gdk.ModifierType.SHIFT_MASK or keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
            self.shift_state = True

    def shift_key_released(self, controller, keyval, keycode, state):
        """
        Checks if the Shift key is released and sets the internal shift state
        variable accordingly.
        """
        if state & Gdk.ModifierType.SHIFT_MASK or keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
            self.shift_state = False
