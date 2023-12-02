# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from .backends.file import BASIC_TAGS, TAG_NAMES
from .config import config
from .utils import get_readable_length
from . import APP_GRESOURCE_PATH

from gi.repository import Adw, Gtk, Gio
import os


def parse_placeholder_string(string, file):
    """
    Takes a string with tag placeholders and replaces them with the provided
    file's data.
    """
    output = string
    for tag in BASIC_TAGS + file.supported_extra_tags + ("length", "bitrate"):
        if tag == "title":
            null_value = "Untitled"
        elif tag in file.int_properties + file.float_properties:
            null_value = 0
        else:
            null_value = "Unknown " + TAG_NAMES[tag]

        if tag in file.int_properties + file.float_properties + ("length", "bitrate"):
            value = file.get_property(tag)
            if not value or value < 0:
                value = 0
            if tag == "length":
                tag_replaced = get_readable_length(int(value))
            elif tag == "tracknumber" or tag == "totaltracknumber":
                tag_replaced = str(value).zfill(2)
            else:
                tag_replaced = str(value)
        else:
            value = file.get_property(tag)
            if not value:
                tag_replaced = null_value
            else:
                tag_replaced = str(value).replace("/", "_")
        output = output.replace("{" + tag + "}", tag_replaced)
    if output in (",", ".", ".."):
        output = "_"
    return output


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/rename.ui")
class EartagRenameDialog(Adw.Window):
    __gtype_name__ = "EartagRenameDialog"

    rename_progress = Gtk.Template.Child()
    error_banner = Gtk.Template.Child()

    filename_entry = Gtk.Template.Child()
    preview_entry = Gtk.Template.Child()

    def __init__(self, window):
        super().__init__(modal=True, transient_for=window)
        self.file_manager = window.file_manager

        self.file_manager.rename_task.bind_property(
            "progress", self.rename_progress, "fraction"
        )
        self.file_manager.rename_task.connect("task-done", self.on_done)

        self.files = list(self.file_manager.selected_files).copy()
        config.bind(
            "rename-placeholder",
            self.filename_entry,
            "text",
            Gio.SettingsBindFlags.DEFAULT,
        )

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        self.files = None
        self.close()

    @Gtk.Template.Callback()
    def do_rename(self, *args):
        self.error_banner.set_revealed(False)
        format = self.filename_entry.get_text()
        names = []
        for file in self.files:
            basepath = os.path.dirname(file.props.path)
            names.append(
                os.path.join(
                    basepath,
                    parse_placeholder_string(format, file) + file.props.filetype,
                )
            )

        self.set_sensitive(False)

        self.file_manager.rename_files(self.files, names)

    @Gtk.Template.Callback()
    def update_preview(self, *args):
        example_file = self.file_manager.selected_files[0]
        parsed_placeholder = parse_placeholder_string(
            self.filename_entry.get_text(), example_file
        )
        self.preview_entry.set_text(parsed_placeholder + example_file.props.filetype)

    def on_done(self, task, *args):
        if task.failed:
            self.set_sensitive(True)
            self.error_banner.set_revealed(True)
        else:
            self.files = None
            self.close()
