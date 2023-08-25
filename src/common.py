# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

# This file contains various functions/classes used in multiple places that
# were generic enough to be split into a single file.

from gi.repository import Gdk, GLib, Gtk, GObject, Pango
import os.path
import magic
import mimetypes
import threading
import time
import re
from itertools import groupby

from .backends.file import CoverType

def all_equal(iterable):
    """
    Check if all elements in a list are equal. Source:
    https://stackoverflow.com/questions/3844801/check-if-all-elements-in-a-list-are-identical
    """
    g = groupby(iterable)
    return next(g, True) and not next(g, False)

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

def find_in_model(model, item):
    """
    Gets the position of an item in the model, or None if not found.
    Replacement for .find function in models that don't have it.
    """
    i = 0
    while True:
        found = model.get_item(i)
        if not found:
            break
        if found == item:
            return i
        i += 1
    return None

def inspect_prettyprint(stack):
    """
    Convenience function that pretty-prints the results of inspect.stack().

    This is not used anywhere in the program; it's only here for debugging
    purposes, since inspect is a pretty useful tool for finding optimization
    issues, and ends up being used quite frequently.
    """
    print("--- Inspect trace: ---")

    for frame in stack:
        print(f'\033[1m{frame.filename}:{frame.lineno}\033[0m')
        print(''.join(frame.code_context)) # already includes newlines

    print("--- End trace ---")

class EartagPopoverButton(Gtk.Box):
    """
    Re-implementation of GtkMenuButton that doesn't have the same issues as
    it does. Notably:

    - doesn't prevent arrow navigation from working correctly
    - doesn't suffer from https://gitlab.gnome.org/GNOME/gtk/-/issues/5568
      (though that one is actually worked around in the AlbumCoverButton)
    """
    __gtype_name__ = 'EartagPopoverButton'

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
        self.toggle_button.bind_property('active', self.popover, 'visible', GObject.BindingFlags.BIDIRECTIONAL)
        self.append(self._popover)

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

    @GObject.Property(type=bool, default=False)
    def is_running(self):
        if not self.thread:
            return False
        return self.thread.is_alive()

    def reset_progress(self):
        self.props.progress = 0

    def set_progress_threadsafe(self, value):
        """
        Wrapper around self.props.progress that updates the progress, wrapped
        around GLib.idle_add. This is the preferred way for users to set the
        progress variable.
        """
        GLib.idle_add(self.set_property, 'progress', value)

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
        GLib.idle_add(self.emit, 'task-done')

def isfloat(value):
    """Checks if the given value is a valid float."""
    try:
        float(value)
    except ValueError:
        return False
    return True

class EartagEntryLimiters(GObject.Object):
    """
    Common input validators for entries. Assumes inheriting object is a
    descendant of GtkEditable (and thus has a get_delegate method and
    insert-text signal).

    Adds properties that can be quickly set/unset to connect/disconnect
    an entry.

    You might be able to use multiple limiters at once, but this is
    completely untested, and you will have to re-set the input purpose
    manually since every property setter overrides it.
    """

    def setup_limiters(self):
        """
        Call this **AFTER** the super().__init__() call in the inheritant.
        """
        self._limiter_connections = {}
        self._limiter_connections['destroy'] = \
            self.connect('destroy', self._break_limiter_connections)

    def _break_limiter_connections(self, *args):
        for conn_type in ('numeric', 'float', 'date'):
            if conn_type in self._limiter_connections:
                self.disconnect(self._limiter_connections[conn_type])
        self.disconnect(self._limiter_connections['destroy'])
        self._limiter_connections = {}

    #
    # Numeric validator: allows only digits ([0-9]).
    #

    # https://gitlab.gnome.org/GNOME/pygobject/-/issues/577
    """
    @GObject.Property(type=bool, default=False)
    def is_numeric(self):
        try:
            return self._is_numeric
        except AttributeError:
            self._is_numeric = False
            return False

    @is_numeric.setter
    def is_numeric(self, value):
        try:
            if value == self._is_numeric:
                return
        except AttributeError:
            pass

        self._is_numeric = value
        if value:
            self.set_input_purpose(Gtk.InputPurpose.DIGITS)
            self._limiter_connections['numeric'] = \
                self.get_delegate().connect('insert-text', self.disallow_nonnumeric)
        else:
            self.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
            if 'numeric' in self._limiter_connections:
                self.disconnect(self._limiter_connections['numeric'])
                del self._limiter_connections['numeric']
    """

    def disallow_nonnumeric(self, entry, text, length, position, *args):
        if not text:
            return
        if not text.isdigit():
            GObject.signal_stop_emission_by_name(entry, 'insert-text')

    #
    # Float validator: allows digits and one dot.
    #

    # https://gitlab.gnome.org/GNOME/pygobject/-/issues/577
    """
    @GObject.Property(type=bool, default=False)
    def is_float(self):
        try:
            return self._is_float
        except AttributeError:
            self._is_float = False
            return False

    @is_float.setter
    def is_float(self, value):
        try:
            if value == self._is_float:
                return
        except AttributeError:
            pass

        self._is_float = value
        if value:
            self.set_input_purpose(Gtk.InputPurpose.NUMBER)
            self._limiter_connections['float'] = \
                self.get_delegate().connect('insert-text', self.disallow_nonfloat)
        else:
            self.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
            if 'float' in self._limiter_connections:
                self.disconnect(self._limiter_connections['float'])
                del self._limiter_connections['float']
    """

    def disallow_nonfloat(self, entry, text, length, position, *args):
        if not text:
            return
        if '.' in text and '.' in entry.get_text():
            GObject.signal_stop_emission_by_name(entry, 'insert-text')
        if text != '.' and not isfloat(text):
            GObject.signal_stop_emission_by_name(entry, 'insert-text')

    #
    # Date validator: allows YYYYYYYYY..., YYYY-MM or YYYY-MM-DD dates.
    #

    # https://gitlab.gnome.org/GNOME/pygobject/-/issues/577
    """
    @GObject.Property(type=bool, default=False)
    def is_date(self):
        try:
            return self._is_date
        except AttributeError:
            self._is_date = False
            return False

    @is_date.setter
    def is_date(self, value):
        try:
            if value == self._is_date:
                return
        except AttributeError:
            pass

        self._is_date = value
        self.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
        if value:
            self._limiter_connections['date'] = \
                self.get_delegate().connect('insert-text', self.disallow_nondate)
        else:
            if 'date' in self._limiter_connections:
                self.disconnect(self._limiter_connections['date'])
                del self._limiter_connections['date']
    """

    def disallow_nondate(self, entry, text, length, position, *args):
        if not text:
            return
        elif not re.match("^[0-9-]*$", text):
            GObject.signal_stop_emission_by_name(entry, 'insert-text')
            return

        current_text = entry.get_buffer().get_text()

        current_length = len(current_text)
        if current_length + length > 10:
            GObject.signal_stop_emission_by_name(entry, 'insert-text')
            return

        sep_count = (current_text + text).count('-')

        if sep_count > 2:
            GObject.signal_stop_emission_by_name(entry, 'insert-text')
            return

class EartagEditableLabel(Gtk.EditableLabel):
    """
    Editable labels are missing a few nice features that we need
    (namely proper centering and word wrapping), but since they're
    just GtkStacks with a regular GtkLabel inside, we can modify
    them to suit our needs. This class automates the process.
    """
    __gtype_name__ = 'EartagEditableLabel'

    def __init__(self):
        super().__init__()
        self._placeholder = ''
        self._original_placeholder = ''

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

        self.bind_property('placeholder-text', editable, 'placeholder-text',
            GObject.BindingFlags.SYNC_CREATE)

        self.connect('notify::editing', self.display_placeholder)
        self.connect('notify::text', self.display_placeholder)

        self.label = label
        self.editable = editable
        self.stack = stack
        self.display_placeholder()

    def display_placeholder(self, *args):
        """Displays/hides placeholder in non-editing mode as needed."""
        if not self.get_text():
            self.label.set_label(self.placeholder_text)
            self.label.add_css_class('dim-label')
        else:
            self.label.remove_css_class('dim-label')
        self.stack.update_property([Gtk.AccessibleProperty.LABEL], [self.label.get_label()])

    @GObject.Property(type=str)
    def placeholder_text(self):
        """Placeholder to display when the text is empty."""
        return self._placeholder

    @placeholder_text.setter
    def placeholder_text(self, value):
        self._placeholder = value
        self.display_placeholder()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/albumcoverimage.ui')
class EartagAlbumCoverImage(Gtk.Stack):
    __gtype_name__ = 'EartagAlbumCoverImage'

    no_cover = Gtk.Template.Child()
    cover_image = Gtk.Template.Child()

    file = None

    def __init__(self):
        super().__init__()
        self._cover_type = CoverType.FRONT
        self.connect('destroy', self.on_destroy)

    def on_destroy(self, *args):
        self.file = None

    def bind_to_file(self, file):
        self.file = file

        if file.supports_album_covers:
            self.on_cover_change()
            self.file.connect('notify::front-cover-path', self.on_cover_change)
            self.file.connect('notify::back-cover-path', self.on_cover_change)
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
        if not self.file:
            self.set_visible_child(self.no_cover)
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
            self.set_visible_child(self.cover_image)
            if self.cover_image.get_pixel_size() <= 48:
                pixbuf = cover.cover_small
            else:
                pixbuf = cover.cover_large

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

    @GObject.Property(type=int)
    def cover_type(self):
        """Whether to display the front or back cover."""
        return self._cover_type

    @cover_type.setter
    def cover_type(self, value):
        self._cover_type = value
        self.on_cover_change()
