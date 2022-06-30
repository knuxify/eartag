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
from .common import EartagEditableLabel

from gi.repository import Adw, Gtk, Gdk, Gio, GObject
import os.path
import traceback
import magic
import mimetypes

@Gtk.Template(resource_path='/org/dithernet/Eartag/ui/albumcover.ui')
class EartagAlbumCover(Adw.Bin):
    __gtype_name__ = 'EartagAlbumCover'

    preview_stack = Gtk.Template.Child()
    no_cover = Gtk.Template.Child()
    cover_image = Gtk.Template.Child()

    file = None
    image_file_filter = Gtk.Template.Child()
    image_file_binding = None

    drop_highlight_revealer = Gtk.Template.Child()

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

    def bind_to_file(self, file):
        if self.image_file_binding:
            self.image_file_binding.unbind()
        self.image_file_binding = None

        self.file = file

        if file.supports_album_covers:
            self.set_sensitive(True)
        else:
            self.set_sensitive(False)
            self.cover_image.set_from_file(None)
            self.on_cover_change()
            return

        self.image_file_binding = self.file.bind_property(
                'cover_path', self.cover_image, 'file',
                GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.on_cover_change()
        self.file.connect('notify::cover_path', self.on_cover_change)

    def on_cover_change(self, *args):
        if self.file.cover_path and os.path.exists(self.file.cover_path):
            self.preview_stack.set_visible_child(self.cover_image)
        else:
            self.preview_stack.set_visible_child(self.no_cover)

    def on_destroy(self, *args):
        if self.image_file_binding:
            self.image_file_binding.unbind()
        self.file = None

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
            self.file.notify('cover-path')
            self.on_cover_change()
        self.file_chooser.destroy()

    # Drag-and-drop

    def on_drag_accept(self, target, drop, *args):
        drop.read_value_async(Gio.File, 0, None, self.verify_file_valid)
        return True

    def verify_file_valid(self, drop, task, *args):
        file = drop.read_value_finish(task)
        path = file.get_path()
        if not mimetypes.guess_type(path)[0].startswith('image/') and \
            not magic.Magic(mime=True).from_file(path).startswith('image/'):
                self.drop_target.reject()
                self.on_drag_unhover()

    def on_drag_hover(self, *args):
        self.drop_highlight_revealer.set_reveal_child(True)
        return Gdk.DragAction.COPY

    def on_drag_unhover(self, *args):
        self.drop_highlight_revealer.set_reveal_child(False)

    def on_drag_drop(self, drop_target, value, *args):
        path = value.get_path()
        self.file.cover_path = path
        self.file.notify('cover-path')
        self.on_cover_change()
        self.on_drag_unhover()

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

@Gtk.Template(resource_path='/org/dithernet/Eartag/ui/fileview.ui')
class EartagFileView(Adw.Bin):
    __gtype_name__ = 'EartagFileView'

    album_cover = Gtk.Template.Child()
    title_entry = Gtk.Template.Child()
    artist_entry = Gtk.Template.Child()
    tracknumber_entry = Gtk.Template.Child()
    album_entry = Gtk.Template.Child()
    albumartist_entry = Gtk.Template.Child()
    genre_entry = Gtk.Template.Child()
    releaseyear_entry = Gtk.Template.Child()
    comment_entry = Gtk.Template.Child()

    file = None
    writable = False
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
        file_basename = os.path.basename(self.file_path)

        try:
            self.file = eartagfile_from_path(self.file_path)
        except:
            traceback.print_exc()
            self.error_dialog = Gtk.MessageDialog(
                                    transient_for=self.get_native(),
                                    buttons=Gtk.ButtonsType.OK,
                                    message_type=Gtk.MessageType.ERROR,
                                    text=_("Failed to load file"),
                                    secondary_text=_("Could not load file {f}. Check the logs for more information.").format(f=file_basename)
            )
            self.error_dialog.connect('response', self.close_dialog)
            self.error_dialog.show()
            return False

        window = self.get_native()
        window.save_button.set_visible(True)
        window.set_title('{f} — Eartag'.format(f=file_basename))
        window.window_title.set_subtitle(file_basename)
        window.content_stack.set_visible_child(self)

        try:
            writable_check = open(self.file_path, 'a')
            writable_check.close()
        except OSError:
            self.writable = False
            # TRANSLATORS: Tooltip text for save button when saving is disabled
            window.save_button.set_tooltip_text(_('File is read-only, saving is disabled'))
            window.save_button.set_sensitive(False)
            self.get_native().toast_overlay.add_toast(
                Adw.Toast.new(_("Opened file is read-only; changes cannot be saved."))
            )
        else:
            self.writable = True
            window.save_button.set_tooltip_text('')
            self.bindings.append(
                self.file.bind_property('is_modified', window.save_button, 'sensitive',
                    GObject.BindingFlags.SYNC_CREATE)
            )

        self.album_cover.bind_to_file(self.file)

        self.setup_entry(self.title_entry, 'title')
        self.setup_entry(self.artist_entry, 'artist')
        self.setup_entry(self.tracknumber_entry, ['tracknumber', 'totaltracknumber'])
        self.setup_entry(self.album_entry, 'album')
        self.setup_entry(self.albumartist_entry, 'albumartist')
        self.setup_entry(self.genre_entry, 'genre')
        self.setup_entry(self.releaseyear_entry, 'releaseyear')
        self.setup_entry(self.comment_entry, 'comment')

    def setup_entry(self, entry, property):
        if type(entry) == EartagTagListItem:
            entry.bind_to_property(self.file, property)
            self.bindings = self.bindings + entry.bindings
        elif type(entry) == EartagEditableLabel:
            self.bindings.append(
                self.file.bind_property(property, entry.editable, 'text',
                    GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
            )
            entry.notify('text')

    def close_dialog(self, dialog, *args):
        dialog.close()

    def save(self):
        """Saves changes to the file."""
        if not self.writable:
            return False

        try:
            self.file.save()
        except:
            traceback.print_exc()
            file_basename = os.path.basename(self.file_path)
            self.error_dialog = Gtk.MessageDialog(
                                    transient_for=self.get_native(),
                                    buttons=Gtk.ButtonsType.OK,
                                    message_type=Gtk.MessageType.ERROR,
                                    text=_("Failed to save file"),
                                    secondary_text=_("Could not save file {f}. Check the logs for more information.").format(f=file_basename)
            )
            self.error_dialog.connect('response', self.close_dialog)
            self.error_dialog.show()
            return False
        else:
            self.get_native().toast_overlay.add_toast(
                Adw.Toast.new(_("Saved changes to file"))
            )
