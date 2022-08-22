from gi.repository import GObject, Gtk
import os.path

@Gtk.Template(resource_path='/app/drey/EarTag/ui/filelistitem.ui')
class EartagFileListItem(Gtk.Box):
    __gtype_name__ = 'EartagFileListItem'

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
        self.filename_label.set_label(os.path.basename(file.path))
        self.coverart_image.bind_to_file(file)

    def on_destroy(self, *args):
        if self.bindings:
            for b in self.bindings:
                b.unbind()
        self.file = None

    @Gtk.Template.Callback()
    def remove_item(self, *args):
        self.filelist.file_manager.remove(self.file)
        self.on_destroy()

    @GObject.Property(type=str)
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self.title_label.set_label(value or '(No title)')

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
