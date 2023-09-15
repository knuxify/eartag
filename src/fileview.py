# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from .backends.file import EartagFile, EXTRA_TAGS, TAG_NAMES, CoverType
from .utils import get_readable_length
from .utils.validation import is_valid_image_file
from .utils.widgets import EartagAlbumCoverImage, EartagPopoverButton  # noqa: F401
from .tagentry import ( # noqa: F401
    EartagTagEntry, EartagTagEntryRow,
    EartagTagEditableLabel
)

from gi.repository import Adw, Gtk, Gdk, Gio, GLib, GObject

import gettext
import magic
import mimetypes
import shutil
import os.path

@Gtk.Template(resource_path='/app/drey/EarTag/ui/albumcoverbutton.ui')
class EartagAlbumCoverButton(Adw.Bin):
    __gtype_name__ = 'EartagAlbumCoverButton'

    button = Gtk.Template.Child()
    cover_image = Gtk.Template.Child()

    highlight_revealer = Gtk.Template.Child()
    highlight_stack = Gtk.Template.Child()
    drop_highlight = Gtk.Template.Child()
    hover_highlight = Gtk.Template.Child()

    handling_drag = False
    handling_undefined_drag = False
    image_file_filter = Gtk.Template.Child()

    front_toggle = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self._cover_type = CoverType.FRONT
        self._remove_undo_buffer = {}

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

        self.front_toggle.connect('notify::active', self.update_from_switcher)
        self.front_toggle.set_active(True)

        self.cover_image.connect('cover-changed', self.update_coverbutton_save_availability)
        self.cover_image.connect('notify::cover-type', self.update_coverbutton_save_availability)
        self.cover_image.connect('notify::is-empty', self.update_coverbutton_save_availability)

        self.bind_property('cover-type', self.cover_image, 'cover-type')

        # Register actions for popover menu
        self.install_action('albumcoverbutton.load', None, self.show_cover_file_chooser)
        self.install_action('albumcoverbutton.save', None, self.save_cover)
        self.action_set_enabled('albumcoverbutton.save', False)
        self.install_action('albumcoverbutton.remove', None, self.remove_cover)

        self.files = []

    def _dropdown_lockup_workaround(self, toggle, *args):
        """
        Workaround for https://gitlab.gnome.org/GNOME/gtk/-/issues/5568
        """
        if not toggle.get_active():
            self.button.popover.popdown()

    def update_from_switcher(self, toggle, *args):
        """Sets the displayed cover by checking the cover switcher."""
        if toggle.get_active():
            self.cover_type = CoverType.FRONT
        else:
            self.cover_type = CoverType.BACK

    @GObject.Property(type=int)
    def cover_type(self):
        """Whether to display the front or back cover."""
        return self._cover_type

    @cover_type.setter
    def cover_type(self, value):
        self._cover_type = value

    def update_coverbutton_save_availability(self, *args):
        if self.cover_type == CoverType.FRONT:
            cover = 'front_cover'
        else:
            cover = 'back_cover'

        self.action_set_enabled('albumcoverbutton.save', not self.cover_image.is_empty)

        enable_remove = False
        for file in self.files:
            if not getattr(file, cover).is_empty():
                enable_remove = True
            break

        self.action_set_enabled('albumcoverbutton.remove', enable_remove)

    def bind_to_file(self, file):
        self.files.append(file)

        if len(self.files) < 2:
            if not file.supports_album_covers:
                self.set_visible(False)
                self.update_coverbutton_save_availability()
                return False
            else:
                self.set_visible(True)
            self.cover_image.bind_to_file(file)
            self.cover_image.mark_as_nonempty()
        else:
            covers_different = False
            our_cover = file.get_cover(self.cover_type)

            if False in [f.supports_album_covers for f in self.files]:
                self.set_visible(False)
            else:
                self.set_visible(True)

            for _file in self.files:
                if _file.get_cover(self.cover_type) != our_cover:
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
                self.update_coverbutton_save_availability()
                break
            else:
                self.set_visible(True)

        if len(self.files) > 1:
            covers_different = False
            our_cover = self.files[0].get_cover(self.cover_type)
            for _file in self.files:
                if _file.get_cover(self.cover_type) != our_cover:
                    covers_different = True
                    if _file.supports_album_covers and _file.front_cover:
                        self.cover_image.bind_to_file(_file)
                    self.cover_image.mark_as_empty()
                    break
            if not covers_different:
                self.cover_image.mark_as_nonempty()
                if self.files[0].supports_album_covers and \
                        self.files[0].get_cover(self.cover_type):
                    self.cover_image.bind_to_file(self.files[0])

        elif len(self.files) == 1:
            self.cover_image.bind_to_file(self.files[0])
            self.cover_image.on_cover_change()

    def on_destroy(self, *args):
        self.files = None

    def show_cover_file_chooser(self, *args):
        """Shows the file chooser."""
        file_chooser = Gtk.FileDialog(
            title=_("Select Album Cover Image"),
            modal=True
        )
        _cancellable = Gio.Cancellable.new()

        _filters = Gio.ListStore.new(Gtk.FileFilter)
        _filters.append(self.image_file_filter)
        file_chooser.set_filters(_filters)

        file_chooser.open(self.get_native(), _cancellable,
            self.open_cover_file_from_dialog)

    def save_cover(self, *args):
        """Opens a file dialog to have the cover art to a file."""

        if self.cover_type == CoverType.FRONT:
            cover_path = self.files[0].front_cover_path
        elif self.cover_type == CoverType.BACK:
            cover_path = self.files[0].back_cover_path
        if not cover_path:
            return

        cover_mime = magic.from_file(cover_path, mime=True)
        cover_extension = mimetypes.guess_extension(cover_mime)
        target_folder, target_filename = os.path.split(self.files[0].path)
        target_filename = os.path.splitext(target_filename)[0] + cover_extension

        file_chooser = Gtk.FileDialog(title=_("Save Album Cover To…"), modal=True,
            initial_folder=Gio.File.new_for_path(target_folder), initial_name=target_filename)
        _cancellable = Gio.Cancellable.new()

        file_chooser.save(self.get_native(), _cancellable, self._save_cover_response)

    def _save_cover_response(self, dialog, result):
        try:
            response = dialog.save_finish(result)
        except GLib.GError:
            return

        if not response:
            return

        if self.cover_type == CoverType.FRONT:
            cover_path = self.files[0].front_cover_path
        elif self.cover_type == CoverType.BACK:
            cover_path = self.files[0].back_cover_path

        if cover_path:
            save_path = response.get_path()
            cover_mime = magic.from_file(cover_path, mime=True)
            cover_extension = mimetypes.guess_extension(cover_mime)
            if cover_extension and not save_path.endswith(cover_extension):
                save_path += cover_extension
            shutil.copyfile(cover_path, save_path)

        toast = Adw.Toast.new(_("Saved cover to {path}").format(path=save_path))
        self.get_native().toast_overlay.add_toast(toast)

    def remove_cover(self, *args):
        self._remove_undo_budder = {}
        self._remove_undo_buffer['type'] = self.cover_type

        if self.cover_type == CoverType.FRONT:
            cover_path_prop = 'front_cover_path'
        elif self.cover_type == CoverType.BACK:
            cover_path_prop = 'back_cover_path'

        for file in self.files:
            self._remove_undo_buffer[file.id] = file.get_property(cover_path_prop)
            # HACK: Instead of setting the cover path directly (which will
            # call delete_cover) we set the underlying property instead.
            # That was we can still recover the tempfile-based covers if the
            # remove gets undone. We call delete_cover later on.
            setattr(file, '_' + cover_path_prop, '')
            file.mark_as_modified(cover_path_prop)
            file.notify(cover_path_prop)

        remove_msg = gettext.ngettext(
            "Removed cover from file",
            "Removed covers from {n} files",
            len(self.files)).format(n=len(self.files))
        toast = Adw.Toast.new(remove_msg)
        toast.set_button_label(_("Undo"))
        toast.connect('button-clicked', self._remove_undo)
        toast.connect('dismissed', self._remove_undo_clear)
        self.get_native().toast_overlay.add_toast(toast)

    def _remove_undo(self, *args):
        if self._remove_undo_buffer['type'] == CoverType.FRONT:
            cover_path_prop = 'front_cover_path'
        elif self._remove_undo_buffer['type'] == CoverType.BACK:
            cover_path_prop = 'back_cover_path'

        file_manager = self.get_native().file_manager
        for file in file_manager.files:
            if file.id not in self._remove_undo_buffer:
                continue
            file.set_property(cover_path_prop, self._remove_undo_buffer[file.id])

        for _file in self.files:
            if _file.get_cover(self.cover_type) != self.files[0]:
                covers_different = True
                self.cover_image.mark_as_empty()
                break
        self._remove_undo_buffer = {}

    def _remove_undo_clear(self, *args):
        if 'type' not in self._remove_undo_buffer:
            return

        if self._remove_undo_buffer['type'] == CoverType.FRONT:
            cover_path_prop = 'front_cover_path'
        elif self._remove_undo_buffer['type'] == CoverType.BACK:
            cover_path_prop = 'back_cover_path'

        file_manager = self.get_native().file_manager
        for file in file_manager.files:
            if file.id not in self._remove_undo_buffer:
                continue
            if file.get_property(cover_path_prop) != self._remove_undo_buffer[file.id]:
                continue
            file.delete_cover(self._remove_undo_buffer['type'])

        for _file in self.files:
            if _file.get_cover(self.cover_type) != self.files[0]:
                covers_different = True
                self.cover_image.mark_as_empty()
                break

        self._remove_undo_buffer = {}

    def open_cover_file_from_dialog(self, dialog, result):
        """
        Callback for a FileChooser that takes the response and opens the file
        selected in the dialog.
        """
        try:
            response = dialog.open_finish(result)
        except GLib.GError:
            return

        if not response:
            return

        if self.cover_type == CoverType.FRONT:
            for file in self.files:
                file.front_cover_path = response.get_path()
                file.notify('front-cover-path')
        elif self.cover_type == CoverType.BACK:
            for file in self.files:
                file.back_cover_path = response.get_path()
                file.notify('back-cover-path')

        self.cover_image.on_cover_change()

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
        if self.cover_type == CoverType.FRONT:
            for file in self.files:
                file.front_cover_path = path
                file.notify('front-cover-path')
        elif self.cover_type == CoverType.BACK:
            for file in self.files:
                file.back_cover_path = path
                file.notify('back-cover-path')
        self.cover_image.on_cover_change()
        self.on_drag_unhover()

    # Hover
    def on_hover(self, *args):
        if not self.handling_drag and not self.handling_undefined_drag:
            self.highlight_stack.set_visible_child(self.hover_highlight)
            self.highlight_revealer.set_reveal_child(True)

    def on_unhover(self, *args):
        self.highlight_revealer.set_reveal_child(False)

# ActionRow with two TagEntries, used for track numbers.
@Gtk.Template(resource_path='/app/drey/EarTag/ui/rows/tagdoublerow.ui')
class EartagTagDoubleRow(Adw.ActionRow):
    __gtype_name__ = 'EartagTagDoubleRow'

    _max_width_chars = -1

    first_entry = Gtk.Template.Child()
    double_separator_label = Gtk.Template.Child()
    second_entry = Gtk.Template.Child()
    suffixes = Gtk.Template.Child()

    @GObject.Property(type=str, default='')
    def double_separator(self):
        return self.double_separator_label.get_label()

    @double_separator.setter
    def double_separator(self, value):
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
        self.first_entry.set_max_width_chars(value)
        self.second_entry.set_max_width_chars(value)

    @GObject.Property(type=bool, default=False)
    def is_numeric(self):
        return self.first_entry.is_numeric

    @is_numeric.setter
    def is_numeric(self, value):
        self.first_entry.is_numeric = value
        self.second_entry.is_numeric = value

    @GObject.Property(type=str, default=None)
    def first_property(self):
        return self.first_entry.bound_property

    @first_property.setter
    def first_property(self, value):
        self.first_entry.bound_property = value

    @GObject.Property(type=str, default=None)
    def second_property(self):
        return self.second_entry.bound_property

    @second_property.setter
    def second_property(self, value):
        self.second_entry.bound_property = value

    def bind_to_file(self, file):
        self.first_entry.bind_to_file(file)
        self.second_entry.bind_to_file(file)

    def unbind_from_file(self, file):
        self.first_entry.unbind_from_file(file)
        self.second_entry.unbind_from_file(file)

more_item_size_group = Gtk.SizeGroup()

extra_tag_names = dict(
    [(k,v) for k,v in TAG_NAMES.items() if k in ['none'] + list(EXTRA_TAGS)]
)
extra_tag_names_swapped = dict(
    [(v, k) for k,v in extra_tag_names.items()]
)
more_item_tag_strings = Gtk.StringList.new(list(extra_tag_names.values()))

@Gtk.Template(resource_path='/app/drey/EarTag/ui/rows/extratagrow.ui')
class EartagExtraTagRow(Adw.ActionRow):
    __gtype_name__ = 'EartagExtraTagRow'

    _max_width_chars = -1

    handled_tags = []
    skip_filter_change = False

    tag_selector = Gtk.Template.Child()
    value_entry = Gtk.Template.Child()
    row_remove_button = Gtk.Template.Child()

    def __init__(self, property=None, parent=None):
        super().__init__()

        self.files = []
        self.ignore_edit = {}
        self._numeric_connect = None
        self.parent = parent

        if property:
            self.value_entry.bound_property = property
            self.ignore_selector_select = True

        self.tag_model = Gtk.FilterListModel(model=more_item_tag_strings)
        self.tag_filter = Gtk.CustomFilter.new(self.tag_filter_func, self.tag_model)
        self.tag_model.set_filter(self.tag_filter)
        self.tag_selector.set_model(self.tag_model)

        # I wish we could just use "DropDown:activate" but it never gets emitted,
        # but it is just a ToggleButton underneath!
        self.tag_selector.get_first_child().connect('clicked', self.refresh_filter)

        global more_item_size_group
        more_item_size_group.add_widget(self.tag_selector)

        if property:
            tag_pos = self.get_tag_position_in_selector(property)
            if tag_pos >= 0:
                self.tag_selector.set_selected(tag_pos)
            self.ignore_selector_select = False

    def bind_to_file(self, file):
        self.value_entry.bind_to_file(file)

    def unbind_from_file(self, file):
        self.value_entry.unbind_from_file(file)

    @GObject.Property(type=str)
    def bound_property(self):
        return self.value_entry.bound_property

    @bound_property.setter
    def bound_property(self, tag):
        old_tag = None
        if self.value_entry.bound_property:
            old_tag = self.value_entry.bound_property

        if tag == old_tag:
            return

        # For "Select a value" rows, make the entry and remove button
        # unclickable
        self.value_entry.set_sensitive(tag != 'none')
        self.row_remove_button.set_sensitive(tag != 'none')

        # Set up the value entry for this tag
        self.value_entry.bound_property = tag
        self.value_entry.is_numeric = tag in EartagFile.int_properties
        self.value_entry.is_float = tag in EartagFile.float_properties

        for row in self.parent._rows:
            row.refresh_filter()

    @Gtk.Template.Callback()
    def on_tag_selector_select(self, dropdown, *args):
        if self.ignore_selector_select:
            return

        selected_item = dropdown.get_selected_item()
        if not selected_item:
            return
        tag = extra_tag_names_swapped[selected_item.get_string()]

        self.bound_property = tag

        if tag != 'none':
            self.parent.refresh_none_row()

    def tag_filter_func(self, _tag_name, *args):
        """Filter function for the tag dropdown."""
        present_tags = self.parent.get_present_tags()

        tag_name = _tag_name.get_string()
        tag_prop = extra_tag_names_swapped[tag_name]

        if tag_prop == 'none' and self.bound_property == 'none':
            return True
        if tag_prop in present_tags and self.bound_property != tag_prop:
            return False
        if tag_prop in self.parent.get_blocked_tags():
            return False

        return True

    def refresh_filter(self, *args):
        self.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

    def get_tag_position_in_selector(self, tag):
        item_count = self.tag_model.get_n_items()
        tag_name = extra_tag_names[tag]

        for i in range(item_count):
            if self.tag_model.get_item(i).get_string() == tag_name:
                return i

        return -1

    @Gtk.Template.Callback()
    def do_remove_row(self, *args):
        """Removes the row."""
        self.parent.remove_and_unbind_extra_row(self)

    # TODO: use Adw.Breakpoint once libadwaita 1.4 comes out
    def make_compact(self, *args):
        """Makes the row compact."""
        self.add_css_class('compact')
        self.get_first_child().set_orientation(Gtk.Orientation.VERTICAL)
        self.tag_selector.set_hexpand(True)
        self.value_entry.set_hexpand(True)

    def make_noncompact(self, *args):
        """Makes the row non-compact."""
        self.remove_css_class('compact')
        self.get_first_child().set_orientation(Gtk.Orientation.HORIZONTAL)
        self.tag_selector.set_hexpand(False)
        self.value_entry.set_hexpand(False)

class EartagExtraTagsExpander(Adw.ExpanderRow):
    """
    Used for the "More tags" row in the FileView.
    """
    __gtype_name__ = 'EartagExtraTagsExpander'

    def __init__(self):
        super().__init__()
        self.set_title(_('More tags'))
        self._rows = []
        self.bound_files = []
        self.bound_file_ids = []
        self.skip_filter_change = False
        self._blocked_tags_cached = []
        self._present_tags_cached = []
        self._last_loaded_filetypes = []
        self._last_present_tags = {} # id: tags

        # We can select multiple files of multiple types at once, but
        # they're not guaranteed to all have the same available extra tags.
        # Thus, we assemble a list of "blocked tags" to ignore based on
        # bound files. A list of these tags can be received by calling the
        # get_blocked_tags method.
        self.blocked_tags = {}      # type: tags
        self.loaded_filetypes = {}  # type: count

        # Initialize an initial "none" row
        self.add_empty_row()

    def get_rows_sorted(self):
        rows = {}
        for row in self._rows:
            rows[row.bound_property] = row
        return rows

    #
    # Row management functions
    #

    def add_empty_row(self, *args):
        self.add_extra_row('none', skip_adding_none=True)

    def refresh_none_row(self):
        """Adds a 'none' row if needed, and moves it to the end."""
        rows = self.get_rows_sorted()
        if 'none' in rows:
            self.remove(rows['none'])
            self.add_row(rows['none'])
        else:
            self.add_empty_row()

    def add_extra_row(self, tag, skip_adding_none=False):
        """
        Adds an extra row for the given tag. Consumers should make sure that
        a row with this tag doesn't exist yet.

        Returns the newly created row.
        """
        rows = self.get_rows_sorted()
        if tag in rows:
            return None

        row = EartagExtraTagRow(tag, self)
        self._rows.append(row)
        self.add_row(row)

        for file in self.bound_files:
            row.bind_to_file(file)

        # Update row item filters
        if not self.skip_filter_change:
            for row in self._rows:
                row.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

        row.value_entry.set_sensitive(not tag == 'none')
        row.row_remove_button.set_sensitive(not tag == 'none')

        # Move "none" row to the end
        if not skip_adding_none and tag != 'none':
            self.refresh_none_row()

    def remove_extra_row(self, row, skip_adding_none=False):
        """
        Removes a 'more tags' row from the fileview.
        """
        if row not in self._rows:
            return

        self._rows.remove(row)

        for file in set(row.files + self.bound_files):
            row.unbind_from_file(file)

        self.remove(row)

        # Update row item filters
        if not self.skip_filter_change:
            for row in self._rows:
                row.tag_filter.changed(Gtk.FilterChange.DIFFERENT)

        # Move "none" row to the end
        if not skip_adding_none:
            self.refresh_none_row()

        del row

    def remove_and_unbind_extra_row(self, row, skip_adding_none=False):
        """
        Removes a 'more tags' row from the fileview. Used in the callback
        function of the rows' delete button.
        """
        removed_tag = row.value_entry.bound_property
        if removed_tag != 'none':
            for file in self.bound_files:
                if removed_tag in file.present_extra_tags:
                    file.present_extra_tags.remove(removed_tag)
                    file.delete_tag(removed_tag)

        self.remove_extra_row(row, skip_adding_none=skip_adding_none)

    #
    # File handling functions
    #

    def get_blocked_tags(self):
        """
        Shorthand to get a list of all blocked tags in opened files.
        """
        if self._last_loaded_filetypes != list(self.loaded_filetypes.keys()):
            self._last_loaded_filetypes = list(self.loaded_filetypes.keys())
            self._blocked_tags_cached = []
            for filetype, blocklist in self.blocked_tags.items():
                if filetype not in self.loaded_filetypes:
                    continue
                for tag in blocklist:
                    if tag not in self._blocked_tags_cached:
                        self._blocked_tags_cached.append(tag)

            for row in self._rows:
                row.refresh_filter()
        return self._blocked_tags_cached

    def get_present_tags(self):
        """
        Shorthand to get a list of all present tags in opened files.

        This is only used in bind_to_file and unbind_from_file to add/prune
        newly used/unused entries; for most other cases, you'll likely want
        self.get_rows_sorted().keys() instead.
        """
        blocked_tags = self.get_blocked_tags()
        last_present_ids = list(self._last_present_tags.keys())
        if last_present_ids != self.bound_file_ids:
            removed_files = set(last_present_ids) - set(self.bound_file_ids)
            added_files = set(self.bound_file_ids) - set(last_present_ids)

            for fid in removed_files:
                del self._last_present_tags[fid]

            # TODO: this is kinda slow, since we need to iterate over all files
            # to find the ones with a given ID. Experiment with some ways to
            # get a file by ID.
            for fid in added_files:
                for file in self.bound_files:
                    if file.id == fid:
                        break
                self._last_present_tags[fid] = file.present_extra_tags

            self._present_tags_cached = []
            for taglist in self._last_present_tags.values():
                for tag in taglist:
                    if tag not in self._present_tags_cached and \
                            tag not in blocked_tags:
                        self._present_tags_cached.append(tag)

        return self._present_tags_cached

    def refresh_present_tags(self):
        """
        Like the update function of get_present_tags, but handles only
        existing files, and checks for changes in present extra tags.
        """
        blocked_tags = self.get_blocked_tags()

        for file in self.bound_files:
            self._last_present_tags[file.id] = file.present_extra_tags

        self._present_tags_cached = []
        for taglist in self._last_present_tags.values():
            for tag in taglist:
                if tag not in self._present_tags_cached and \
                        tag not in blocked_tags:
                    self._present_tags_cached.append(tag)

    def refresh_entries(self, old_blocked_tags=None):
        """Adds missing entries and removes unused ones."""
        blocked_tags = self.get_blocked_tags()
        present_tags = self.get_present_tags()

        for tag, row in self.get_rows_sorted().items():
            if tag in blocked_tags or tag not in present_tags:
                self.remove_extra_row(row, skip_adding_none=True)

        for tag in present_tags:
            if tag not in self._rows:
                self.add_extra_row(tag, skip_adding_none=True)

        if old_blocked_tags is not None and old_blocked_tags != blocked_tags:
            found_tags = []
            for tag in set(old_blocked_tags) - set(blocked_tags):
                for file in self.bound_files:
                    if tag in file.present_extra_tags:
                        found_tags.append(tag)
                        break
                if tag in found_tags:
                    continue
            for tag in found_tags:
                self.add_extra_row(tag, skip_adding_none=True)

        self.refresh_none_row()

    def slow_refresh_entries(self):
        """Like refresh_entries, but forces an update of present tags."""
        self.refresh_present_tags()
        self.refresh_entries()

    def bind_to_file(self, file, skip_refresh_entries=False):
        if file in self.bound_files:
            return

        self.skip_filter_change = True
        self.bound_files.append(file)
        self.bound_file_ids.append(file.id)

        if not skip_refresh_entries:
            blocked_tags_before_unbind = self.get_blocked_tags()
        filetype = file.__gtype_name__
        if filetype not in self.loaded_filetypes:
            self.loaded_filetypes[filetype] = 1

            # We don't remove this later on purpose - this information is
            # cached inside of this class for future reference.
            if filetype not in self.blocked_tags:
                self.blocked_tags[filetype] = []
                for tag in set(EXTRA_TAGS) - set(file.supported_extra_tags):
                    self.blocked_tags[filetype].append(tag)
        else:
            self.loaded_filetypes[filetype] += 1

        for row in self._rows:
            row.bind_to_file(file)

        row_tags = self.get_rows_sorted().keys()
        for tag in file.present_extra_tags:
            if tag not in row_tags:
                self.add_extra_row(tag)

        # Add/remove entries
        if not skip_refresh_entries:
            self.refresh_entries(old_blocked_tags=blocked_tags_before_unbind)

        self.skip_filter_change = False

    def unbind_from_file(self, file, skip_refresh_entries=False):
        if file not in self.bound_files:
            return

        filetype = file.__gtype_name__
        if filetype in self.loaded_filetypes:
            self.loaded_filetypes[filetype] -= 1

            if self.loaded_filetypes[filetype] == 0:
                del self.loaded_filetypes[filetype]

                for tag in set(EXTRA_TAGS) - set(file.supported_extra_tags):
                    if tag in self.blocked_tags:
                        self.blocked_tags.remove(tag)

        for row in self._rows:
            row.unbind_from_file(file)
        if not skip_refresh_entries:
            blocked_tags_before_unbind = self.get_blocked_tags()
        self.skip_filter_change = True
        self.bound_file_ids.remove(file.id)
        self.bound_files.remove(file)

        # Add/remove entries
        if not skip_refresh_entries:
            self.refresh_entries(old_blocked_tags=blocked_tags_before_unbind)

        self.skip_filter_change = False

class EartagFileInfoLabel(Gtk.Label):
    """Label showing information about opened files."""
    __gtype_name__ = 'EartagFileInfoLabel'

    def __init__(self):
        super().__init__()
        self.add_css_class('dim-label')
        self.add_css_class('numeric')
        self._files = []
        self.refresh_label()

    def bind_to_file(self, file):
        self._files.append(file)
        # Call refresh_label once all files are bound

    def unbind_from_file(self, file):
        self._files.remove(file)
        # Call refresh_label once all files are unbound

    def refresh_label(self):
        if len(self._files) == 0:
            self.set_label('')
        elif len(self._files) == 1:
            self._set_info_label(self._files[0])
        else:
            self.set_label(_('(Multiple files selected)'))

    def _set_info_label(self, file):
        length_readable = get_readable_length(int(file.length))

        # Get human-readable version of channel count
        channels = file.channels
        if channels == 0:
            channels_readable = 'N/A'
        elif channels == 1:
            channels_readable = 'Mono'
        elif channels == 2:
            channels_readable = 'Stereo'
        else:
            channels_readable = gettext.ngettext("1 channel", "{n} channels", channels).format(n=channels) # noqa: E501

        if file.bitrate > -1:
            bitrate_readable = str(file.bitrate)
        else:
            bitrate_readable = "N/A"

        self.set_label('{length} • {bitrate} kbps • {channels} • {filetype}'.format(
            filetype=file.filetype,
            length=length_readable,
            bitrate=bitrate_readable,
            channels=channels_readable
        ))

@Gtk.Template(resource_path='/app/drey/EarTag/ui/fileview.ui')
class EartagFileView(Gtk.Stack):
    __gtype_name__ = 'EartagFileView'

    loading = Gtk.Template.Child()
    content_stack = Gtk.Template.Child()
    content_scroll = Gtk.Template.Child()
    select_file = Gtk.Template.Child()

    important_data_container = Gtk.Template.Child()
    tag_list = Gtk.Template.Child()

    album_cover = Gtk.Template.Child()
    title_entry = Gtk.Template.Child()
    artist_entry = Gtk.Template.Child()
    file_info = Gtk.Template.Child()
    tracknumber_entry = Gtk.Template.Child()
    album_entry = Gtk.Template.Child()
    albumartist_entry = Gtk.Template.Child()
    genre_entry = Gtk.Template.Child()
    releasedate_entry = Gtk.Template.Child()
    comment_entry = Gtk.Template.Child()
    more_tags_expander = Gtk.Template.Child()

    previous_file_button_revealer = Gtk.Template.Child()
    next_file_button_revealer = Gtk.Template.Child()
    previous_file_button = Gtk.Template.Child()
    next_file_button = Gtk.Template.Child()

    writable = False
    bound_files = []

    def __init__(self):
        """Initializes the EartagFileView."""
        super().__init__()

        self.bindable_entries = (self.album_cover, self.title_entry, self.artist_entry,
            self.tracknumber_entry, self.album_entry, self.albumartist_entry,
            self.genre_entry, self.releasedate_entry, self.comment_entry,
            self.file_info)

        self.previous_fileview_width = 0

    def set_file_manager(self, file_manager):
        self.file_manager = file_manager
        self.file_manager.connect('refresh-needed', self.update_binds)
        self.file_manager.connect('selection-changed', self.update_binds)
        self.file_manager.connect('selection-override', self.update_binds)
        self.file_manager.load_task.connect('notify::progress', self.update_loading)
        self.file_manager.connect('notify::has-error', self.update_error)

        sidebar = self.get_native().sidebar
        self.next_file_button.connect('clicked', sidebar.select_next)
        self.previous_file_button.connect('clicked', sidebar.select_previous)
        sidebar.connect('notify::selection-mode', self.update_buttons)

    def update_error(self, *args):
        # Currently this is only used by the releasedate entry. Expand this
        # when needed.
        if self.file_manager.has_error:
            self.releasedate_entry.add_css_class('error')
        else:
            self.releasedate_entry.remove_css_class('error')

    # TODO: rewrite this to use Adw.Breakpoint once libadwaita 1.4 is available
    def setup_resize_handler(self, *args):
        # There's no easy way to call a function whenever a singular widget is resized,
        # so we just call this on resize changes:
        surface = self.get_native().get_surface()
        surface.connect('layout', self.handle_resize)
        self.handle_resize()

    def handle_resize(self, *args):
        fileview_width = self.get_width()
        if fileview_width == self.previous_fileview_width:
            return
        if fileview_width <= 430:
            for entry in self.more_tags_expander._rows:
                entry.make_compact()
        else:
            for entry in self.more_tags_expander._rows:
                entry.make_noncompact()
        self.previous_fileview_width = fileview_width
    # ENDTODO

    def update_loading(self, task, *args):
        if task.progress == 0:
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
        self.update_buttons()

        # Get list of selected (added)/unselected (removed) files
        added_files = [file for file in self.file_manager.selected_files
            if file not in self.bound_files]
        removed_files = [file for file in self.bound_files
            if file not in self.file_manager.selected_files]

        # Handle added and removed files
        self._unbind_files(removed_files)
        self._bind_files(added_files)

        # Make save/fields sensitive/insensitive based on whether selected files are
        # all writable
        has_unwritable = False
        for file in self.file_manager.selected_files:
            if not file.is_writable:
                has_unwritable = True
                break

        if has_unwritable:
            self.album_cover.set_sensitive(False)
            self.important_data_container.set_sensitive(False)
            self.tag_list.set_sensitive(False)
        else:
            self.album_cover.set_sensitive(True)
            self.important_data_container.set_sensitive(True)
            self.tag_list.set_sensitive(True)

        # Scroll to the top of the view
        adjust = self.content_scroll.get_vadjustment()
        adjust.set_value(adjust.get_lower())

    def _bind_files(self, files):
        """Binds a file to the fileview. Used internally in update_binds."""
        if not files:
            return

        old_blocked_tags = self.more_tags_expander.get_blocked_tags()
        for file in files:
            if file in self.bound_files:
                continue
            self.bound_files.append(file)

            for entry in self.bindable_entries:
                entry.bind_to_file(file)

            self.more_tags_expander.bind_to_file(file, skip_refresh_entries=True)
        self.more_tags_expander.refresh_entries(old_blocked_tags=old_blocked_tags)

        self.file_info.refresh_label()

    def _unbind_files(self, files):
        """Unbinds a file from the fileview. Used internally in update_binds."""
        if not files:
            return

        old_blocked_tags = self.more_tags_expander.get_blocked_tags()
        for file in files:
            if file not in self.bound_files:
                continue
            self.bound_files.remove(file)

            for entry in self.bindable_entries:
                entry.unbind_from_file(file)

            self.more_tags_expander.unbind_from_file(file, skip_refresh_entries=True)
        self.more_tags_expander.refresh_entries(old_blocked_tags=old_blocked_tags)

        self.file_info.refresh_label()
