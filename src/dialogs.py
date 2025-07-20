# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Adw, Gtk, Gdk
from . import APP_GRESOURCE_PATH
import asyncio

from enum import IntEnum


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/dialogs/closewarning.ui")
class EartagCloseWarningDialog(Adw.AlertDialog):
    __gtype_name__ = "EartagCloseWarningDialog"

    def __init__(self, window, file_manager):
        super().__init__()
        self.window = window
        self.file_manager = file_manager

    async def handle_response_async(self, dialog, response):
        if response == "discard":
            self.window.force_close = True
            self.window.close()
        elif response == "save":
            if not await self.file_manager.save_async():
                self.close()
                return
            self.window.close()
        self.close()

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        asyncio.create_task(self.handle_response_async(dialog, response))


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/dialogs/discardwarning.ui")
class EartagDiscardWarningDialog(Adw.AlertDialog):
    __gtype_name__ = "EartagDiscardWarningDialog"

    def __init__(self):
        self.closed_event = asyncio.Event()
        self.response = None

    def __del__(self):
        self.closed_event.clear()
        del self.closed_event
        del self.response

    async def wait_for_response(self):
        """Wait for a response from the dialog."""
        await self.closed_event.wait()
        return self.response

    def present(self, window):
        """Show the dialog."""
        self.closed_event.clear()
        self.response = None
        super().present(window)

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        """Save the response from the dialog to the response property."""
        self.response = response
        self.closed_event.set()
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


class EartagErrorType(IntEnum):
    """Error types which can be passed to the EartagErrorDialog."""

    ERROR_UNKNOWN = 0
    ERROR_LOAD = 1
    ERROR_RENAME = 2
    ERROR_SAVE = 3


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/dialogs/error.ui")
class EartagErrorDialog(Adw.AlertDialog):
    """Generic error dialog with a log view."""

    __gtype_name__ = "EartagErrorDialog"

    logs_view = Gtk.Template.Child()

    def __init__(self, error_type: EartagErrorType, logs: str):
        super().__init__()
        self.logs = logs

        if error_type == EartagErrorType.ERROR_LOAD:
            self.props.heading = _("Failed to Load Files")
            error_message = _("Some files could not be loaded.")

        elif error_type == EartagErrorType.ERROR_RENAME:
            self.props.heading = _("Failed to Rename Files")
            error_message = _("Some files could not be renamed.")

        elif error_type == EartagErrorType.ERROR_SAVE:
            self.props.heading = _("Failed to Save Files")
            error_message = _("Some files could not be saved.")

        else:
            self.props.heading = _("An Error Has Occured")
            error_message = _("An internal error has occured.")

        self.props.body = (
            error_message
            + "\n\n"
            + _(
                'Please copy the logs below and <a href="https://gitlab.gnome.org/World/eartag/-/issues/new">submit an issue report</a>.'
            )
        )

        self.logs_view.get_buffer().set_text(self.logs)

    def present(self, parent):
        self._parent = parent
        super().present(parent)

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == "copy":
            self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(self.logs))
            self._parent.toast_overlay.add_toast(Adw.Toast.new(_("Copied error log to clipboard")))
        self.close()
        del self._parent


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
