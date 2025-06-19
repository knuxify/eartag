# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import GObject, Gtk
import re

from .misc import is_float


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
        self._limiter_connections["destroy"] = self.connect(
            "destroy", self._break_limiter_connections
        )

    def _break_limiter_connections(self, *args):
        for conn_type in ("numeric", "float", "date"):
            if conn_type in self._limiter_connections:
                self.get_delegate().disconnect(self._limiter_connections[conn_type])
        self.disconnect(self._limiter_connections["destroy"])
        self._limiter_connections = {}

    # The following properties should be copied into the subclass
    # (see https://gitlab.gnome.org/GNOME/pygobject/-/issues/577)
    """
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
    """

    #
    # Numeric validator: allows only digits ([0-9]).
    #

    @property
    def _is_numeric_prop(self):
        try:
            return self._is_numeric
        except AttributeError:
            self._is_numeric = False
            return False

    @_is_numeric_prop.setter
    def _is_numeric_prop(self, value):
        try:
            if value == self._is_numeric:
                return
        except AttributeError:
            pass

        self._is_numeric = value
        if value:
            self.set_input_purpose(Gtk.InputPurpose.DIGITS)
            self._limiter_connections["numeric"] = self.get_delegate().connect(
                "insert-text", EartagEntryLimiters.disallow_nonnumeric
            )
        else:
            self.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
            if "numeric" in self._limiter_connections:
                self.get_delegate().disconnect(self._limiter_connections["numeric"])
                del self._limiter_connections["numeric"]

    @staticmethod
    def disallow_nonnumeric(entry, text, length, position, *args):
        if not text:
            return
        if not text.isdigit():
            GObject.signal_stop_emission_by_name(entry, "insert-text")

    #
    # Float validator: allows digits and one dot.
    #

    @property
    def _is_float_prop(self):
        try:
            return self._is_float
        except AttributeError:
            self._is_float = False
            return False

    @_is_float_prop.setter
    def _is_float_prop(self, value):
        try:
            if value == self._is_float:
                return
        except AttributeError:
            pass

        self._is_float = value
        if value:
            self.set_input_purpose(Gtk.InputPurpose.NUMBER)
            self._limiter_connections["float"] = self.get_delegate().connect(
                "insert-text", EartagEntryLimiters.disallow_nonfloat
            )
        else:
            self.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
            if "float" in self._limiter_connections:
                self.get_delegate().disconnect(self._limiter_connections["float"])
                del self._limiter_connections["float"]

    @staticmethod
    def disallow_nonfloat(entry, text, length, position, *args):
        if not text:
            return
        if "." in text and "." in entry.get_text():
            GObject.signal_stop_emission_by_name(entry, "insert-text")
        if text != "." and not is_float(text):
            GObject.signal_stop_emission_by_name(entry, "insert-text")

    #
    # Date validator: allows YYYYYYYYY..., YYYY-MM or YYYY-MM-DD dates.
    #

    @property
    def _is_date_prop(self):
        try:
            return self._is_date
        except AttributeError:
            self._is_date = False
            return False

    @_is_date_prop.setter
    def _is_date_prop(self, value):
        try:
            if value == self._is_date:
                return
        except AttributeError:
            pass

        self._is_date = value
        self.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
        if value:
            self._limiter_connections["date"] = self.get_delegate().connect(
                "insert-text", EartagEntryLimiters.disallow_nondate
            )
        else:
            if "date" in self._limiter_connections:
                self.get_delegate().disconnect(self._limiter_connections["date"])
                del self._limiter_connections["date"]

    @staticmethod
    def disallow_nondate(entry, text, length, position, *args):
        if not text:
            return
        elif not re.match("^[0-9-]*$", text):
            GObject.signal_stop_emission_by_name(entry, "insert-text")
            return

        current_text = entry.get_buffer().get_text()

        current_length = len(current_text)
        if current_length + length > 10:
            GObject.signal_stop_emission_by_name(entry, "insert-text")
            return

        sep_count = (current_text + text).count("-")

        if sep_count > 2:
            GObject.signal_stop_emission_by_name(entry, "insert-text")
            return
