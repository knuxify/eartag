# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from .backends.file import EartagFile, BASIC_TAGS, EXTRA_TAGS, TAG_NAMES, CoverType
from .utils import get_readable_length, file_is_sandboxed
from .utils.validation import is_valid_image_file
from .utils.widgets import EartagAlbumCoverImage, EartagPopoverButton  # noqa: F401
from .tagentry import (  # noqa: F401
    EartagTagEntry,
    EartagTagEntryRow,
    EartagTagEditableLabel,
)
from . import APP_GRESOURCE_PATH

from gi.repository import Adw, Gtk, Gdk, Gio, GLib, GObject

import gettext
import magic
import mimetypes
import shutil
import os.path


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/albumcoverbutton.ui")
class EartagAlbumCoverButton(Adw.Bin):
    __gtype_name__ = "EartagAlbumCoverButton"

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
        self.cover_tempdir = None

        self.connect("destroy", self.on_destroy)
        self.drop_target = Gtk.DropTarget(
            actions=Gdk.DragAction.COPY,
            formats=Gdk.ContentFormats.new_for_gtype(Gio.File),
        )

        self.drop_target.connect("accept", self.on_drag_accept)
        self.drop_target.connect("enter", self.on_drag_hover)
        self.drop_target.connect("leave", self.on_drag_unhover)
        self.drop_target.connect("drop", self.on_drag_drop)
        self.add_controller(self.drop_target)

        self.hover_controller = Gtk.EventControllerMotion.new()
        self.hover_controller.connect("enter", self.on_hover)
        self.hover_controller.connect("leave", self.on_unhover)
        self.add_controller(self.hover_controller)

        self.front_toggle.connect("notify::active", self.update_from_switcher)
        self.front_toggle.set_active(True)

        self.cover_image.connect(
            "cover-changed", self.update_coverbutton_save_availability
        )
        self.cover_image.connect(
            "notify::cover-type", self.update_coverbutton_save_availability
        )
        self.cover_image.connect(
            "notify::is-empty", self.update_coverbutton_save_availability
        )

        self.bind_property("cover-type", self.cover_image, "cover-type")

        # Register actions for popover menu
        self.install_action("albumcoverbutton.load", None, self.show_cover_file_chooser)
        self.install_action("albumcoverbutton.save", None, self.save_cover)
        self.action_set_enabled("albumcoverbutton.save", False)
        self.install_action("albumcoverbutton.remove", None, self.remove_cover)

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
            cover = "front_cover"
        else:
            cover = "back_cover"

        self.action_set_enabled("albumcoverbutton.save", not self.cover_image.is_empty)

        enable_remove = False
        for file in self.files:
            if not getattr(file, cover).is_empty():
                enable_remove = True
            break

        self.action_set_enabled("albumcoverbutton.remove", enable_remove)

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
                if self.files[0].supports_album_covers and self.files[0].get_cover(
                    self.cover_type
                ):
                    self.cover_image.bind_to_file(self.files[0])

        elif len(self.files) == 1:
            self.cover_image.bind_to_file(self.files[0])
            self.cover_image.on_cover_change()

    def on_destroy(self, *args):
        self.files = None
        if self.cover_tempdir:
            self.cover_tempdir.cleanup()
            self.cover_tempdir = None

    def show_cover_file_chooser(self, *args):
        """Shows the file chooser."""
        file_chooser = Gtk.FileDialog(title=_("Select Album Cover Image"), modal=True)
        _cancellable = Gio.Cancellable.new()

        _filters = Gio.ListStore.new(Gtk.FileFilter)
        _filters.append(self.image_file_filter)
        file_chooser.set_filters(_filters)

        file_chooser.open(
            self.get_native(), _cancellable, self.open_cover_file_from_dialog
        )

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
                file.notify("front-cover-path")
        elif self.cover_type == CoverType.BACK:
            for file in self.files:
                file.back_cover_path = response.get_path()
                file.notify("back-cover-path")

        self.cover_image.on_cover_change()

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

        file_chooser = Gtk.FileDialog(
            title=_("Save Album Cover To…"),
            modal=True,
            initial_folder=Gio.File.new_for_path(target_folder),
            initial_name=target_filename,
        )
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

        # TRANSLATORS: {path} is a placeholder for the path.
        # **Do not change the text between the curly brackets!**
        toast = Adw.Toast.new(_("Saved cover to {path}").format(path=save_path))
        self.get_native().toast_overlay.add_toast(toast)

    def remove_cover(self, *args):
        self._remove_undo_budder = {}
        self._remove_undo_buffer["type"] = self.cover_type

        if self.cover_type == CoverType.FRONT:
            cover_path_prop = "front_cover_path"
        elif self.cover_type == CoverType.BACK:
            cover_path_prop = "back_cover_path"

        for file in self.files:
            cover_path = file.get_property(cover_path_prop)
            cover_is_modified = cover_path_prop in file.modified_tags
            self._remove_undo_buffer[file.id] = (
                cover_path,
                cover_path,
                cover_is_modified,
            )
            file.delete_cover(self.cover_type)

        self.cover_image.on_cover_change()

        remove_msg = gettext.ngettext(
            "Removed cover from file", "Removed covers from {n} files", len(self.files)
        ).format(n=len(self.files))
        toast = Adw.Toast.new(remove_msg)
        toast.set_button_label(_("Undo"))
        toast.connect("button-clicked", self._remove_undo)
        toast.connect("dismissed", self._remove_undo_clear)
        self.get_native().toast_overlay.add_toast(toast)

    def _remove_undo(self, *args):
        if self._remove_undo_buffer["type"] == CoverType.FRONT:
            cover_path_prop = "front_cover_path"
        elif self._remove_undo_buffer["type"] == CoverType.BACK:
            cover_path_prop = "back_cover_path"

        file_manager = self.get_native().file_manager
        for file in file_manager.files:
            if file.id not in self._remove_undo_buffer:
                continue
            file.set_property(cover_path_prop, self._remove_undo_buffer[file.id][1])
            was_modified = self._remove_undo_buffer[file.id][2]
            if was_modified:
                file.mark_as_modified(cover_path_prop)
            else:
                file.mark_tag_as_unmodified(cover_path_prop)

        self.cover_image.on_cover_change()

        self._remove_undo_buffer = {}

    def _remove_undo_clear(self, *args):
        if "type" not in self._remove_undo_buffer:
            return

        self._remove_undo_buffer = {}

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
                file.notify("front-cover-path")
        elif self.cover_type == CoverType.BACK:
            for file in self.files:
                file.back_cover_path = path
                file.notify("back-cover-path")
        self.cover_image.on_cover_change()
        self.on_drag_unhover()

    # Hover
    def on_hover(self, *args):
        if not self.handling_drag and not self.handling_undefined_drag:
            self.highlight_stack.set_visible_child(self.hover_highlight)
            self.highlight_revealer.set_reveal_child(True)

    def on_unhover(self, *args):
        self.highlight_revealer.set_reveal_child(False)


extra_tag_names = dict(
    [(k, v) for k, v in TAG_NAMES.items() if k in ["none"] + list(EXTRA_TAGS)]
)
extra_tag_names_swapped = dict([(v, k) for k, v in extra_tag_names.items()])
more_item_tag_strings = Gtk.StringList.new(list(extra_tag_names.values()))


class EartagExtraTagRow(EartagTagEntryRow):
    __gtype_name__ = "EartagExtraTagRow"

    def __init__(self, tag, parent):
        super().__init__()
        self.parent = parent

        self.bound_property = tag
        self.is_numeric = tag in EartagFile.int_properties
        self.is_float = tag in EartagFile.float_properties
        self.set_title(extra_tag_names[tag])

        self.row_remove_button = Gtk.Button(
            icon_name="edit-delete-symbolic", valign=Gtk.Align.CENTER
        )
        self.row_remove_button.add_css_class("flat")
        self.row_remove_button.connect("clicked", self.do_remove_row)
        self.add_suffix(self.row_remove_button)

    def do_remove_row(self, *args):
        """Removes the row."""
        self.parent.remove_and_unbind_extra_row(self)


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/moretagsgroup.ui")
class EartagMoreTagsGroup(Gtk.Box):
    """
    Used for the "More tags" row in the FileView.
    """

    __gtype_name__ = "EartagMoreTagsGroup"

    tag_entry_listbox = Gtk.Template.Child()
    tag_selector = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        # self.set_title(_('More tags'))
        self._rows = []
        self.bound_files = []
        self.bound_file_ids = []
        self.skip_filter_change = False
        self._blocked_tags_cached = []
        self._present_tags_cached = []
        self._last_loaded_filetypes = []
        self._last_present_tags = {}  # id: tags
        self._ignore_tag_selector = False

        # We can select multiple files of multiple types at once, but
        # they're not guaranteed to all have the same available extra tags.
        # Thus, we assemble a list of "blocked tags" to ignore based on
        # bound files. A list of these tags can be received by calling the
        # get_blocked_tags method.
        self.blocked_tags = {}  # type: tags
        self.loaded_filetypes = {}  # type: count

        self.tag_filter = Gtk.CustomFilter.new(
            self.tag_filter_func, self.tag_selector.tag_model
        )
        self.tag_selector.set_filter(self.tag_filter)

    def get_rows_sorted(self):
        rows = {}
        for row in self._rows:
            rows[row.bound_property] = row
        return rows

    # "Add additional tag" field

    def refresh_tag_filter(self, *args):
        """Refreshes the filter for the additional tag add row."""
        self.tag_filter.changed(Gtk.FilterChange.DIFFERENT)
        self.tag_entry_listbox.props.visible = bool(
            [i for i in self.get_rows_sorted().keys() if i in EXTRA_TAGS]
        )

    @Gtk.Template.Callback()
    def add_row_from_selector(self, selector, tag):
        """Adds a new row based on the tag selector."""
        self.add_extra_row(tag)

    def tag_filter_func(self, _tag_name, *args):
        """Filter function for the tag dropdown."""
        if not self.tag_selector.tag_filter_func(_tag_name):
            return False

        present_tags = list(self.get_rows_sorted().keys())

        tag_name = _tag_name.get_string()
        tag_prop = self.tag_selector.tag_names_swapped[tag_name]

        if tag_prop in ("length", "bitrate") + BASIC_TAGS:
            return False
        if tag_prop == "none":
            return False
        if tag_prop in present_tags:
            return False
        if tag_prop in self.get_blocked_tags():
            return False

        return True

    #
    # Row management functions
    #

    def add_extra_row(self, tag, skip_filter_refresh=False):
        """
        Adds an extra row for the given tag. Consumers should make sure that
        a row with this tag doesn't exist yet.

        Returns the newly created row.
        """
        rows = self.get_rows_sorted()
        if tag in rows:
            return None

        row = EartagExtraTagRow(tag, self)
        row.set_title(extra_tag_names[tag])
        self._rows.append(row)
        self.tag_entry_listbox.append(row)

        if tag not in self._present_tags_cached:
            self._present_tags_cached.append(tag)

        for file in self.bound_files:
            row.bind_to_file(file)

        if not skip_filter_refresh:
            self.refresh_tag_filter()

    def remove_extra_row(self, row, skip_filter_refresh=False):
        """
        Removes a 'more tags' row from the fileview.
        """
        if row not in self._rows:
            return

        self._rows.remove(row)

        for file in set(row.files + self.bound_files):
            row.unbind_from_file(file)

        if row.bound_property in self._present_tags_cached:
            self._present_tags_cached.remove(row.bound_property)

        self.tag_entry_listbox.remove(row)

        if not skip_filter_refresh:
            self.refresh_tag_filter()

    def remove_and_unbind_extra_row(self, row, skip_filter_refresh=False):
        """
        Removes a 'more tags' row from the fileview. Used in the callback
        function of the rows' delete button.
        """
        removed_tag = row.bound_property
        if removed_tag != "none":
            for file in self.bound_files:
                if removed_tag in file.present_extra_tags:
                    file.present_extra_tags.remove(removed_tag)
                    file.delete_tag(removed_tag)

        self.remove_extra_row(row, skip_filter_refresh=skip_filter_refresh)

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

            self.refresh_tag_filter()

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
                    if tag not in self._present_tags_cached and tag not in blocked_tags:
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
                if tag not in self._present_tags_cached and tag not in blocked_tags:
                    self._present_tags_cached.append(tag)

        self.refresh_tag_filter()

    def refresh_entries(self, old_blocked_tags=None):
        """Adds missing entries and removes unused ones."""
        blocked_tags = self.get_blocked_tags()
        present_tags = self.get_present_tags()

        for tag, row in self.get_rows_sorted().items():
            if tag in blocked_tags or tag not in present_tags:
                self.remove_extra_row(row, skip_filter_refresh=True)

        for tag in present_tags:
            if tag not in self._rows:
                self.add_extra_row(tag, skip_filter_refresh=True)

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
                self.add_extra_row(tag, skip_filter_refresh=True)

        self.refresh_tag_filter()

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

    __gtype_name__ = "EartagFileInfoLabel"

    def __init__(self):
        super().__init__()
        self.add_css_class("dim-label")
        self.add_css_class("numeric")
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
            self.set_label("")
        elif len(self._files) == 1:
            self._set_info_label(self._files[0])
        else:
            self.set_label(_("(Multiple files selected)"))

    def _set_info_label(self, file):
        length_readable = get_readable_length(int(file.length))

        # Get human-readable version of channel count
        channels = file.channels
        if channels == 0:
            channels_readable = "N/A"
        elif channels == 1:
            channels_readable = "Mono"
        elif channels == 2:
            channels_readable = "Stereo"
        else:
            channels_readable = gettext.ngettext(
                "1 channel", "{n} channels", channels
            ).format(
                n=channels
            )  # noqa: E501

        if file.bitrate > -1:
            bitrate_readable = str(file.bitrate)
        else:
            bitrate_readable = "N/A"

        self.set_label(
            "{length} • {bitrate} kbps • {channels} • {filetype}".format(
                filetype=file.filetype,
                length=length_readable,
                bitrate=bitrate_readable,
                channels=channels_readable,
            )
        )


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/filenamerow.ui")
class EartagFilenameRow(Adw.EntryRow):
    __gtype_name__ = "EartagFilenameRow"

    error = GObject.Property(type=bool, default=False)

    def __init__(self):
        super().__init__()
        self._files = []
        self._connections = {}
        self._title = self.props.title
        self.get_delegate().connect("insert-text", self.validate_input)

    def bind_to_file(self, file):
        self._files.append(file)
        self._connections[file.id] = file.connect("notify::path", self.update_on_bind)
        self.update_on_bind()

    def unbind_from_file(self, file):
        file.disconnect(self._connections[file.id])
        del self._connections[file.id]
        self._files.remove(file)
        self.update_on_bind()

    def update_on_bind(self, *args):
        if len(self._files) > 1:
            self.props.title = self._title + " " + _("(multiple files)")
            self.set_editable(False)
            self.props.show_apply_button = False
            self.set_text("")
        elif len(self._files) == 1:
            path = self._files[0].path
            self.props.title = self._title
            self.set_editable(not file_is_sandboxed(path))
            self.props.show_apply_button = True
            self.set_text(os.path.basename(path))
        else:
            self.props.title = self._title
            self.set_editable(False)
            self.props.show_apply_button = False
            self.set_text("")

    @Gtk.Template.Callback()
    def set_filename(self, *args):
        if len(self._files) != 1:
            return
        old_path = self._files[0].path
        self.get_native().file_manager.rename_files(
            (self._files[0],),
            (os.path.join(os.path.dirname(old_path), self.get_text()),),
        )

    def validate_input(self, entry, text, length, position, *args):
        if "/" in text:
            GObject.signal_stop_emission_by_name(entry, "insert-text")


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/fileview.ui")
class EartagFileView(Gtk.Stack):
    __gtype_name__ = "EartagFileView"

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
    totaltracknumber_entry = Gtk.Template.Child()
    album_entry = Gtk.Template.Child()
    albumartist_entry = Gtk.Template.Child()
    genre_entry = Gtk.Template.Child()
    releasedate_entry = Gtk.Template.Child()
    comment_entry = Gtk.Template.Child()
    filename_entry = Gtk.Template.Child()
    more_tags_group = Gtk.Template.Child()

    previous_file_button_revealer = Gtk.Template.Child()
    next_file_button_revealer = Gtk.Template.Child()
    previous_file_button = Gtk.Template.Child()
    next_file_button = Gtk.Template.Child()

    writable = False
    bound_files = []

    def __init__(self):
        """Initializes the EartagFileView."""
        super().__init__()

        self.bindable_entries = (
            self.album_cover,
            self.title_entry,
            self.artist_entry,
            self.tracknumber_entry,
            self.totaltracknumber_entry,
            self.album_entry,
            self.albumartist_entry,
            self.genre_entry,
            self.releasedate_entry,
            self.comment_entry,
            self.filename_entry,
            self.file_info,
        )

        self.previous_fileview_width = 0

    def on_close(self):
        self.album_cover.on_destroy()

    def set_file_manager(self, file_manager):
        self.file_manager = file_manager
        self.file_manager.connect("refresh-needed", self.update_binds)
        self.file_manager.connect("selection-changed", self.update_binds)
        self.file_manager.load_task.connect("notify::progress", self.update_loading)
        self.file_manager.connect("notify::has-error", self.update_error)

        window = self.get_native()
        self.next_file_button.connect("clicked", window.select_next)
        self.previous_file_button.connect("clicked", window.select_previous)
        window.connect("notify::selection-mode", self.update_buttons)

    def update_error(self, *args):
        # Currently this is only used by the releasedate entry. Expand this
        # when needed.
        if self.file_manager.has_error:
            self.releasedate_entry.add_css_class("error")
        else:
            self.releasedate_entry.remove_css_class("error")

    def update_loading(self, task, *args):
        if task.progress == 0:
            self.set_visible_child(self.content_stack)
        else:
            self.set_visible_child(self.loading)

    def update_buttons(self, *args):
        """Updates the side switcher button state."""
        if len(self.file_manager.files) == 0 or self.get_native().selection_mode:
            self.previous_file_button.set_sensitive(False)
            self.previous_file_button_revealer.set_reveal_child(False)
            self.next_file_button.set_sensitive(False)
            self.next_file_button_revealer.set_reveal_child(False)
        else:
            if self.file_manager.selected_files.get_n_items() > 1:
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
        added_files = [
            file
            for file in self.file_manager.selected_files_list
            if file not in self.bound_files
        ]
        removed_files = [
            file for file in self.bound_files if not self.file_manager.is_selected(file)
        ]

        # Handle added and removed files
        self._unbind_files(removed_files)
        self._bind_files(added_files)

        # Make save/fields sensitive/insensitive based on whether selected files are
        # all writable
        has_unwritable = False
        for file in self.file_manager.selected_files_list:
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

        old_blocked_tags = self.more_tags_group.get_blocked_tags()
        for file in files:
            if file in self.bound_files:
                continue
            self.bound_files.append(file)

            for entry in self.bindable_entries:
                entry.bind_to_file(file)

            self.more_tags_group.bind_to_file(file, skip_refresh_entries=True)
        self.more_tags_group.refresh_entries(old_blocked_tags=old_blocked_tags)

        self.file_info.refresh_label()

    def _unbind_files(self, files):
        """Unbinds a file from the fileview. Used internally in update_binds."""
        if not files:
            return

        old_blocked_tags = self.more_tags_group.get_blocked_tags()
        for file in files:
            if file not in self.bound_files:
                continue
            self.bound_files.remove(file)

            for entry in self.bindable_entries:
                entry.unbind_from_file(file)

            self.more_tags_group.unbind_from_file(file, skip_refresh_entries=True)
        self.more_tags_group.refresh_entries(old_blocked_tags=old_blocked_tags)

        self.file_info.refresh_label()

    @GObject.Property(type=bool, default=False)
    def compact(self):
        return self.more_tags_group.compact

    @compact.setter
    def compact(self, value):
        self.more_tags_group.compact = value
