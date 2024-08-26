# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Adw, Gtk
from . import APP_GRESOURCE_PATH


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/dialogs/closewarning.ui")
class EartagCloseWarningDialog(Adw.AlertDialog):
    __gtype_name__ = "EartagCloseWarningDialog"

    def __init__(self, window, file_manager):
        super().__init__()
        self.window = window
        self.file_manager = file_manager

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == "discard":
            self.window.force_close = True
            self.window.close()
        elif response == "save":
            if not self.file_manager.save():
                return False
            self.window.close()
        self.close()


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/dialogs/discardwarning.ui")
class EartagDiscardWarningDialog(Adw.AlertDialog):
    __gtype_name__ = "EartagDiscardWarningDialog"

    def __init__(self, file_manager, paths):
        self.paths = paths
        self.file_manager = file_manager

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == "save":
            if not self.file_manager.save():
                return False
        if response != "cancel":
            self.file_manager.load_files(
                self.paths, mode=self.file_manager.LOAD_OVERWRITE
            )
        self.close()


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/dialogs/removaldiscardwarning.ui")
class EartagRemovalDiscardWarningDialog(Adw.AlertDialog):
    __gtype_name__ = "EartagRemovalDiscardWarningDialog"

    def __init__(self, file_manager, files):
        super().__init__()
        self.file_manager = file_manager
        self.files = files

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == "save":
            if not self.file_manager.save():
                return False
        if response != "cancel":
            self.file_manager.remove_files(self.files, force_discard=True)
        self.file = None
        self.close()


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/dialogs/loadingfailure.ui")
class EartagLoadingFailureDialog(Adw.AlertDialog):
    __gtype_name__ = "EartagLoadingFailureDialog"

    def __init__(self, filename):
        super().__init__()
        self.set_body(self.get_body().format(f=filename))

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        self.close()


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/dialogs/renamefailure.ui")
class EartagRenameFailureDialog(Adw.AlertDialog):
    __gtype_name__ = "EartagRenameFailureDialog"

    def __init__(self, filename):
        super().__init__()
        self.set_body(self.get_body().format(f=filename))

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        self.close()


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/dialogs/savefailure.ui")
class EartagSaveFailureDialog(Adw.AlertDialog):
    __gtype_name__ = "EartagSaveFailureDialog"

    def __init__(self, filename):
        super().__init__()
        self.set_body(self.get_body().format(f=filename))

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        self.close()


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/dialogs/tagdeletewarning.ui")
class EartagTagDeleteWarningDialog(Adw.AlertDialog):
    __gtype_name__ = "EartagTagDeleteWarningDialog"

    def __init__(self, window):
        super().__init__()
        self.window = window

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response != "cancel":
            self.window.do_delete_all_tags()
        self.close()
