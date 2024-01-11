# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from . import APP_GRESOURCE_PATH

from gi.repository import Adw, Gtk, Pango, GObject
from typing import Optional
import re

THEMES = {
    "light": {
        "bracket_color": (61, 56, 70),
        "placeholder_colors": (
            (26, 95, 180),   # @blue_5
            (38, 162, 105),  # @green_5
            (229, 165, 10),  # @yellow_5
            (198, 70, 0),    # @orange_5
            (165, 29, 45),   # @red_5
            (97, 53, 131),   # @purple_5
            (99, 69, 44),    # @brown_5
        )
    },
    "dark": {
        "bracket_color": (154, 153, 150),
        "placeholder_colors": (
            (153, 193, 241),  # @blue_1
            (143, 240, 164),  # @green_1
            (249, 240, 107),  # @yellow_1
            (255, 190, 111),  # @orange_1
            (246, 97, 81),    # @red_1
            (220, 138, 221),  # @purple_1
            (181, 131, 90),   # @brown_2
        )
    },
}


def pango_attr_iter(attrlist: Pango.AttrList):
    """Provides an iterator for Pango.AttrList."""
    iter = attrlist.get_iterator()
    try:
        attr = iter.get_attrs()[0]
    except IndexError:
        return
    while attr:
        yield attr
        iter.next()
        try:
            attr = iter.get_attrs()[0]
        except IndexError:
            break

def attr_foreground_new(color: (int, int, int), start_index, end_index) -> Pango.Attribute:
    """Shorthand function to create a new Pango AttrForeground."""
    attr = Pango.attr_foreground_new((color[0])*256, (color[1])*256, (color[2])*256)
    attr.start_index = start_index
    attr.end_index = end_index
    return attr

class EartagPlaceholderSyntaxHighlighter(GObject.Object):
    """Helper object for placeholder syntax highlighting."""

    error = GObject.Property(type=bool, default=False)

    theme = GObject.Property(type=str, default="light")
    high_contrast = GObject.Property(type=bool, default=False)

    def __init__(self, widget):
        """
        Sets up syntax highlighting for a widget.
        """
        super().__init__()

        self._tag_positions_changed = False
        self._tag_positions = []

        self.attrs = Pango.AttrList()

        self.widget = widget
        widget.get_delegate().get_buffer().connect('inserted-text', self.syntax_highlighting_insert)
        widget.get_delegate().get_buffer().connect('deleted-text', self.syntax_highlighting_remove)
        widget.set_attributes(self.attrs)

        self.connect('notify::error', self.on_error)
        style_manager = Adw.StyleManager.get_default()
        style_manager.connect('notify::dark', self.update_theme)
        style_manager.connect('notify::high-contrast', self.update_theme)
        self.update_theme(style_manager)

    def update_theme(self, style_manager, *args):
        self.props.theme = "dark" if style_manager.props.dark else "light"
        self.props.high_contrast = style_manager.props.high_contrast
        self.attrs.update(0, len(self.widget.get_text()), 0)
        self.add_tags_from_text(self.widget.get_text(), 0)

    @property
    def tag_positions(self):
        """Helper function that returns tag positions."""
        error = False
        tags = []

        pos = 0
        current_tag = None
        for char in self.widget.get_text():
            if char == '{':
                if current_tag:
                    error = True
                    break
                current_tag = (pos, None, False)
            elif char == '}':
                current_tag = (current_tag[0], pos, True)
                tags.append(current_tag)
                current_tag = None

            pos += 1

        if current_tag:
            tags.append( (current_tag[0], pos, False) )

        if error != self.props.error:
            self.props.error = error

        return tags

    def tag_in_position(self, pos: int) -> Optional[int]:
        """
        Returns whether a tag is present in the entry text for the given
        position. If one is present, the index of the tag in the tag_positions
        list is returned (note that this is not necessarily the order of the
        tag in the text).
        """
        i = 0
        total_len = len(self.widget.get_text())
        for start, end, closed in self.tag_positions:
            if pos > start and (end == start or pos < end or (not closed and pos == end)):
                return i
            i += 1
        return None

    def add_tags_from_text(self, text: str, position: int = 0):
        """Adds tags from text at a starting position."""
        # Split inserted text into chunks: opening and closing brackets are
        # handled separately, as we need to note down that a placeholder
        # has been opened/closed.
        chunks = [x for x in re.split('({)|(})', text) if x]

        # Due to the chunk-based parsing, we also need to remember where
        # we are in a parse; thus, we save it to the cur_pos variable.
        cur_pos = position

        for text in chunks:
            color_attr = None
            tag_pos = self.tag_in_position(cur_pos)

            if text == '{':
                if tag_pos is None:
                    color = THEMES[self.theme]["bracket_color"]
                    color_attr = attr_foreground_new(color, cur_pos, cur_pos+len(text))
            elif text == '}':
                color = THEMES[self.theme]["bracket_color"]
                color_attr = attr_foreground_new(color, cur_pos, cur_pos+len(text))
            else:
                if tag_pos is not None:
                    self.attrs.update(cur_pos, 0, len(text))
                    color = THEMES[self.theme]["placeholder_colors"][
                        tag_pos % len(THEMES[self.theme]["placeholder_colors"])
                    ]
                    color_attr = attr_foreground_new(color, cur_pos, cur_pos+len(text))

            if color_attr and not self.props.error:
                self.attrs.change(color_attr)

            cur_pos += len(text)

    def syntax_highlighting_insert(self, entry, position: int, text: str, *args):
        """
        Updates the placeholder syntax highlighting after text insertion.
        """
        self.add_tags_from_text(text, position)

    def syntax_highlighting_remove(self, entry, position: int, n_chars: int, *args):
        """
        Updates the placeholder syntax highlighting after text removal.
        """
        self.attrs.update(position, n_chars, 0)
        self.tag_positions  # make sure error check runs

    def on_error(self, *args):
        """Handles an error."""
        if self.props.error:
            self.attrs.update(0, len(self.widget.get_text()), 0)
        else:
            self.add_tags_from_text(self.widget.get_text(), 0)

class EartagGuessRow(Gtk.Box):
    __gtype_name__ = 'EartagGuessRow'


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
        custom_syntax_highlight = EartagPlaceholderSyntaxHighlighter(self.custom_entry)
        custom_syntax_highlight.connect('notify::error', self.on_syntax_highlight_error)

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
