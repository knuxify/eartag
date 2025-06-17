# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Adw, GObject, Gtk

from .utils.limiters import EartagEntryLimiters
from .utils.widgets import EartagEditableLabel
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
        self._connections["changed"] = self.connect("changed", self.on_entry_change)
        self._connections["destroy"] = self.connect("destroy", self.destroy_tagentry)

    def destroy_tagentry(self, *args):
        for file in self.files.copy():
            self.unbind_from_file(file)

        self.disconnect(self._connections["changed"])
        del self._connections["changed"]

        self.disconnect(self._connections["destroy"])
        del self._connections["destroy"]

    def bind_to_file(self, file):
        if file in self.files:
            return

        self._connections[file.id] = file.connect("modified", self.on_file_change)
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
                    file.set_property(self.bound_property, 0)
        elif self.bound_property in EartagFile.float_properties:
            for file in self.files:
                try:
                    file.set_property(self.bound_property, float(self.get_text()))
                except ValueError:
                    file.set_property(self.bound_property, 0.0)
        else:
            for file in self.files:
                file.set_property(self.bound_property, self.get_text())

        self.tagentry_placeholder = ""

        self._ignore_text_change = False

    def on_file_change(self, file, changed_property, *args):
        if self._ignore_text_change:
            return

        if changed_property != self.bound_property and changed_property is not None:
            return

        self.refresh_text()

    def refresh_text(self):
        """
        Shows/hides the "multiple values" placeholder based on whether or
        not there are different values present.
        """
        self._ignore_text_change = True
        if self.has_different_values():
            self.props.text = ""
            self.tagentry_placeholder = _("(multiple values)")
        else:
            if self.files:
                value = self.files[0].get_property(self.bound_property)
                if value is not None:
                    self.props.text = str(value)
                else:
                    self.props.text = ""
            else:
                self.props.text = ""
            self.tagentry_placeholder = ""
        self._ignore_text_change = False


class EartagTagEntry(Gtk.Entry, EartagTagEntryBase, EartagEntryLimiters):
    """Simple GtkEntry implementing EartagTagEntryBase."""

    __gtype_name__ = "EartagTagEntry"

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
        if value and self.bound_property in ("tracknumber", "totaltracknumber"):
            self.props.placeholder_text = "..."
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
        return self._is_numeric_prop

    @is_numeric.setter
    def is_numeric(self, value):
        self._is_numeric_prop = value

    @GObject.Property(type=bool, default=False)
    def is_float(self):
        return self._is_float_prop

    @is_float.setter
    def is_float(self, value):
        self._is_float_prop = value

    @GObject.Property(type=bool, default=False)
    def is_date(self):
        return self._is_date_prop

    @is_date.setter
    def is_date(self, value):
        self._is_date_prop = value


class EartagTagEntryRow(Adw.EntryRow, EartagTagEntryBase, EartagEntryLimiters):
    """Simple AdwEntryRow implementing EartagTagEntryBase."""

    __gtype_name__ = "EartagTagEntryRow"

    def __init__(self):
        super().__init__()
        self._placeholder_text = ""
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
            self.set_title(self._title + " " + value)
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
        return self._is_numeric_prop

    @is_numeric.setter
    def is_numeric(self, value):
        self._is_numeric_prop = value

    @GObject.Property(type=bool, default=False)
    def is_float(self):
        return self._is_float_prop

    @is_float.setter
    def is_float(self, value):
        self._is_float_prop = value

    @GObject.Property(type=bool, default=False)
    def is_date(self):
        return self._is_date_prop

    @is_date.setter
    def is_date(self, value):
        self._is_date_prop = value


class EartagTagEditableLabel(EartagEditableLabel, EartagTagEntryBase):
    """Simple EartagEditableLabel implementing EartagTagEntryBase."""

    __gtype_name__ = "EartagTagEditableLabel"

    def __init__(self):
        super().__init__()
        self._tagentry_placeholder = ""
        self.setup_tagentry()

    @GObject.Property(type=str, default=None)
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value
        Gtk.Accessible.update_property(self, (Gtk.AccessibleProperty.LABEL,), (value,))
        Gtk.Accessible.update_property(
            self.entry, (Gtk.AccessibleProperty.LABEL,), (value,)
        )

    # Custom handler to avoid overwriting the original placeholder
    @GObject.Property(type=str, default=None)
    def tagentry_placeholder(self):
        return self._tagentry_placeholder

    @tagentry_placeholder.setter
    def tagentry_placeholder(self, value):
        self._tagentry_placeholder = value
        if value:
            self.placeholder_text = self._title + " " + value
        else:
            self.placeholder_text = self._title

    @GObject.Property(type=str, default=None)
    def bound_property(self):
        return self._property

    @bound_property.setter
    def bound_property(self, value):
        self._property = value
        self.refresh_text()
