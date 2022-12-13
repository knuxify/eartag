# sidebar.py
#
# Copyright 2022 knuxify
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE X CONSORTIUM BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# Except as contained in this notice, the name(s) of the above copyright
# holders shall not be used in advertising or otherwise to promote the sale,
# use or other dealings in this Software without prior written
# authorization.

from gi.repository import GObject, Gtk, GLib
import os.path
import gettext

@Gtk.Template(resource_path='/app/drey/EarTag/ui/filelistitem.ui')
class EartagFileListItem(Gtk.Box):
    __gtype_name__ = 'EartagFileListItem'

    modified_icon = Gtk.Template.Child()
    coverart_image = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    filename_label = Gtk.Template.Child()
    _title = None
    file = None

    cover_edit_stack = Gtk.Template.Child()
    select_button = Gtk.Template.Child()

    def __init__(self, filelist):
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
        self.bindings.append(self.file.bind_property('is-modified', self.modified_icon,
            'visible', GObject.BindingFlags.SYNC_CREATE))
        self.filename_label.set_label(os.path.basename(file.path))
        self.coverart_image.bind_to_file(file)
        self.handle_selection_change()

    def on_destroy(self, *args):
        if self.bindings:
            for b in self.bindings:
                b.unbind()
        self.file = None

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
        if self.file_manager.remove(self.file):
            self.on_destroy()

    @GObject.Property(type=str)
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        # TRANSLATORS: Placeholder for file sidebar items with no title set
        self.title_label.set_label(value or _('(No title)'))

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
        self.add_css_class('navigation-sidebar')
        self._selection_mode = False
        self._ignore_unselect = False

    def set_file_manager(self, file_manager):
        self.file_manager = file_manager
        self.file_manager.connect('selection-override', self.handle_selection_override)

    def set_sidebar(self, sidebar):
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

        self.set_model(self.selection_model)

    def setup(self, factory, list_item):
        list_item.set_child(EartagFileListItem(self))

    def bind(self, factory, list_item):
        child = list_item.get_child()
        file = list_item.get_item()
        child.bind_to_file(file)

    def handle_selection_override(self, *args):
        """
        When files are loaded for the first time, the selection is empty;
        we need to set the selection here since we only keep the information
        about the display order in the filter list.

        The file manager emits selection-override when this is needed.
        """
        if not self.selection_mode:
            self.selection_model.select_item(0, True)
            if len(self.file_manager.selected_files) == 0 and self.file_manager.files:
                self.update_selection_from_model(self.selection_model, 0, 1)

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
        a_album = GLib.utf8_casefold(a.album or '', -1)
        b_album = GLib.utf8_casefold(b.album or '', -1)
        collate = GLib.utf8_collate(a_album, b_album)

        # Step 2. Compare track numbers
        if (a.tracknumber or -1) > (b.tracknumber or -1):
            collate += 2
        elif (a.tracknumber or -1) < (b.tracknumber or -1):
            collate -= 2

        # Step 3. If the result is inconclusive, compare filenames
        if collate == 0:
            a_filename = GLib.utf8_casefold(os.path.basename(a.path), -1)
            b_filename = GLib.utf8_casefold(os.path.basename(b.path), -1)
            collate = GLib.utf8_collate(a_filename, b_filename)

        return collate

    def enable_selection_mode(self, *args):
        self.selection_model.set_can_unselect(True)
        self._ignore_unselect = True
        self.selection_model.unselect_item(self.selection_model.get_selected())
        self._ignore_unselect = False

    def disable_selection_mode(self, *args):
        if self.file_manager.selected_files:
            first_selected_file = self.file_manager.selected_files[0]
            for file in self.file_manager.selected_files:
                if file != first_selected_file:
                    self.file_manager._selected_files.remove(file)

            for item_no in range(0, self.filter_model.get_n_items()):
                if self.filter_model.get_item(item_no) == first_selected_file:
                    self.selection_model.select_item(item_no, True)
                    break

        self.file_manager.emit('selection-changed')
        self.selection_model.set_can_unselect(False)

    def select_all(self, *args):
        self.file_manager.select_all()

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

    def update_selection_from_model(self, selection_model, position, n_items):
        """Updates the selected files."""
        if self._ignore_unselect:
            return

        unselected_file = None
        selected_file = None
        selected_file_pos = None

        for pos in (position, position + n_items - 1):
            if selection_model.is_selected(pos):
                selected_file = self.filter_model.get_item(pos)
                selected_file_pos = pos
            else:
                unselected_file = self.filter_model.get_item(pos)

        if self.selection_mode:
            if selected_file:
                self._ignore_unselect = True
                self.selection_model.unselect_item(selected_file_pos)
                self._ignore_unselect = False
                if selected_file not in self.file_manager.selected_files:
                    self.file_manager.selected_files.append(selected_file)
                else:
                    self.file_manager.selected_files.remove(selected_file)
                self.file_manager.emit('selection-changed')
        else:
            self.file_manager.selected_files = [selected_file]

@Gtk.Template(resource_path='/app/drey/EarTag/ui/sidebar.ui')
class EartagSidebar(Gtk.Box):
    __gtype_name__ = 'EartagSidebar'

    list_stack = Gtk.Template.Child()
    list_scroll = Gtk.Template.Child()
    file_list = Gtk.Template.Child()
    no_files = Gtk.Template.Child()

    search_bar = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    no_results = Gtk.Template.Child()

    action_bar = Gtk.Template.Child()
    select_all_button = Gtk.Template.Child()
    remove_selected_button = Gtk.Template.Child()
    selected_message_label = Gtk.Template.Child()

    loading_progressbar = Gtk.Template.Child()
    loading_progressbar_revealer = Gtk.Template.Child()

    def __init__(self):
        super().__init__()

        self.search_bar.set_key_capture_widget(self)
        self.search_bar.connect_entry(self.search_entry)
        self.search_entry.connect('search-changed', self.search_changed)

    def set_file_manager(self, file_manager):
        self.file_manager = file_manager
        self.file_list.set_file_manager(self.file_manager)
        self.list_stack.set_visible_child(self.no_files)
        self.file_list.set_sidebar(self)

        self.file_manager.connect('files-loaded', self.refresh_actionbar_button_state)
        self.file_manager.files.connect('items-changed', self.refresh_actionbar_button_state)
        self.file_manager.connect('selection-changed', self.refresh_actionbar_button_state)
        self.file_manager.connect('notify::loading-progress', self.update_loading_progressbar)
        self.refresh_actionbar_button_state()

    def update_loading_progressbar(self, *args):
        """
        Updates the loading progressbar's position.
        """
        loading_progress = self.file_manager.get_property('loading-progress')
        self.loading_progressbar_revealer.set_reveal_child(not loading_progress == 0)
        self.set_sensitive(loading_progress == 0)
        self.file_list.set_visible(loading_progress == 0)
        self.loading_progressbar.set_fraction(loading_progress)

    def toggle_fileview(self, *args):
        """
        Shows/hides the fileview/"no files" message depending on opened files.
        """
        if self.file_manager.files.get_n_items() > 0:
            self.list_stack.set_visible_child(self.list_scroll)
        else:
            self.list_stack.set_visible_child(self.no_files)

    def search_changed(self, search_entry, *args):
        """Emitted when the search has changed."""
        self.file_list.filter.changed(Gtk.FilterChange.DIFFERENT)

        if self.file_list.filter_model.get_n_items() == 0 and \
                self.file_manager.files.get_n_items() > 0:
            self.list_stack.set_visible_child(self.no_results)
        else:
            self.toggle_fileview()

        # Scroll back to top of list
        vadjust = self.file_list.get_vadjustment()
        vadjust.set_value(vadjust.get_lower())

        # Update the switcher buttons in the fileview
        self.get_native().file_view.update_buttons()

    def toggle_selection_mode(self, *args):
        self.file_list.toggle_selection_mode()

    @Gtk.Template.Callback()
    def select_all(self, *args):
        self.file_list.select_all()

    @Gtk.Template.Callback()
    def remove_selected(self, *args):
        old_selected = self.file_manager.selected_files.copy()
        self.file_manager.remove_multiple(old_selected)

    def refresh_actionbar_button_state(self, *args):
        if not self.file_manager.files or not self.selection_mode:
            selected_message = ''
            self.action_bar.set_sensitive(False)
            self.action_bar.set_revealed(False)
        else:
            self.action_bar.set_sensitive(True)
            self.action_bar.set_revealed(True)
            selected_file_count = len(self.file_manager.selected_files)
            if selected_file_count == 0:
                selected_message = _('No files selected')
                self.remove_selected_button.set_sensitive(False)
            else:
                selected_message = gettext.ngettext(
                    "{n} file selected", "{n} files selected", selected_file_count).\
                        format(n=selected_file_count)
                self.remove_selected_button.set_sensitive(True)

        self.selected_message_label.set_label(selected_message)

    @GObject.Property(type=bool, default=False)
    def selection_mode(self):
        """Whether the sidebar is in selection mode or not."""
        return self.file_list.selection_mode

    @selection_mode.setter
    def selection_mode(self, value):
        self.file_list.selection_mode = value
        # Workaround for the text not showing up on initial load
        self.refresh_actionbar_button_state()

    def select_next(self, *args):
        """Selects the next item on the sidebar."""
        if self.file_list.selection_model.get_n_items() <= 1 or self.selection_mode:
            return
        selected = self.file_list.selection_model.get_selected()
        if selected + 1 >= self.file_list.selection_model.get_n_items():
            self.file_list.selection_model.set_selected(0)
        else:
            self.file_list.selection_model.set_selected(selected + 1)

    def select_previous(self, *args):
        """Selects the previous item on the sidebar."""
        if self.file_list.selection_model.get_n_items() <= 1 or self.selection_mode:
            return
        selected = self.file_list.selection_model.get_selected()
        if selected - 1 >= 0:
            self.file_list.selection_model.set_selected(selected - 1)
        else:
            self.file_list.selection_model.set_selected(self.file_list.selection_model.get_n_items() - 1)
