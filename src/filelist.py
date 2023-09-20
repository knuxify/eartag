# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import GObject, Gtk, GLib
import os.path

from .utils import find_in_model

@Gtk.Template(resource_path='/app/drey/EarTag/ui/filelistitem.ui')
class EartagFileListItem(Gtk.Box):
    __gtype_name__ = 'EartagFileListItem'

    status_icon_stack = Gtk.Template.Child()
    modified_icon = Gtk.Template.Child()
    error_icon = Gtk.Template.Child()

    coverart_image = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    filename_label = Gtk.Template.Child()
    _title = None
    file = None

    cover_edit_stack = Gtk.Template.Child()
    select_button = Gtk.Template.Child()
    remove_button = Gtk.Template.Child()
    suffixes = Gtk.Template.Child()

    def __init__(self, filelist, mode):
        super().__init__()
        self._selected = False
        self.filelist = filelist
        if self.filelist.selection_mode:
            self.show_selection_button()
        self.file_manager = filelist.file_manager
        self.file_manager.connect('selection-changed', self.handle_selection_change)
        self.filelist.connect('notify::selection-mode', self.toggle_selection_mode)
        self.connect('destroy', self.on_destroy)
        self.bindings = []
        if mode == 'selected':
            self.remove_button.set_visible(False)

    def bind_to_file(self, file):
        if self.bindings:
            for b in self.bindings:
                b.unbind()
        self.file = file

        # We don't do this with a binding as it causes weird problems with self-
        # unselecting files
        self.select_button.connect('toggled', self.handle_select_button_change)
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
        self.handle_selection_change()

    def on_destroy(self, *args):
        if self.bindings:
            for b in self.bindings:
                b.unbind()
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
        return self.file in self.file_manager.selected_files

    @selected.setter
    def selected(self, value):
        if value and self.file not in self.file_manager.selected_files:
            self.file_manager.selected_files.append(self.file)
        elif not value and self.file in self.file_manager.selected_files:
            self.file_manager.selected_files.remove(self.file)
        self.file_manager.emit('selection-changed')

    def handle_select_button_change(self, button):
        if self.selected != button.get_active():
            self.selected = button.get_active()

    def handle_selection_change(self, *args):
        if self.file in self.file_manager.selected_files:
            self.select_button.set_active(True)
        else:
            self.select_button.set_active(False)

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
        self.sidebar = None
        self.sidebar_factory = Gtk.SignalListItemFactory()
        self.sidebar_factory.connect('setup', self.setup)
        self.sidebar_factory.connect('bind', self.bind)
        self.sidebar_factory.connect('unbind', self.bind)
        self.set_factory(self.sidebar_factory)
        self._selection_mode = False
        self._ignore_unselect = False
        self.file_manager = None
        self._widgets = {}

    def set_file_manager(self, file_manager):
        self.file_manager = file_manager
        self.file_manager.connect('selection-override', self.handle_selection_override)
        self.file_manager.connect('select-first', self.handle_select_first)

    def set_sidebar(self, sidebar):
        self.mode = 'sidebar'
        self.sidebar = sidebar

        # Set up sort model for sort button
        self.sort_model = Gtk.SortListModel(model=self.file_manager.files)
        self.sorter = Gtk.CustomSorter.new(self.sort_func, None)
        self.sort_model.set_sorter(self.sorter)

        # Set up filter model for search
        self.filter_model = Gtk.FilterListModel(model=self.sort_model)
        self.filter = Gtk.CustomFilter.new(self.filter_func, self.filter_model)
        self.filter_model.set_filter(self.filter)

        self.selection_model = Gtk.SingleSelection(model=self.filter_model)
        self.selection_model.connect('selection-changed', self.update_selection_from_model)
        self.selection_model.set_autoselect(False)
        self.selection_model.set_can_unselect(False)

        self.set_model(self.selection_model)

        self.set_single_click_activate(False)
        self.connect('activate', self.handle_activate)

    def setup_for_selected(self):
        self.mode = 'selected'
        # Set up sort model for sort button
        self.sort_model = Gtk.SortListModel(model=self.file_manager.files)
        self.sorter = Gtk.CustomSorter.new(self.sort_func, None)
        self.sort_model.set_sorter(self.sorter)

        # Set up filter model for only leaving selected items
        self.filter_model = Gtk.FilterListModel(model=self.sort_model)
        self.filter = Gtk.CustomFilter.new(self.selected_filter_func, self.filter_model)
        self.filter_model.set_filter(self.filter)

        self.selection_model = Gtk.NoSelection(model=self.filter_model)

        self.set_model(self.selection_model)

    def setup(self, factory, list_item):
        list_item.set_child(EartagFileListItem(self, self.mode))

    def bind(self, factory, list_item):
        child = list_item.get_child()
        file = list_item.get_item()
        child.bind_to_file(file)
        self._widgets[file.id] = child

    def unbind(self, factory, list_item):
        file = list_item.get_item()
        del self._widgets[file.id]

    def handle_selection_override(self, *args):
        """
        Handle selection change from external source.
        """
        self._ignore_unselect = True

        if not self.selection_mode:
            if not self.file_manager.selected_files:
                self.selection_model.unselect_all()
                self._ignore_unselect = False
                return
            new_index = find_in_model(self.selection_model,
                self.file_manager.selected_files[0])
            if new_index < 0:
                self.selection_model.unselect_all()
            else:
                self.selection_model.select_item(new_index, True)

            if self.sidebar:
                self.sidebar.scroll_to_index(new_index)
        else:
            self.selection_model.unselect_all()
            for file in self.file_manager.selected_files:
                new_index = find_in_model(self.selection_model, file)
                if new_index > -1:
                    self.selection_model.select_item(new_index, False)

        self._ignore_unselect = False

    def handle_select_first(self, *args):
        """
        As the sorted list of files is completely unknown to the file manager,
        it cannot tell which item is the first in the sidebar. Thus, when the
        first item needs to be selected (when the currently selected item is
        removed), we have to select it manually here.
        """
        if self.selection_mode:
            return

        new_selection = self.selection_model.get_item(0)
        if not new_selection:
            return
        self.file_manager.selected_files = [new_selection]
        self.file_manager.emit('selection-changed')
        self.selection_model.select_item(0, True)

        if self.sidebar:
            self.sidebar.scroll_to_top()

    def filter_func(self, file, *args):
        """Custom filter for file search."""
        query = self.sidebar.search_entry.get_text()
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

    def sort_func(self, a, b, *args):
        """Custom sort function implementation for file sorting."""

        # Step 1. Compare album names
        a_album = GLib.utf8_casefold(a.albumsort or a.album or '', -1)
        b_album = GLib.utf8_casefold(b.albumsort or b.album or '', -1)
        collate = GLib.utf8_collate(a_album, b_album)

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
            collate = GLib.utf8_collate(a_filename, b_filename)

        return collate

    def selected_filter_func(self, file, *args):
        return file in self.file_manager.selected_files

    def enable_selection_mode(self, *args):
        self.set_single_click_activate(True)
        self.selection_model.set_can_unselect(True)
        self._ignore_unselect = True
        self.selection_model.unselect_item(self.selection_model.get_selected())
        self._ignore_unselect = False

    def disable_selection_mode(self, *args):
        self.set_single_click_activate(False)

        try:
            self.file_manager.selected_files
        except AttributeError:
            return

        if self.file_manager.selected_files:
            first_selected_file = self.file_manager.selected_files[0]
            for file in self.file_manager.selected_files.copy():
                if file != first_selected_file:
                    self.file_manager.selected_files.remove(file)
            found_selected = False
            for item_no in range(0, self.filter_model.get_n_items()):
                if self.filter_model.get_item(item_no) == first_selected_file:
                    self.selection_model.select_item(item_no, True)
                    found_selected = True
                    break
            if not found_selected:
                self.file_manager.emit('select-first')
        else:
            self.file_manager.emit('select-first')

        self.file_manager.emit('selection-changed')
        self.selection_model.set_can_unselect(False)

    def select_all(self, *args):
        self.file_manager.selected_files = list(self.filter_model)
        self.file_manager.emit('selection-changed')

    def unselect_all(self, *args):
        for file in list(self.filter_model):
            if file in self.file_manager.selected_files:
                self.file_manager.selected_files.remove(file)
        self.file_manager.emit('selection-changed')

    def all_selected(self):
        n_items = len(list(self.filter_model))
        n_selected = 0
        for file in list(self.filter_model):
            if file in self.file_manager.selected_files:
                n_selected += 1
        return n_items == n_selected

    @GObject.Property(type=bool, default=False)
    def selection_mode(self):
        """Whether the sidebar is in selection mode or not."""
        return self._selection_mode

    @selection_mode.setter
    def selection_mode(self, value):
        self._selection_mode = value
        if value:
            self.enable_selection_mode()
        else:
            self.disable_selection_mode()

    # We use two separate mechanisms to handle selecting files on the sidebar:
    # - Non-selection-mode: uses the selection model on the listview.
    # - Selection mode: uses handle_activate.
    #
    # This fixes an issue where moving around with arrow keys on the sidebar
    # while in selection mode would select/deselect the item that was navigated
    # onto, making properly selecting these impossible.
    #
    # However, using that same approach in non-selection-mode caused the
    # selected item to no longer be highlighted as selected in the sidebar
    # (even with a manual call to set_selected). Thus, we use the old mechanism
    # for single selection mode, and the new mechanism for multiple selection
    # mode.

    def update_selection_from_model(self, selection_model, position, n_items):
        if self.selection_mode:
            self.selection_model.unselect_all()
            return

        if self._ignore_unselect:
            return

        for pos in (position, position + n_items - 1):
            if selection_model.is_selected(pos):
                selected_file = self.filter_model.get_item(pos)

        self.file_manager.selected_files = [selected_file]
        self.file_manager.emit('selection-changed')

    def handle_activate(self, _, position):
        if not self.selection_mode:
            return

        item = self.selection_model.get_item(position)
        if item in self.file_manager.selected_files:
            self.file_manager.selected_files.remove(item)
        else:
            self.file_manager.selected_files.append(item)
        self.file_manager.emit('selection-changed')
