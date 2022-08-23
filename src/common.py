# common.py
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

# This file contains various functions/classes used in multiple places that
# were generic enough to be split into a single file.

from gi.repository import Gtk, GObject, Pango
import os.path
import magic
import mimetypes

VALID_NONAUDIO_MIMES = ('application/ogg', 'application/x-ogg', 'video/x-wmv')
def is_valid_music_file(path):
    """
    Takes a path to a file and returns True if it's supported, False otherwise.
    """
    # In Flatpak, some files don't exist; double-check to make sure
    if not os.path.exists(path):
        return False

    mimetype = magic.Magic(mime=True).from_file(path)
    if mimetype == 'application/octet-stream':
        # Try to guess mimetype from filetype if magic fails
        mimetype = mimetypes.guess_type(path)[0]

    if not mimetype or not mimetype.startswith('audio/') and mimetype not in VALID_NONAUDIO_MIMES:
        return False
    return True

def is_valid_image_file(path):
    """
    Takes a path to a file and returns True if it's supported, False otherwise.
    """
    # In Flatpak, some files don't exist; double-check to make sure
    if not os.path.exists(path):
        return False

    mimetype = magic.Magic(mime=True).from_file(path)
    if mimetype == 'application/octet-stream':
        # Try to guess mimetype from filetype if magic fails
        mimetype = mimetypes.guess_type(path)[0]

    if not mimetype or not mimetype in ['image/jpeg', 'image/png']:
        return False
    return True

class EartagMultipleValueEntry:
    """
    A set of common functions used by entries that can have multiple values.

    Usage instructions:
      - Inherit from this class in the desired object.
      - Set the properties list to contain the property the entry is bound to.
      - Connect the on_changed signal to your entry's change.
    """
    def refresh_multiple_values(self, file=None):
        if not file:
            try:
                file = self.files[0]
            except IndexError:
                return False

        self._setup_entry(self.value_entry, file, False)
        if self._is_double:
            self._setup_entry(self.value_entry_double, file, True)

    def _multiple_values_check(self, checked_file, property):
        """
        Used internally in bind_to_property to figure out if there are
        multiple values for a property.

        Returns True if there are multiple values, False otherwise.
        """
        value = checked_file.get_property(property)
        for _file in self.files:
            if _file == checked_file:
                continue

            if _file.get_property(property) != value:
                return True
        return False

    def _setup_entry(self, entry, file, is_double):
        has_multiple_files = len(self.files) > 1

        # TRANSLATORS: Placeholder displayed when multiple files with different values are created
        _multiple_values =_('(multiple values)')

        property = (is_double and self.properties[1]) or self.properties[0]
        if has_multiple_files and self._multiple_values_check(file, property):
            entry.set_placeholder_text(_multiple_values)
            self.ignore_edit[property] = True
            entry.set_text('')
            self.ignore_edit[property] = False
        else:
            self.ignore_edit[property] = True
            entry.set_text(str(file.get_property(property)) or '')
            self.ignore_edit[property] = False
            entry.set_placeholder_text('')

    def bind_to_file(self, file):
        if file in self.files:
            return
        self.files.append(file)
        self.refresh_multiple_values(file)

    def unbind_from_file(self, file):
        if file not in self.files:
            return
        self.files.remove(file)
        self.refresh_multiple_values()

    def on_changed(self, entry, is_double=False):
        property = (is_double and self.properties[1]) or self.properties[0]
        if property in self.ignore_edit and not self.ignore_edit[property]:
            value = entry.get_text()
            if self._is_numeric:
                try:
                    value = int(value)
                except ValueError:
                    value = -1
            for file in self.files:
                if file.get_property(property) != value:
                    if self._is_numeric and not value:
                        continue
                        #file.set_property(property, -1)
                    file.set_property(property, value)
        else:
            return False

class EartagEditableLabel(Gtk.EditableLabel, EartagMultipleValueEntry):
    """
    Editable labels are missing a few nice features that we need
    (namely proper centering and word wrapping), but since they're
    just GtkStacks with a regular GtkLabel inside, we can modify
    them to suit our needs. This class automates the process.
    """
    __gtype_name__ = 'EartagEditableLabel'

    _is_numeric = False
    _is_double = False

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

        # Setup necessary for EartagMultipleValueEntry
        self.value_entry = self
        self.connect('changed', self.on_changed)

        self.label = label
        self.editable = editable
        self.display_placeholder()

        self.files = []
        self.properties = []
        self.ignore_edit = {}

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

    # Implemented for EartagMultipleValueEntry
    def set_placeholder_text(self, value):
        self.set_property('placeholder', value)
        self.display_placeholder()

    def _setup_entry(self, entry, file, is_double):
        EartagMultipleValueEntry._setup_entry(self, entry, file, is_double)
        self.display_placeholder()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/albumcoverimage.ui')
class EartagAlbumCoverImage(Gtk.Stack):
    __gtype_name__ = 'EartagAlbumCoverImage'

    no_cover = Gtk.Template.Child()
    cover_image = Gtk.Template.Child()

    file = None
    image_file_binding = None

    def __init__(self):
        super().__init__()
        self.connect('destroy', self.on_destroy)

    def on_destroy(self, *args):
        if self.image_file_binding:
            self.image_file_binding.unbind()
        self.file = None

    def bind_to_file(self, file):
        if self.image_file_binding:
            self.image_file_binding.unbind()
        self.image_file_binding = None

        self.file = file

        if file.supports_album_covers:
            self.image_file_binding = self.file.bind_property(
                    'cover_path', self.cover_image, 'file',
                    GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
            )
            self.on_cover_change()
            self.file.connect('notify::cover_path', self.on_cover_change)
        else:
            self.cover_image.set_from_file(None)
            self.on_cover_change()

    def on_cover_change(self, *args):
        if self.file.cover_path and os.path.exists(self.file.cover_path):
            self.set_visible_child(self.cover_image)
        else:
            self.set_visible_child(self.no_cover)

    @GObject.Property(type=int, default=196)
    def pixel_size(self):
        return self.cover_image.get_pixel_size()

    @pixel_size.setter
    def pixel_size(self, value):
        self.cover_image.set_pixel_size(value)
        if value < 100:
            if value > 36:
                self.no_cover.set_pixel_size(32)
            else:
                self.no_cover.set_pixel_size(value - 4)
        else:
            self.no_cover.set_pixel_size(96)
