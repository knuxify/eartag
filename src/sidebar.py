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

from gi.repository import GObject, Gtk
import os.path

@Gtk.Template(resource_path='/app/drey/EarTag/ui/filelistitem.ui')
class EartagFileListItem(Gtk.Box):
    __gtype_name__ = 'EartagFileListItem'

    modified_icon = Gtk.Template.Child()
    coverart_image = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    filename_label = Gtk.Template.Child()
    _title = None
    file = None
    bindings = []

    def __init__(self, filelist):
        super().__init__()
        self.filelist = filelist
        self.connect('destroy', self.on_destroy)

    def bind_to_file(self, file):
        if self.bindings:
            for b in self.bindings:
                b.unbind()
        self.file = file

        self.bindings.append(self.file.bind_property('title', self, 'title',
            GObject.BindingFlags.SYNC_CREATE))
        self.bindings.append(self.file.bind_property('is-modified', self.modified_icon,
            'visible', GObject.BindingFlags.SYNC_CREATE))
        self.filename_label.set_label(os.path.basename(file.path))
        self.coverart_image.bind_to_file(file)

    def on_destroy(self, *args):
        if self.bindings:
            for b in self.bindings:
                b.unbind()
        self.file = None

    @Gtk.Template.Callback()
    def remove_item(self, *args):
        if self.filelist.file_manager.remove(self.file):
            self.on_destroy()

    @GObject.Property(type=str)
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        # TRANSLATORS: Placeholder for file sidebar items with no title set
        self.title_label.set_label(value or _('(No title)'))

class EartagFileList(Gtk.ListView):
    """List of opened tracks."""
    __gtype_name__ = 'EartagFileList'

    def __init__(self):
        super().__init__()
        self.sidebar_factory = Gtk.SignalListItemFactory()
        self.sidebar_factory.connect('setup', self.setup)
        self.sidebar_factory.connect('bind', self.bind)
        self.set_factory(self.sidebar_factory)
        self.add_css_class('navigation-sidebar')

    def set_file_manager(self, file_manager):
        self.file_manager = file_manager
        self.file_manager.connect('selection-override', self.handle_selection_override)
        self.selection_model = Gtk.MultiSelection(model=self.file_manager.files)
        self.selection_model.connect('selection-changed', self.update_selection)
        self.set_model(self.selection_model)

    def setup(self, factory, list_item):
        list_item.set_child(EartagFileListItem(self))

    def bind(self, factory, list_item):
        child = list_item.get_child()
        file = list_item.get_item()
        child.bind_to_file(file)

    def update_selection(self, selection_model, position, n_items):
        """Updates the selected files."""
        # TODO: use get_selection_in_range to improve potential performance.
        # this is a rather naive implementation.
        #selection = self.selection_model.get_selection_in_range(position, n_items)
        selection = self.selection_model.get_selection()

        # Get list of selected items
        selected_items = []
        for i in range(selection.get_size()):
            item_no = selection.get_nth(i)
            selected_items.append(self.file_manager.files.get_item(item_no))

        file_count = self.file_manager.files.get_n_items()
        check_count = position

        self.file_manager.selected_files = selected_items

    def handle_selection_override(self, *args):
        """
        When a file is loaded and the selected files list is empty,
        the first loaded file is automatically added by the file manager
        to the list of selected files.

        Since the sidebar doesn't always listen to selection events
        (we're the primary generator of those, see function above, so
        capturing them would cause infinite loops and other problems),
        it provides a secondary event, named "selection-override", which
        is used to signify a selection event from outside the sidebar.
        """
        if self.file_manager.selected_files:
            self.selection_model.select_item(
                self.file_manager.files.find(
                    self.file_manager.selected_files[0]
                )[1], True
            )
