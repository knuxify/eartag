# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from . import APP_GRESOURCE_PATH
from .utils.tagsyntaxhighlight import EartagPlaceholderSyntaxHighlighter
from .backends.file import BASIC_TAGS, EXTRA_TAGS, TAG_NAMES

from gi.repository import Adw, Gtk
import re

class EartagGuessRow(Gtk.Box):
    __gtype_name__ = 'EartagGuessRow'


def guess_from_filename(filename: str, placeholder: str) -> dict:
    """
    Takes a filename and a placeholder string and splits the filename
    up into a dict containing tag data.
    """
    # Step 1. Split placeholder string into static strings and placeholders.
    placeholder_split = [x for x in re.split('({.*?})', placeholder) if x]

    tags = set()

    # Step 2. Generate regex rule from the placeholders. This replaces every
    # valid placeholder found with a Regex capture group.
    pattern = "^"
    for element in placeholder_split:
        if element.startswith('{') and element.endswith('}'):
            tag = element[1:-1]
            if tag in BASIC_TAGS + EXTRA_TAGS + ('length', 'bitrate'):
                pattern += f"(?P<{tag}>.*)"
                tags.add(tag)
                continue
        pattern += re.escape(element)
    pattern += "$"

    match = re.match(pattern, filename)

    if not match:
        return {}

    out = {}
    for tag in tags:
        out[tag] = match.group(tag)

    return out

@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/guess.ui')
class EartagGuessDialog(Adw.Window):
    """Dialog for guessing selected files' tags from their filename."""
    __gtype_name__ = 'EartagGuessDialog'

    custom_entry = Gtk.Template.Child()
    apply_button = Gtk.Template.Child()

    guess_presets = [
        '{artist} - {title}'
        '{tracknumber} {title}'
        '{tracknumber} {artist} - {title}'
    ]

    def __init__(self, parent):
        super().__init__(modal=True, transient_for=parent)
        custom_syntax_highlight = EartagPlaceholderSyntaxHighlighter(self.custom_entry, "entry")
        custom_syntax_highlight.connect('notify::error', self.on_syntax_highlight_error)
        self.custom_entry.connect('changed', self.update_example)

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        self.close()

    @Gtk.Template.Callback()
    def do_apply(self, *args):
        pass

    def on_syntax_highlight_error(self, syntax, *args):
        if syntax.props.error:
            self.custom_entry.add_css_class('error')
            self.apply_button.set_sensitive(False)  # todo: only do this when custom is selected
        else:
            self.custom_entry.remove_css_class('error')
            self.apply_button.set_sensitive(True)  # todo: only do this when custom is selected

    def update_example(self, *args):
        guess_from_filename("test - my example filename", self.custom_entry.get_text())
