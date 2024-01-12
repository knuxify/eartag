# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from ..backends.file import BASIC_TAGS, EXTRA_TAGS, TAG_NAMES

from gi.repository import Adw, Gtk, Pango, GObject, GLib
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

    def __init__(self, widget, widget_type="entry"):
        """
        Sets up syntax highlighting for a widget.
        """
        super().__init__()

        self._tag_positions_changed = False
        self._tag_positions = []

        self.attrs = Pango.AttrList()

        self.widget = widget
        self.widget_type = widget_type

        if widget_type == "entry":
            # If we bind to the standard changed signal, the attrs don't update
            # until another character is set; this seems to be early enough to work.
            widget.get_delegate().get_buffer().connect('inserted-text', self.syntax_highlighting_inserted)
            widget.get_delegate().get_buffer().connect('deleted-text', self.syntax_highlighting_deleted)
        elif widget_type == "label":
            widget.connect('notify::label', self.syntax_highlighting_label_updated)

        widget.set_attributes(self.attrs)

        self.widget_type = "entry"

        style_manager = Adw.StyleManager.get_default()
        style_manager.connect('notify::dark', self.update_theme)
        style_manager.connect('notify::high-contrast', self.update_theme)
        self.update_theme(style_manager)

    def get_text(self):
        if self.widget_type == "entry":
            return self.widget.get_text()
        elif self.widget_type == "label":
            return self.widget.get_label()

    def update_theme(self, style_manager, *args):
        self.props.theme = "dark" if style_manager.props.dark else "light"
        self.props.high_contrast = style_manager.props.high_contrast
        self.update_syntax_highlighting()

    def update_syntax_highlighting(self, full_text=None):
        """Helper function that returns tag positions."""

        # You might call this a lazy implementation - every time text is
        # inserted or removed, we clear all attributes and re-do everything
        # from scratch. A *good* implementation would instead only modify
        # the parts that are needed.
        #
        # I spent an entire day writing such an implementation, before I
        # realized that I had written nearly 150 lines of code, and it still
        # wasn't working like I wanted to. To handle all sorts of edge cases,
        # I'd need to add a lot more checks.
        #
        # So, if it were a "good" implementation, we would have to perform
        # many more checks and write a lot more code for something that would
        # cause all formatting to fall apart if only the user dares to insert
        # something in a different order than you anticipated.
        #
        # The performance difference is negligible (we're dealing with strings
        # that are like ~40 characters tops!), and this is probably faster
        # since we don't have to do all these checks. Feel free to rewrite this
        # if you think that you can do it better, but remember to increase the
        # Counter of Hours Lost to Attribute Issues below:
        #
        # HOURS_LOST = 12

        # Clear all existing attributes
        self.attrs.filter(lambda *a: True)

        error = False
        tags = []

        def add_bracket_color(position):
            color = THEMES[self.theme]["bracket_color"]
            color_attr = attr_foreground_new(color, position, position+1)
            self.attrs.insert(color_attr)

        def add_tag_color(tag_number, start, end):
            color = THEMES[self.theme]["placeholder_colors"][
                tag_number % len(THEMES[self.theme]["placeholder_colors"])
            ]
            color_attr = attr_foreground_new(color, start, end)
            self.attrs.insert(color_attr)

        pos = 0
        current_tag = None
        n_tags = 0

        if full_text is None:
            full_text = self.get_text()

        for char in full_text:
            if char == '{':
                if current_tag:
                    error = True
                    break
                current_tag = (pos, None, False)
                add_bracket_color(pos)

            elif char == '}':
                try:
                    current_tag = (current_tag[0], pos, True)
                except TypeError:  # current_tag is None
                    error = True
                    break

                tag_name = full_text[current_tag[0]+1:current_tag[1]]
                if tag_name in BASIC_TAGS + EXTRA_TAGS + ('length', 'bitrate'):
                    add_tag_color(n_tags, current_tag[0]+1, current_tag[1])
                add_bracket_color(pos)

                n_tags += 1
                tags.append(current_tag)
                current_tag = None

            pos += 1

        if current_tag:
            n_tags += 1
            tags.append( (current_tag[0], pos, False) )

        self.props.error = error
        assert self.props.error == error

        if self.widget_type == "entry":
            GLib.idle_add(self.widget.get_delegate().queue_draw)

    def syntax_highlighting_inserted(self, *args):
        """
        Updates the placeholder syntax highlighting after text insertion.
        """
        self.update_syntax_highlighting()

    def syntax_highlighting_deleted(self, entry, position: int, n_chars: int):
        """
        Updates the placeholder syntax highlighting after text removal.
        """
        full_text = entry.get_text()
        full_text = full_text[:position] + full_text[position+n_chars:]
        self.update_syntax_highlighting(full_text)

    def syntax_highlighting_label_updated(self, label, *args):
        self.update_syntax_highlighting(label.get_label())
