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
        self.toggle_button.update_relation(
            (Gtk.AccessibleRelation.LABELLED_BY,),
            (Gtk.AccessibleList.new_from_list((self,)),),
        )

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


def _delegate_getter(self, prop):
    return self.entry.get_delegate().get_property(prop)


def _delegate_setter(self, prop, value):
    return self.entry.get_delegate().set_property(prop, value)


class EartagEditableLabel(Gtk.Overlay, Gtk.Editable):
    """Editable label widget."""

    __gtype_name__ = "EartagEditableLabel"

    def __init__(self):
        super().__init__()
        self._last_edit_state = None

        self.add_css_class("editablelabel")

        self.entry = Gtk.Entry(valign=Gtk.Align.CENTER)
        self.entry.set_alignment(0.5)
        self.label = Gtk.Label(
            can_focus=False,
            can_target=False,
            wrap=True,
            valign=Gtk.Align.CENTER,
            lines=3,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
            ellipsize=Pango.EllipsizeMode.MIDDLE,
            max_width_chars=128,
            justify=Gtk.Justification.CENTER,
            halign=Gtk.Align.CENTER,
        )
        self.label.set_cursor(Gdk.Cursor.new_from_name("text"))

        self.set_child(self.entry)
        self.add_overlay(self.label)
        self.set_measure_overlay(self.label, True)

        self.entry.bind_property(
            "placeholder-text",
            self,
            "placeholder-text",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )
        self.entry.get_delegate().bind_property(
            "has-focus", self, "editing", GObject.BindingFlags.SYNC_CREATE
        )

        self.entry.get_delegate().connect("changed", self.update_label)
        self.entry.connect("notify::placeholder-text", self.update_label)
        self.update_label()

        self.connect("notify::editing", self.update_editing)
        self.update_editing()

        self.init_delegate()

    def update_editing(self, *args):
        if self._last_edit_state == self.props.editing:
            return

        self.entry.set_size_request(-1, self.label.get_height())

        if self.props.editing:
            # Switch which bit is visible
            self.label.props.visible = False
            self.entry.props.opacity = 1
        else:
            # Switch which bit is visible
            self.label.props.visible = True
            # self.label.props.opacity = 1
            self.entry.props.opacity = 0

        self.update_label()

        self._last_edit_state = self.props.editing

    def update_label(self, *args):
        if self.entry.props.text:
            self.label.set_text(self.entry.props.text)
            self.label.remove_css_class("dimmed")
        else:
            self.label.set_text(self.entry.props.placeholder_text or "")
            self.label.add_css_class("dimmed")

    def do_get_delegate(self):
        return self.entry.get_delegate()

    # Properties (TODO: find a better way to auto-proxy them?)
    cursor_position = GObject.Property(
        type=int,
        default=0,
        getter=lambda self: _delegate_getter(self, "cursor_position"),
        flags=GObject.ParamFlags.READABLE,
    )
    editable = GObject.Property(
        type=bool,
        default=True,
        getter=lambda self: _delegate_getter(self, "editable"),
        setter=lambda self, value: _delegate_setter(self, "editable", value),
    )
    enable_undo = GObject.Property(
        type=bool,
        default=True,
        getter=lambda self: _delegate_getter(self, "enable_undo"),
        setter=lambda self, value: _delegate_setter(self, "enable_undo", value),
    )
    max_width_chars = GObject.Property(
        type=int,
        default=-1,
        getter=lambda self: _delegate_getter(self, "max_width_chars"),
        setter=lambda self, value: _delegate_setter(self, "max_width_chars", value),
    )
    selection_bound = GObject.Property(
        type=int,
        default=0,
        getter=lambda self: _delegate_getter(self, "selection_bound"),
        setter=lambda self, value: _delegate_setter(self, "selection_bound", value),
    )
    text = GObject.Property(
        type=str,
        getter=lambda self: _delegate_getter(self, "text"),
        setter=lambda self, value: _delegate_setter(self, "text", value),
    )
    width_chars = GObject.Property(
        type=int,
        default=-1,
        getter=lambda self: _delegate_getter(self, "width_chars"),
        setter=lambda self, value: _delegate_setter(self, "width_chars", value),
    )
    xalign = GObject.Property(
        type=GObject.type_from_name("gfloat"),  # float converts to gdouble which causes warning
        default=0.0,
        getter=lambda self: _delegate_getter(self, "xalign"),
        setter=lambda self, value: _delegate_setter(self, "xalign", value),
    )

    # Custom properties
    editing = GObject.Property(type=bool, default=False)
    placeholder_text = GObject.Property(type=str)


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/albumcoverimage.ui")
class EartagAlbumCoverImage(Gtk.Stack):
    __gtype_name__ = "EartagAlbumCoverImage"

    no_cover = Gtk.Template.Child()
    cover_image = Gtk.Template.Child()

    file = None

    def __init__(self):
        super().__init__()
        self._cover_type = CoverType.FRONT
        self._connections = []
        self.connect("destroy", self.on_destroy)

    def on_destroy(self, *args):
        self.unbind_from_file()

    def bind_to_file(self, file):
        """
        Bind to a file.

        Note that only one file can be bound; binding to a file while a file is
        already bound will unbind the currently bound file.
        """
        if self.file:
            self.unbind_from_file()

        self.file = file

        if file.supports_album_covers:
            self.on_cover_change()
            self._connections.append(
                self.file.connect("notify::front-cover-path", self.on_cover_change)
            )
            self._connections.append(
                self.file.connect("notify::back-cover-path", self.on_cover_change)
            )
        else:
            self.cover_image.set_from_file(None)
            self.on_cover_change()

    def unbind_from_file(self, file=None):
        if not self.file or (file and file != self.file):
            return False

        while len(self._connections) > 0:
            self.file.disconnect(self._connections[0])
            del self._connections[0]

        del self.file
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

        # In today's episode of "fun facts about GTK/Adw internals":
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
