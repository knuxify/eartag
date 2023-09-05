# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import Adw, Gtk, GLib, Gio, GObject, GdkPixbuf

import os

from .common import EartagBackgroundTask, EartagModelExpanderRow, find_in_model
from .musicbrainz import acoustid_identify_file, get_recordings_for_file, MusicBrainzRecording, MusicBrainzRelease
from .sidebar import EartagFileList # noqa: F401
from .backends.file import EartagFile

# TODO: this should be configurable
ACOUSTID_CONFIDENCE_TRESHOLD = 85.0

@Gtk.Template(resource_path='/app/drey/EarTag/ui/identifycoverimage.ui')
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


@Gtk.Template(resource_path='/app/drey/EarTag/ui/identifyreleaserow.ui')
class EartagIdentifyReleaseRow(EartagModelExpanderRow):
    """
    Representation of MusicBrainz releases for the ItemRow
    dropdowns.
    """
    __gtype_name__ = 'EartagIdentifyMusicBrainzRow'

    def __init__(self):
        super().__init__()
        self._bindings = []
        self.obj = None

    def bind_to_release(self, release):
        """Takes a MusicBrainzRelease and binds to it."""
        self.release = release
        self.unbind()
        self._bindings = [
            self.release.bind_property('thumbnail_path', self.cover_image, 'cover_path'),
            self.release.bind_property('title', self, 'title'),
        ]
        self._connections = [
            self.release.connect('notify::artist', self.update_subtitle),
            self.release.connect('notify::album', self.update_subtitle),
        ]
        self.update_subtitle()

    def unbind(self):
        for binding in self._bindings:
            binding.unbind()

        for conn in self._connections:
            self.release.disconnect(conn)

        self.release = None

    def update_subtitle(self, *args):
        self._subtitle = self.release.artist + ' • ' + self.release.album
        self.set_subtitle(self._subtitle)


@Gtk.Template(resource_path='/app/drey/EarTag/ui/identifyfilerow.ui')
class EartagIdentifyFileRow(Adw.ActionRow):
    """
    Representation of files recordings for the identify dialog.
    """
    __gtype_name__ = 'EartagIdentifyFileRow'

    cover_image = Gtk.Template.Child()

    suffix_stack = Gtk.Template.Child()
    loading_icon = Gtk.Template.Child()
    not_found_icon = Gtk.Template.Child()

    def __init__(self, file):
        super().__init__()
        self._bindings = []
        self.file = None

        self.connect('destroy', self.unbind)

        self.bind_to_file(file)

    def bind_to_file(self, file):
        self.file = file

        self._bindings = [
            self.file.bind_property('front_cover_path', self.cover_image, 'cover_path', GObject.BindingFlags.SYNC_CREATE),
            self.file.bind_property('title', self, 'title', GObject.BindingFlags.SYNC_CREATE),
        ]
        self._connections = [
            self.file.connect('notify::artist', self.update_subtitle),
            self.file.connect('notify::album', self.update_subtitle),
        ]
        self.update_subtitle()

    def unbind(self, *args):
        for row in self.recording_rows + self.release_rows:
            row.unbind()

        self.file = None

    @GObject.Property(type=MusicBrainzRecording)
    def recording(self):
        return self._recording

    @recording.setter
    def recording(self, value):
        self._recording = value

    @GObject.Property(type=MusicBrainzRelease)
    def release(self):
        return self._release

    @release.setter
    def release(self, value):
        self._release = value

    def fill_recordings_releases(self):
        recordings = get_recordings_for_file(self.file)
        if recordings:
            self.recordings.splice(0, self.recordings.get_n_items(), recordings)
            self.recording = self.recordings.get_item(0)
            self.not_found_icon.set_visible(False)
        else:
            self.set_expanded(False)
            self.set_sensitive(True)
            self.not_found_icon.set_visible(True)

    def select_release_by_id(self, id):
        for rel in self.available_releases:
            if rel.release_id == id:
                self.release = rel
                return True
        return False

    def update_subtitle(self, *args):
        self._subtitle = f'{self.file.artist or 'N/A'} • {self.file.album or 'N/A'}' \
            + f' ({os.path.basename(file.path)})'
        self.set_subtitle(self._subtitle)

    def start_loading(self):
        self.suffix_stack.set_visible(True)
        self.suffix_stack.set_visible_child(self.loading_icon)
        self.loading_icon.start()

    def mark_as_unidentified(self):
        self.suffix_stack.set_visible_child(self.not_found_icon)
        self.loading_icon.stop()


@Gtk.Template(resource_path='/app/drey/EarTag/ui/identify.ui')
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
        self.files_unidentified = Gtk.FilterListModel(
            model=self.files,
            filter=self.unidentified_filter
        )
        self.recordings = {}  # file.id: EartagMusicBrainzRecording
        self.apply_files = []
        self.release_rows = {}  # release.id: EartagIdentifyReleaseRow

        self.identified_files = 0
        self.identify_task = EartagBackgroundTask(self.identify_files)
        self.apply_task = EartagBackgroundTask(self.apply_func)

        # For some reason we can't create this from the template, so it
        # has to be added here:
        self.unidentified_row = EartagModelExpanderRow()
        self.unidentified_row.set_title(_('Unidentified Files'))
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
                    _file = self.files_unidentified.get_item(n)

            if unid_index < 0:
                print("Could not find file in unidentifed filter, this should never happen!")
                continue

            unid_row = self.unidentified_row.get_row_at_index(unid_index)
            GLib.idle_add(unid_row.start_loading)

            recordings = []

            if file.title and file.artist:
                recordings = get_recordings_for_file(file)

            if not recordings or len(recordings) > 1:
                id_confidence, id_recording = acoustid_identify_file(file)
                if id_confidence >= ACOUSTID_CONFIDENCE_TRESHOLD and id_recording:
                    recordings = [id_recording]

            if recordings:
                rec = recordings[0]
                self.recordings[file.id] = rec

                if rec.release.release_id in self.release_rows:
                    self.release_rows[rec.release.release_id].update_filter()
                else:
                    self.release_rows[rec.release.release_id] = \
                        EartagIdentifyReleaseRow(rec.release)

                GLib.idle_add(
                    self.unidentified_filter.changed,
                    Gtk.FilterChange.MORE_STRICT
                )
                self.apply_files.append(file.id)
            else:
                GLib.idle_add(unid_row.mark_as_unidentified)

            self.identify_task.increment_progress(progress_step)

        self.identify_task.emit_task_done()

    def on_identify_done(self, task, *args):
        self.apply_button.set_sensitive(True)
        # TODO: add toggle for all files

    @Gtk.Template.Callback()
    def do_apply(self, *args):
        self.apply_button.set_sensitive(False)
        self.content_listbox.set_sensitive(False)

        self.apply_task.reset()
        self.apply_task.run()

    def apply_func(self, *args, **kwargs):
        files = [file for file in self.files if file.id in self.apply_files]
        progress_step = 1 / len(files)

        for file in files:
            rec = self.recordings[file.id]
            rec.apply_data_to_file(file)
            self.apply_task.increment_progress(progress_step)

        self.apply_task.emit_task_done()

    def on_apply_done(self, *args):
        self.file_manager.emit('refresh-needed')
        self.parent.toast_overlay.add_toast(
            Adw.Toast.new(_("Identified {identified} out of {total} tracks").format(
                identified=self.identified_files, total=len(self.files)
            ))
        )
        self.files = None
        #self.identify_task = None
        #self.apply_task = None
        #self.close()

    def unidentified_filter_func(self, file, *args):
        return file.id not in self.recordings
