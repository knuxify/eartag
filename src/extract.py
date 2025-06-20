# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from . import APP_GRESOURCE_PATH
from .backends.file import EartagFile, VALID_TAGS, EXTRA_TAGS
from .config import config
from .utils.asynctask import EartagAsyncTask
from .utils.extracttags import extract_tags_from_filename
from .utils.tagsyntaxhighlight import (
    EartagPlaceholderSyntaxHighlighter,
    attr_foreground_new,
    THEMES,
)
from .utils.previewselector import EartagPreviewSelectorButton  # noqa: F401
from .utils.tagselector import EartagTagSelectorButton  # noqa: F401
from .utils.misc import filename_valid

from gi.repository import Adw, Gtk, Gio, GObject, Pango
import re
import os.path


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/extract.ui")
class EartagExtractTagsDialog(Adw.Dialog):
    """Dialog for extracting selected files' tags from their filename."""

    __gtype_name__ = "EartagExtractTagsDialog"

    pattern_entry = Gtk.Template.Child()
    preview_entry = Gtk.Template.Child()
    preview_selector_button = Gtk.Template.Child()
    apply_button = Gtk.Template.Child()
    toggle_strip_common_suffixes = Gtk.Template.Child()

    rename_progress = Gtk.Template.Child()
    content_clamp = Gtk.Template.Child()

    tag_selector = Gtk.Template.Child()

    theme = GObject.Property(type=str, default="light")

    strip_common_suffixes = GObject.Property(type=bool, default=True)
    validation_passed = GObject.Property(type=bool, default=True)

    preview_selector_button = Gtk.Template.Child()

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self._connections = []
        self.custom_syntax_highlight = EartagPlaceholderSyntaxHighlighter(
            self.pattern_entry, "entry"
        )
        self.custom_syntax_highlight.bind_property(
            "error", self, "validation-passed", GObject.BindingFlags.SYNC_CREATE
        )
        self.custom_syntax_highlight.connect("notify::error", self.check_for_errors)
        self.connect("notify::validation-passed", self.on_syntax_highlight_error)

        self._entry_conn = self.pattern_entry.connect("changed", self.update_preview)

        self.custom_syntax_highlight.bind_property(
            "theme",
            self,
            "theme",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )
        self._connections.append(self.connect("notify::theme", self.update_preview))

        self.files = parent.file_manager.selected_files_list.copy()

        self.preview_selector_button.set_files(self.files)
        self.preview_selector_button.set_formatting_function(self.generate_preview_attrs)
        self._preview_update_conn = self.preview_selector_button.connect(
            "notify::selected-index", self.update_preview
        )

        config.bind(
            "extract-strip-common-suffixes",
            self,
            "strip-common-suffixes",
            Gio.SettingsBindFlags.DEFAULT,
        )
        self.bind_property(
            "strip-common-suffixes",
            self.toggle_strip_common_suffixes,
            "active",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )
        self._connections.append(self.connect("notify::strip-common-suffixes", self.update_preview))

        config.bind("extract-pattern", self.pattern_entry, "text", Gio.SettingsBindFlags.DEFAULT)

        self.apply_task = EartagAsyncTask(self.apply_func)
        self.apply_task.bind_property("progress", self.rename_progress, "fraction")
        self.apply_task.connect("task-done", self.on_apply_done)

        # Custom filter for tag selector to filter out already present tags
        self.tag_filter = Gtk.CustomFilter.new(self.tag_filter_func, self.tag_selector.tag_model)
        self.tag_selector.set_filter(self.tag_filter)

        self.pattern_entry.connect("changed", self.tag_selector.refresh_tag_filter)
        self.pattern_entry.connect("changed", self.check_for_errors)

        self.check_for_errors()
        self.update_preview()
        self.tag_selector.refresh_tag_filter()

    @property
    def present_tags(self) -> list:
        tags = re.findall(r"{(.*?)}", self.pattern_entry.get_text())
        tags = [x for x in set(tags) if x in VALID_TAGS]
        return tags

    def tag_filter_func(self, _tag_name, *args):
        """Filter function for the tag dropdown."""
        if not self.tag_selector.tag_filter_func(_tag_name):
            return False
        tag = self.tag_selector.tag_names_swapped[_tag_name.get_string()]
        if tag in ("length", "bitrate"):
            return False
        if tag in self.present_tags:
            return False
        return True

    @Gtk.Template.Callback()
    def add_tag_from_selector(self, selector, tag, *args):
        self.pattern_entry.insert_text("{" + tag + "}", self.pattern_entry.props.cursor_position)

    def on_syntax_highlight_error(self, *args):
        if not self.props.validation_passed:
            self.pattern_entry.add_css_class("error")
            self.apply_button.set_sensitive(False)  # todo: only do this when custom is selected
        else:
            self.pattern_entry.remove_css_class("error")
            self.apply_button.set_sensitive(True)  # todo: only do this when custom is selected

    def get_extracted(self, filename: str, positions: bool = False) -> dict:
        """
        Applies the pattern from pattern entry to the given filename
        and returns a guess (see extract_tags_from_filename function docs
        for more information).
        """
        filename_suffixless = os.path.splitext(filename)[0]

        if self.props.strip_common_suffixes:
            # Modern yt-dlp: square brackets with ID inside
            # (could be YouTube ID, or longer for e.g. SoundCloud,
            # so we don't limit it)
            if filename_suffixless.endswith("]"):
                try:
                    filename_stripped = re.match(r"(.*?) \[(.*)\]", filename_suffixless).group(1)
                    assert filename_stripped
                except (AssertionError, AttributeError, IndexError):
                    pass
                else:
                    filename_suffixless = filename_stripped

            # Old youtube-dl: "-" and then YouTube ID. To minimize
            # the likelihood for misdetections, we only check for
            # YouTube IDs that have numbers or special characters
            # in them.
            try:
                if re.match(r"-([A-Za-z0-9_\-]{11})", filename_suffixless[-12:]) and re.search(
                    r"[0-9_\-]", filename_suffixless[-11:]
                ):
                    filename_suffixless = filename_suffixless[:-12]
            except IndexError:
                pass

        extracted = extract_tags_from_filename(
            filename_suffixless, self.pattern_entry.get_text(), positions=positions
        )

        return extracted

    def generate_preview_attrs(self, file: EartagFile):
        filename = os.path.basename(file.props.path)
        extracted = self.get_extracted(filename, positions=True)

        preview_attrs = Pango.AttrList()
        self.preview_entry.set_text(filename)

        present_tags = []
        n = 0
        for tag, tag_data in extracted.items():
            if tag in present_tags:
                continue
            present_tags.append(tag)
            span = tag_data[1]
            color = THEMES[self.props.theme]["placeholder_colors"][
                n % len(THEMES[self.props.theme]["placeholder_colors"])
            ]
            color_attr = attr_foreground_new(color, span[0], span[1])
            preview_attrs.insert(color_attr)
            n += 1

        self.preview_entry.notify("attributes")
        self.preview_entry.set_attributes(preview_attrs)

        return (filename, preview_attrs)

    def update_preview(self, *args):
        """Updates the text and syntax highlighting on the preview entry."""
        self.preview_selector_button.emit("formatting-changed")
        preview_text, preview_attrs = self.generate_preview_attrs(
            self.files[self.preview_selector_button.props.selected_index]
        )
        self.preview_entry.set_text(preview_text)
        self.preview_entry.set_attributes(preview_attrs)

    @Gtk.Template.Callback()
    def do_apply(self, *args):
        if self.apply_button.props.sensitive is False:
            return
        if len(self.files) < 1:
            self.close()
        self.content_clamp.set_sensitive(False)
        self.apply_button.set_sensitive(False)
        self.set_can_close(False)
        self.apply_task.run()

    async def apply_func(self):
        self.extracted = 0

        progress_step = 1 / len(self.files)

        for file in self.files:
            filename = os.path.basename(file.path)
            extract = self.get_extracted(filename, positions=False)
            if not extract:
                continue

            for tag, value in extract.items():
                if tag not in EXTRA_TAGS or (
                    tag in EXTRA_TAGS and tag in file.supported_extra_tags
                ):
                    if tag in file.int_properties:
                        try:
                            file.set_property(tag, int(value))
                        except (TypeError, ValueError):
                            pass
                    elif tag in file.float_properties:
                        try:
                            file.set_property(tag, float(value))
                        except (TypeError, ValueError):
                            pass
                    else:
                        try:
                            value = value.strip()
                        except AttributeError:
                            pass
                        file.set_property(tag, value)

            self.extracted += 1
            self.apply_task.increment_progress(progress_step)

    def on_apply_done(self, *args):
        self.parent.toast_overlay.add_toast(
            Adw.Toast.new(
                ngettext(
                    # TRANSLATORS: {extracted} is a placeholder for the number
                    # of tracks the tags were succesfully extracted for.
                    # **Do not translate the text between the curly brackets!**
                    "Extracted tags for 1 track",
                    "Extracted tags for {extracted} tracks",
                    self.extracted,
                ).format(extracted=self.extracted)
            )
        )
        self._close()

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        if self.apply_task.is_running:
            self.apply_task.stop()
        self.preview_selector_button.disconnect(self._preview_update_conn)
        self.preview_selector_button.teardown()
        self.set_can_close(True)
        self._close()

    def _close(self):
        for conn in self._connections:
            self.disconnect(conn)
        self.pattern_entry.disconnect(self._entry_conn)
        self._connections = []
        self._entry_conn = None
        self.files = None
        self.set_can_close(True)
        self.close()

    def check_for_errors(self, *args):
        if self.custom_syntax_highlight.props.error:
            self.props.validation_passed = False
            return
        self.props.validation_passed = filename_valid(
            self.pattern_entry.get_text(), allow_path=False
        )
