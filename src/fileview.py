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
from .common import (
    EartagEditableLabel,
    is_valid_image_file,
    EartagAlbumCoverImage,
    EartagMultipleValueEntry
)
from .backends.file import EartagFile

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

        self.files = []

    def bind_to_file(self, file):
        self.files.append(file)

        if len(self.files) < 2:
            if not file.supports_album_covers:
                self.set_visible(False)
                return False
            else:
                self.set_visible(True)
            self.cover_image.bind_to_file(file)
            self.cover_image.mark_as_nonempty()
        else:
            covers_different = False
            our_cover = file.cover

            if False in [f.supports_album_covers for f in self.files]:
                self.set_visible(False)
            else:
                self.set_visible(True)

            for _file in self.files:
                if _file.cover != our_cover:
                    covers_different = True
                    self.cover_image.mark_as_empty()
                    break
            if not covers_different:
                self.cover_image.mark_as_nonempty()

    def unbind_from_file(self, file):
        self.files.remove(file)

        for _file in self.files:
            if not _file.supports_album_covers:
                self.set_visible(False)
                break
            else:
                self.set_visible(True)

        if len(self.files) > 1:
            covers_different = False
            our_cover = self.files[0].cover
            for _file in self.files:
                if _file.cover != our_cover:
                    covers_different = True
                    if _file.supports_album_covers and _file.cover:
                        self.cover_image.bind_to_file(_file)
                    self.cover_image.mark_as_empty()
                    break
            if not covers_different:
                self.cover_image.mark_as_nonempty()
                if self.files[0].supports_album_covers and self.files[0].cover:
                    self.cover_image.bind_to_file(self.files[0])

        elif len(self.files) == 1:
            self.cover_image.bind_to_file(self.files[0])
            self.cover_image.on_cover_change()

    def on_destroy(self, *args):
        self.files = None

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
            for file in self.files:
                file.cover_path = dialog.get_file().get_path()
                file.notify('cover-path')
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
        for file in self.files:
            file.cover_path = path
            file.notify('cover-path')
        self.cover_image.on_cover_change()
        self.on_drag_unhover()

    # Hover
    def on_hover(self, *args):
        if not self.handling_drag and not self.handling_undefined_drag:
            self.highlight_stack.set_visible_child(self.hover_highlight)
            self.highlight_revealer.set_reveal_child(True)

    def on_unhover(self, *args):
        self.highlight_revealer.set_reveal_child(False)

class EartagTagListItemBase:
    def on_destroy(self, *args):
        self.files = []

    def disallow_nonnumeric(self, entry, text, length, position, *args):
        if text and not text.isdigit():
            GObject.signal_stop_emission_by_name(entry, 'insert-text')

    def _set_property(self, property, property_double=None):
        if property_double:
            if not self._is_double:
                raise ValueError
            self.properties = [property, property_double]
            self.ignore_edit[property_double] = False
        else:
            self.properties = [property]
        self.ignore_edit[property] = False

class EartagTagListItem(Adw.EntryRow, EartagTagListItemBase, EartagMultipleValueEntry):
    __gtype_name__ = 'EartagTagListItem'

    _is_double = False
    _is_numeric = False

    def __init__(self):
        super().__init__(use_markup=True)
        self._title = self.get_title()

        self.value_entry = self # for compatibility

        self.connect('changed', self.on_changed, False)
        self.connect('destroy', self.on_destroy)

        self.files = []
        self.properties = []
        self.ignore_edit = {}
        self._placeholder = ''

    @GObject.Property(type=bool, default=False)
    def is_double(self):
        return False

    @GObject.Property(type=bool, default=False)
    def is_numeric(self):
        return self._is_numeric

    @is_numeric.setter
    def is_numeric(self, value):
        self._is_numeric = value
        if value == True:
            self.set_input_purpose(Gtk.InputPurpose.DIGITS)
            self.get_delegate().connect('insert-text', self.disallow_nonnumeric)

    def set_placeholder_text(self, text):
        """
        This is used by EartagMultipleValueEntry to show a placeholder value
        when there are multiple files selected.

        In the case of AdwEntryRows, the title acts as the placeholder,
        but if we overrode the title, then the purpose of the field wouldn't
        be displayed.

        So, instead, we append the placeholder to the title, and remove it when
        the state changes.
        """
        if self._placeholder and text:
            return
        self._placeholder = text
        if text:
            # TODO: it would be nice to have the placeholder text highlighted in bold,
            # currently https://gitlab.gnome.org/GNOME/libadwaita/-/issues/579 is
            # preventing us from doing that but i got a fix for it merged; revisit once
            # the next minor libadwaita release is out
            self.set_title(self.get_title() + ' ' + text)
        else:
            if self._title:
                self.set_title(self._title)
            else:
                # This if-else statement is a workaround for cases where the _title
                # variable doesn't get initialized properly.
                self._title = self.get_title()

class EartagTagListDoubleItem(Adw.ActionRow, EartagTagListItemBase, EartagMultipleValueEntry):
    __gtype_name__ = 'EartagTagListDoubleItem'

    _is_double = True
    _is_numeric = False
    _max_width_chars = -1

    def __init__(self):
        super().__init__(can_target=False, focusable=False, focus_on_click=False)
        self.suffixes = Gtk.Box(valign=Gtk.Align.CENTER, halign=Gtk.Align.END, spacing=6)
        self.add_suffix(self.suffixes)

        self.value_entry = Gtk.Entry(valign=Gtk.Align.CENTER)
        self.value_entry.connect('changed', self.on_changed, False)
        self.suffixes.append(self.value_entry)

        self.double_separator_label = Gtk.Label(valign=Gtk.Align.CENTER)
        self.suffixes.append(self.double_separator_label)

        self.value_entry_double = Gtk.Entry(valign=Gtk.Align.CENTER)
        self.value_entry_double.connect('changed', self.on_changed, True)
        self.suffixes.append(self.value_entry_double)

        self.set_activatable_widget(self.value_entry)
        self.connect('destroy', self.on_destroy)

        self.files = []
        self.properties = []
        self.ignore_edit = {}

    @GObject.Property(type=str, default='')
    def double_separator(self):
        return self._double_separator

    @double_separator.setter
    def double_separator(self, value):
        self._double_separator = value
        if value:
            self.double_separator_label.set_label(value)
            self.double_separator_label.set_visible(True)
        else:
            self.double_separator_label.set_visible(False)

    @GObject.Property(type=bool, default=False)
    def is_double(self):
        return True

    @GObject.Property(type=int, default=-1)
    def max_width_chars(self):
        return self._max_width_chars

    @max_width_chars.setter
    def max_width_chars(self, value):
        self._max_width_chars = value
        self.value_entry.set_max_width_chars(value)
        self.value_entry_double.set_max_width_chars(value)

    @GObject.Property(type=bool, default=False)
    def is_numeric(self):
        return self._is_numeric

    @is_numeric.setter
    def is_numeric(self, value):
        self._is_numeric = value
        if value == True:
            self.value_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
            self.value_entry.get_delegate().connect('insert-text', self.disallow_nonnumeric)

            self.value_entry_double.set_input_purpose(Gtk.InputPurpose.DIGITS)
            self.value_entry_double.get_delegate().connect('insert-text', self.disallow_nonnumeric)

class EartagTagListMoreItem(Adw.ActionRow, EartagTagListItemBase, EartagMultipleValueEntry):
    __gtype_name__ = 'EartagTagListMoreItem'

    _is_double = False
    _is_numeric = False
    _max_width_chars = -1

    # I wish GTK had a built-in list type like StringList but for ID-human readable value pairs,
    # but for now this will have to suffice:
    tag_names = {
        "none": _("(Select a tag)"),
        "bpm": _("BPM"), # TRANSLATORS: Short for "beats per minute".
        "compilation": _("Compilation"),
        "composer": _("Composer"),
        "copyright": _("Copyright"),
        "encodedby": _("Encoded by"),
        "mood": _("Mood"),
        "conductor": _("Conductor"), # TRANSLATORS: Orchestra conductor
        "arranger": _("Arranger"),
        "discnumber": _("Disc number"),
        "publisher": _("Publisher"),
        "isrc": "ISRC",
        "language": _("Language"),
        "discsubtitle": _("Disc subtitle"),

        "albumartistsort": _("Album artist (sort)"), # TRANSLATORS: This is a sort tag, as in, a tag that dictates how music software should treat this tag when sorting.
        "albumsort": _("Album (sort)"), # TRANSLATORS: This is a sort tag, as in, a tag that dictates how music software should treat this tag when sorting.
        "composersort": _("Composer (sort)"), # TRANSLATORS: This is a sort tag, as in, a tag that dictates how music software should treat this tag when sorting.
        "artistsort": _("Artist (sort)"), # TRANSLATORS: This is a sort tag, as in, a tag that dictates how music software should treat this tag when sorting.
        "titlesort": _("Title (sort)") # TRANSLATORS: This is a sort tag, as in, a tag that dictates how music software should treat this tag when sorting.
    }

    handled_tags = []
    skip_filter_change = False

    def __init__(self, property=None):
        super().__init__()

        self.files = []
        if property:
            self.properties = [property]
        else:
            self.properties = []
        self.ignore_edit = {}
        self._numeric_connect = None

        self._tag_names_swapped = {}
        for k, v in self.tag_names.items():
            self._tag_names_swapped[v] = k

        self.value_entry = Gtk.Entry(valign=Gtk.Align.CENTER)
        self.value_entry.connect('changed', self.on_changed, False)
        self.add_suffix(self.value_entry)

        self.remove_button = Gtk.Button(icon_name='list-remove-symbolic', valign=Gtk.Align.CENTER)
        self.remove_button.connect('clicked', self.remove_row)
        self.remove_button.add_css_class('flat')
        self.add_suffix(self.remove_button)

        tag_strings = Gtk.StringList.new(list(self.tag_names.values()))
        self.tag_model = Gtk.FilterListModel(model=tag_strings)
        self.tag_filter = Gtk.CustomFilter.new(self.tag_filter_func, self.tag_model)
        self.tag_model.set_filter(self.tag_filter)

        self.tag_selector = Gtk.DropDown.new(model=self.tag_model)
        self.tag_selector.set_valign(Gtk.Align.CENTER)
        # I wish we could just use "DropDown:activate" but it never gets emitted,
        # but it is just a ToggleButton underneath!
        self.tag_selector.get_first_child().connect('clicked', self.refresh_filter)
        self.tag_selector.connect('notify::selected', self.on_tag_selector_select)

        if property:
            self._set_property(property)
        self.on_tag_selector_select(self.tag_selector)
        self.add_prefix(self.tag_selector)

        self.set_activatable_widget(self.value_entry)
        self.connect('destroy', self.on_destroy)

    @GObject.Property(type=bool, default=False)
    def is_double(self):
        return False

    @GObject.Property(type=bool, default=False)
    def is_numeric(self):
        return self._is_numeric

    @is_numeric.setter
    def is_numeric(self, value):
        self._is_numeric = value
        if value is True:
            self.value_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
            if not self._numeric_connect:
                self._numeric_connect = self.value_entry.get_delegate().connect('insert-text', self.disallow_nonnumeric)
        else:
            self.value_entry.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
            if self._numeric_connect:
                self.value_entry.get_delegate().disconnect(self._numeric_connect)
                self._numeric_connect = None

    def tag_filter_func(self, _tag_name, *args):
        present_tags = dict([(entry.properties[0], entry) for entry in EartagFileView.more_entries])

        tag_name = _tag_name.get_string()
        tag_prop = self._tag_names_swapped[tag_name]

        if tag_prop == 'none' and 'none' in self.properties:
            return True
        if tag_prop in present_tags and tag_prop not in self.properties:
            return False

        banned_tags_list = []
        for taglist in EartagFileView.banned_tags.values():
            for tag in taglist:
                if tag not in banned_tags_list:
                    banned_tags_list.append(tag)

        if tag_prop in banned_tags_list:
            return False
        return True

    def _set_property(self, property, property_double=None):
        super()._set_property(property, None)
        n = 0
        item = self.tag_model.get_item(n)
        found = None
        while item:
            if item.get_string() == self.tag_names[property]:
                found = n
                break
            n += 1
            item = self.tag_model.get_item(n)

        if found:
            self.tag_selector.set_selected(found)

    def on_tag_selector_select(self, dropdown, *args):
        present_tags = dict([(entry.properties[0], entry) for entry in EartagFileView.more_entries])

        old_tag = None
        if self.properties:
            old_tag = self.properties[0]

        selected_item = dropdown.get_selected_item()
        if not selected_item:
            self.refresh_filter()
            self._set_property(old_tag)
            return

        property = self._tag_names_swapped[selected_item.get_string()]
        if property == 'none':
            self.value_entry.set_sensitive(False)
            self.remove_button.set_sensitive(False)
            return
        self.value_entry.set_sensitive(True)
        self.remove_button.set_sensitive(True)
        self.properties = [property]
        if property in EartagFile.int_properties and not self._is_numeric:
            self.set_property('is_numeric', True)
        elif property not in EartagFile.int_properties and self._is_numeric:
            self.set_property('is_numeric', False)
        for file in self.files:
            if property not in file.present_extra_tags:
                file.present_extra_tags.append(property)
            self.refresh_multiple_values(file)
        if old_tag == 'none':
            self.get_native().file_view.add_empty_row()
        if not self.skip_filter_change:
            for row in present_tags.values():
                row.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

    def remove_row(self, *args):
        """Removes the row."""
        self.get_native().file_view.remove_and_unbind_extra_row(self)

    def refresh_filter(self, *args):
        self.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

@Gtk.Template(resource_path='/app/drey/EarTag/ui/fileview.ui')
class EartagFileView(Gtk.Stack):
    __gtype_name__ = 'EartagFileView'

    loading = Gtk.Template.Child()
    content_stack = Gtk.Template.Child()
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

    more_tags_expander = Gtk.Template.Child()

    previous_file_button_revealer = Gtk.Template.Child()
    next_file_button_revealer = Gtk.Template.Child()
    previous_file_button = Gtk.Template.Child()
    next_file_button = Gtk.Template.Child()

    writable = False
    bindings = {}
    bound_files = []
    more_entries = []
    banned_tags = {}
    opened_filetypes = {}

    def __init__(self):
        """Initializes the EartagFileView."""
        super().__init__()

        # Initialize an initial "none" row
        self.add_empty_row()

    def set_file_manager(self, file_manager):
        self.file_manager = file_manager
        self.file_manager.connect('files_loaded', self.update_binds)
        self.file_manager.connect('selection_changed', self.update_binds)
        self.file_manager.connect('files_removed', self.update_binds)
        self.file_manager.connect('notify::loading-progress', self.update_loading)

        sidebar = self.get_native().sidebar
        self.next_file_button.connect('clicked', sidebar.select_next)
        self.previous_file_button.connect('clicked', sidebar.select_previous)
        sidebar.connect('notify::selection-mode', self.update_buttons)

    def update_loading(self, *args):
        if self.file_manager.loading_progress == 0:
            self.set_visible_child(self.content_stack)
        else:
            self.set_visible_child(self.loading)

    def update_buttons(self, *args):
        """Updates the side switcher button state."""
        if len(self.file_manager.files) == 0 or self.get_native().sidebar.selection_mode:
            self.previous_file_button.set_sensitive(False)
            self.previous_file_button_revealer.set_reveal_child(False)
            self.next_file_button.set_sensitive(False)
            self.next_file_button_revealer.set_reveal_child(False)
        else:
            if self.get_native().sidebar.file_list.selection_model.get_n_items() > 1:
                self.previous_file_button.set_sensitive(True)
                self.next_file_button.set_sensitive(True)
            else:
                self.previous_file_button.set_sensitive(False)
                self.next_file_button.set_sensitive(False)
            self.previous_file_button_revealer.set_reveal_child(True)
            self.next_file_button_revealer.set_reveal_child(True)

    def update_binds(self, *args):
        """
        Reads the file data from the file manager and applies it
        to the file view.
        """
        window = self.get_native()

        self.update_buttons()

        # Get list of selected (added)/unselected (removed) files
        added_files = [file for file in self.file_manager.selected_files if file not in self.bound_files]
        removed_files = [file for file in self.bound_files if file not in self.file_manager.selected_files]

        # Set up the active view (hide fileview if there are no selected files)
        selected_files_count = len(self.file_manager.selected_files)
        if selected_files_count <= 0:
            window.set_title('Ear Tag')
            window.window_title.set_subtitle('')
            if self.file_manager.files:
                self.content_stack.set_visible_child(self.select_file)

            self._unbind_files(self.bindings.copy().keys())

            self.bindings = {}
            self.bound_files = []

            window.run_sort()
            return False
        else:
            files = self.file_manager.selected_files

        self.content_stack.set_visible_child(self.content_scroll)

        # Set up window title and file info label
        if len(files) == 1:
            file = files[0]
            file_basename = os.path.basename(file.path)
            window.set_title('{f} — Ear Tag'.format(f=file_basename))
            window.window_title.set_subtitle(file_basename)

            self._set_info_label(file)
        else:
            # TRANSLATOR: Placeholder for file path when multiple files are selected
            _multiple_files = _('(Multiple files selected)')
            window.set_title('{f} — Ear Tag'.format(f=_multiple_files))
            window.window_title.set_subtitle(_multiple_files)
            self.file_info.set_label(_multiple_files)

        # Handle added and removed files
        self._unbind_files(removed_files)
        self._bind_files(added_files)

        # Make save/fields sensitive/insensitive based on whether selected files are
        # all writable
        has_unwritable = False
        for file in files:
            if not file.is_writable:
                has_unwritable = True
                break
        if has_unwritable:
            self.set_sensitive(False)
            window.save_button.set_tooltip_text(_('File is read-only, saving is disabled'))
            window.save_button.set_sensitive(False)
        else:
            self.set_sensitive(True)
            window.save_button.set_tooltip_text('')
            window.save_button.set_sensitive(self.file_manager.is_modified)

        # Scroll to the top of the view
        adjust = self.content_scroll.get_vadjustment()
        adjust.set_value(adjust.get_lower())

    def setup_entry(self, file, entry, property, property_double=None):
        if isinstance(entry, EartagTagListItemBase):
            if not isinstance(entry, EartagTagListMoreItem):
                entry._set_property(property, property_double)
            entry.bind_to_file(file)
        elif isinstance(entry, EartagEditableLabel):
            entry.properties = [property]
            entry.ignore_edit = {property: False}
            entry.bind_to_file(file)
            entry.notify('text')

    def unbind_entry(self, file, entry):
        if isinstance(entry, EartagTagListItemBase):
            entry.unbind_from_file(file)
        elif isinstance(entry, EartagEditableLabel):
            entry.unbind_from_file(file)
            entry.notify('text')

    def _bind_files(self, files):
        """Binds a file to the fileview. Used internally in update_binds."""
        if not files:
            return

        EartagTagListMoreItem.skip_filter_change = True

        all_tags = EartagTagListMoreItem.tag_names.keys()
        more_entries_dict = dict([(entry.properties[0], entry) for entry in self.more_entries])

        banned_tags_list = []
        for taglist in self.banned_tags.values():
            for tag in taglist:
                if tag not in banned_tags_list:
                    banned_tags_list.append(tag)

        all_present_extra_tags = ['none']
        for file in set(self.bound_files + files):
            for tag in file.present_extra_tags:
                if tag not in all_present_extra_tags:
                    all_present_extra_tags.append(tag)

        for tag in all_present_extra_tags:
            if tag not in more_entries_dict and tag not in banned_tags_list:
                entry = self.add_extra_row(tag, skip_adding_none=True)
                more_entries_dict[tag] = entry

        for file in files:
            if file not in self.bindings:
                self.bindings[file] = []
            self.bound_files.append(file)

            self.setup_entry(file, self.title_entry, 'title')
            self.setup_entry(file, self.artist_entry, 'artist')
            self.setup_entry(file, self.tracknumber_entry, 'tracknumber', 'totaltracknumber')
            self.setup_entry(file, self.album_entry, 'album')
            self.setup_entry(file, self.albumartist_entry, 'albumartist')
            self.setup_entry(file, self.genre_entry, 'genre')
            self.setup_entry(file, self.releaseyear_entry, 'releaseyear')
            self.setup_entry(file, self.comment_entry, 'comment')
            self.album_cover.bind_to_file(file)

            filetype = file.__gtype_name__
            if filetype not in self.opened_filetypes:
                self.opened_filetypes[filetype] = 1
            else:
                self.opened_filetypes[filetype] += 1

            if filetype not in self.banned_tags:
                for tag in all_tags:
                    if tag == 'none':
                        continue
                    if tag not in file.supported_extra_tags:
                        if tag not in banned_tags_list:
                            banned_tags_list.append(tag)
                        if filetype not in self.banned_tags:
                            self.banned_tags[filetype] = [tag]
                        else:
                            self.banned_tags[filetype].append(tag)

            for tag, entry in more_entries_dict.items():
                if tag not in banned_tags_list:
                    self.setup_entry(file, entry, tag)

        for tag in banned_tags_list:
            if tag in more_entries_dict:
                entry = more_entries_dict[tag]
                self.remove_extra_row(entry)
                del(more_entries_dict[tag])

        # Move "none" entry to the bottom
        none_entry = more_entries_dict['none']
        self.more_tags_expander.remove(none_entry)
        self.more_tags_expander.add_row(none_entry)

        for entry in self.more_entries:
            entry.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

        EartagTagListMoreItem.skip_filter_change = False

    def _unbind_files(self, files):
        """Unbinds a file from the fileview. Used internally in update_binds."""
        if not files:
            return

        EartagTagListMoreItem.skip_filter_change = True

        more_entries_dict = dict([(entry.properties[0], entry) for entry in self.more_entries])

        for file in files:
            for binding in self.bindings[file]:
                binding.unbind()
            del(self.bindings[file])
            self.bound_files.remove(file)

            filetype = file.__gtype_name__
            self.opened_filetypes[filetype] -= 1

            self.unbind_entry(file, self.title_entry)
            self.unbind_entry(file, self.artist_entry)
            self.unbind_entry(file, self.tracknumber_entry)
            self.unbind_entry(file, self.album_entry)
            self.unbind_entry(file, self.albumartist_entry)
            self.unbind_entry(file, self.genre_entry)
            self.unbind_entry(file, self.releaseyear_entry)
            self.unbind_entry(file, self.comment_entry)
            self.album_cover.unbind_from_file(file)

            for entry in self.more_entries:
                self.unbind_entry(file, entry)

        all_present_extra_tags = ['none']
        for file in self.bound_files:
            for tag in file.present_extra_tags:
                if tag not in all_present_extra_tags:
                    all_present_extra_tags.append(tag)

        for tag, entry in more_entries_dict.copy().items():
            if tag not in all_present_extra_tags:
                self.remove_extra_row(entry)
                del(more_entries_dict[tag])

        unbanned_filetypes = []

        for filetype, count in self.opened_filetypes.copy().items():
            if count <= 0:
                del(self.opened_filetypes[filetype])
                if filetype in self.banned_tags:
                    unbanned_filetypes.append(filetype)

        if unbanned_filetypes:
            banned_tags_list = []
            potentially_unbanned_tags_list = []
            for ft, taglist in self.banned_tags.items():
                if ft in unbanned_filetypes:
                    for tag in taglist:
                        if tag not in potentially_unbanned_tags_list:
                            potentially_unbanned_tags_list.append(tag)
                else:
                    for tag in taglist:
                        if tag not in banned_tags_list:
                            banned_tags_list.append(tag)
            unbanned_tags_list = []
            for tag in potentially_unbanned_tags_list:
                if tag not in banned_tags_list:
                    unbanned_tags_list.append(tag)

            for tag in unbanned_tags_list:
                if tag in all_present_extra_tags:
                    if tag not in more_entries_dict:
                        self.add_extra_row(tag, skip_adding_none=True)

            for filetype in unbanned_filetypes:
                del(self.banned_tags[filetype])

        none_entry = more_entries_dict['none']
        self.more_tags_expander.remove(none_entry)
        self.more_tags_expander.add_row(none_entry)

        for entry in self.more_entries:
            entry.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

        EartagTagListMoreItem.skip_filter_change = False

    def add_empty_row(self, *args):
        self.add_extra_row('none')

    def add_extra_row(self, tag, skip_adding_none=False):
        """
        Adds an extra row for the given tag. Consumers are required to make sure that
        a row with this tag doesn't exist yet.

        Returns the newly created row.
        """
        entry = EartagTagListMoreItem(tag)
        self.more_entries.append(entry)
        self.more_tags_expander.add_row(entry)

        for file in self.bound_files:
            self.setup_entry(file, entry, tag)

        # Update entry item filters
        if not EartagTagListMoreItem.skip_filter_change:
            for entry in self.more_entries:
                entry.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

        if not skip_adding_none:
            # Move "none" entry to the end
            none_entry = None
            for entry in self.more_entries:
                if entry.properties and entry.properties[0] == 'none':
                    none_entry = entry
                    break
            if none_entry:
                self.more_tags_expander.remove(none_entry)
                self.more_tags_expander.add_row(none_entry)

        return entry

    def remove_extra_row(self, row, skip_adding_none=False):
        """
        Removes a 'more tags' row from the fileview.
        """
        if row not in self.more_entries:
            return
        self.more_entries.remove(row)
        self.more_tags_expander.remove(row)

        # Update entry item filters
        if not EartagTagListMoreItem.skip_filter_change:
            for entry in self.more_entries:
                entry.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

        # Move "none" entry to the end
        if not skip_adding_none:
            none_entry = None
            for entry in self.more_entries:
                if entry.properties and entry.properties[0] == 'none':
                    none_entry = entry
                    break
            if none_entry:
                self.more_tags_expander.remove(none_entry)
                self.more_tags_expander.add_row(none_entry)

    def remove_and_unbind_extra_row(self, row):
        """
        Removes a 'more tags' row from the fileview. Used in the callback
        function of the rows' delete button.
        """
        removed_tag = row.properties[0]
        for file in self.bound_files:
            if removed_tag in file.present_extra_tags:
                file.present_extra_tags.remove(removed_tag)
                file.delete_tag(removed_tag)

        self.remove_extra_row(row)

    def _set_info_label(self, file):
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
        if channels == 0:
            channels_readable = 'N/A'
        elif channels == 1:
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

    def save(self):
        """Saves changes to the file."""
        self.file_manager.save()
