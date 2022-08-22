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
from .common import EartagEditableLabel, is_valid_image_file, EartagAlbumCoverImage

from gi.repository import Adw, Gtk, Gdk, Gio, GObject
import os.path
import traceback
import magic
import mimetypes

import gettext

@Gtk.Template(resource_path='/app/drey/EarTag/ui/albumcoverbutton.ui')
class EartagAlbumCoverButton(Adw.Bin):
    __gtype_name__ = 'EartagAlbumCoverButton'

    cover_image = Gtk.Template.Child()

    highlight_revealer = Gtk.Template.Child()
    highlight_stack = Gtk.Template.Child()
    drop_highlight = Gtk.Template.Child()
    hover_highlight = Gtk.Template.Child()

    handling_drag = False
    handling_undefined_drag = False
    image_file_filter = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.connect('destroy', self.on_destroy)
        self.drop_target = Gtk.DropTarget(
            actions=Gdk.DragAction.COPY,
            formats=Gdk.ContentFormats.new_for_gtype(Gio.File)
            )

        self.drop_target.connect('accept', self.on_drag_accept)
        self.drop_target.connect('enter', self.on_drag_hover)
        self.drop_target.connect('leave', self.on_drag_unhover)
        self.drop_target.connect('drop', self.on_drag_drop)
        self.add_controller(self.drop_target)

        self.hover_controller = Gtk.EventControllerMotion.new()
        self.hover_controller.connect('enter', self.on_hover)
        self.hover_controller.connect('leave', self.on_unhover)
        self.add_controller(self.hover_controller)

    def bind_to_file(self, file):
        self.file = file
        self.cover_image.bind_to_file(file)

        if file.supports_album_covers:
            self.set_visible(True)
        else:
            self.set_visible(False)

    def on_destroy(self, *args):
        self.file = None

    @Gtk.Template.Callback()
    def show_cover_file_chooser(self, *args):
        """Shows the file chooser."""
        self.file_chooser = Gtk.FileChooserNative(
                                title=_("Select Album Cover Image"),
                                transient_for=self.get_native(),
                                action=Gtk.FileChooserAction.OPEN,
                                filter=self.image_file_filter
                                )

        self.file_chooser.connect('response', self.open_cover_file_from_dialog)
        self.file_chooser.show()

    def open_cover_file_from_dialog(self, dialog, response):
        """
        Callback for a FileChooser that takes the response and opens the file
        selected in the dialog.
        """
        if response == Gtk.ResponseType.ACCEPT:
            self.file.cover_path = dialog.get_file().get_path()
            self.file.notify('cover-path')
            self.cover_image.on_cover_change()
        self.file_chooser.destroy()

    # Drag-and-drop

    def on_drag_accept(self, target, drop, *args):
        drop.read_value_async(Gio.File, 0, None, self.verify_file_valid)
        return True

    def verify_file_valid(self, drop, task, *args):
        file = drop.read_value_finish(task)
        path = file.get_path()
        if not is_valid_image_file(path):
            self.handling_undefined_drag = True
            self.drop_target.reject()
            self.on_drag_unhover()
        else:
            self.handling_undefined_drag = False

    def on_drag_hover(self, *args):
        self.handling_drag = True
        self.highlight_stack.set_visible_child(self.drop_highlight)
        self.highlight_revealer.set_reveal_child(True)
        return Gdk.DragAction.COPY

    def on_drag_unhover(self, *args):
        self.highlight_revealer.set_reveal_child(False)
        self.handling_drag = False

    def on_drag_drop(self, drop_target, value, *args):
        path = value.get_path()
        self.file.cover_path = path
        self.file.notify('cover-path')
        self.cover_image.on_cover_change()
        self.on_drag_unhover()

    # Hover
    def on_hover(self, *args):
        if not self.handling_drag and not self.handling_undefined_drag:
            self.highlight_stack.set_visible_child(self.hover_highlight)
            self.highlight_revealer.set_reveal_child(True)

    def on_unhover(self, *args):
        self.highlight_revealer.set_reveal_child(False)

class EartagTagListItem(Adw.ActionRow):
    __gtype_name__ = 'EartagTagListItem'

    _is_double = False
    _is_numeric = False
    _max_width_chars = -1
    bindings = []

    value_entry_double = None

    def __init__(self):
        super().__init__(can_target=False, focusable=False, focus_on_click=False)
        self.suffixes = Gtk.Box(valign=Gtk.Align.CENTER, halign=Gtk.Align.END, spacing=6)
        self.add_suffix(self.suffixes)

        self.value_entry = Gtk.Entry(valign=Gtk.Align.CENTER)
        self.suffixes.append(self.value_entry)

        self.double_separator_label = Gtk.Label(valign=Gtk.Align.CENTER, visible=False)
        self.suffixes.append(self.double_separator_label)

        self.value_entry_double = Gtk.Entry(valign=Gtk.Align.CENTER, visible=False)
        self.suffixes.append(self.value_entry_double)

        self.set_activatable_widget(self.value_entry)
        self.connect('destroy', self.on_destroy)

    def on_destroy(self, *args):
        if self.bindings:
            for binding in self.bindings:
                binding.unbind()
        self.bindings = []

    def disallow_nonnumeric(self, entry, text, length, position, *args):
        if text and not text.isdigit():
            GObject.signal_stop_emission_by_name(entry, 'insert-text')

    def bind_to_property(self, file, property):
        if type(property) == list and self._is_double:
            self.bindings.append(
                file.bind_property(property[0], self.value_entry, 'text',
                    GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
            )

            self.bindings.append(
                file.bind_property(property[1], self.value_entry_double, 'text',
                    GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
            )
        else:
            self.bindings.append(
                file.bind_property(property, self.value_entry, 'text',
                    GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
            )

    @GObject.Property(type=int, default=-1)
    def max_width_chars(self):
        return self._max_width_chars

    @max_width_chars.setter
    def set_max_width_chars(self, value):
        self._max_width_chars = value
        self.value_entry.set_max_width_chars(value)
        if self._is_double:
            self.value_entry_double.set_max_width_chars(value)

    @GObject.Property(type=bool, default=False)
    def is_numeric(self):
        return self._is_numeric

    @is_numeric.setter
    def set_is_numeric(self, value):
        self._is_numeric = value
        if value == True:
            self.value_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
            self.value_entry.get_delegate().connect('insert-text', self.disallow_nonnumeric)
            if self._is_double:
                self.value_entry_double.set_input_purpose(Gtk.InputPurpose.DIGITS)
                self.value_entry_double.get_delegate().connect('insert-text', self.disallow_nonnumeric)

    @GObject.Property(type=str, default='')
    def double_separator(self):
        return self._double_separator

    @double_separator.setter
    def set_double_separator(self, value):
        self._double_separator = value
        if value:
            self.double_separator_label.set_label(value)
            self.double_separator_label.set_visible(True)
        else:
            self.double_separator_label.set_visible(False)

    @GObject.Property(type=bool, default=False)
    def is_double(self):
        return self._is_double

    @is_double.setter
    def set_is_double(self, value):
        self._is_double = value
        if value:
            self.value_entry_double.set_visible(True)
            # Update other properties to ensure the input purpose is set
            self.set_property('is-numeric', self.get_property('is-numeric'))
            self.set_property('max-width-chars', self.get_property('max-width-chars'))
        else:
            self.value_entry_double.set_visible(False)

@Gtk.Template(resource_path='/app/drey/EarTag/ui/fileview.ui')
class EartagFileView(Gtk.Stack):
    __gtype_name__ = 'EartagFileView'

    content_scroll = Gtk.Template.Child()
    select_file = Gtk.Template.Child()

    album_cover = Gtk.Template.Child()
    title_entry = Gtk.Template.Child()
    artist_entry = Gtk.Template.Child()
    file_info = Gtk.Template.Child()
    tracknumber_entry = Gtk.Template.Child()
    album_entry = Gtk.Template.Child()
    albumartist_entry = Gtk.Template.Child()
    genre_entry = Gtk.Template.Child()
    releaseyear_entry = Gtk.Template.Child()
    comment_entry = Gtk.Template.Child()

    writable = False
    bindings = []

    def __init__(self):
        """Initializes the EartagFileView."""
        super().__init__()

    def set_file_manager(self, file_manager):
        self.file_manager = file_manager
        self.file_manager.connect('files_loaded', self.bind_to_file)
        self.file_manager.connect('selection_changed', self.bind_to_file)

    def bind_to_file(self, *args):
        """
        Reads the file data from the file manager and applies it
        to the file view.
        """
        window = self.get_native()

        if self.bindings:
            for binding in self.bindings:
                binding.unbind()
            self.bindings = []

        selected_files_count = len(self.file_manager.selected_files)
        if selected_files_count <= 0:
            window.set_title('Ear Tag')
            window.window_title.set_subtitle('')
            if self.file_manager.files:
                self.set_visible_child(self.select_file)
            return False
        elif selected_files_count == 1:
            file = self.file_manager.selected_files[0]
        else:
            raise NotImplementedError

        self.set_visible_child(self.content_scroll)

        file_basename = os.path.basename(file.path)

        window.save_button.set_visible(True)
        window.set_title('{f} — Ear Tag'.format(f=file_basename))
        window.window_title.set_subtitle(file_basename)

        if not file.is_writable:
            # TRANSLATORS: Tooltip text for save button when saving is disabled
            window.save_button.set_tooltip_text(_('File is read-only, saving is disabled'))
            window.save_button.set_sensitive(False)
            self.get_native().toast_overlay.add_toast(
                Adw.Toast.new(_("Opened file is read-only; changes cannot be saved."))
            )
        else:
            window.save_button.set_tooltip_text('')
        self.set_sensitive(file.is_writable)

        self.album_cover.bind_to_file(file)

        self.setup_entry(file, self.title_entry, 'title')
        self.setup_entry(file, self.artist_entry, 'artist')
        self.setup_entry(file, self.tracknumber_entry, ['tracknumber', 'totaltracknumber'])
        self.setup_entry(file, self.album_entry, 'album')
        self.setup_entry(file, self.albumartist_entry, 'albumartist')
        self.setup_entry(file, self.genre_entry, 'genre')
        self.setup_entry(file, self.releaseyear_entry, 'releaseyear')
        self.setup_entry(file, self.comment_entry, 'comment')

        # Get human-readable version of length
        length_min, length_sec = divmod(int(file.length), 60)
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

        # Get human-readable version of channel count
        channels = file.channels
        if channels == 1:
            channels_readable = 'Mono'
        elif channels == 2:
            channels_readable = 'Stereo'
        else:
            channels_readable = gettext.ngettext("{n} channel", "{n} channels", channels).format(n=channels)

        self.file_info.set_label('{length} • {bitrate} kbps • {channels} • {filetype}'.format(
            filetype=file.filetype,
            length=length_readable,
            bitrate=file.bitrate,
            channels=channels_readable
        ))

    def setup_entry(self, file, entry, property):
        if type(entry) == EartagTagListItem:
            entry.bind_to_property(file, property)
            self.bindings = self.bindings + entry.bindings
        elif type(entry) == EartagEditableLabel:
            self.bindings.append(
                file.bind_property(property, entry.editable, 'text',
                    GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
            )
            entry.notify('text')

    def save(self):
        """Saves changes to the file."""
        self.file_manager.save()
