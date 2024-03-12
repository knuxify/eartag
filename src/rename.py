# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from . import APP_GRESOURCE_PATH
from .backends.file import EartagFile, VALID_TAGS, TAG_NAMES
from .config import config
from .utils import get_readable_length, file_is_sandboxed
from .utils.misc import filename_valid
from .utils.tagselector import EartagTagSelectorButton  # noqa: F401
from .utils.tagsyntaxhighlight import (
    EartagPlaceholderSyntaxHighlighter,
    attr_foreground_new,
    THEMES,
)
from .utils.previewselector import EartagPreviewSelectorButton  # noqa: F401

from gi.repository import Adw, GLib, Gtk, Gio, GObject, Pango
import os
import re


def tag_is_int(file, tag):
    return tag in file.int_properties + file.float_properties + ("length", "bitrate")


def get_formatted_tag(file: "EartagFile", tag: str) -> str:
    """
    Returns the value of the tag formatted according to placeholder preview rules.
    """
    parsed_value = ""

    if tag in VALID_TAGS + ("length", "bitrate"):
        value = file.get_property(tag)
        if not value:
            if tag == "title":
                parsed_value = _("Untitled")
            elif tag_is_int(file, tag):
                if tag.endswith("tracknumber") or tag.endswith("discnumber"):
                    parsed_value = "00"
                else:
                    parsed_value = "0"
            else:
                parsed_value = _("Unknown {tag_name}").format(tag_name=TAG_NAMES[tag])

        else:
            if tag_is_int(file, tag):
                if not value or value < 0:
                    value = 0
                if tag == "length":
                    parsed_value = get_readable_length(int(value))
                elif tag.endswith("tracknumber") or tag.endswith("discnumber"):
                    parsed_value = str(value).zfill(2)
                else:
                    parsed_value = str(value)
            else:
                parsed_value = str(value)
                # Other characters are cleaned by cleanup_filename; these are
                # potential file path separators we need to filter out first,
                # otherwise they'll get treated as folders (valid as far as
                # renaming and moving to a folder is concerned).
                parsed_value = parsed_value.replace("/", "_")

    return parsed_value


def parse_placeholder_string(
    placeholder: str, file: "EartagFile", positions: bool = False
) -> dict:
    """
    Takes a placeholder string and a file and returns a string filled with the
    placeholders.
    """
    if placeholder == "":
        if positions:
            return "", []
        return ""

    # Pango attributes (used for syntax highlighting) use offsets calculated
    # in bytes, not Python characters, so we encode the placeholder to UTF-8
    # so that the returned group positions match the byte count.
    placeholder = placeholder.encode("utf-8")

    n = 0
    offset = 0
    out = placeholder
    present_tags = set()
    _positions = []
    for match in re.finditer(r"{.*?}".encode("utf-8"), placeholder):
        try:
            tag_name = match.group(0)[1:-1].decode("utf-8")
        except (IndexError, UnicodeDecodeError):
            continue

        if "{" in tag_name or "}" in tag_name:
            continue

        if tag_name == "" or tag_name in present_tags:
            continue

        if tag_name not in VALID_TAGS + ("length", "bitrate"):
            continue

        present_tags.add(tag_name)

        formatted_value = get_formatted_tag(file, tag_name).encode("utf-8")
        out = out.replace(("{" + tag_name + "}").encode("utf-8"), formatted_value, 1)

        _positions.append(
            (
                match.span(0)[0] + offset,
                match.span(0)[0] + offset + len(formatted_value),
            )
        )
        offset += len(formatted_value) - len(("{" + tag_name + "}").encode("utf-8"))
        n += 1

    out = out.decode("utf-8")

    if positions:
        return out, _positions
    return out


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/rename.ui")
class EartagRenameDialog(Adw.Window):
    __gtype_name__ = "EartagRenameDialog"

    toast_overlay = Gtk.Template.Child()

    rename_button = Gtk.Template.Child()
    rename_progress = Gtk.Template.Child()
    error_banner = Gtk.Template.Child()

    sandbox_warning_banner = Gtk.Template.Child()

    filename_entry = Gtk.Template.Child()
    preview_entry = Gtk.Template.Child()
    preview_selector_button = Gtk.Template.Child()

    _last_folder = None

    folder_selector_row = Gtk.Template.Child()
    folder_remove_button = Gtk.Template.Child()

    validation_passed = GObject.Property(type=bool, default=True)

    tag_selector = Gtk.Template.Child()

    def __init__(self, window):
        super().__init__(modal=True, transient_for=window)
        self.file_manager = window.file_manager
        self._folder = None
        self._has_sandboxed_files = False

        self.files = self.file_manager.selected_files_list.copy()
        for file in self.files:
            if file_is_sandboxed(file.path):
                self._has_sandboxed_files = True
                break

        self.syntax_highlight = EartagPlaceholderSyntaxHighlighter(
            self.filename_entry, "entry", allow_duplicates=True
        )

        self.folder_chooser = Gtk.FileDialog(modal=True)
        self.bind_property(
            "folder",
            self.folder_selector_row,
            "subtitle",
            GObject.BindingFlags.SYNC_CREATE,
        )
        if EartagRenameDialog._last_folder is not None:
            self.props.folder = EartagRenameDialog._last_folder
        elif os.path.exists(config["rename-base-folder"]):
            self.props.folder = config["rename-base-folder"]

        self.file_manager.rename_task.bind_property(
            "progress", self.rename_progress, "fraction"
        )
        self.file_manager.rename_task.connect("task-done", self.on_done)

        config.bind(
            "rename-placeholder",
            self.filename_entry,
            "text",
            Gio.SettingsBindFlags.DEFAULT,
        )

        if self._has_sandboxed_files and not self.props.folder:
            self.sandbox_warning_banner.props.revealed = True

        self.preview_selector_button.set_files(self.files)
        self.preview_selector_button.set_formatting_function(
            self.generate_preview_attrs
        )
        self._preview_update_conn = self.preview_selector_button.connect(
            "notify::selected-index", self.update_preview
        )

        self.connect("notify::folder", self.validate_placeholder)
        self.connect("notify::validation-passed", self.update_rename_button_sensitivity)
        self.validate_placeholder()
        self.update_rename_button_sensitivity()

    def validate_placeholder(self, *args):
        """Validates the filename input."""
        placeholder = self.filename_entry.get_text()
        if "/" in placeholder and not self.props.folder:
            self.props.validation_passed = False
        else:
            if self.props.folder and placeholder.startswith("/"):
                self.props.validation_passed = False
            else:
                self.props.validation_passed = filename_valid(
                    self.filename_entry.get_text(), allow_path=bool(self.props.folder)
                )
        self.update_rename_button_sensitivity()
        self.folder_remove_button.props.sensitive = bool(self.props.folder)

    def update_rename_button_sensitivity(self, *args):
        if self.props.validation_passed:
            self.filename_entry.remove_css_class("error")
        else:
            self.filename_entry.add_css_class("error")

        has_sandboxed = self._has_sandboxed_files and not self.props.folder

        self.rename_button.set_sensitive(
            self.props.validation_passed and not has_sandboxed
        )

    @Gtk.Template.Callback()
    def add_placeholder_from_selector(self, selector, tag, *args):
        """Adds a new placeholder based on the tag selector."""
        self.filename_entry.insert_text(
            "{" + tag + "}", self.filename_entry.props.cursor_position
        )

    # Move to folder feature

    @GObject.Property(type=str, default=None)
    def folder(self):
        """Base folder to use for the "move to folder" option."""
        return self._folder

    @folder.setter
    def folder(self, value):
        self._folder = value
        EartagRenameDialog._last_folder = value
        if not value:
            config["rename-base-folder"] = ""
        elif not value.startswith("/run/user/"):
            config["rename-base-folder"] = value

        self.sandbox_warning_banner.props.revealed = (
            self._has_sandboxed_files and not value
        )

    @Gtk.Template.Callback()
    def show_folder_selector(self, *args):
        self.folder_chooser.select_folder(
            self, None, self.select_folder_from_selector, None
        )

    def select_folder_from_selector(self, source, result, data):
        try:
            response = self.folder_chooser.select_folder_finish(result)
        except GLib.GError:
            return

        if not response:
            return

        folder = response.get_path()
        try:
            assert os.path.exists(folder)
        except AssertionError:
            self.toast_overlay.add_toast(
                Adw.Toast.new(_("Selected folder does not exist"))
            )
        else:
            try:
                assert os.access(folder, os.W_OK)
            except AssertionError:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(_("Selected folder is read-only"))
                )
            else:
                self.props.folder = response.get_path()

    @Gtk.Template.Callback()
    def remove_folder(self, *args):
        self.props.folder = None

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        self.preview_selector_button.disconnect(self._preview_update_conn)
        self.preview_selector_button.teardown()
        self.files = None
        self.close()

    @Gtk.Template.Callback()
    def do_rename(self, *args):
        has_sandboxed = self._has_sandboxed_files and not self.props.folder
        if not (self.props.validation_passed and not has_sandboxed):
            return

        self.error_banner.set_revealed(False)
        format = self.filename_entry.get_text()
        names = []
        for file in self.files:
            if self.props.folder:
                basepath = self.props.folder
            else:
                basepath = os.path.dirname(file.props.path)
            names.append(
                os.path.join(
                    basepath,
                    parse_placeholder_string(format, file) + file.props.filetype,
                )
            )

        self.set_sensitive(False)

        self.file_manager.rename_files(self.files, names)

    # Preview

    def generate_preview_attrs(self, file: EartagFile):
        """Generates preview attributes for a given file."""
        preview_attrs = Pango.AttrList()

        parsed_placeholder, placeholder_positions = parse_placeholder_string(
            self.filename_entry.get_text(), file, positions=True
        )
        preview_text = parsed_placeholder + file.props.filetype

        for n in range(len(placeholder_positions)):
            start, end = placeholder_positions[n]
            color = THEMES[self.syntax_highlight.props.theme]["placeholder_colors"][
                n % len(THEMES[self.syntax_highlight.props.theme]["placeholder_colors"])
            ]
            color_attr = attr_foreground_new(color, start, end)
            preview_attrs.insert(color_attr)
        return preview_text, preview_attrs

    @Gtk.Template.Callback()
    def update_preview(self, *args):
        """Validates the input and updates the preview."""
        # TODO: figure out why this is needed
        if not self.files:
            self.preview_selector_button.teardown()
            return
        self.validate_placeholder()
        self.preview_selector_button.emit("formatting-changed")
        preview_text, preview_attrs = self.generate_preview_attrs(
            self.files[self.preview_selector_button.props.selected_index]
        )
        self.preview_entry.set_text(preview_text)
        self.preview_entry.set_attributes(preview_attrs)

    def on_done(self, task, *args):
        if task.failed:
            self.set_sensitive(True)
            self.error_banner.set_revealed(True)
        else:
            self.files = None
            self.close()

    @Gtk.Template.Callback()
    def on_sandbox_warning_learn_more(self, *args):
        Gio.AppInfo.launch_default_for_uri(
            "https://gitlab.gnome.org/World/eartag/-/wikis/How-to-fix-renaming-files-not-working-under-Flatpak"  # noqa: E501
        )
