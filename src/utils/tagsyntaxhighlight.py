# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from ..backends.file import BASIC_TAGS, EXTRA_TAGS

from gi.repository import Adw, Pango, GObject
import re

THEMES = {
    "light": {
        "bracket_color": (61, 56, 70),
        "placeholder_colors": (
            (26, 95, 180),  # @blue_5
            (38, 162, 105),  # @green_5
            (229, 165, 10),  # @yellow_5
            (198, 70, 0),  # @orange_5
            (165, 29, 45),  # @red_5
            (97, 53, 131),  # @purple_5
            (99, 69, 44),  # @brown_5
        ),
    },
    "dark": {
        "bracket_color": (154, 153, 150),
        "placeholder_colors": (
            (153, 193, 241),  # @blue_1
            (143, 240, 164),  # @green_1
            (249, 240, 107),  # @yellow_1
            (255, 190, 111),  # @orange_1
            (246, 97, 81),  # @red_1
            (220, 138, 221),  # @purple_1
            (181, 131, 90),  # @brown_2
        ),
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


def attr_foreground_new(
    color: (int, int, int), start_index, end_index
) -> Pango.Attribute:
    """Shorthand function to create a new Pango AttrForeground."""
    attr = Pango.attr_foreground_new(
        (color[0]) * 256, (color[1]) * 256, (color[2]) * 256
    )
    attr.start_index = start_index
    attr.end_index = end_index
    return attr


def attr_underline_new(start_index, end_index) -> Pango.Attribute:
    """Shorthand function to create a new Pango AttrUnderline."""
    attr = Pango.attr_underline_new(Pango.Underline.SINGLE)
    attr.start_index = start_index
    attr.end_index = end_index
    return attr


class EartagPlaceholderSyntaxHighlighter(GObject.Object):
    """Helper object for placeholder syntax highlighting."""

    error = GObject.Property(type=bool, default=False)

    theme = GObject.Property(type=str, default="light")
    high_contrast = GObject.Property(type=bool, default=False)

    def __init__(self, widget, widget_type="entry", allow_duplicates=False):
        """
        Sets up syntax highlighting for a widget.
        """
        super().__init__()

        self._tag_positions_changed = False
        self._tag_positions = []

        self.widget = widget
        self.widget_type = widget_type
        self.allow_duplicates = allow_duplicates

        if widget_type == "entry":
            widget.get_delegate().get_buffer().connect(
                "inserted-text", self.syntax_highlighting_inserted
            )
            widget.get_delegate().get_buffer().connect(
                "deleted-text", self.syntax_highlighting_deleted
            )
        elif widget_type == "label":
            widget.connect("notify::label", self.syntax_highlighting_label_updated)

        self.widget_type = "entry"

        style_manager = Adw.StyleManager.get_default()
        style_manager.connect("notify::dark", self.update_theme)
        style_manager.connect("notify::high-contrast", self.update_theme)
        self.update_theme(style_manager)

        self.update_syntax_highlighting()

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
        attrs = Pango.AttrList()
        error = False

        # Pango attributes (used for syntax highlighting) use offsets calculated
        # in bytes, not Python characters, so we encode the pattern and filename
        # to UTF-8 so that the returned group positions match the byte count.
        if full_text is None:
            full_text = self.get_text()
        full_text = full_text.encode("utf-8")

        n = 0
        present_tags = set()
        for match in re.finditer(r"{.*?}".encode("utf-8"), full_text):
            try:
                tag_name = match.group(0)[1:-1].decode("utf-8")
            except (IndexError, UnicodeDecodeError):
                error = True
                continue

            if "{" in tag_name or "}" in tag_name:
                error = True
                continue

            if tag_name == "" or tag_name in present_tags:
                continue

            if tag_name not in BASIC_TAGS + EXTRA_TAGS + ("length", "bitrate"):
                continue

            present_tags.add(tag_name)

            # Add bracket colors
            for position in (match.span(0)[0], match.span(0)[1] - 1):
                color_attr = attr_foreground_new(
                    THEMES[self.theme]["bracket_color"], position, position + 1
                )
                attrs.insert(color_attr)

            # Add tag color
            color = THEMES[self.theme]["placeholder_colors"][
                n % len(THEMES[self.theme]["placeholder_colors"])
            ]
            color_attr = attr_foreground_new(
                color, match.span(0)[0] + 1, match.span(0)[1] - 1
            )
            attrs.insert(color_attr)

            n += 1

        self.props.error = error

        self.widget.set_attributes(attrs)

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
        full_text = full_text[:position] + full_text[position + n_chars :]
        self.update_syntax_highlighting(full_text)

    def syntax_highlighting_label_updated(self, label, *args):
        self.update_syntax_highlighting(label.get_label())
