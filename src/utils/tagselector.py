# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors
"""
Common code for the placeholder selector used in the rename and extract UIs,
as well as the fileview "add extra tags" button.
"""

from .. import APP_GRESOURCE_PATH
from ..backends.file import VALID_TAGS, TAG_NAMES

from gi.repository import Gdk, Gtk, GObject


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/tagselectorbutton.ui")
class EartagTagSelectorButton(Gtk.MenuButton):
    """
    Button that allows you to select a tag from a list.

    Users can bind to the tag-selected signal to get the name
    of the tag.
    """

    __gtype_name__ = "EartagTagSelectorButton"

    tag_list_popover = Gtk.Template.Child()
    tag_list = Gtk.Template.Child()
    tag_list_search_entry = Gtk.Template.Child()

    def __init__(self):
        # Extra tag filter for additional tag field
        self.tag_names = dict(
            [(k, v) for k, v in TAG_NAMES.items() if k in VALID_TAGS + ("length", "bitrate")]
        )
        self.tag_names_swapped = dict([(v, k) for k, v in self.tag_names.items()])
        tag_model_nofilter = Gtk.StringList.new(list(self.tag_names.values()))
        self.tag_model = Gtk.FilterListModel(model=tag_model_nofilter)
        self.tag_filter = Gtk.CustomFilter.new(self.tag_filter_func, self.tag_model)
        self.tag_model.set_filter(self.tag_filter)

        self.tag_selection_model = Gtk.NoSelection.new(self.tag_model)

        # "Add additional tag" field (we can reuse the factory from the "more tags" selector):
        self._ignore_tag_selector = False

        factory = Gtk.BuilderListItemFactory.new_from_resource(
            None, f"{APP_GRESOURCE_PATH}/ui/moretagsgroupfactory.ui"
        )
        self.tag_list.set_model(self.tag_selection_model)
        self.tag_list.set_factory(factory)
        self.tag_list.connect("activate", self.add_placeholder_from_selector)

        # Close popover if Escape key is pressed in search entry
        controller = Gtk.ShortcutController()
        trigger = Gtk.KeyvalTrigger.new(Gdk.keyval_from_name("Escape"), 0)
        shortcut = Gtk.Shortcut.new(trigger, Gtk.CallbackAction.new(self.close_popover))
        controller.add_shortcut(shortcut)
        self.tag_list_search_entry.add_controller(controller)

    def add_placeholder_from_selector(self, listview, position, *args):
        """Adds a new placeholder based on the tag selector."""
        if self._ignore_tag_selector:
            return

        self._ignore_tag_selector = True

        selected_item = self.tag_selection_model.get_item(position)
        if not selected_item:
            return
        if selected_item.get_string() == "none":
            return
        tag = self.tag_names_swapped[selected_item.get_string()]

        self.tag_list_popover.popdown()

        self.emit("tag-selected", tag)

        self._ignore_tag_selector = False

    @GObject.Signal(arg_types=(str,))
    def tag_selected(self, tag: str):
        """Emitted when a tag is selected."""

    def tag_filter_func(self, _tag_name, *args):
        """Filter function for the tag dropdown."""
        tag_name = _tag_name.get_string()
        query = self.get_search_query()
        if query:
            return query.lower() in tag_name.lower()
        return True

    def close_popover(self, *args):
        self.tag_list_popover.popdown()

    @Gtk.Template.Callback()
    def refresh_tag_filter(self, *args):
        """Refreshes the filter for the tag placeholder insert row."""
        self.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

    def set_filter(self, filter):
        """
        Sets a custom filter for the tag selector.

        The primary user of this function is the FileView code, which needs
        to manage its own filter model to keep track of available tags and
        remove already present ones.
        """
        self.tag_filter = filter
        self.tag_model.set_filter(self.tag_filter)

    def get_search_query(self) -> str:
        """Returns the search query typed into the search entry."""
        return self.tag_list_search_entry.get_text()
