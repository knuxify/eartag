# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Adw, Gtk, GLib, Gio, GObject, GdkPixbuf

import os
import time
import html

from .musicbrainz import (
    acoustid_identify_file, get_recordings_for_file,
    MusicBrainzRecording, MusicBrainzRelease, MusicBrainzReleaseGroup,
)
from .utils import simplify_compare, reg_and_simple_cmp, find_in_model, all_equal
from .utils.bgtask import EartagBackgroundTask
from .utils.widgets import EartagModelExpanderRow
from .backends.file import EartagFile

@Gtk.Template(resource_path='/app/drey/EarTag/ui/identify/coverimage.ui')
class EartagIdentifyCoverImage(Gtk.Stack):
    __gtype_name__ = 'EartagIdentifyCoverImage'

    no_cover = Gtk.Template.Child()
    cover_image = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self._cover_path = None

    @GObject.Property(type=str)
    def cover_path(self):
        return self._cover_path

    @cover_path.setter
    def cover_path(self, path):
        self._cover_path = path

        if not path or not os.path.exists(path):
            self.set_visible_child(self.no_cover)
            return

        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            path, 48, 48, True
        )

        self.cover_image.set_from_pixbuf(pixbuf)
        self.set_visible_child(self.cover_image)


class EartagIdentifyReleaseRow(EartagModelExpanderRow):
    """
    Representation of MusicBrainz releases for the ItemRow
    dropdowns.
    """
    __gtype_name__ = 'EartagIdentifyReleaseRow'

    def __init__(self, parent, release=None):
        super().__init__()
        self._bindings = []
        self._connections = []
        self.parent = parent
        self.obj = None

        # Unfortunately we can't set the parent to EartagModelExpanderRow
        # in a template for some weird reason, so we have to set this widget
        # up manually here:

        self.add_css_class('identify-release-row')

        self.cover_image = EartagIdentifyCoverImage()
        self.cover_image.set_hexpand(False)
        self.add_prefix(self.cover_image)

        self.apply_checkbox = Gtk.CheckButton()
        self.apply_checkbox.set_active(True)
        self.apply_checkbox.set_sensitive(False)
        self.apply_checkbox.connect('notify::active', self.toggle_row_checkboxes)
        self.apply_checkbox.add_css_class('selection-mode')
        self.add_suffix(self.apply_checkbox)

        if release:
            self.bind_to_release(release)

        self._rec_filter = Gtk.CustomFilter()
        self._rec_filter.set_filter_func(self._rec_filter_func)
        self._rec_filter_model = Gtk.FilterListModel(
            model=self.parent.recordings_model,
            filter=self._rec_filter
        )

        self._rec_sorter = Gtk.CustomSorter()
        self._rec_sorter.set_sort_func(self._rec_sorter_func)
        self._rec_sorter_model = Gtk.SortListModel(
            model=self._rec_filter_model,
            sorter=self._rec_sorter
        )

        self.bind_model(self._rec_sorter_model, self.row_create)

        # Release chooser filter setup
        self._rel_model = Gio.ListStore(item_type=MusicBrainzRelease)

        self.release_popover = Gtk.Popover()
        self.release_popover_list = Gtk.ListBox()
        self.release_popover_list.bind_model(self._rel_model, self.rel_row_create)
        self.release_popover_list.add_css_class('boxed-list')
        self.release_popover_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.release_popover.set_child(self.release_popover_list)
        self._relswitch_first_row = None

        self.release_popover_toggle = Gtk.MenuButton(popover=self.release_popover)
        self.release_popover_toggle.set_valign(Gtk.Align.CENTER)
        self.release_popover_toggle.set_visible(False)
        # TRANSLATORS: Tooltip for release switcher button in MusicBrainz identification dialog.
        # This allows the user to switch between different releases of an album, EP, etc.
        self.release_popover_toggle.set_tooltip_text(_('Other releases'))
        self.release_popover_toggle.set_icon_name('view-more-symbolic')
        self.add_suffix(self.release_popover_toggle)

    def bind_to_release(self, release):
        """Takes a MusicBrainzRelease and binds to it."""
        self.release = release

        self._bindings = [
            self.release.bind_property('thumbnail_path', self.cover_image, 'cover_path',
                                       GObject.BindingFlags.SYNC_CREATE),
        ]
        self._connections = [
            self.release.connect('notify::title', self.update_title),
            self.release.connect('notify::disambiguation', self.update_title),
            self.release.connect('notify::artist', self.update_subtitle),
            self.release.connect('notify::releasedate', self.update_subtitle),
        ]
        self.update_title()
        self.update_subtitle()

    def unbind(self):
        for binding in self._bindings:
            binding.unbind()

        for conn in self._connections:
            self.release.disconnect(conn)

        self.release = None

    def update_title(self, *args):
        title = html.escape(self.release.title)
        if self.release.disambiguation:
            opacity = 0.55
            if Adw.StyleManager.get_default().get_high_contrast():
                opacity = 0.9
            title += f' <span alpha="{int(opacity * 100)}%">(' \
                     + html.escape(self.release.disambiguation) + ')</span>'
        self.set_title(title)

    def update_subtitle(self, *args):
        self._subtitle = html.escape(self.release.artist)
        if self.release.releasedate:
            self._subtitle += ' • ' + self.release.releasedate
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
        row.apply_checkbox.connect('notify::active', self.toggle_make_inconsistent)
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
        GLib.idle_add(
            self._rel_model.splice,
            0, self._rel_model.get_n_items(), releases
        )

    def rel_row_create(self, rel, *args):
        row = EartagIdentifyAltReleaseRow(self, rel)
        if self._relswitch_first_row:
            row.apply_checkbox.set_active(False)
            self._relswitch_first_row.apply_checkbox.set_group(row.apply_checkbox)
            self._relswitch_first_row.set_sensitive(True)
        else:
            self._relswitch_first_row = row
            row.set_sensitive(False)
        row.apply_checkbox.connect(
            'notify::active', self.set_release_from_selector, rel.release_id
        )
        return row

    def set_release_from_selector(self, _t1, _t2, rel_id):
        rel = None
        for rel in self._rel_model:
            if rel.release_id == rel_id:
                break
        self.unbind()
        self.bind_to_release(rel)
        for rec in self._rec_sorter_model:
            for _rel in rec.available_releases:
                if _rel.release_id == rel.release_id:
                    rec.release = _rel
                    break
        self.update_filter()


@Gtk.Template(resource_path='/app/drey/EarTag/ui/identify/altreleaserow.ui')
class EartagIdentifyAltReleaseRow(Adw.ActionRow):
    """
    Representation of releases for the release switcher dropdown.
    """
    __gtype_name__ = 'EartagIdentifyAltReleaseRow'

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
            self.release.bind_property('thumbnail_path', self.cover_image, 'cover_path',
                                       GObject.BindingFlags.SYNC_CREATE),
        ]
        self._connections = [
            self.release.connect('notify::title', self.update_title),
            self.release.connect('notify::artist', self.update_subtitle),
        ]
        self.update_title()
        self.update_subtitle()

    def unbind(self, *args):
        for binding in self._bindings:
            binding.unbind()

        for conn in self._connections:
            self.release.disconnect(conn)

        self.release = None
        self.parent = None

    def update_title(self, *args):
        title = html.escape(self.release.title)
        if self.release.disambiguation:
            opacity = 0.55
            if Adw.StyleManager.get_default().get_high_contrast():
                opacity = 0.9
            title += f' <span alpha="{int(opacity * 100)}%">(' \
                     + html.escape(self.release.disambiguation) + ')</span>'
        self.set_title(title)

    def update_subtitle(self, *args):
        self._subtitle = html.escape(self.release.artist)
        if self.release.releasedate:
            self._subtitle += ' • ' + self.release.releasedate
        self.set_subtitle(self._subtitle)

@Gtk.Template(resource_path='/app/drey/EarTag/ui/identify/filerow.ui')
class EartagIdentifyFileRow(Adw.ActionRow):
    """
    Representation of files for the identify dialog.
    """
    __gtype_name__ = 'EartagIdentifyFileRow'

    cover_image = Gtk.Template.Child()

    suffix_stack = Gtk.Template.Child()
    loading_icon = Gtk.Template.Child()
    not_found_icon = Gtk.Template.Child()

    def __init__(self, file):
        super().__init__()
        self._bindings = []
        self._connections = []
        self.file = None

        self.connect('destroy', self.unbind)

        self.bind_to_file(file)

    def bind_to_file(self, file):
        self.file = file

        self._bindings = [
            self.file.bind_property('front_cover_path', self.cover_image, 'cover_path',
                                    GObject.BindingFlags.SYNC_CREATE),
        ]
        self._connections = [
            self.file.connect('notify::title', self.update_title),
            self.file.connect('notify::artist', self.update_subtitle),
            self.file.connect('notify::album', self.update_subtitle),
        ]
        self.update_title()
        self.update_subtitle()

    def unbind(self, *args):
        for binding in self._bindings:
            binding.unbind()

        for conn in self._connections:
            self.file.disconnect(conn)

        self.file = None

    def update_title(self, *args):
        self.set_title(html.escape(self.file.title))

    def update_subtitle(self, *args):
        self._subtitle = f'{self.file.artist or "N/A"} • {self.file.album or "N/A"}' \
            + f' ({os.path.basename(self.file.path)})'
        self.set_subtitle(html.escape(self._subtitle))

    def start_loading(self):
        self.suffix_stack.set_visible(True)
        self.suffix_stack.set_visible_child(self.loading_icon)
        self.loading_icon.start()

    def mark_as_unidentified(self):
        self.suffix_stack.set_visible_child(self.not_found_icon)
        self.loading_icon.stop()


@Gtk.Template(resource_path='/app/drey/EarTag/ui/identify/recordingrow.ui')
class EartagIdentifyRecordingRow(Adw.ActionRow):
    """
    Representation of recordings for the identify dialog.
    """
    __gtype_name__ = 'EartagIdentifyRecordingRow'

    apply_checkbox = Gtk.Template.Child()

    def __init__(self, parent, recording):
        super().__init__()
        self._bindings = []
        self._connections = []
        self.recording = None
        file_id = None
        self.parent = parent
        assert self.parent
        for file_id, _rec in self.parent.parent.recordings.items():
            if _rec.recording_id == recording.recording_id:
                break
        self.file_id = file_id

        self.file_name = ''
        if file_id:
            for file in self.parent.parent.files:
                if file.id == self.file_id:
                    self.file_name = os.path.basename(file.path)
                    break

        self.connect('destroy', self.unbind)

        self.bind_to_recording(recording)

    def bind_to_recording(self, recording):
        self.recording = recording

        self._connections = [
            self.recording.connect('notify::title', self.update_title),
            self.recording.connect('notify::artist', self.update_subtitle),
            self.recording.connect('notify::album', self.update_subtitle),
        ]
        self.update_title()
        self.update_subtitle()

    def unbind(self, *args):
        for conn in self._connections:
            self.recording.disconnect(conn)

        self.recording = None
        self.parent = None

    def update_title(self, *args):
        self.set_title(html.escape(self.recording.title))

    def update_subtitle(self, *args):
        self._subtitle = f'{self.recording.artist or "N/A"} • {self.recording.album or "N/A"} ({self.file_name or "N/A"})'  # noqa: E501
        self.set_subtitle(html.escape(self._subtitle))

    def start_loading(self):
        self.suffix_stack.set_visible(True)
        self.suffix_stack.set_visible_child(self.loading_icon)
        self.loading_icon.start()

    def mark_as_unidentified(self):
        self.suffix_stack.set_visible_child(self.not_found_icon)
        self.loading_icon.stop()

    @Gtk.Template.Callback()
    def toggle_apply(self, toggle, *args):
        if toggle.props.active and self.file_id not in self.parent.parent.apply_files:
            self.parent.parent.apply_files.append(self.file_id)
            self.parent.parent.apply_files_changed()
        elif not toggle.props.active and self.file_id in self.parent.parent.apply_files:
            self.parent.parent.apply_files.remove(self.file_id)
            self.parent.parent.apply_files_changed()


@Gtk.Template(resource_path='/app/drey/EarTag/ui/identify/identify.ui')
class EartagIdentifyDialog(Adw.Window):
    __gtype_name__ = 'EartagIdentifyDialog'

    id_progress = Gtk.Template.Child()
    content_listbox = Gtk.Template.Child()

    cancel_button = Gtk.Template.Child()
    identify_button = Gtk.Template.Child()
    apply_button = Gtk.Template.Child()
    end_button_stack = Gtk.Template.Child()

    def __init__(self, window):
        super().__init__(modal=True, transient_for=window)
        self.parent = window
        self.file_manager = window.file_manager

        self.files = Gio.ListStore(item_type=EartagFile)
        self.unidentified_filter = Gtk.CustomFilter()
        self.unidentified_filter.set_filter_func(self.unidentified_filter_func)
        self.unidentified_filter.connect('changed', self.mark_unidentified_filter_as_changed)
        self.files_unidentified = Gtk.FilterListModel(
            model=self.files,
            filter=self.unidentified_filter
        )
        self.recordings = {}  # file.id: MusicBrainzRecording
        self.recordings_model = Gio.ListStore(item_type=MusicBrainzRecording)
        self.apply_files = []
        self.release_rows = {}  # release.id: EartagIdentifyReleaseRow

        self.identify_task = EartagBackgroundTask(self.identify_files)
        self.apply_task = EartagBackgroundTask(self.apply_func)

        # For some reason we can't create this from the template, so it
        # has to be added here:
        self.unidentified_row = EartagModelExpanderRow()
        self.unidentified_row.set_title(_('Unidentified Files'))
        self.unidentified_row.set_expanded(True)
        cover_dummy = EartagIdentifyCoverImage()
        cover_dummy.set_hexpand(False)
        self.unidentified_row.add_prefix(cover_dummy)
        self.unidentified_row.bind_model(self.files_unidentified, self.unidentified_row_create)

        self.content_listbox.append(self.unidentified_row)

        self.identify_task.bind_property(
            'progress', self.id_progress, 'fraction'
        )
        self.identify_task.connect('task-done', self.on_identify_done)

        self.apply_task.bind_property(
            'progress', self.id_progress, 'fraction'
        )
        self.apply_task.connect('task-done', self.on_apply_done)

        self.files.splice(0, self.files.get_n_items(), self.file_manager.selected_files.copy())

        self.connect('close-request', self.on_close_request)

    def on_close_request(self, *args):
        for row in self.release_rows.values():
            row.unbind()
        self.release_rows = {}
        self.parent.file_view.more_tags_expander.slow_refresh_entries()

    def unidentified_row_create(self, file, *args):
        return EartagIdentifyFileRow(file)

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        if self.identify_task.is_running:
            self.identify_task.stop()
        if self.apply_task.is_running:
            self.apply_task.stop()
        self.files = None
        self.close()

    @Gtk.Template.Callback()
    def do_identify(self, *args):
        self.identify_button.set_sensitive(False)
        self.apply_button.set_sensitive(False)
        self.end_button_stack.set_visible_child(self.apply_button)

        self.identify_task.reset()
        self.identify_task.run()

    def _identify_set_recording(self, file, rec):
        try:
            rec.release
        except ValueError:
            rec.release = rec.available_releases[0]

        self.recordings[file.id] = rec
        self.recordings_model.append(rec)

        if rec.release.release_id in self.release_rows:
            row = self.release_rows[rec.release.release_id]
            row._filter_changed = False
            GLib.idle_add(row.update_filter)
            while not row._filter_changed:
                time.sleep(0.1)
            self.release_rows[rec.release.release_id].update_filter()
            row._filter_changed = False
        else:
            self.release_rows[rec.release.release_id] = \
                EartagIdentifyReleaseRow(self, rec.release)
            GLib.idle_add(
                self.content_listbox.prepend,
                self.release_rows[rec.release.release_id]
            )

        self._filter_changed = False
        GLib.idle_add(
            self.unidentified_filter.changed,
            Gtk.FilterChange.DIFFERENT
        )

        self.apply_files.append(file.id)

        # Prevent weird errors by waiting a bit for the filter to update
        while not self._filter_changed:
            time.sleep(0.1)

        self._filter_changed = False

    def identify_files(self, *args, **kwargs):
        progress_step = 1 / len(self.files)

        for file in self.files:
            if self.identify_task.halt:
                self.identify_task.emit_task_done()
                return

            unid_index = find_in_model(self.files_unidentified, file)
            if unid_index < 0:
                n = 0
                _file = self.files_unidentified.get_item(n)
                while _file:
                    if _file.id == file.id:
                        unid_index = n
                        break
                    n += 1
                    _file = self.files_unidentified.get_item(n)

            if unid_index < 0:
                print("Could not find file in unidentifed filter, this should never happen!")
                continue

            unid_row = self.unidentified_row.get_row_at_index(unid_index)
            GLib.idle_add(unid_row.start_loading)

            recordings = []

            if file.title and file.artist:
                recordings = get_recordings_for_file(file)

            # Halt again if needed; the previous operation takes a while
            if self.identify_task.halt:
                self.identify_task.emit_task_done()
                return

            if not recordings or len(recordings) > 1:
                id_confidence, id_recording = acoustid_identify_file(file)

                # Make sure the recording we got from AcoustID matches the
                # file we have:
                if id_recording:
                    match = True
                    if file.title and not reg_and_simple_cmp(id_recording.title, file.title):
                        match = False

                    if file.album:
                        try:
                            id_recording.release
                        except ValueError:  # multiple releases
                            match = False
                            for rel in id_recording.available_releases:
                                if reg_and_simple_cmp(rel.title, file.album):
                                    match = True
                                    break
                        else:
                            if not reg_and_simple_cmp(id_recording.album, file.album):
                                match = False

                    if match:
                        recordings = [id_recording]

            # Halt again if needed; the previous operation takes a while
            if self.identify_task.halt:
                self.identify_task.emit_task_done()
                return

            if recordings:
                rec = recordings[0]
                if not rec.available_releases:
                    GLib.idle_add(unid_row.mark_as_unidentified)
                else:
                    self._identify_set_recording(file, rec)
                    self.identify_task.increment_progress(progress_step)
            else:
                GLib.idle_add(unid_row.mark_as_unidentified)

        # Once we have identified all the files we could, check in
        # the releases we have to make sure we can't find other tracks
        # (MusicBrainz lookups tend to lose a few tracks on the way):
        for file in list(self.files_unidentified).copy():
            if self.identify_task.halt:
                self.identify_task.emit_task_done()
                return

            rec = None
            for row in self.release_rows.values():
                rel = row.release

                # Check if the release matches our artist and album
                if rel.artist != file.artist and \
                        not simplify_compare(rel.artist, file.artist):
                    continue

                if file.album:
                    if rel.title != file.album and \
                            not simplify_compare(rel.title, file.album):
                        continue

                for track in row.release.tracks:
                    # Halt again if needed; the previous operation takes a while
                    if self.identify_task.halt:
                        self.identify_task.emit_task_done()
                        return

                    if reg_and_simple_cmp(track['title'], file.title):
                        try:
                            rec = MusicBrainzRecording(track['recording']['id'], file=file)
                            if rec:
                                self._identify_set_recording(file, rec)
                                break
                        except ValueError:
                            pass
                if rec:
                    break
            if rec:
                continue

            self.identify_task.increment_progress(progress_step)

        # Sometimes, a single track will end up getting misidentified as part
        # of another release; look through "small releases" and try to group
        # them into larger releases.

        small_rels = []
        big_rels = []
        for rel in [row.release for row in self.release_rows.values()]:
            if rel.totaltracknumber < 2:
                small_rels.append(rel)
            else:
                big_rels.append(rel)

        for s_rel in small_rels:
            for s_track in s_rel.tracks:
                for b_rel in big_rels:
                    for b_track in b_rel.tracks:
                        if simplify_compare(s_track['title'], b_track['title']):
                            for rec in self.release_rows[s_rel.release_id].recordings:
                                rec.release = b_rel
                            GLib.idle_add(
                                self.content_listbox.remove,
                                self.release_rows[s_rel.release_id]
                            )
                            del self.release_rows[s_rel.release_id]

        # At the very end, go back through available release groups and try
        # to find common releases to group together.
        # TODO: This code could probably be modified to use less loops,
        # but this current iteration is focused more on accuracy and clear
        # code than speed.

        groups = {}  # group ID: releases for this group
        for rel in [row.release for row in self.release_rows.values()]:
            if rel.group.relgroup_id not in groups:
                groups[rel.group.relgroup_id] = [rel]
            else:
                groups[rel.group.relgroup_id].append(rel)

        for group_id, our_releases in groups.items():
            if self.identify_task.halt:
                self.identify_task.emit_task_done()
                return

            group = MusicBrainzReleaseGroup.setup_from_id(group_id)
            if len(group.releases) == 1:
                self.release_rows[group.releases[0].release_id].refresh_alternative_releases(
                    [group.releases[0]]
                )

                continue
            releases = group.releases.copy()

            # (Explaination of the rf variable: this allows us to preserve the
            # loop order, since just doing a list.insert(list.pop(list.index(...)))
            # manouver would cause the releases to go in backwards order which would
            # throw off our existing order.)

            # Prioritize releases we already found
            rf = []
            for rel in releases.copy():
                if rel in our_releases:
                    rf.append(rel)
            releases = rf + [r for r in releases if r not in rf]

            # The previous operation might take a while, halt if needed
            if self.identify_task.halt:
                self.identify_task.emit_task_done()
                return

            rel_recordings = {}  # recording: file

            # Get a list of recordings for this release group, and the files
            # they represent
            for rel in our_releases:
                for file_id, rec in self.recordings.items():
                    if rec.release == rel:
                        for file in self.files:
                            if file.id == file_id:
                                rel_recordings[rec] = file

            # rel_files = dict((v,k) for k,v in rel_recordings.items())

            # Now that we have all the data we need, proceed with the
            # grouping heuristics:

            preferred_release = None

            # HEURISTIC 1
            # If our files have an album name, and if it's the same for all
            # of them, prioritize the releases that match the album name
            # (in simple match or not).

            if all_equal([f.album for f in rel_recordings.values()]) and \
                    list(rel_recordings.values())[0].album:
                _album = list(rel_recordings.values())[0].album

                rf = []
                for rel in releases.copy():
                    if simplify_compare(rel.title, _album):
                        rf.append(rel)
                releases = rf + [r for r in releases if r not in rf]

            # HEURISTIC 2
            # If our files have a total track number, and if it's the same
            # for all of them, prioritize the releases with the same amount
            # of tracks.
            # (If we don't have a total track number, try to guess from the
            # amount of matching recordings, so long as that number is
            # plausibly high (> 2).)

            _total_tracks = None

            if all_equal([f.totaltracknumber for f in rel_recordings.values()]):
                _total_tracks = self.files[0].totaltracknumber

            if not _total_tracks and len(rel_recordings) > 2:
                _total_tracks = len(rel_recordings)

            if _total_tracks:
                rf = []
                for rel in releases.copy():
                    if rel.totaltracknumber == _total_tracks:
                        rf.append(rel)
                releases = rf + [r for r in releases if r not in rf]

            # HEURISTIC 3:
            # Remove releases that aren't present in all recordings.
            for rec in rel_recordings:
                for rel in releases.copy():
                    if rel.release_id not in [r.release_id for r in rec.available_releases]:
                        releases.remove(rel)

            # If we end up with no releases after this, continue.
            if not releases:
                continue

            # Once we have ran our releases list through all the releases,
            # pick the first one we got:

            preferred_release = releases[0]

            # This release will now be applied to all matching recordings.

            for rec in rel_recordings:
                rec.release = preferred_release

                if rec.release.release_id in self.release_rows:
                    self.release_rows[rec.release.release_id].update_filter()
                else:
                    self.release_rows[rec.release.release_id] = \
                        EartagIdentifyReleaseRow(self, rec.release)
                    GLib.idle_add(
                        self.content_listbox.prepend,
                        self.release_rows[rec.release.release_id]
                    )

            self.release_rows[preferred_release.release_id].refresh_alternative_releases(
                [rel for rel in releases if rel.totaltracknumber >= len(rel_recordings)]
            )

            for k, row in list(self.release_rows.items()).copy():
                row.update_filter()

                if row._rec_filter_model.get_n_items() == 0:
                    del self.release_rows[k]
                    GLib.idle_add(self.content_listbox.remove, row)

        self.identify_task.emit_task_done()

    def on_identify_done(self, task, *args):
        try:
            identified = self.files.get_n_items() - self.files_unidentified.get_n_items()
        except AttributeError:  # this happens when the operation is cancelled
            return
        self.apply_button.set_sensitive(bool(identified))
        for relrow in self.release_rows.values():
            relrow.toggle_apply_sensitivity(True)
        if not self.files_unidentified.get_n_items():
            self.unidentified_row.set_visible(False)

    @Gtk.Template.Callback()
    def do_apply(self, *args):
        self.apply_button.set_sensitive(False)
        for relrow in self.release_rows.values():
            relrow.toggle_apply_sensitivity(False)

        self.apply_task.reset()
        self.apply_task.run()

    def apply_func(self, *args, **kwargs):
        files = [file for file in self.files if file.id in self.apply_files]
        if not files:
            self.apply_task.emit_task_done()
            return

        progress_step = 1 / len(files)

        for file in files:
            if self.apply_task.halt:
                self.apply_task.emit_task_done()
                return

            rec = self.recordings[file.id]
            rec.release.update_covers()
            GLib.idle_add(rec.apply_data_to_file, file)
            self.apply_task.increment_progress(progress_step)

        self.apply_task.emit_task_done()

    def on_apply_done(self, *args):
        self.file_manager.emit('refresh-needed')
        try:
            identified = self.files.get_n_items() - self.files_unidentified.get_n_items()
        except AttributeError:  # this happens when the operation is cancelled
            return
        self.parent.toast_overlay.add_toast(
            Adw.Toast.new(_("Identified {identified} out of {total} tracks").format(
                identified=identified, total=self.files.get_n_items()
            ))
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
