# tagentry.py
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

from gi.repository import Adw, GObject, Gtk

from .common import EartagEditableLabel, EartagEntryLimiters
from .backends.file import EartagFile

class EartagTagEntryBase(GObject.Object):
    """
    Base class for tag entries: entries which are bound to files and carry
    the value for a specific tag.

    Tag entries have the following variables:
     - self.bound_property - contains the name of the file's property to bind to.
                       Default value: None
     - self.files    - contains a list of files that this tag entry is bound to.
                       Default value: []
    These are set up automatically when calling entry_setup, which should be
    called in the init function of the entry subclass.

    Entries are expected to have the following:
     - "text" property
     - "changed" signal
     - "tagentry-placeholder" property
    The first two are implemented by GtkEditable; the last one has to be
    implemented in the entry class manually.

    The files property is managed by this class; the preferred way for users
    to bind files is to use bind_to_file and unbind_from_file methods.
    """

    """
    @GObject.Property(type=str, default=None)
    def bound_property(self):
        return self._property

    @bound_property.setter
    def bound_property(self, value):
        self._property = value
        self.refresh_text()
    """

    def setup_tagentry(self, property=None):
        self._ignore_text_change = False
        self._property = property
        self.files = []
        self._connections = {}
        self.connect('changed', self.on_entry_change)

    def bind_to_file(self, file):
        if file in self.files:
            return

        self._connections[file.id] = \
            file.connect('modified', self.on_file_change)
        self.files.append(file)

        self.refresh_text()

    def unbind_from_file(self, file):
        if file not in self.files:
            return

        file.disconnect(self._connections[file.id])
        self.files.remove(file)

        self.refresh_text()

    def has_different_values(self):
        """
        Checks whether or not all files have the same values. Returns True
        if there are multiple different values, False otherwise.
        """
        if not self.files:
            return False

        ref = self.files[0].get_property(self.bound_property)
        for file in self.files:
            if file.get_property(self.bound_property) != ref:
                return True
        return False

    def on_entry_change(self, *args):
        if self._ignore_text_change:
            return

        self._ignore_text_change = True

        if self.bound_property in EartagFile.int_properties:
            for file in self.files:
                try:
                    file.set_property(self.bound_property, int(self.get_text()))
                except ValueError:
                    file.set_property(self.bound_property, None)
        elif self.bound_property in EartagFile.float_properties:
            for file in self.files:
                try:
                    file.set_property(self.bound_property, float(self.get_text()))
                except ValueError:
                    file.set_property(self.bound_property, None)
        else:
            for file in self.files:
                file.set_property(self.bound_property, self.get_text())

        self.tagentry_placeholder = ''

        self._ignore_text_change = False

    def on_file_change(self, file, changed_property, *args):
        if self._ignore_text_change:
            return

        if changed_property != self.bound_property:
            return

        self.refresh_text()

    def refresh_text(self):
        """
        Shows/hides the "multiple values" placeholder based on whether or
        not there are different values present.
        """
        self._ignore_text_change = True
        if self.has_different_values():
            self.props.text = ''
            self.tagentry_placeholder = _('(multiple values)')
        else:
            if self.files:
                value = self.files[0].get_property(self.bound_property)
                if value is not None:
                    self.props.text = str(value)
                else:
                    self.props.text = ''
            else:
                self.props.text = ''
            self.tagentry_placeholder = ''
        self._ignore_text_change = False

class EartagTagEntry(Gtk.Entry, EartagTagEntryBase, EartagEntryLimiters):
    """Simple GtkEntry implementing EartagTagEntryBase."""
    __gtype_name__ = 'EartagTagEntry'

    def __init__(self):
        super().__init__()
        self.setup_tagentry()
        self.setup_limiters()

    @GObject.Property(type=str)
    def tagentry_placeholder(self):
        return self.props.placeholder_text

    @tagentry_placeholder.setter
    def tagentry_placeholder(self, value):
        # Bit of a hack, but: override the placeholder value for track
        # number and total track number entries to prevent them from
        # expanding the app window when set
        if value and self.bound_property in ('tracknumber', 'totaltracknumber'):
            self.props.placeholder_text = '...'
        else:
            self.props.placeholder_text = value

    # https://gitlab.gnome.org/GNOME/pygobject/-/issues/577
    # (I wish Python had macros...)
    @GObject.Property(type=str, default=None)
    def bound_property(self):
        return self._property

    @bound_property.setter
    def bound_property(self, value):
        self._property = value
        self.refresh_text()

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

class EartagTagEntryRow(Adw.EntryRow, EartagTagEntryBase, EartagEntryLimiters):
    """Simple AdwEntryRow implementing EartagTagEntryBase."""
    __gtype_name__ = 'EartagTagEntryRow'

    def __init__(self):
        super().__init__()
        self._placeholder_text = ''
        self._title = self.props.title
        self.setup_tagentry()
        self.setup_limiters()

    # AdwEntryRows do not have placeholder text; the entry's title doubles
    # as the placeholder. So, to simulate a placeholder without ruining
    # the entry title, we append the placeholder text to the title.
    @GObject.Property(type=str)
    def tagentry_placeholder(self):
        return self._placeholder_text

    @tagentry_placeholder.setter
    def tagentry_placeholder(self, value):
        if not self._title and self.props.title:
            self._title = self.props.title
        self._placeholder_text = value
        if value:
            self.set_title(self._title + ' ' + value)
        else:
            self.set_title(self._title)

    # https://gitlab.gnome.org/GNOME/pygobject/-/issues/577
    @GObject.Property(type=str, default=None)
    def bound_property(self):
        return self._property

    @bound_property.setter
    def bound_property(self, value):
        self._property = value
        self.refresh_text()

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

class EartagTagEditableLabel(EartagEditableLabel, EartagTagEntryBase):
    """Simple EartagEditableLabel implementing EartagTagEntryBase."""

    __gtype_name__ = 'EartagTagEditableLabel'

    def __init__(self):
        super().__init__()
        self._tagentry_placeholder = ''
        self.setup_tagentry()

    @GObject.Property(type=str, default=None)
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value

    # Custom handler to avoid overwriting the original placeholder
    @GObject.Property(type=str, default=None)
    def tagentry_placeholder(self):
        return self._tagentry_placeholder

    @tagentry_placeholder.setter
    def tagentry_placeholder(self, value):
        self._tagentry_placeholder = value
        if value:
            self.placeholder_text = self._title + ' ' + value
        else:
            self.placeholder_text = self._title

    @GObject.Property(type=str, default=None)
    def bound_property(self):
        return self._property

    @bound_property.setter
    def bound_property(self, value):
        self._property = value
        self.refresh_text()
