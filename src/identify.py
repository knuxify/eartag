# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Adw, Gtk, Gio, GObject, GdkPixbuf

import asyncio
import os
import html
import traceback
import re

from .musicbrainz import (
    acoustid_identify_file,
    MusicBrainzRecording,
    MusicBrainzRelease,
)
from .logger import logger
from .utils import find_in_model
from .utils.asynctask import EartagAsyncTask
from .utils.extracttags import extract_tags_from_filename
from .utils.widgets import EartagModelExpanderRow
from .backends.file import EartagFile
from . import APP_GRESOURCE_PATH


MBID_REGEX = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
RECORDING_URL_REGEX = r"^(https?://)?musicbrainz.org/recording/(?P<mbid>" + MBID_REGEX + ")/?$"


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/identify/coverimage.ui")
class EartagIdentifyCoverImage(Gtk.Stack):
    __gtype_name__ = "EartagIdentifyCoverImage"

    no_cover = Gtk.Template.Child()
    cover_image = Gtk.Template.Child()
    loading_icon = Gtk.Template.Child()

    loading = GObject.Property(type=bool, default=False)
    cover_path = GObject.Property(type=str, default="")

    def __init__(self):
        super().__init__()
        self._cover_path = None
        self.connect("notify::loading", self.update)
        self.connect("notify::cover-path", self.update)

    def update(self, *args):
        """Update the cover according to the current state."""
        if self.props.loading:
            self.set_visible_child(self.loading_icon)
            return

        path = self.props.cover_path

        if not path or not os.path.exists(path):
            self.set_visible_child(self.no_cover)
            return

        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 48, 48, True)

        self.cover_image.set_from_pixbuf(pixbuf)
        self.set_visible_child(self.cover_image)


class EartagIdentifyReleaseRow(EartagModelExpanderRow):
    """
    Representation of MusicBrainz releases for the ItemRow
    dropdowns.
    """

    __gtype_name__ = "EartagIdentifyReleaseRow"

    def __init__(self, parent, release=None):
        super().__init__()
        self._bindings = []
        self._connections = []
        self.parent = parent
        self.release = None
        self.obj = None

        # Unfortunately we can't set the parent to EartagModelExpanderRow
        # in a template for some weird reason, so we have to set this widget
        # up manually here:

        self.add_css_class("identify-release-row")

        self.cover_image = EartagIdentifyCoverImage()
        self.cover_image.set_hexpand(False)
        self.add_prefix(self.cover_image)

        self.apply_checkbox = Gtk.CheckButton()
        self.apply_checkbox.set_active(True)
        self.apply_checkbox.set_sensitive(False)
        self.apply_checkbox.set_valign(Gtk.Align.CENTER)
        self.apply_checkbox.connect("notify::active", self.toggle_row_checkboxes)
        self.apply_checkbox.add_css_class("selection-mode")
        self.apply_checkbox.set_tooltip_text(_("Apply identified data"))
        self.add_suffix(self.apply_checkbox)

        if release:
            self.bind_to_release(release)

        self._rec_filter = Gtk.CustomFilter()
        self._rec_filter.set_filter_func(self._rec_filter_func)
        self._rec_filter_model = Gtk.FilterListModel(
            model=self.parent.recordings_model, filter=self._rec_filter
        )

        self._rec_sorter = Gtk.CustomSorter()
        self._rec_sorter.set_sort_func(self._rec_sorter_func)
        self._rec_sorter_model = Gtk.SortListModel(
            model=self._rec_filter_model, sorter=self._rec_sorter
        )

        self.bind_model(self._rec_sorter_model, self.row_create)

        # Release chooser filter setup
        self._rel_model = Gio.ListStore(item_type=MusicBrainzRelease)

        self.release_popover = Gtk.Popover()
        self.release_popover_scrolled_window = Gtk.ScrolledWindow()
        self.release_popover_list = Gtk.ListBox()
        self.release_popover_list.bind_model(self._rel_model, self.rel_row_create)
        self.release_popover_list.add_css_class("boxed-list")
        self.release_popover_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.release_popover_scrolled_window.set_policy(
            Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC
        )
        self.release_popover_scrolled_window.set_propagate_natural_height(True)
        self.release_popover_scrolled_window.set_propagate_natural_width(True)
        self.release_popover_scrolled_window.set_child(self.release_popover_list)
        self.release_popover.set_child(self.release_popover_scrolled_window)
        self._relswitch_first_row = None

        self.release_url_button = Gtk.Button()
        self.release_url_button.set_icon_name("external-link-symbolic")
        # TRANSLATORS: Tooltip for button to open release info in MusicBrainz identification dialog.
        self.release_url_button.set_tooltip_text(_("See release on MusicBrainz"))
        self.release_url_button.set_valign(Gtk.Align.CENTER)
        self.release_url_button.connect("clicked", self.open_release_url)
        self.release_url_button.add_css_class("flat")
        self.release_url_launcher = Gtk.UriLauncher.new("")
        self.add_suffix(self.release_url_button)

        self.release_popover_toggle = Gtk.MenuButton(popover=self.release_popover)
        self.release_popover_toggle.set_valign(Gtk.Align.CENTER)
        self.release_popover_toggle.set_visible(False)
        # TRANSLATORS: Tooltip for release switcher button in MusicBrainz identification dialog.
        # This allows the user to switch between different releases of an album, EP, etc.
        self.release_popover_toggle.set_tooltip_text(_("Other releases"))
        self.release_popover_toggle.set_icon_name("view-more-symbolic")
        self.release_popover_toggle.add_css_class("flat")
        self.release_popover_toggle.connect("notify::active", self.download_alt_release_thumbnails)
        self.add_suffix(self.release_popover_toggle)

    def bind_to_release(self, release):
        """Takes a MusicBrainzRelease and binds to it."""
        if self.release:
            self.unbind()

        self.release = release

        self._bindings = [
            self.release.bind_property(
                "thumbnail_path",
                self.cover_image,
                "cover_path",
                GObject.BindingFlags.SYNC_CREATE,
            ),
            self.release.bind_property(
                "thumbnail_loaded",
                self.cover_image,
                "loading",
                GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.INVERT_BOOLEAN,
            ),
        ]
        self._connections = [
            self.release.connect("notify::title", self.update_title),
            self.release.connect("notify::disambiguation", self.update_title),
            self.release.connect("notify::artist", self.update_subtitle),
            self.release.connect("notify::releasedate", self.update_subtitle),
        ]
        self.update_title()
        self.update_subtitle()

        release.queue_thumbnail_download()

    def unbind(self):
        for binding in self._bindings:
            binding.unbind()

        for conn in self._connections:
            if conn:
                self.release.disconnect(conn)

        self.release = None

    def update_title(self, *args):
        title = html.escape(self.release.title)
        if self.release.disambiguation:
            opacity = 0.55
            if Adw.StyleManager.get_default().get_high_contrast():
                opacity = 0.9
            title += (
                f' <span alpha="{int(opacity * 100)}%">('
                + html.escape(self.release.disambiguation)
                + ")</span>"
            )
        self.set_title(title)

    def update_subtitle(self, *args):
        self._subtitle = html.escape(self.release.artist)
        if self.release.releasedate:
            self._subtitle += " • " + self.release.releasedate
        self.set_subtitle(self._subtitle)

    def update_filter(self):
        self._filter_changed = False
        self._rec_filter.changed(Gtk.FilterChange.DIFFERENT)
        self._filter_changed = True

    def _rec_filter_func(self, recording):
        try:
            assert recording.release
        except (AttributeError, ValueError, AssertionError):
            return False
        return recording.release.release_id == self.release.release_id

    def _rec_sorter_func(self, rec1, rec2, *args):
        return rec1.tracknumber - rec2.tracknumber

    def row_create(self, recording, *args):
        row = EartagIdentifyRecordingRow(self, recording)
        row.apply_checkbox.connect("notify::active", self.toggle_make_inconsistent)
        return row

    def toggle_apply_sensitivity(self, value):
        n = 0
        row = self.get_row_at_index(n)
        while row:
            row.apply_checkbox.set_sensitive(value)
            n += 1
            row = self.get_row_at_index(n)
        self.apply_checkbox.set_sensitive(value)
        self.release_popover_toggle.set_sensitive(value)
        self.release_popover_toggle.set_visible(bool(self._rel_model.get_n_items() > 1))

    def toggle_row_checkboxes(self, toggle, *args):
        toggle.set_inconsistent(False)
        n = 0
        row = self.get_row_at_index(n)
        while row:
            row.apply_checkbox.set_active(toggle.props.active)
            n += 1
            row = self.get_row_at_index(n)

    def toggle_make_inconsistent(self, *args):
        n = 0
        row = self.get_row_at_index(n)
        active = row.apply_checkbox.get_active()
        while row:
            if row.apply_checkbox.get_active() != active:
                self.apply_checkbox.set_inconsistent(True)
                return
            n += 1
            row = self.get_row_at_index(n)
        self.apply_checkbox.set_inconsistent(False)
        if active != self.apply_checkbox.props.active:
            self.apply_checkbox.set_active(active)

    def refresh_alternative_releases(self, releases):
        """
        Used by the identification process to fill in the release switcher
        button model.
        """
        self.release_popover_toggle.set_visible(bool(releases))
        self._rel_model.splice(0, self._rel_model.get_n_items(), releases)

    def rel_row_create(self, rel, *args):
        row = EartagIdentifyAltReleaseRow(self, rel)
        if self._relswitch_first_row:
            row.apply_checkbox.set_active(False)
            row.apply_checkbox.set_group(self._relswitch_first_row.apply_checkbox)
            self._relswitch_first_row.set_sensitive(True)
        else:
            self._relswitch_first_row = row
            row.set_sensitive(False)
        if rel == self.release:
            row.apply_checkbox.set_active(True)
        row.apply_checkbox.connect("notify::active", self.set_release_from_selector, rel.release_id)
        return row

    def download_alt_release_thumbnails(self, *args):
        """
        Start downloading alternative release thumbnails when the popover
        is opened.
        """
        if not self.release_popover_toggle.props.active:
            return

        for rel in self._rel_model:
            rel.queue_thumbnail_download()

    def set_release_from_selector(self, _t1, _t2, rel_id):
        rel = None
        for rel in self._rel_model:
            if rel.release_id == rel_id:
                break

        if self.release:
            del self.parent.release_rows[self.release.release_id]

        for rec in self._rec_sorter_model:
            for _rel in rec.available_releases:
                if _rel.release_id == rel.release_id:
                    rec.release = _rel
                    break

        if rel_id in self.parent.release_rows:
            self.parent.content_listbox.remove(self)
            self.parent.release_rows[rel_id].update_filter()
            self.parent.release_rows[rel_id].toggle_apply_sensitivity(True)
        else:
            self.bind_to_release(rel)
            self.parent.release_rows[rel_id] = self
            self.update_filter()
            self.toggle_apply_sensitivity(True)

    def open_release_url(self, *args):
        """Open the currently bound release's MusicBrainz page."""

        async def _open(self):
            self.release_url_launcher.props.uri = (
                f"https://musicbrainz.org/release/{self.release.release_id}"
            )
            await self.release_url_launcher.launch(self.get_root())

        asyncio.create_task(_open(self))


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/identify/altreleaserow.ui")
class EartagIdentifyAltReleaseRow(Adw.ActionRow):
    """
    Representation of releases for the release switcher dropdown.
    """

    __gtype_name__ = "EartagIdentifyAltReleaseRow"

    cover_image = Gtk.Template.Child()
    apply_checkbox = Gtk.Template.Child()

    def __init__(self, parent, release):
        super().__init__()
        self._bindings = []
        self._connections = []
        self.release = release

        self.bind_to_release(release)

    def bind_to_release(self, release):
        self.release = release

        self._bindings = [
            self.release.bind_property(
                "thumbnail_path",
                self.cover_image,
                "cover_path",
                GObject.BindingFlags.SYNC_CREATE,
            ),
            self.release.bind_property(
                "thumbnail_loaded",
                self.cover_image,
                "loading",
                GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.INVERT_BOOLEAN,
            ),
        ]
        self._connections = [
            self.release.connect("notify::title", self.update_title),
            self.release.connect("notify::artist", self.update_subtitle),
        ]
        self.update_title()
        self.update_subtitle()

    def unbind(self, *args):
        if self.release:
            for binding in self._bindings:
                binding.unbind()

            for conn in self._connections:
                self.release.disconnect(conn)

        self._connections = []
        self._bindings = []

        self.release = None
        self.parent = None

    def update_title(self, *args):
        title = html.escape(self.release.title)
        if self.release.disambiguation:
            opacity = 0.55
            if Adw.StyleManager.get_default().get_high_contrast():
                opacity = 0.9
            title += (
                f' <span alpha="{int(opacity * 100)}%">('
                + html.escape(self.release.disambiguation)
                + ")</span>"
            )
        self.set_title(title)

    def update_subtitle(self, *args):
        self._subtitle = html.escape(self.release.artist)
        if self.release.releasedate:
            self._subtitle += " • " + self.release.releasedate
        self.set_subtitle(self._subtitle)


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/identify/filerow.ui")
class EartagIdentifyFileRow(Adw.ActionRow):
    """
    Representation of files for the identify dialog.
    """

    __gtype_name__ = "EartagIdentifyFileRow"

    cover_image = Gtk.Template.Child()

    suffix_stack = Gtk.Template.Child()
    loading_icon = Gtk.Template.Child()
    not_found_icon = Gtk.Template.Child()

    recording_override_popover = Gtk.Template.Child()
    recording_override_entry = Gtk.Template.Child()
    recording_override_apply_button = Gtk.Template.Child()

    def __init__(self, file, parent):
        super().__init__()
        self._connections = []
        self.file = None
        self.parent = parent

        self.connect("destroy", self.unbind)

        self.bind_to_file(file)

        self.validate_recording_override_entry()

    def bind_to_file(self, file):
        if self.file:
            self.unbind()

        self.file = file
        self.cover_image.bind_to_file(file)

        self._connections = [
            self.file.connect("notify::title", self.update_title),
            self.file.connect("notify::artist", self.update_subtitle),
            self.file.connect("notify::album", self.update_subtitle),
        ]
        self.update_title()
        self.update_subtitle()

    def unbind(self, *args):
        for conn in self._connections:
            self.file.disconnect(conn)
        self.cover_image.unbind_from_file()

        self.file = None

    def update_title(self, *args):
        self.set_title(html.escape(self.file.title))

    def update_subtitle(self, *args):
        self._subtitle = (
            f"{self.file.artist or 'N/A'} • {self.file.album or 'N/A'}"
            + f" ({os.path.basename(self.file.path)})"
        )
        self.set_subtitle(html.escape(self._subtitle))

    def start_loading(self):
        self.suffix_stack.set_visible(True)
        self.suffix_stack.set_visible_child(self.loading_icon)

    def mark_as_unidentified(self):
        self.suffix_stack.set_visible_child(self.not_found_icon)

    def get_mbid_from_recording_override_entry(self):
        # Reuse the IdentifyRecordingRow function for convenience
        return EartagIdentifyRecordingRow.get_mbid_from_recording_override_entry(self)

    @Gtk.Template.Callback()
    def validate_recording_override_entry(self, *args):
        # Reuse the IdentifyRecordingRow function for convenience
        return EartagIdentifyRecordingRow.validate_recording_override_entry(self)

    @Gtk.Template.Callback()
    def set_recording_override_from_entry(self, *args):
        """Apply the recording ID or URL from the recording override entry."""

        async def _set_rec_override(self):
            mbid = self.get_mbid_from_recording_override_entry()
            if not mbid:
                return

            self.recording_override_popover.props.sensitive = False

            rec = await MusicBrainzRecording.new_for_id(mbid)

            self.parent._identify_set_recording(self.file.id, rec)
            self.parent.on_identify_done(None, show_toast=False)

            self.recording_override_popover.props.sensitive = True

        asyncio.create_task(_set_rec_override(self))


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/identify/recordingrow.ui")
class EartagIdentifyRecordingRow(Adw.ActionRow):
    """
    Representation of recordings for the identify dialog.
    """

    __gtype_name__ = "EartagIdentifyRecordingRow"

    apply_checkbox = Gtk.Template.Child()
    recording_url_button = Gtk.Template.Child()

    recording_override_popover = Gtk.Template.Child()
    recording_override_entry = Gtk.Template.Child()
    recording_override_apply_button = Gtk.Template.Child()

    def __init__(self, parent, recording):
        super().__init__()
        self._bindings = []
        self._connections = []
        self.recording = None
        file_id = None
        self.parent = parent
        assert self.parent
        for _file_id, rec in self.parent.parent.recordings.items():
            if rec.recording_id == recording.recording_id:
                file_id = _file_id
                break
        self.file_id = file_id

        self.file_name = ""
        if file_id:
            for file in self.parent.parent.files:
                if file.id == self.file_id:
                    self.file_name = os.path.basename(file.path)
                    break

        self.recording_url_launcher = Gtk.UriLauncher.new("")

        self.connect("destroy", self.unbind)

        self.bind_to_recording(recording)

        self.validate_recording_override_entry()

    def bind_to_recording(self, recording):
        self.recording = recording

        self._connections = [
            self.recording.connect("notify::title", self.update_title),
            self.recording.connect("notify::artist", self.update_subtitle),
            self.recording.connect("notify::album", self.update_subtitle),
        ]
        self.update_title()
        self.update_subtitle()

    def unbind(self, *args):
        for conn in self._connections:
            self.recording.disconnect(conn)

        self.recording = None
        self.parent = None

    def update_title(self, *args):
        title = html.escape(self.recording.title)
        if self.recording.disambiguation:
            opacity = 0.55
            if Adw.StyleManager.get_default().get_high_contrast():
                opacity = 0.9
            title += (
                f' <span alpha="{int(opacity * 100)}%">('
                + html.escape(self.recording.disambiguation)
                + ")</span>"
            )
        self.set_title(title)

    def update_subtitle(self, *args):
        self._subtitle = f"{self.recording.artist or 'N/A'} • {self.recording.album or 'N/A'} ({self.file_name or 'N/A'})"  # noqa: E501
        self.set_subtitle(html.escape(self._subtitle))

    def start_loading(self):
        self.suffix_stack.set_visible(True)
        self.suffix_stack.set_visible_child(self.loading_icon)

    def mark_as_unidentified(self):
        self.suffix_stack.set_visible_child(self.not_found_icon)

    @Gtk.Template.Callback()
    def toggle_apply(self, toggle, *args):
        if toggle.props.active and self.file_id not in self.parent.parent.apply_files:
            self.parent.parent.apply_files.append(self.file_id)
            self.parent.parent.apply_files_changed()
        elif not toggle.props.active and self.file_id in self.parent.parent.apply_files:
            self.parent.parent.apply_files.remove(self.file_id)
            self.parent.parent.apply_files_changed()

    @Gtk.Template.Callback()
    def open_recording_url(self, *args):
        """Open the currently bound recording's MusicBrainz page."""

        async def _open(self):
            self.recording_url_launcher.props.uri = (
                f"https://musicbrainz.org/recording/{self.recording.recording_id}"
            )
            await self.recording_url_launcher.launch(self.get_root())

        asyncio.create_task(_open(self))

    def get_mbid_from_recording_override_entry(self) -> str | None:
        """
        Extract the MBID from the URL or raw ID string given to the recording
        override entry.
        """
        entry_text = self.recording_override_entry.get_text().strip()

        if re.match(f"^{MBID_REGEX}$", entry_text):
            # Raw MBID
            mbid = entry_text
        else:
            # URL
            match = re.match(RECORDING_URL_REGEX, entry_text)
            try:
                mbid = match.group("mbid")
            except (AttributeError, IndexError):  # no match
                return None

        return mbid

    @Gtk.Template.Callback()
    def validate_recording_override_entry(self, *args):
        """Validate the contents of the recording override entry."""
        if self.get_mbid_from_recording_override_entry():
            self.recording_override_entry.remove_css_class("error")
            self.recording_override_apply_button.props.sensitive = True
        else:
            self.recording_override_entry.add_css_class("error")
            self.recording_override_apply_button.props.sensitive = False

    @Gtk.Template.Callback()
    def set_recording_override_from_entry(self, *args):
        """Apply the recording ID or URL from the recording override entry."""

        async def _set_rec_override(self):
            mbid = self.get_mbid_from_recording_override_entry()
            if not mbid:
                return

            self.recording_override_popover.props.sensitive = False

            rec = await MusicBrainzRecording.new_for_id(mbid)

            self.parent.parent._identify_set_recording(self.file_id, rec)
            self.parent.parent.on_identify_done(None, show_toast=False)

            self.recording_override_popover.props.sensitive = True

        asyncio.create_task(_set_rec_override(self))


@Gtk.Template(resource_path=f"{APP_GRESOURCE_PATH}/ui/identify/identify.ui")
class EartagIdentifyDialog(Adw.Dialog):
    __gtype_name__ = "EartagIdentifyDialog"

    toast_overlay = Gtk.Template.Child()

    id_progress = Gtk.Template.Child()
    content_listbox = Gtk.Template.Child()

    cancel_button = Gtk.Template.Child()
    identify_button = Gtk.Template.Child()
    apply_button = Gtk.Template.Child()
    end_button_stack = Gtk.Template.Child()

    apply_progress = GObject.Property(type=float, minimum=0, maximum=1)

    def __init__(self, window):
        super().__init__()
        self.parent = window
        self.file_manager = window.file_manager

        self.files = Gio.ListStore(item_type=EartagFile)
        self.unidentified_filter = Gtk.CustomFilter()
        self.unidentified_filter.set_filter_func(self.unidentified_filter_func)
        self.unidentified_filter.connect("changed", self.mark_unidentified_filter_as_changed)
        self.files_unidentified = Gtk.FilterListModel(
            model=self.files, filter=self.unidentified_filter
        )
        self.recordings = {}  # file.id: MusicBrainzRecording
        self.recordings_model = Gio.ListStore(item_type=MusicBrainzRecording)
        self.apply_files = []
        self.release_rows = {}  # release.id: EartagIdentifyReleaseRow

        self.identify_task = EartagAsyncTask(self.identify_files)
        self.apply_task = EartagAsyncTask(self.apply_func)

        # For some reason we can't create this from the template, so it
        # has to be added here:
        self.unidentified_row = EartagModelExpanderRow()
        self.unidentified_row.set_title(_("Unidentified Files"))
        self.unidentified_row.set_expanded(True)
        cover_dummy = EartagIdentifyCoverImage()
        cover_dummy.set_hexpand(False)
        self.unidentified_row.add_prefix(cover_dummy)
        self.unidentified_row.bind_model(self.files_unidentified, self.unidentified_row_create)

        self.content_listbox.append(self.unidentified_row)

        self.identify_task.bind_property("progress", self.id_progress, "fraction")
        self.identify_task.connect("task-done", self.on_identify_done)

        self.apply_task.bind_property("progress", self.id_progress, "fraction")
        self.apply_task.connect("task-done", self.on_apply_done)

        self.files.splice(0, self.files.get_n_items(), self.file_manager.selected_files_list)

        self.connect("closed", self.on_close_request)

    def on_close_request(self, *args):
        for row in self.release_rows.values():
            row.unbind()
        self.release_rows = {}

    def unidentified_row_create(self, file, *args):
        return EartagIdentifyFileRow(file, self)

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        try:
            if self.identify_task.is_running:
                self.identify_task.stop()
            if self.apply_task.is_running:
                self.apply_task.stop()
        except AttributeError:
            pass
        self.files = None
        self.props.can_close = True
        self.close()

    @Gtk.Template.Callback()
    def do_identify(self, *args):
        self.identify_button.set_sensitive(False)
        self.apply_button.set_sensitive(False)
        self.set_can_close(False)

        self.identify_task.run()

    def _identify_set_recording(self, file_id: str, rec: MusicBrainzRecording):
        try:
            rec.release  # noqa: B018
        except ValueError:
            rec.release = rec.available_releases[0]

        if file_id in self.recordings:
            old_rec = self.recordings[file_id]
            index = self.recordings_model.find(old_rec)[1]
            if index is not None:
                self.recordings_model.remove(index)
            old_relrow = self.release_rows[old_rec.release.release_id]
            old_relrow._filter_changed = False
            old_relrow.update_filter()
            old_relrow._filter_changed = False
            if old_relrow._rec_sorter_model.get_n_items() == 0:
                self.content_listbox.remove(old_relrow)
                del self.release_rows[old_rec.release.release_id]

        self.recordings[file_id] = rec
        self.recordings_model.append(rec)

        if rec.release.release_id in self.release_rows:
            row = self.release_rows[rec.release.release_id]
            row._filter_changed = False
            row.update_filter()
            row._filter_changed = False
        else:
            self.release_rows[rec.release.release_id] = EartagIdentifyReleaseRow(self, rec.release)
            self.content_listbox.prepend(self.release_rows[rec.release.release_id])

        self._filter_changed = False
        self.unidentified_filter.changed(Gtk.FilterChange.DIFFERENT)
        self._filter_changed = False

        self.apply_files.append(file_id)

    async def identify_files(self, *args, **kwargs):
        progress_step = 1 / len(self.files)

        found_recordings = []

        # Step 1. Go over each file and find recordings
        for file in self.files:
            logger.info(f"Identifying recordings for file: {file}")
            unid_index = find_in_model(self.files_unidentified, file)
            if unid_index < 0:
                logger.error("Could not find file in unidentifed filter, this should never happen!")
                continue

            unid_row = self.unidentified_row.get_row_at_index(unid_index)
            unid_row.start_loading()

            recordings = []

            try:
                if file.title and file.artist:
                    # For files with a title/artist tag, look up the data in MusicBrainz
                    recordings = await MusicBrainzRecording.get_recordings_for_file(file)
                else:
                    logger.debug("No title or artist tag, trying to guess tags from filename...")
                    tag_guesses = []
                    for guess_pattern in (
                        "{artist} - {title}",
                        "{title} - {artist}",
                        "{artist} — {title}",
                        "{title} — {artist}",
                        "{title}",
                    ):
                        tag_guesses.append(
                            extract_tags_from_filename(
                                file.path, guess_pattern, strip_common_suffixes=True
                            )
                        )

                    for guess in tag_guesses:
                        if not guess:
                            continue

                        recordings += await MusicBrainzRecording.get_recordings_for_file(
                            file, overrides=guess, sort=False
                        )

                    recordings = MusicBrainzRecording.sort_recordings(recordings, file=file)

                # If we don't find anything or we find multiple recordings, try AcoustID
                if (
                    not recordings
                    or len(recordings) > 1
                    or (recordings[0].release and recordings[0].release.status != "official")
                    or not file.title
                    or not file.artist
                ):
                    logger.debug("Trying AcoustID, just to be sure...")
                    id_confidence, id_recording = await acoustid_identify_file(file)

                    if id_recording:
                        recordings = MusicBrainzRecording.sort_recordings(
                            recordings + [id_recording], file=file
                        )

                if recordings:
                    rec = recordings[0]
                    found_recordings.append(rec)
                    if not rec.available_releases:
                        unid_row.mark_as_unidentified()
                    else:
                        self._identify_set_recording(file.id, rec)
                        self.identify_task.increment_progress(progress_step)
                else:
                    unid_row.mark_as_unidentified()

            except asyncio.exceptions.CancelledError:
                return

            except:  # noqa: E722
                # Prevent crashes in recording identification from aborting the identification
                logger.error(f"Failure while identifying file {file}:")
                traceback.print_exc()
                unid_row.mark_as_unidentified()
                continue

        # Once we're done identifying all recordings, go back through found releases and
        # group together releases belonging to the same release group.
        #
        # We need to do this since we might be dealing with a "deluxe edition" with extra
        # tracks; in that case, all tracks should fall under the deluxe edition.

        logger.debug("Done identifying files, grouping will now proceed")

        groups = {}  # group ID: releases for this group
        for rel in [row.release for row in self.release_rows.values()]:
            if rel.group.relgroup_id not in groups:
                groups[rel.group.relgroup_id] = [rel]
            else:
                groups[rel.group.relgroup_id].append(rel)

        logger.debug(f"Per-group identified releases: {groups}")

        group_recs = {}  # group ID: recordings for this group
        for rec in found_recordings:
            if rec.release.group.relgroup_id in group_recs:
                group_recs[rec.release.group.relgroup_id].append(rec)
            else:
                group_recs[rec.release.group.relgroup_id] = [rec]

        logger.debug(f"Per-group identified recordings: {group_recs}")

        # For each group, figure out which one contains the most of our identified
        # recordings. The one that covers the most wins.
        for group_id in groups.keys():
            rel_trackcount = {}  # release ID: [recording IDs]
            for rec in group_recs[group_id]:
                rec_rel_ids = [rel.release_id for rel in rec.available_releases]
                for rel_id in rec_rel_ids:
                    if rel_id in rel_trackcount:
                        rel_trackcount[rel_id].add(rec.recording_id)
                    else:
                        rel_trackcount[rel_id] = {
                            rec.recording_id,
                        }

            rel_trackcount_sorted = sorted(
                rel_trackcount.items(), key=lambda v: len(v[1]), reverse=True
            )

            logger.debug(f"Found {len(rel_trackcount_sorted)} possible releases")

            target_release = rel_trackcount_sorted[0][0]
            target_rel_recordings = set()

            logger.debug(f"Selected {target_release} as target release")

            for rec in group_recs[group_id]:
                for rel in rec.available_releases:
                    if rel.release_id == target_release:
                        target_rel_recordings.add(rec.recording_id)
                        rec.release = rel
                        break

            # Set up alternative releases
            alt_releases = set()
            for rel_id, rec_ids in rel_trackcount.items():
                if rel_trackcount[target_release].issubset(rec_ids):
                    alt_releases.add(rel_id)

            logger.debug(
                f"Found {len(alt_releases)} alternative releases for release {target_release}:\n{alt_releases}"
            )
            all_releases = set()
            for rec in group_recs[group_id]:
                if rec.recording_id not in target_rel_recordings:
                    continue
                all_releases = all_releases.union(set(rec.available_releases))

            self.release_rows[target_release].refresh_alternative_releases(
                [rel for rel in all_releases if rel.release_id in alt_releases]
            )

        for k, row in list(self.release_rows.items()).copy():
            row.update_filter()
            if row._rec_filter_model.get_n_items() == 0:
                del self.release_rows[k]
                self.content_listbox.remove(row)

    def on_identify_done(self, task, *args, show_toast: bool = True):
        try:
            identified = self.files.get_n_items() - self.files_unidentified.get_n_items()
        except AttributeError:  # this happens when the operation is cancelled
            return
        self.end_button_stack.set_visible_child(self.apply_button)
        self.apply_button.set_sensitive(bool(identified))
        self.set_can_close(True)
        for relrow in self.release_rows.values():
            relrow.toggle_apply_sensitivity(True)
        if not self.files_unidentified.get_n_items():
            self.unidentified_row.set_visible(False)

        if show_toast:
            self.toast_overlay.add_toast(
                Adw.Toast.new(
                    ngettext(
                        # TRANSLATORS: {identified} is a placeholder for the number
                        # of tracks that were succesfully identified.
                        # **Do not translate the text between the curly brackets!**
                        "Identified 1 track",
                        "Identified {identified} tracks",
                        identified,
                    ).format(identified=identified)
                )
            )

    @Gtk.Template.Callback()
    def do_apply(self, *args):
        self.apply_button.set_sensitive(False)
        for relrow in self.release_rows.values():
            relrow.toggle_apply_sensitivity(False)
        self.set_can_close(False)

        self.apply_task.run()

    async def apply_func(self):
        files = [file for file in self.files if file.id in self.apply_files]
        if not files:
            return

        # Step 1. Download covers
        releases = set()
        for file in files:
            rec = self.recordings[file.id]
            releases.add(rec.release)

        progress_step = 1 / (len(files) + len(releases))

        sem = asyncio.Semaphore(5)
        _tasks = set()
        async with asyncio.TaskGroup() as tg:
            while releases:
                async with sem:
                    _tasks.add(tg.create_task(releases.pop().download_covers_async()))
                    self.apply_task.increment_progress(progress_step)
        del releases
        del _tasks
        del sem

        # Step 2. Apply tags to files
        for file in files:
            rec = self.recordings[file.id]
            # Ugly quirk: since release objects are derived from the data in the
            # recording object, and not shared, downloading covers for one does
            # not mark the covers for all recordings as downloaded.
            #
            # We run download_covers_async() on each of the recordings to update
            # the cover data; no actual data gets downloaded, since covers are
            # cached.
            await rec.download_covers_async()

            await rec.apply_data_to_file(file)
            self.apply_task.increment_progress(progress_step)

    def on_apply_done(self, *args):
        self.props.can_close = True
        self.file_manager.emit("refresh-needed")
        try:
            identified = self.files.get_n_items() - self.files_unidentified.get_n_items()
        except AttributeError:  # this happens when the operation is cancelled
            return
        self.parent.toast_overlay.add_toast(
            Adw.Toast.new(
                ngettext(
                    # TRANSLATORS: {n} is a placeholder for the number
                    # of tracks that were succesfully identified.
                    # **Do not translate the text between the curly brackets!**
                    "Applied changes to 1 track",
                    "Applied changes to {n} tracks",
                    identified,
                ).format(n=identified)
            )
        )
        self.files = None
        self.identify_task = None
        self.apply_task = None
        self.close()

    def unidentified_filter_func(self, file, *args):
        return file.id not in self.recordings

    def apply_files_changed(self, *args):
        self.apply_button.set_sensitive(bool(self.apply_files))

    def mark_unidentified_filter_as_changed(self, *args):
        """
        Since we call a filter change from a thread, we have to wait for it
        to finish first to allow the unidentified rows to refresh, else we
        get weird errors in the identify loop.
        """
        self._filter_changed = True
