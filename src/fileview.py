# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from .backends import FILE_CLASSES
from .backends.file import EartagFile, BASIC_TAGS, EXTRA_TAGS, TAG_NAMES, CoverType
from .logger import logger
from .utils import get_readable_length, file_is_sandboxed
from .utils.validation import is_valid_image_file
from .utils.widgets import EartagAlbumCoverImage, EartagPopoverButton  # noqa: F401
from .tagentry import (  # noqa: F401
    EartagTagEntryManager,
    EartagTagEntry,
    EartagTagEntryRow,
    EartagTagEditableLabel,
)
from . import APP_GRESOURCE_PATH

from gi.repository import Adw, Gtk, Gdk, Gio, GLib, GObject

import asyncio
from functools import cached_property
import mimetypes
import traceback
import os.path

from collections.abc import Iterable


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

        self.cover_image.connect("cover-changed", self.update_coverbutton_save_availability)
        self.cover_image.connect("notify::cover-type", self.update_coverbutton_save_availability)
        self.cover_image.connect("notify::is-empty", self.update_coverbutton_save_availability)

        self.bind_property("cover-type", self.cover_image, "cover-type")

        # Register actions for popover menu
        self.install_action("albumcoverbutton.load", None, self.show_cover_file_chooser)
        self.install_action("albumcoverbutton.save", None, self.save_cover)
        self.action_set_enabled("albumcoverbutton.save", False)
        self.install_action("albumcoverbutton.remove", None, self.remove_cover)

        self.files = set()

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
        if self.cover_type == CoverType.FRONT:
            title = _("Album cover (front)")
        else:
            title = _("Album cover (back)")

        Gtk.Accessible.update_property(self, (Gtk.AccessibleProperty.LABEL,), (title,))
        Gtk.Accessible.update_property(self.button, (Gtk.AccessibleProperty.LABEL,), (title,))
        self.button.set_tooltip_text(title)

    def update_coverbutton_save_availability(self, *args):
        if self.cover_type == CoverType.FRONT:
            cover = "front_cover"
        else:
            cover = "back_cover"

        self.action_set_enabled("albumcoverbutton.save", not self.cover_image.is_empty)

        enable_remove = False
        for file in self.files:
            if getattr(file, cover):
                enable_remove = True
                break

        self.action_set_enabled("albumcoverbutton.remove", enable_remove)

    def bind_to_files(self, files):
        self.files |= set(files)

        file = next(iter(self.files))
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

    def unbind_from_files(self, files):
        for file in files:
            if file in self.files:
                self.files.remove(file)

        for _file in self.files:
            if not _file.supports_album_covers:
                self.set_visible(False)
                self.update_coverbutton_save_availability()
                break
            else:
                self.set_visible(True)

        if len(self.files) > 0:
            file = next(iter(self.files))
            if len(self.files) > 1:
                covers_different = False
                our_cover = file.get_cover(self.cover_type)
                for _file in self.files:
                    if _file.get_cover(self.cover_type) != our_cover:
                        covers_different = True
                        self.cover_image.mark_as_empty()
                        break
                if not covers_different:
                    self.cover_image.mark_as_nonempty()
                    if file.supports_album_covers and file.get_cover(self.cover_type):
                        self.cover_image.bind_to_file(file)

            elif len(self.files) == 1:
                self.cover_image.bind_to_file(file)
                self.cover_image.on_cover_change()

    def on_destroy(self, *args):
        self.files = None
        if self.cover_tempdir:
            self.cover_tempdir.cleanup()
            self.cover_tempdir = None

    def show_cover_file_chooser(self, *args):
        asyncio.create_task(self.show_cover_file_chooser_async())

    async def show_cover_file_chooser_async(self):
        """Shows the file chooser."""
        file_chooser = Gtk.FileDialog(title=_("Select Album Cover Image"), modal=True)

        _filters = Gio.ListStore.new(Gtk.FileFilter)
        _filters.append(self.image_file_filter)
        file_chooser.set_filters(_filters)

        try:
            gfile = await file_chooser.open(self.get_native(), None)
        except GLib.GError:
            traceback.print_exc()
            return

        if not gfile:
            return

        for file in self.files:
            try:
                await file.set_cover_from_path(self.cover_type, gfile.get_path())
            except:  # noqa: E722
                logger.error(f"Error while setting cover for file {file}:")
                traceback.print_exc()

        self.cover_image.on_cover_change()

    def save_cover(self, *args):
        asyncio.create_task(self.save_cover_async())

    async def save_cover_async(self):
        """Opens a file dialog to have the cover art to a file."""
        if self.cover_type == CoverType.FRONT:
            cover = self.files[0].front_cover
        elif self.cover_type == CoverType.BACK:
            cover = self.files[0].back_cover
        else:
            return

        cover_extension = mimetypes.guess_extension(cover.mime)
        target_folder, target_filename = os.path.split(self.files[0].path)
        target_filename = os.path.splitext(target_filename)[0] + cover_extension

        file_chooser = Gtk.FileDialog(
            title=_("Save Album Cover To…"),
            modal=True,
            initial_folder=Gio.File.new_for_path(target_folder),
            initial_name=target_filename,
        )

        try:
            response = await file_chooser.save(self.get_native(), None)
        except GLib.GError:
            return

        if not response:
            return

        save_path = response.get_path()

        if cover_extension and not save_path.endswith(cover_extension):
            save_path += cover_extension

        try:
            await cover.save_to_path(save_path)
        except:  # noqa: E722
            logger.error("Failed to save cover:")
            traceback.print_exc()
        else:
            # TRANSLATORS: {path} is a placeholder for the path.
            # **Do not change the text between the curly brackets!**
            toast = Adw.Toast.new(_("Saved cover to {path}").format(path=save_path))
            self.get_native().toast_overlay.add_toast(toast)

    def remove_cover(self, *args):
        self._remove_undo_buffer = {}
        self._remove_undo_buffer["type"] = self.cover_type

        if self.cover_type == CoverType.FRONT:
            cover_prop = "front_cover"
        elif self.cover_type == CoverType.BACK:
            cover_prop = "back_cover"

        for file in self.files:
            cover = file.get_property(cover_prop)
            cover_is_modified = cover_prop in file.modified_tags
            self._remove_undo_buffer[file.id] = [
                cover,
                cover_is_modified,
            ]
            file.delete_cover(self.cover_type)

        self.cover_image.on_cover_change()

        remove_msg = ngettext(
            "Removed cover from file", "Removed covers from {n} files", len(self.files)
        ).format(n=len(self.files))
        toast = Adw.Toast.new(remove_msg)
        toast.set_button_label(_("Undo"))
        toast.connect("button-clicked", self._remove_undo)
        toast.connect("dismissed", self._remove_undo_clear)
        self.get_native().toast_overlay.add_toast(toast)

    def _remove_undo(self, *args):
        asyncio.create_task(self._remove_undo_async())

    async def _remove_undo_async(self):
        if self._remove_undo_buffer["type"] == CoverType.FRONT:
            cover_prop = "front_cover"
        elif self._remove_undo_buffer["type"] == CoverType.BACK:
            cover_prop = "back_cover"
        else:
            return

        file_manager = self.get_native().file_manager
        for file in file_manager.files:
            if file.id not in self._remove_undo_buffer:
                continue
            file.set_property(cover_prop, self._remove_undo_buffer[file.id][0])
            was_modified = self._remove_undo_buffer[file.id][1]
            if was_modified:
                file.mark_as_modified(cover_prop)
            else:
                file.mark_tag_as_unmodified(cover_prop)

        self.cover_image.on_cover_change()

        self._remove_undo_clear()

    def _remove_undo_clear(self, *args):
        if "type" not in self._remove_undo_buffer:
            return

        for k, v in self._remove_undo_buffer.items():
            if k == "type":
                continue
            del v[0]  # Make absolutely sure the covers are unreffed
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
        asyncio.create_task(self.on_drag_drop_async(drop_target, value))

    async def on_drag_drop_async(self, drop_target, value):
        path = value.get_path()
        if not path:
            return
        for file in self.files:
            await file.set_cover_from_path(self.cover_type, path)
        self.cover_image.on_cover_change()
        self.on_drag_unhover()

    # Hover
    def on_hover(self, *args):
        if not self.handling_drag and not self.handling_undefined_drag:
            self.highlight_stack.set_visible_child(self.hover_highlight)
            self.highlight_revealer.set_reveal_child(True)

    def on_unhover(self, *args):
        self.highlight_revealer.set_reveal_child(False)


extra_tag_names = dict([(k, v) for k, v in TAG_NAMES.items() if k in ["none"] + list(EXTRA_TAGS)])
extra_tag_names_swapped = dict([(v, k) for k, v in extra_tag_names.items()])
more_item_tag_strings = Gtk.StringList.new(list(extra_tag_names.values()))


class EartagExtraTagRow(EartagTagEntryRow):
    __gtype_name__ = "EartagExtraTagRow"

    def __init__(self, tag, parent):
        super().__init__()
        self.props.visible = False
        self.parent = parent

        self.bound_property = tag

        self.is_numeric = tag in EartagFile.int_properties
        self.is_float = tag in EartagFile.float_properties

        self.row_remove_button = Gtk.Button(
            icon_name="edit-delete-symbolic", valign=Gtk.Align.CENTER
        )
        self.row_remove_button.props.tooltip_text = _("Remove tag")
        self.row_remove_button.add_css_class("flat")
        self._remove_clicked_connect = self.row_remove_button.connect(
            "clicked", self.remove_button_pressed
        )
        self.add_suffix(self.row_remove_button)

        self._destroy_connect = self.connect("destroy", self._on_destroy)

    @GObject.Property(type=str, default="")
    def bound_property(self):
        try:
            return self._bound_property
        except AttributeError:
            return ""

    @bound_property.setter
    def bound_property(self, value: str):
        self._bound_property = value
        self.set_title(extra_tag_names[value])

    def remove_button_pressed(self, *args):
        self.parent.remove_tag(self.bound_property)

    def _on_destroy(self, *args):
        try:
            self.row_remove_button  # noqa: B018
        except AttributeError:
            return
        self.row_remove_button.disconnect(self._remove_clicked_connect)
        self.disconnect(self._destroy_connect)
        del self.row_remove_button
        del self.parent


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

        self.tagentry_manager = EartagTagEntryManager()

        #: Filetypes bound to this entry (gtype name: count).
        self.filetypes: dict[str, int] = {}

        #: Files bound to this entry.
        self.files: set[EartagFile] = set()

        #: File connections.
        self.file_connections: dict[str, list[int]] = {}

        # Set up allowed tag lists for each filetype. Since different filetypes
        # have different sets of allowed extra tags, we store them in this class
        # and use this information to show/hide certain entries.
        self.allowed_tags_for_filetype: dict[str, Iterable[str]] = {}
        for filetype in FILE_CLASSES:
            self.allowed_tags_for_filetype[filetype.__gtype_name__] = filetype.supported_extra_tags

        #: Entry rows under this group.
        self.entries: dict[str, Gtk.Widget] = {}

        #: All present properties in files, and the IDs of the files that have them.
        #: To get the actually shown properties, check self.tagentry_manager.managed_properties
        #: (since that value excludes blocked tags).
        self.present_props: dict[str, set[str]] = {}

        self.tag_filter = Gtk.CustomFilter.new(self.tag_filter_func, self.tag_selector.tag_model)
        self.tag_selector.set_filter(self.tag_filter)

        # Set up the entries for all extra tags. The entries start out hidden;
        # once they become needed, we show them again. This allows us to
        # avoid having to create/destroy the row objects every time, and is
        # relatively cheap since all entry-related operations are only
        # done in the manager, and only bound to it when shown.

        for tag in EXTRA_TAGS:
            self.entries[tag] = EartagExtraTagRow(tag, self)
            self.tag_entry_listbox.append(self.entries[tag])

    @cached_property
    def blocked_tags(self) -> set[str]:
        """List of tags not allowed for all available filetypes."""
        allowed_types_values = []
        for ftype, values in self.allowed_tags_for_filetype.items():
            if self.filetypes.get(ftype, 0) > 0:
                allowed_types_values.append(values)

        if allowed_types_values:
            allowed_types_intersection = set.intersection(*[set(x) for x in allowed_types_values])
        else:
            allowed_types_intersection = set(EXTRA_TAGS)

        return set(EXTRA_TAGS) - allowed_types_intersection

    # File management

    async def bind_to_files(self, files: Iterable[EartagFile]):
        """Bind to the files in the provided iterable."""
        old_filetypes = set(k for k, v in self.filetypes.items() if v)
        for file in files:
            if file in self.files:
                continue
            self.files.add(file)
            self.file_connections[file.id] = [file.connect("modified", self.on_file_modified)]

            present_extra_tags = set(file.present_extra_tags)

            for tag in present_extra_tags:
                if tag in self.present_props:
                    self.present_props[tag].add(file.id)
                    if len(self.present_props[tag]) == 1:
                        self.show_entry(tag)
                else:
                    self.present_props[tag] = set((file.id,))
                    self.show_entry(tag)

            if file.__gtype_name__ in self.filetypes:
                self.filetypes[file.__gtype_name__] += 1
            else:
                self.filetypes[file.__gtype_name__] = 1
        new_filetypes = set(k for k, v in self.filetypes.items() if v)

        if old_filetypes != new_filetypes:
            # Clear cached blocked tags value
            try:
                del self.blocked_tags
            except AttributeError:
                pass

            # Hide blocked entries
            for tag in set.intersection(
                self.blocked_tags, self.tagentry_manager.managed_properties
            ):
                self.hide_entry(tag)

        await self.tagentry_manager.bind_to_files(files)

    async def unbind_from_files(self, files: Iterable[EartagFile]):
        """Unbind from the files in the provided iterable."""
        old_filetypes = set(k for k, v in self.filetypes.items() if v)
        for file in files:
            if file not in self.files:
                continue
            self.files.remove(file)
            for conn in self.file_connections[file.id]:
                file.disconnect(conn)

            present_extra_tags = set(file.present_extra_tags)

            for tag in present_extra_tags:
                self.present_props[tag].remove(file.id)
                if len(self.present_props[tag]) == 0:
                    del self.present_props[tag]
                    self.hide_entry(tag)
                    self.tagentry_manager.entry_inconsistency[tag] = False

            self.filetypes[file.__gtype_name__] -= 1
        new_filetypes = set(k for k, v in self.filetypes.items() if v)

        if old_filetypes != new_filetypes:
            old_blocked_tags = self.blocked_tags.copy()

            # Clear cached blocked tags value
            try:
                del self.blocked_tags
            except AttributeError:
                pass

            # Unhide blocked entries
            for tag in old_blocked_tags - self.blocked_tags:
                if tag in self.present_props:
                    self.show_entry(tag)

        await self.tagentry_manager.unbind_from_files(files)

    # Entry management

    def show_entry(self, prop: str):
        """Show the extra row for the given property."""
        self.entries[prop].props.visible = True
        self.tagentry_manager.add_entry(prop, self.entries[prop])
        self.refresh_tag_filter()

    def hide_entry(self, prop: str):
        """Hide the extra row for the given property."""
        self.entries[prop].props.visible = False
        self.tagentry_manager.remove_entry(prop)
        self.refresh_tag_filter()

    def remove_tag(self, prop: str):
        """Remove the tag from all open files."""
        for file in self.tagentry_manager.files:
            if prop in file.present_extra_tags:
                file.present_extra_tags.remove(prop)
                file.delete_tag(prop)

    def on_file_modified(self, file: EartagFile, tag: str):
        """Handle a file being modified, in case an extra tag is added/removed."""
        if tag not in EXTRA_TAGS:
            return
        if tag in file.present_extra_tags:
            if tag in self.present_props:
                self.present_props[tag].add(file.id)
            else:
                self.present_props[tag] = set([file.id])
                self.show_entry(tag)
        else:
            if tag in self.present_props and file.id in self.present_props[tag]:
                self.present_props[tag].remove(file.id)
                if len(self.present_props[tag]) == 0:
                    del self.present_props[tag]
                    self.hide_entry(tag)
                    self.tagentry_manager.entry_inconsistency[tag] = False

    # Tag selection dropdown

    @Gtk.Template.Callback()
    def add_row_from_selector(self, selector, tag):
        """Adds a new row based on the tag selector."""
        self.show_entry(tag)
        self.present_props.add(tag)
        self.entries[tag].grab_focus()

    def refresh_tag_filter(self, *args):
        """Refreshes the filter for the additional tag add row."""
        self.tag_filter.changed(Gtk.FilterChange.DIFFERENT)
        self.tag_entry_listbox.props.visible = bool(self.tagentry_manager.managed_properties)

    def tag_filter_func(self, _tag_name, *args):
        """Filter function for the tag dropdown."""
        if not self.tag_selector.tag_filter_func(_tag_name):
            return False

        present_tags = self.tagentry_manager.managed_properties

        tag_name = _tag_name.get_string()
        tag_prop = self.tag_selector.tag_names_swapped[tag_name]

        if tag_prop in ("length", "bitrate") + BASIC_TAGS:
            return False
        if tag_prop == "none":
            return False
        if tag_prop in present_tags:
            return False
        if tag_prop in self.blocked_tags:
            return False

        return True

    # Miscelaneous

    @GObject.Property(type=bool, default=False)
    def height_below_360(self):
        """Hack to fix https://gitlab.gnome.org/World/eartag/-/merge_requests/130"""
        return self._height_below_360

    @height_below_360.setter
    def height_below_360(self, value):
        self._height_below_360 = value
        if value is True:
            self.tag_selector.set_direction(Gtk.ArrowType.UP)
        else:
            self.tag_selector.set_direction(Gtk.ArrowType.DOWN)


class EartagFileInfoLabel(Gtk.Label):
    """Label showing information about opened files."""

    __gtype_name__ = "EartagFileInfoLabel"

    def __init__(self):
        super().__init__()
        self.add_css_class("dim-label")
        self.add_css_class("numeric")
        self.files = set()
        self.refresh_label()

    def bind_to_files(self, files):
        self.files |= set(files)
        self.refresh_label()

    def unbind_from_files(self, files):
        self.files -= set(files)
        self.refresh_label()

    def refresh_label(self):
        if len(self.files) == 0:
            self.set_label("")
        elif len(self.files) == 1:
            self._set_info_label(next(iter(self.files)))
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
            channels_readable = ngettext("1 channel", "{n} channels", channels).format(n=channels)  # noqa: E501

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
        self.files = set()
        self._connections = {}
        self._title = self.props.title
        self.get_delegate().connect("insert-text", self.validate_input)

    def bind_to_files(self, files: Iterable[EartagFile]):
        self.files |= set(files)
        for file in files:
            self._connections[file.id] = file.connect("notify::path", self.update_on_bind)
        self.update_on_bind()

    def unbind_from_files(self, files: Iterable[EartagFile]):
        for file in files:
            if file in self.files:
                file.disconnect(self._connections[file.id])
                del self._connections[file.id]
                self.files.remove(file)
        self.update_on_bind()

    def update_on_bind(self, *args):
        if len(self.files) > 1:
            self.props.title = self._title + " " + _("(multiple files)")
            self.set_editable(False)
            self.props.show_apply_button = False
            self.set_text("")
        elif len(self.files) == 1:
            path = next(iter(self.files)).path
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
        if len(self.files) != 1:
            return
        file = next(iter(self.files))
        old_path = file.path
        self.get_native().file_manager.rename_files(
            (file,),
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
    content_clamp = Gtk.Template.Child()
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

    def __init__(self):
        """Initializes the EartagFileView."""
        super().__init__()

        self.writable = False
        self.files = set()

        self.bindable_entries = (
            self.album_cover,
            self.filename_entry,
            self.file_info,
        )

        self.tagentries = (
            self.title_entry,
            self.artist_entry,
            self.tracknumber_entry,
            self.totaltracknumber_entry,
            self.album_entry,
            self.albumartist_entry,
            self.genre_entry,
            self.releasedate_entry,
            self.comment_entry,
        )

        self.tagentry_manager = EartagTagEntryManager()

        for tagentry in self.tagentries:
            self.tagentry_manager.add_entry(tagentry.bound_property, tagentry)

        self.previous_fileview_width = 0

    def on_close(self):
        self.album_cover.on_destroy()
        self.tagentry_manager.destroy()

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
        asyncio.create_task(self._update_binds())

    bind_in_progress = GObject.Property(type=bool, default=False)

    async def _update_binds(self):
        self.bind_in_progress = True

        _selected_files = set(self.file_manager.selected_files_list)

        # Get list of selected (added)/unselected (removed) files
        added_files = _selected_files - self.files
        removed_files = self.files - _selected_files

        # Handle added and removed files
        await self._unbind_files(removed_files)
        await self._bind_files(added_files)

        # Make save/fields sensitive/insensitive based on whether selected files are
        # all writable
        has_unwritable = False
        for file in _selected_files:
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

        self.bind_in_progress = False

    async def _bind_files(self, files):
        """Binds a file to the fileview. Used internally in update_binds."""
        if not files:
            return

        self.files |= set(files)
        await self.tagentry_manager.bind_to_files(files)

        for entry in self.bindable_entries:
            entry.bind_to_files(files)

        await self.more_tags_group.bind_to_files(files)

        self.file_info.refresh_label()

    async def _unbind_files(self, files):
        """Unbinds a file from the fileview. Used internally in update_binds."""
        if not files:
            return

        self.files -= set(files)
        await self.tagentry_manager.unbind_from_files(files)

        for entry in self.bindable_entries:
            entry.unbind_from_files(files)

        await self.more_tags_group.unbind_from_files(files)

        self.file_info.refresh_label()

    @GObject.Property(type=bool, default=False)
    def compact(self):
        return self.more_tags_group.compact

    @compact.setter
    def compact(self, value):
        self.more_tags_group.compact = value

    @GObject.Property(type=bool, default=False)
    def height_below_360(self):
        """Hack to fix https://gitlab.gnome.org/World/eartag/-/merge_requests/130"""
        return self.more_tags_group.height_below_360

    @height_below_360.setter
    def height_below_360(self, value):
        self.more_tags_group.height_below_360 = value
