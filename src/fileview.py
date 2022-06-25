# fileview.py
#
# Copyright 2022 knuxify
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE X CONSORTIUM BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# Except as contained in this notice, the name(s) of the above copyright
# holders shall not be used in advertising or otherwise to promote the sale,
# use or other dealings in this Software without prior written
# authorization.

from .file import eartagfile_from_path

from gi.repository import Adw, Gtk, GObject, Pango
from os.path import basename

class EartagEditableLabel(Gtk.EditableLabel):
    """
    Editable labels are missing a few nice features that we need
    (namely proper centering and word wrapping), but since they're
    just GtkStacks with a regular GtkLabel inside, we can modify
    them to suit our needs. This class automates the process.
    """
    __gtype_name__ = 'EartagEditableLabel'

    _placeholder = ''

    def __init__(self):
        super().__init__()

        # The layout is:
        # GtkEditableLabel
        #  -> GtkStack
        #     -> GtkStackPage
        #        -> GtkLabel
        # We use "get_first_child" since that's the easiest way to get
        # the direct child of the object (EditableLabel has no get_child).
        label = self.get_first_child().get_pages()[0].get_child()
        editable = self.get_first_child().get_pages()[1].get_child()

        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        label.set_lines(3)
        label.set_max_width_chars(128)
        label.set_justify(Gtk.Justification.CENTER)
        self.set_alignment(0.5)

        self.bind_property('placeholder', editable, 'placeholder-text',
            GObject.BindingFlags.SYNC_CREATE)

        self.connect('notify::editing', self.display_placeholder)
        self.connect('notify::text', self.display_placeholder)

        self.label = label
        self.editable = editable
        self.display_placeholder()

    def display_placeholder(self, *args):
        """Displays/hides placeholder in non-editing mode as needed."""
        if not self.get_text():
            self.label.set_label(self.placeholder)
            self.label.add_css_class('dim-label')
        else:
            self.label.remove_css_class('dim-label')

    @GObject.Property(type=str)
    def placeholder(self):
        """Placeholder to display when the text is empty."""
        return self._placeholder

    @placeholder.setter
    def placeholder(self, value):
        self._placeholder = value

class EartagTagListItem(Adw.ActionRow):
    __gtype_name__ = 'EartagTagListItem'

    _is_numeric = False

    def __init__(self):
        super().__init__(can_target=False, focusable=False, focus_on_click=False)
        self.value_entry = Gtk.Entry(valign=Gtk.Align.CENTER)
        self.add_suffix(self.value_entry)
        self.set_activatable_widget(self.value_entry)

    def disallow_nonnumeric(self, entry, text, length, position, *args):
        if text and not text.isdigit():
            GObject.signal_stop_emission_by_name(entry, 'insert-text')

    @GObject.Property(type=bool, default=False)
    def is_numeric(self):
        return self._is_numeric

    @is_numeric.setter
    def set_is_numeric(self, value):
        self._is_numeric = value
        if value == True:
            self.value_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
            self.value_entry.get_delegate().connect('insert-text', self.disallow_nonnumeric)

@Gtk.Template(resource_path='/org/dithernet/Eartag/ui/fileview.ui')
class EartagFileView(Adw.Bin):
    __gtype_name__ = 'EartagFileView'

    album_cover_image = Gtk.Template.Child()
    title_entry = Gtk.Template.Child()
    artist_entry = Gtk.Template.Child()
    album_entry = Gtk.Template.Child()
    albumartist_entry = Gtk.Template.Child()
    genre_entry = Gtk.Template.Child()
    releaseyear_entry = Gtk.Template.Child()
    comment_entry = Gtk.Template.Child()

    image_file_filter = Gtk.Template.Child()
    file = None
    bindings = []

    def __init__(self, path=None):
        """Initializes the EartagFileView."""
        super().__init__()

        self.file_path = path
        if path:
            self.load_file()

    def load_file(self):
        """Reads the file path from self.file_path and loads the file."""
        if self.bindings:
            for binding in self.bindings:
                binding.unbind()
            self.bindings = []

        self.file = eartagfile_from_path(self.file_path)

        window = self.get_native()
        window.save_button.set_visible(True)
        file_basename = basename(self.file_path)
        window.set_title('{f} — Eartag'.format(f=file_basename))
        window.window_title.set_subtitle(file_basename)
        window.content_stack.set_visible_child(self)

        self.bindings.append(
            self.file.bind_property('is_modified', window.save_button, 'sensitive',
                GObject.BindingFlags.SYNC_CREATE)
        )

        self.bindings.append(
            self.file.bind_property('cover_path', self.album_cover_image, 'file',
                GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        )

        self.setup_entry(self.title_entry, 'title')
        self.setup_entry(self.artist_entry, 'artist')
        self.setup_entry(self.album_entry, 'album')
        self.setup_entry(self.albumartist_entry, 'albumartist')
        self.setup_entry(self.genre_entry, 'genre')
        self.setup_entry(self.releaseyear_entry, 'releaseyear')
        self.setup_entry(self.comment_entry, 'comment')

    def setup_entry(self, entry, property):
        _entry = entry
        if type(entry) == EartagTagListItem:
            _entry = entry.value_entry
        elif type(entry) == EartagEditableLabel:
            _entry = entry.editable

        self.bindings.append(
            self.file.bind_property(property, _entry, 'text',
                GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        )

        if type(entry) == EartagEditableLabel:
            entry.notify('text')

    @Gtk.Template.Callback()
    def show_cover_file_chooser(self, *args):
        """Shows the file chooser."""
        self.file_chooser = Gtk.FileChooserDialog(
                                title=_("Select Album Cover Image"),
                                transient_for=self.get_native(),
                                action=Gtk.FileChooserAction.OPEN,
                                filter=self.image_file_filter
                                )
        self.file_chooser.add_buttons(
            _("_Cancel"), Gtk.ResponseType.CANCEL,
            _("_Open"), Gtk.ResponseType.ACCEPT
        )

        self.file_chooser.connect('response', self.open_cover_file_from_dialog)

        self.file_chooser.present()

    def open_cover_file_from_dialog(self, dialog, response):
        """
        Callback for a FileChooser that takes the response and opens the file
        selected in the dialog.
        """
        if response == Gtk.ResponseType.ACCEPT:
            self.file.cover_path = dialog.get_file().get_path()
        self.file_chooser.destroy()

    def save(self):
        """Saves changes to the file."""
        self.get_native().toast_overlay.add_toast(
            Adw.Toast.new(_("Saved changes to file"))
        )
        self.file.save()
