# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Adw, Gtk
from . import APP_GRESOURCE_PATH

@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/dialogs/closewarning.ui')
class EartagCloseWarningDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagCloseWarningDialog'

    def __init__(self, window):
        super().__init__(modal=True, transient_for=window)
        self.window = window
        self.file_manager = window.file_manager

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == 'discard':
            self.window.force_close = True
            self.window.close()
        elif response == 'save':
            if not self.file_manager.save():
                return False
            self.window.close()
        self.close()

@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/dialogs/discardwarning.ui')
class EartagDiscardWarningDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagDiscardWarningDialog'

    def __init__(self, window, paths):
        super().__init__(modal=True, transient_for=window)
        self.paths = paths
        self.file_manager = window.file_manager

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == 'save':
            if not self.file_manager.save():
                return False
        if response != 'cancel':
            self.file_manager.load_files(
                self.paths,
                mode=self.file_manager.LOAD_OVERWRITE
            )
        self.close()

@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/dialogs/removaldiscardwarning.ui')
class EartagRemovalDiscardWarningDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagRemovalDiscardWarningDialog'

    def __init__(self, file_manager, files):
        super().__init__(modal=True, transient_for=file_manager.window)
        self.file_manager = file_manager
        self.files = files

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == 'save':
            if not self.file_manager.save():
                return False
        if response != 'cancel':
            self.file_manager.remove_files(self.files, force_discard=True)
        self.file = None
        self.close()

@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/dialogs/loadingfailure.ui')
class EartagLoadingFailureDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagLoadingFailureDialog'

    def __init__(self, window, filename):
        super().__init__(modal=True, transient_for=window)
        self.set_body(self.get_body().format(f=filename))

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        self.close()

@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/dialogs/renamefailure.ui')
class EartagRenameFailureDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagRenameFailureDialog'

    def __init__(self, window, filename):
        super().__init__(modal=True, transient_for=window)
        self.set_body(self.get_body().format(f=filename))

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        self.close()

@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/dialogs/tagdeletewarning.ui')
class EartagTagDeleteWarningDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagTagDeleteWarningDialog'

    def __init__(self, window):
        super().__init__(modal=True, transient_for=window)
        self.window = window

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response != 'cancel':
            self.window.do_delete_all_tags()
        self.close()
