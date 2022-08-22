from gi.repository import GObject, Gtk

@Gtk.Template(resource_path='/app/drey/EarTag/ui/filelistitem.ui')
class EartagFileListItem(Gtk.Box):
    __gtype_name__ = 'EartagFileListItem'

    coverart_image = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    filename_label = Gtk.Template.Child()
    _title = None
    file = None
    bindings = []

    def bind_to_file(self, file):
        if self.bindings:
            for b in self.bindings:
                b.unbind()
        self.file = file

        self.bindings.append(self.file.bind_property('title', self, 'title',
            GObject.BindingFlags.SYNC_CREATE))
        self.coverart_image.bind_to_file(file)

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

    def set_file_manager(self, file_manager):
        self.file_manager = file_manager
        self.selection_model = Gtk.MultiSelection(model=self.file_manager.files)
        self.selection_model.connect('selection-changed', self.update_selection)
        self.set_model(self.selection_model)

    def setup(self, factory, list_item):
        list_item.set_child(EartagFileListItem())

    def bind(self, factory, list_item):
        child = list_item.get_child()
        file = list_item.get_item()
        child.bind_to_file(file)

    def update_selection(self, selection_model, position, n_items):
        """Updates the selected files."""
        selection = self.selection_model.get_selection_in_range(position, n_items)
        values = []
        iter = Gtk.BitsetIter()
        iter.init_first(selection)
        values.append(iter.get_value())
        for i in range(n_items - 1):
            iter.next()
            values.append(iter.get_value())

        file_count = self.file_manager.files.get_n_items()
        check_count = position

        for iter_count in range(n_items):
            item = self.file_manager.files.get_item(check_count)
            if values[iter_count] == 0:
                if item not in self.file_manager.selected_files:
                    self.file_manager.selected_files.append(item)
            elif values[iter_count] == 1:
                if item in self.file_manager.selected_files:
                    self.file_manager.selected_files.remove(item)
            check_count += 1
