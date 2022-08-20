from gi.repository import Gtk

@Gtk.Template(resource_path='/app/drey/EarTag/ui/filelistitem.ui')
class EartagFileListItem(Gtk.Box):
    __gtype_name__ = 'EartagFileListItem'

    title = Gtk.Template.Child()

    def bind_to_file(self, file):
        self.title.set_label(file.title)

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
        self.set_model(Gtk.SingleSelection(model=self.file_manager.files))

    def setup(self, factory, list_item):
        list_item.set_child(EartagFileListItem())

    def bind(self, factory, list_item):
        child = list_item.get_child()
        file = list_item.get_item()
        child.bind_to_file(file)
