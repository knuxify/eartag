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
