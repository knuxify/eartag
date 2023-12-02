# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Adw, Gdk, Gtk, GObject, Pango
import os.path

from ..backends.file import CoverType
from .. import APP_GRESOURCE_PATH


class EartagPopoverButton(Gtk.Box):
    """
    Re-implementation of GtkMenuButton that doesn't have the same issues as
    it does. Notably:

    - doesn't prevent arrow navigation from working correctly
    - doesn't suffer from https://gitlab.gnome.org/GNOME/gtk/-/issues/5568
      (though that one is actually worked around in the AlbumCoverButton)
    """

    __gtype_name__ = "EartagPopoverButton"

    def __init__(self):
        super().__init__()
        self._popover = None
        self.toggle_button = Gtk.ToggleButton()
        self.append(self.toggle_button)

    @GObject.Property(type=Gtk.Widget)
    def child(self):
        return self.toggle_button.get_child()

    @child.setter
    def child(self, value):
        return self.toggle_button.set_child(value)

    @GObject.Property(type=Gtk.Popover)
    def popover(self):
        """The popover to display."""
        return self._popover

    @popover.setter
    def popover(self, value):
        if self._popover:
            self.remove(self._popover)
        self._popover = value
        self.toggle_button.bind_property(
            "active", self.popover, "visible", GObject.BindingFlags.BIDIRECTIONAL
        )
        self.append(self._popover)


class EartagEditableLabel(Gtk.EditableLabel):
    """
    Editable labels are missing a few nice features that we need
    (namely proper centering and word wrapping), but since they're
    just GtkStacks with a regular GtkLabel inside, we can modify
    them to suit our needs. This class automates the process.
    """

    __gtype_name__ = "EartagEditableLabel"

    def __init__(self):
        super().__init__()
        self._placeholder = ""
        self._original_placeholder = ""

        # The layout is:
        # GtkEditableLabel
        #  -> GtkStack
        #     -> GtkStackPage
        #        -> GtkLabel
        # We use "get_first_child" since that's the easiest way to get
        # the direct child of the object (EditableLabel has no get_child).
        stack = self.get_first_child()
        label = stack.get_pages()[0].get_child()
        editable = stack.get_pages()[1].get_child()

        # If we make the editable label focusable, clicking on it to edit it
        # then clicking on another field will cause the editable label to
        # return the focus to itself. Making it unfocusable fixes it, but also
        # makes it impossible to switch to it using the keyboard. So instead,
        # we make the inner stack focusable, which avoids this behavior while
        # still making the label selectable with the keyboard.
        self.set_focusable(False)
        stack.set_focusable(True)

        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        label.set_lines(3)
        label.set_max_width_chars(128)
        label.set_justify(Gtk.Justification.CENTER)
        label.set_cursor(Gdk.Cursor.new_from_name("text"))
        self.set_alignment(0.5)

        self.bind_property(
            "placeholder-text",
            editable,
            "placeholder-text",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.connect("notify::editing", self.display_placeholder)
        self.connect("notify::text", self.display_placeholder)

        self.label = label
        self.editable = editable
        self.stack = stack
        self.display_placeholder()

    def display_placeholder(self, *args):
        """Displays/hides placeholder in non-editing mode as needed."""
        if not self.get_text():
            self.label.set_label(self.placeholder_text)
            self.label.add_css_class("dim-label")
        else:
            self.label.remove_css_class("dim-label")
        self.stack.update_property(
            [Gtk.AccessibleProperty.LABEL], [self.label.get_label()]
        )

    @GObject.Property(type=str)
    def placeholder_text(self):
        """Placeholder to display when the text is empty."""
        return self._placeholder

    @placeholder_text.setter
    def placeholder_text(self, value):
        self._placeholder = value
        self.display_placeholder()


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/albumcoverimage.ui")
class EartagAlbumCoverImage(Gtk.Stack):
    __gtype_name__ = "EartagAlbumCoverImage"

    no_cover = Gtk.Template.Child()
    cover_image = Gtk.Template.Child()

    file = None

    def __init__(self):
        super().__init__()
        self._cover_type = CoverType.FRONT
        self.connect("destroy", self.on_destroy)

    def on_destroy(self, *args):
        self.file = None

    def bind_to_file(self, file):
        self.file = file

        if file.supports_album_covers:
            self.on_cover_change()
            self.file.connect("notify::front-cover-path", self.on_cover_change)
            self.file.connect("notify::back-cover-path", self.on_cover_change)
        else:
            self.cover_image.set_from_file(None)
            self.on_cover_change()

    def unbind_from_file(self, file=None):
        if not self.file or (file and file != self.file):
            return False
        self.file = None

    def mark_as_empty(self):
        """In some cases, we need to force the cover to be shown as empty."""
        if self.get_visible_child() is not self.no_cover:
            self.set_visible_child(self.no_cover)
            self.notify("is-empty")

    def mark_as_nonempty(self):
        self.on_cover_change()

    @GObject.Property(type=bool, default=True)
    def is_empty(self):
        return self.get_visible_child() == self.no_cover

    @GObject.Signal
    def cover_changed(self):
        pass

    def on_cover_change(self, *args):
        if not self.file:
            self.mark_as_empty()
            return

        if self.cover_type == CoverType.FRONT:
            path = self.file.front_cover_path
            cover = self.file.front_cover
        elif self.cover_type == CoverType.BACK:
            path = self.file.back_cover_path
            cover = self.file.back_cover
        else:
            raise ValueError(self.cover_type)

        if path and os.path.exists(path):
            if self.get_visible_child() is not self.cover_image:
                self.set_visible_child(self.cover_image)
                self.notify("is-empty")

            if self.cover_image.get_pixel_size() <= 48:
                pixbuf = cover.cover_small
            else:
                pixbuf = cover.cover_large

            self.cover_image.set_from_pixbuf(pixbuf)
        else:
            self.mark_as_empty()

        self.emit("cover_changed")

    @GObject.Property(type=int, default=196)
    def pixel_size(self):
        return self.cover_image.get_pixel_size()

    @pixel_size.setter
    def pixel_size(self, value):
        self.cover_image.set_pixel_size(value)
        if value < 100:
            if value > 28:
                self.no_cover.set_pixel_size(24)
            else:
                self.no_cover.set_pixel_size(value - 4)
        else:
            self.no_cover.set_pixel_size(96)

    @GObject.Property(type=int)
    def cover_type(self):
        """Whether to display the front or back cover."""
        return self._cover_type

    @cover_type.setter
    def cover_type(self, value):
        self._cover_type = value
        self.on_cover_change()


class EartagModelExpanderRow(Adw.ExpanderRow):
    """
    Subclass of AdwExpanderRow that automatically fills rows based on
    a list model, and exposes some nice-to-have information about child
    rows.
    """

    def __init__(self):
        super().__init__()
        self.model = None

        # In today's episode of "fun facts about GTK/Adw internals:
        # did you know that an AdwExpanderRow consists of not one, but *two*
        # listboxes? That's right - the expander row appears to be a ListBox
        # of its own, and right below it is a GtkRevealer with *another*
        # ListBox in it, simply named "list".

        # Anyways, most of this isn't relevant here. What's relevant is that
        # this is, after all, a listbox inside, so we can just grab it with
        # get_template_child and use the model binding functions there.

        self.list = self.get_template_child(Adw.ExpanderRow, "list")

    def bind_model(self, *args, **kwargs):
        """See Gtk.ListBox.bind_model"""
        return self.list.bind_model(*args, **kwargs)

    def get_row_at_index(self, *args, **kwargs):
        """See Gtk.ListBox.get_row_at_index"""
        return self.list.get_row_at_index(*args, **kwargs)

    def set_placeholder(self, *args, **kwargs):
        """See Gtk.ListBox.set_placeholder"""
        return self.list.set_placeholder(*args, **kwargs)
