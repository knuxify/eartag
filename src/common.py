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

from gi.repository import Gdk, GLib, Gtk, GObject, Pango
import os.path
import magic
import mimetypes
import threading
import time

VALID_AUDIO_MIMES = (
    'application/ogg',
    'application/x-ogg',
    'audio/aac',
    'audio/flac',
    'audio/mp3',
    'audio/mp4',
    'audio/mpeg',
    'audio/ogg',
    'audio/wav',
    'audio/x-flac',
    'audio/x-m4a',
    'audio/x-mp3',
    'audio/x-mpeg',
    'audio/x-ms-wma',
    'audio/x-vorbis+ogg',
    'audio/x-wav',
    'video/mp4',
    'video/x-ms-asf',
    'video/x-wmv'
    )

def is_valid_music_file(path):
    """
    Takes a path to a file and returns True if it's supported, False otherwise.
    """
    # In Flatpak, some files don't exist; double-check to make sure
    if not os.path.exists(path):
        return False

    mimetype = magic.from_file(path, mime=True)
    if mimetype == 'application/octet-stream':
        # Try to guess mimetype from filetype if magic fails
        mimetype = mimetypes.guess_type(path)[0]

    if not mimetype or mimetype not in VALID_AUDIO_MIMES:
        return False
    return True

def is_valid_image_file(path):
    """
    Takes a path to a file and returns True if it's supported, False otherwise.
    """
    # In Flatpak, some files don't exist; double-check to make sure
    if not os.path.exists(path):
        return False

    mimetype = magic.from_file(path, mime=True)
    if mimetype == 'application/octet-stream':
        # Try to guess mimetype from filetype if magic fails
        mimetype = mimetypes.guess_type(path)[0]

    if not mimetype or mimetype not in ['image/jpeg', 'image/png']:
        return False
    return True

def get_readable_length(length):
    """Returns human-readable version of the length, given in seconds."""
    length_min, length_sec = divmod(int(length), 60)
    length_hour, length_min = divmod(length_min, 60)

    if length_hour:
        length_readable = '{h}∶{m}∶{s}'.format(
            h=str(length_hour).rjust(2, '0'),
            m=str(length_min).rjust(2, '0'),
            s=str(length_sec).rjust(2, '0')
        )
    else:
        length_readable = '{m}∶{s}'.format(
            m=str(length_min).rjust(2, '0'),
            s=str(length_sec).rjust(2, '0')
        )

    return length_readable

class EartagBackgroundTask(GObject.Object):
    """
    Convenience class for creating tasks that run in the background
    without freezing the UI.

    Provides a "progress" property that can be used by target functions
    to signify a progress change. This is a float from 0 to 1 and is
    passed directly to GtkProgressBar.

    Also provides an optional "halt" property; target functions can
    check for this property to stop an operation early.

    Remember to pass all code that interacts with GTK through
    GLib.idle_add().
    """
    def __init__(self, target, *args, **kwargs):
        super().__init__()
        self._progress = 0
        self.target = target
        self.reset(args, kwargs)

    def wait_for_completion(self):
        while self.thread.is_alive():
            time.sleep(0.25)

    def stop(self):
        self.halt = True
        self.wait_for_completion()
        self.halt = False

    def run(self):
        self.thread.start()

    def reset(self, args=[], kwargs=[]):
        """Re-creates the inner thread with new args and kwargs."""
        self._is_done = False
        self.thread = None
        self.halt = False
        self.failed = False
        if args and kwargs:
            self.thread = threading.Thread(
                target=self.target, daemon=True,
                args=args, kwargs=kwargs
            )
        elif args:
            self.thread = threading.Thread(
                target=self.target, daemon=True,
                args=args
            )
        elif kwargs:
            self.thread = threading.Thread(
                target=self.target, daemon=True,
                kwargs=kwargs
            )
        else:
            self.thread = threading.Thread(
                target=self.target, daemon=True
            )

    @GObject.Property(type=float, minimum=0, maximum=1)
    def progress(self):
        """
        Float from 0 to 1 signifying the current progress of the operation.
        When the task is done, this automatically resets to 0.

        This value is set by the target function.
        """
        return self._progress

    @progress.setter
    def progress(self, value):
        self._progress = value

    @GObject.Signal
    def task_done(self):
        self.reset_progress()
        self._is_done = True

    def reset_progress(self):
        self.props.progress = 0

    def set_progress_threadsafe(self, value):
        """
        Wrapper around self.props.progress that updates the progress, wrapped
        around GLib.idle_add. This is the preferred way for users to set the
        progress variable.
        """
        GLib.idle_add(lambda *args: self.set_property('progress', value))

    def increment_progress(self, value):
        """
        Wrapper around self.props.progress that increments the progress, wrapped
        around GLib.idle_add. This is the preferred way for users to increment the
        progress variable.
        """
        self.set_progress_threadsafe(self.props.progress + value)

    def emit_task_done(self):
        """
        Wrapper around self.emit('task-done') that is wrapped around
        GLib.idle_add. This is the preferred way for users to emit the
        task-done signal.
        """
        GLib.idle_add(lambda *args: self.emit('task-done'))

class EartagMultipleValueEntry:
    """
    A set of common functions used by entries that can have multiple values.

    Usage instructions:
      - Inherit from this class in the desired object.
      - Set the properties list to contain the property the entry is bound to.
      - Connect the on_changed signal to your entry's change.
    """
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
        _multiple_values = _('(multiple values)')

        property = (is_double and self.properties[1]) or self.properties[0]
        if has_multiple_files and self._multiple_values_check(file, property):
            self.ignore_edit[property] = True
            entry.set_text('')
            self.ignore_edit[property] = False
            entry.set_placeholder_text(_multiple_values)
        else:
            self.ignore_edit[property] = True
            value = file.get_property(property)
            if isinstance(value, int) and value is not None:
                entry.set_text(str(value)) # noqa E501 Ignore this warning, PyGObject won't actually accept a non-string here
            elif isinstance(value, float):
                if str(value).endswith('.0'):
                    entry.set_text(str(value)[:-2])
                else:
                    entry.set_text(str(value))
            elif value:
                entry.set_text(str(value))
            else:
                entry.set_text('')
            self.ignore_edit[property] = False
            entry.set_placeholder_text('')

    def refresh_multiple_values(self, file=None):
        if not file:
            try:
                file = self.files[0]
            except IndexError:
                return False

        self._setup_entry(self.value_entry, file, False)
        if self._is_double:
            self._setup_entry(self.value_entry_double, file, True)

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
                    if property == 'bpm':
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    value = None
            for file in self.files:
                if file.get_property(property) != value:
                    if self._is_numeric and not value:
                        continue
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
        label.set_cursor(Gdk.Cursor.new_from_name('text'))
        self.set_alignment(0.5)

        self.bind_property('placeholder', editable, 'placeholder-text',
            GObject.BindingFlags.SYNC_CREATE)

        self.connect('notify::editing', self.display_placeholder)
        self.connect('notify::text', self.display_placeholder)

        # Setup necessary for EartagMultipleValueEntry
        self.value_entry = self
        self.connect('changed', self.on_changed)
        self._original_placeholder = None

        self.label = label
        self.editable = editable
        self.stack = stack
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
        self.stack.update_property([Gtk.AccessibleProperty.LABEL], [self.label.get_label()])

    @GObject.Property(type=str)
    def placeholder(self):
        """Placeholder to display when the text is empty."""
        return self._placeholder

    @placeholder.setter
    def placeholder(self, value):
        if not self._original_placeholder:
            self._original_placeholder = value
        self._placeholder = value

    # Implemented for EartagMultipleValueEntry
    def set_placeholder_text(self, value):
        if value:
            self.set_property('placeholder', value)
        else:
            self.set_property('placeholder', self._original_placeholder)
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

    def __init__(self):
        super().__init__()
        self.connect('destroy', self.on_destroy)

    def on_destroy(self, *args):
        self.file = None

    def bind_to_file(self, file):
        self.file = file

        if file.supports_album_covers:
            self.on_cover_change()
            self.file.connect('notify::cover-path', self.on_cover_change)
        else:
            self.cover_image.set_from_file(None)
            self.on_cover_change()

    def unbind_from_file(self, file=None):
        if not self.file or (file and file != self.file):
            return False
        if self.image_file_binding:
            self.image_file_binding.unbind()
        self.image_file_binding = None
        self.file = None

    def mark_as_empty(self):
        """In some cases, we need to force the cover to be shown as empty."""
        self.set_visible_child(self.no_cover)

    def mark_as_nonempty(self):
        self.on_cover_change()

    def on_cover_change(self, *args):
        if self.file and self.file.cover_path and os.path.exists(self.file.cover_path):
            self.set_visible_child(self.cover_image)
            if self.cover_image.get_pixel_size() <= 48:
                pixbuf = self.file.cover.cover_small
            else:
                pixbuf = self.file.cover.cover_large

            self.cover_image.set_from_pixbuf(pixbuf)
        else:
            self.set_visible_child(self.no_cover)

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
