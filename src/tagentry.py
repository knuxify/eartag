# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Adw, GObject, Gtk

from ._async import event_loop
from .utils.limiters import EartagEntryLimiters
from .utils.widgets import EartagEditableLabel
from .utils.misc import all_equal, safe_int, safe_float
from .backends.file import EartagFile

from collections.abc import Iterable


class EartagTagEntryManager(GObject.Object):
    """
    Manager grouping together multiple TagEntry-compatible entries.
    Handles binding to a file and synchronizing the values between
    the entries and the bound files.
    """

    def __init__(self):
        """
        Initialize the necessary internal variables for the manager.

        Should be called in the __init__ function of derived classes.
        """
        super().__init__()

        #: Mapping of property to entry.
        self.entries: dict[str, Gtk.Widget] = {}

        #: List of connections made to the entry.
        self.entry_connections: dict[str, list[int]] = {}

        #: Current inconsistency state for the entry.
        self.entry_inconsistency: dict[str, bool] = {}

        #: Set of files bound to the manager.
        self.files: set = set()

        #: List of connections made to files. The key is the file ID.
        self.file_connections: dict[str, list[int]] = {}

        #: If True, the file tag modification signal is ignored.
        self._ignore_file_change: bool = False

        #: If True, the entry text change signal is ignored.
        self._ignore_entry_change: bool = False

    @property
    def managed_properties(self) -> set:
        """Get the set of properties this manager has entries for."""
        return set(self.entries.keys())

    def destroy(self):
        """
        Remove all entries and unbind from all files.

        Should be called from the destroy signal of the derived class.
        """
        event_loop.create_task(self.unbind_from_files(self.files.copy()))

        for prop in self.managed_properties:
            self.remove_entry(prop)

    # File management

    async def bind_to_files(self, files: Iterable[EartagFile]):
        for file in files:
            # TODO: Is this faster than an "if file in self.files" check?
            n_files = len(self.files)
            self.files.add(file)
            if len(self.files) == n_files:
                return
            n_files += 1

            self.file_connections[file.id] = [file.connect("modified", self.handle_file_modified)]

            # Update the entries' "inconsistent" (multiple values) state
            if n_files > 1:
                for prop in [k for k, v in self.entry_inconsistency.items() if v is False]:
                    if prop not in self.entries:
                        continue
                    entry = self.entries[prop]
                    if prop in file.int_properties:
                        val = safe_int(entry.props.text)
                    elif prop in file.float_properties:
                        val = safe_float(entry.props.text)
                    else:
                        val = entry.props.text

                    self.entry_inconsistency[prop] = val != file.get_property(prop)
            else:
                for prop in self.managed_properties:
                    self.entry_inconsistency[prop] = False

        for prop in self.managed_properties:
            self.refresh_entry_text(prop)

    async def unbind_from_files(self, files: Iterable[EartagFile]):
        """Unbind from the files provided by the iterable."""
        for file in files:
            if file.id not in self.file_connections:
                return
            for conn in self.file_connections[file.id]:
                file.disconnect(conn)
            self.files.remove(file)

        for prop in self.managed_properties:
            self.recalculate_inconsistent_state(prop)
            self.refresh_entry_text(prop)

    @GObject.Property(type=bool, default=False)
    def is_busy(self):
        """Whether the manager is currently binding/unbinding files or not."""
        return self.bind_task.is_running or self.unbind_task.is_running

    def handle_file_modified(self, file: EartagFile, tag: str):
        """Handle a file's value being modified."""
        if self._ignore_file_change:
            return

        if tag in self.managed_properties:
            self.refresh_entry_text(tag)

    def recalculate_inconsistent_state(self, prop: str):
        """
        Recalculate the entry inconsistency state for the entry with
        the given property.
        """
        self.entry_inconsistency[prop] = not all_equal(
            file.get_property(prop) for file in self.files
        )

    # Entry management

    def add_entry(self, prop: str, entry: Gtk.Widget):
        """Add an entry for the given property."""
        if prop in self.entries:
            return

        if entry.bound_property != prop:
            entry.bound_property = prop

        self.entries[prop] = entry

        self.entry_connections[prop] = [
            entry.connect("notify::bound-property", self.handle_entry_prop_changed, prop),
            entry.connect("changed", self.handle_entry_changed, prop),
        ]
        self.entry_inconsistency[prop] = False

        self.refresh_entry_text(prop)

    def remove_entry(self, prop: str):
        """Remove the entry for the given property."""
        if prop not in self.entries:
            return

        for conn in self.entry_connections[prop]:
            self.entries[prop].disconnect(conn)
        del self.entry_connections[prop]

        del self.entry_inconsistency[prop]
        del self.entries[prop]

    def get_entry_by_property(self, prop: str) -> Gtk.Widget | None:
        """Return the entry for this property."""
        return self.entries.get(prop, None)

    def has_entry_for_property(self, prop: str) -> bool:
        """Check whether an entry for the given property is present."""
        return prop in self.entries

    def handle_entry_prop_changed(self, entry: Gtk.Widget, old_prop: str):
        """Handle the bound_property value of an entry being changed."""
        new_prop = entry.bound_property

        self.remove_entry(old_prop)
        self.add_entry(entry, new_prop)

    def handle_entry_changed(self, entry: Gtk.Widget, prop: str):
        """Handle the entry contents being changed."""
        if self._ignore_entry_change:
            return

        self._ignore_file_change = True

        entry.tagentry_placeholder = ""

        if prop in EartagFile.int_values:
            value = safe_int(entry.props.text)
        elif prop in EartagFile.float_values:
            value = safe_float(entry.props.text)
        else:
            value = entry.props.text

        for file in self.files:
            file.set_property(prop, value)

        self.entry_inconsistency[prop] = False

        self._ignore_file_change = False

    def refresh_entry_text(self, prop: str):
        """Refresh the data for the entry with the given property."""
        self._ignore_entry_change = True

        entry = self.entries[prop]
        if self.entry_inconsistency[prop]:
            entry.props.text = ""
            entry.tagentry_placeholder = _("(multiple values)")
        else:
            try:
                entry.props.text = str(next(iter(self.files)).get_property(prop) or "")
                entry.tagentry_placeholder = ""
            except StopIteration:
                entry.props.text = ""
                entry.tagentry_placeholder = ""

        self._ignore_entry_change = False


class EartagTagEntryBase(GObject.Object):
    """
    Base class for tag entries: entries which are bound to files and carry
    the value for a specific tag.

    Entries are expected to have the following:
     - "text" property
     - "changed" signal
     - "tagentry-placeholder" property
    The first two are implemented by GtkEditable; the last one has to be
    implemented in the entry class manually.
    """

    # The following line needs to be copied manually to the derived class
    # (until https://gitlab.gnome.org/GNOME/pygobject/-/issues/577 is done)
    # bound_property = GObject.Property(type=str, default=None)


class EartagTagEntry(Gtk.Entry, EartagTagEntryBase, EartagEntryLimiters):
    """Simple GtkEntry implementing EartagTagEntryBase."""

    __gtype_name__ = "EartagTagEntry"

    def __init__(self):
        super().__init__()
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
    bound_property = GObject.Property(type=str, default=None)

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
    bound_property = GObject.Property(type=str, default=None)

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

    @GObject.Property(type=str, default=None)
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value
        Gtk.Accessible.update_property(self, (Gtk.AccessibleProperty.LABEL,), (value,))
        Gtk.Accessible.update_property(self.entry, (Gtk.AccessibleProperty.LABEL,), (value,))

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

    bound_property = GObject.Property(type=str, default=None)
