# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from . import APP_GRESOURCE_PATH
from .config import config
from .utils.bgtask import EartagBackgroundTask
from .utils.tagsyntaxhighlight import (
    EartagPlaceholderSyntaxHighlighter,
    attr_foreground_new, THEMES
)
from .utils.tagselector import EartagTagSelectorButton  # noqa: F401
from .utils.misc import filename_valid
from .backends.file import BASIC_TAGS, EXTRA_TAGS

from gi.repository import Adw, Gtk, Gio, GLib, GObject, Pango
import re
import os.path
import time

def guess_tags_from_filename(filename: str, placeholder: str, positions: bool = False) -> dict:
    """
    Takes a filename and a placeholder string and splits the filename
    up into a dict containing tag data.
    """
    # Step 1. Split placeholder string into static strings and placeholders.
    placeholder_split = [x for x in re.split('({.*?})', placeholder) if x]

    tags = []

    # Step 2. Generate regex rule from the placeholders. This replaces every
    # valid placeholder found with a Regex capture group.
    pattern = "^"
    for element in placeholder_split:
        if element.startswith('{') and element.endswith('}'):
            tag = element[1:-1]
            if tag in BASIC_TAGS + EXTRA_TAGS + ('length', 'bitrate') and tag not in tags:
                pattern += f"(?P<{tag}>.*?)"
                tags.append(tag)
                continue
        pattern += re.escape(element)
    pattern += "$"

    match = re.match(pattern, filename)

    if not match:
        return {}

    out = {}
    if positions:
        for tag in tags:
            tag_matched = match.group(tag)
            if not tag_matched:
                continue
            span = match.span(tag)
            out[tag] = (tag_matched, span)
    else:
        for tag in tags:
            tag_matched = match.group(tag)
            if not tag_matched:
                continue
            out[tag] = tag_matched

    return out


@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/guess.ui')
class EartagGuessDialog(Adw.Window):
    """Dialog for guessing selected files' tags from their filename."""
    __gtype_name__ = 'EartagGuessDialog'

    pattern_entry = Gtk.Template.Child()
    preview_entry = Gtk.Template.Child()
    apply_button = Gtk.Template.Child()
    toggle_strip_common_suffixes = Gtk.Template.Child()

    rename_progress = Gtk.Template.Child()
    content_clamp = Gtk.Template.Child()

    tag_selector = Gtk.Template.Child()

    theme = GObject.Property(type=str, default="light")

    strip_common_suffixes = GObject.Property(type=bool, default=True)

    validation_passed = GObject.Property(type=bool, default=True)

    guess_presets = [
        '{artist} - {title}'
        '{tracknumber} {title}'
        '{tracknumber} {artist} - {title}'
    ]

    def __init__(self, parent):
        super().__init__(modal=True, transient_for=parent)
        self.parent = parent
        self._connections = []
        self.custom_syntax_highlight = EartagPlaceholderSyntaxHighlighter(self.pattern_entry, "entry")
        self.custom_syntax_highlight.bind_property(
            'error', self, 'validation-passed',
            GObject.BindingFlags.SYNC_CREATE
        )
        self.custom_syntax_highlight.connect('notify::error', self.check_for_errors)
        self.connect('notify::validation-passed', self.on_syntax_highlight_error)

        self.custom_syntax_highlight.bind_property(
            'theme', self, 'theme',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self._connections.append(
            self.connect('notify::theme', self.update_preview)
        )

        self.files = parent.file_manager.selected_files_list.copy()
        self.preview_entry.set_text(os.path.basename(self.files[0].path))

        config.bind('guess-strip-common-suffixes',
            self, 'strip-common-suffixes',
            Gio.SettingsBindFlags.DEFAULT
        )
        self.bind_property(
            'strip-common-suffixes', self.toggle_strip_common_suffixes, 'active',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self._connections.append(
            self.connect('notify::strip-common-suffixes', self.update_preview)
        )

        self.tag_selector.refresh_tag_filter

        config.bind('guess-pattern',
            self.pattern_entry, 'text',
            Gio.SettingsBindFlags.DEFAULT
        )

        self.apply_task = EartagBackgroundTask(self.apply_func)
        self.apply_task.bind_property(
            'progress', self.rename_progress, 'fraction'
        )
        self.apply_task.connect('task-done', self.on_apply_done)

        # Custom filter for tag selector to filter out already present tags
        self.tag_filter = Gtk.CustomFilter.new(self.tag_filter_func, self.tag_selector.tag_model)
        self.tag_selector.set_filter(self.tag_filter)
        self.pattern_entry.connect('changed', self.tag_selector.refresh_tag_filter)

        self.pattern_entry.connect('changed', self.check_for_errors)

    @property
    def present_tags(self) -> list:
        tags = re.findall(r'{(.*?)}', self.pattern_entry.get_text())
        tags = [x for x in set(tags) if x in BASIC_TAGS + EXTRA_TAGS]
        return tags

    def tag_filter_func(self, _tag_name, *args):
        """Filter function for the tag dropdown."""
        if not self.tag_selector.tag_filter_func(_tag_name):
            return False
        tag = self.tag_selector.tag_names_swapped[_tag_name.get_string()]
        if tag in ('length', 'bitrate'):
            return False
        if tag in self.present_tags:
            return False
        return True

    @Gtk.Template.Callback()
    def add_tag_from_selector(self, selector, tag, *args):
        self.pattern_entry.set_text(self.pattern_entry.get_text() + '{' + tag + '}')

    def on_syntax_highlight_error(self, *args):
        if not self.props.validation_passed:
            self.pattern_entry.add_css_class('error')
            self.apply_button.set_sensitive(False)  # todo: only do this when custom is selected
        else:
            self.pattern_entry.remove_css_class('error')
            self.apply_button.set_sensitive(True)  # todo: only do this when custom is selected

    def get_guess(self, filename: str, positions: bool = False) -> dict:
        """
        Applies the pattern from pattern entry to the given filename
        and returns a guess (see guess_tags_from_filename function docs
        for more information).
        """
        filename_suffixless = os.path.splitext(filename)[0]

        if self.props.strip_common_suffixes:
            # Modern yt-dlp: square brackets with ID inside
            # (could be YouTube ID, or longer for e.g. SoundCloud,
            # so we don't limit it)
            if filename_suffixless.endswith(']'):
                try:
                    filename_stripped = re.match(r'(.*) [(.*)]', filename_suffixless).group(1)
                    assert filename_stripped
                except:
                    pass
                else:
                    filename_suffixless = filename_stripped

            # Old youtube-dl: "-" and then YouTube ID. To minimize
            # the likelihood for misdetections, we only check for
            # YouTube IDs that have numbers or special characters
            # in them.
            try:
                if re.match(r'-([A-Za-z0-9_\-]{11})', filename_suffixless[-12:]) \
                        and re.search(r'[0-9_\-]', filename_suffixless[-11:]):
                    filename_suffixless = filename_suffixless[:-12]
            except IndexError:
                pass

        guess = guess_tags_from_filename(
            filename_suffixless,
            self.pattern_entry.get_text(),
            positions=positions
        )

        return guess

    @Gtk.Template.Callback()
    def update_preview(self, *args):
        """Updates the text and syntax highlighting on the preview entry."""

        filename = os.path.basename(self.files[0].path)
        guess = self.get_guess(filename, positions=True)

        preview_attrs = Pango.AttrList()
        self.preview_entry.set_text(filename)

        present_tags = []
        n = 0
        for tag, tag_data in guess.items():
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

        self.preview_entry.notify('attributes')
        self.preview_entry.set_attributes(preview_attrs)

    @Gtk.Template.Callback()
    def do_apply(self, *args):
        if len(self.files) < 1:
            self.close()
        self.content_clamp.set_sensitive(False)
        self.apply_button.set_sensitive(False)
        self.apply_task.reset()
        self.apply_task.run()

    def apply_func(self):
        self.guessed = 0

        progress_step = 1 / len(self.files)

        for file in self.files:
            if self.apply_task.halt:
                self.apply_task.emit_task_done()
                return

            filename = os.path.basename(file.path)
            guess = self.get_guess(filename, positions=False)
            if not guess:
                continue

            for tag, value in guess.items():
                if tag not in EXTRA_TAGS or \
                        (tag in EXTRA_TAGS and tag in file.supported_extra_tags):
                    if tag in file.int_properties:
                        try:
                            GLib.idle_add(file.set_property, tag, int(value))
                        except (TypeError, ValueError):
                            pass
                    if tag in file.float_properties:
                        try:
                            GLib.idle_add(file.set_property, tag, float(value))
                        except (TypeError, ValueError):
                            pass
                    else:
                        GLib.idle_add(file.set_property, tag, value)

            # Sleep for a bit to make sure tags are set
            time.sleep(0.05)

            self.guessed += 1
            self.apply_task.increment_progress(progress_step)

        self.apply_task.emit_task_done()

    def on_apply_done(self, *args):
        self.parent.toast_overlay.add_toast(
            Adw.Toast.new(_("Guessed tags for {guessed} out of {total} tracks").format(
                guessed=self.guessed, total=len(self.files)
            ))
        )
        self._close()

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        if self.apply_task.is_running:
            self.apply_task.stop()
        self._close()

    def _close(self):
        for conn in self._connections:
            self.disconnect(conn)
        self.files = None
        self.close()

    def check_for_errors(self, *args):
        if self.custom_syntax_highlight.props.error:
            self.props.validation_passed = False
            return
        self.props.validation_passed = filename_valid(
            self.pattern_entry.get_text(),
            allow_path=False
        )
