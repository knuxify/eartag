# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors
"""
Common code for the preview selector in the rename and extract tags dialogs.
"""

from gi.repository import Gtk, GObject, Gio, Gdk
import os.path

from ..backends.file import EartagFile
from .. import APP_GRESOURCE_PATH


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/previewselectoritem.ui")
class EartagPreviewSelectorItem(Gtk.Box):
    """
    Representation of a file for the preview file selector in the rename
    and extract tags dialogs.
    """

    __gtype_name__ = "EartagPreviewSelectorItem"

    formatted_path_label = Gtk.Template.Child()
    filename_label = Gtk.Template.Child()

    def __init__(self, parent, formatting_function):
        """
        Initializes the EartagPreviewSelectorItem. formatting_function should be
        a function that takes an EartagFile and returns a tuple containing
        a string to display and a PangoAttrList containing its Pango attributes.
        """
        super().__init__()
        self._file = None
        self._func = formatting_function
        self._parent = parent
        self._formatting_changed_conn = self._parent.connect(
            "formatting-changed", self.update_label
        )

    @GObject.Property(type=EartagFile, default=None)
    def file(self):
        return self._file

    @file.setter
    def file(self, new_file: EartagFile):
        self._file = new_file
        if new_file is not None:
            self.update_label()

    def update_label(self, *args):
        label, attributes = self._func(self._file)
        self.formatted_path_label.props.label = label
        self.formatted_path_label.props.attributes = attributes
        self.filename_label.props.label = os.path.basename(self._file.props.path)

    def unbind(self):
        self.props.file = None
        del self._file

    def teardown(self):
        self._parent.disconnect(self._formatting_changed_conn)
        del self._func
        del self._parent


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/previewselectorbutton.ui")
class EartagPreviewSelectorButton(Gtk.MenuButton):
    """
    Previewed file selector for the rename and extract tags dialogs.
    """

    __gtype_name__ = "EartagPreviewSelectorButton"

    popover = Gtk.Template.Child()
    list = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()

    selected_index = GObject.Property(type=int, default=0)

    # Emit this signal when the formatting needs to be refreshed
    formatting_changed = GObject.Signal()

    def __init__(self):
        self.search_entry.connect("search-changed", self.refresh_filter)

        self.model_nofilter = Gio.ListStore(item_type=EartagFile)
        self.model = Gtk.FilterListModel(model=self.model_nofilter)
        self.filter = Gtk.CustomFilter.new(self.filter_func, self.model)
        self.model.set_filter(self.filter)

        self.selection_model = Gtk.NoSelection.new(self.model)

        # "Add additional preview_selector" field
        # (we can reuse the factory from the "more preview_selectors" selector):
        self._ignore_preview_selector_selector = False

        self.factory = Gtk.SignalListItemFactory.new()
        self.factory.connect("setup", self.factory_setup)
        self.factory.connect("bind", self.factory_bind)
        self.factory.connect("unbind", self.factory_unbind)
        self.factory.connect("teardown", self.factory_teardown)
        self.list.set_model(self.selection_model)
        self.list.connect("activate", self.set_previewed_file_from_selection)

        # Close popover if Escape key is pressed in search entry
        controller = Gtk.ShortcutController()
        trigger = Gtk.KeyvalTrigger.new(Gdk.keyval_from_name("Escape"), 0)
        shortcut = Gtk.Shortcut.new(
            trigger, Gtk.CallbackAction.new(self.close_preview_selector_popover)
        )
        controller.add_shortcut(shortcut)
        self.search_entry.add_controller(controller)

    def set_files(self, files: list):
        self.model_nofilter.splice(0, 0, files)
        self.refresh_filter()

    def set_formatting_function(self, func):
        self._formatting_function = func
        # We do this here since otherwise it will fail as the formatting
        # function isn't set yet.
        self.list.set_factory(self.factory)

    def filter_func(self, item, *args):
        """Filter function for the tag dropdown."""
        query = self.search_entry.get_text()
        if query:
            return (
                query.lower()
                in f"{item.props.artist.lower()} {item.props.title.lower()}"
                or query.lower() in os.path.basename(item.path).lower()
            )
        return True

    def refresh_filter(self, *args):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)

    def close_preview_selector_popover(self, *args):
        self.popover.popdown()

    def set_previewed_file_from_selection(self, list, selection, *args):
        item = self.model.get_item(selection)
        index_found, index = self.model_nofilter.find(item)
        index = index if index_found else 0
        self.props.selected_index = index
        self.close_preview_selector_popover()

    def factory_setup(self, factory, list_item):
        list_item.set_child(EartagPreviewSelectorItem(self, self._formatting_function))

    def factory_bind(self, factory, list_item):
        list_item.get_child().props.file = list_item.get_item()

    def factory_unbind(self, factory, list_item):
        list_item.get_child().unbind()
        list_item.get_child().teardown()

    def factory_teardown(self, factory, list_item):
        if list_item.get_child():
            list_item.get_child().teardown()

    def teardown(self):
        # Ensure no items are left over
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self.filter.set_filter_func(lambda *x: False)
