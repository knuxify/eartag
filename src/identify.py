# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

"""
The actual AcoustID integration has been moved to the musicbrainz.py file.
"""

from gi.repository import Adw, Gtk, GLib, Gio, GObject

from .common import EartagBackgroundTask
from .musicbrainz import acoustid_identify_file, get_recordings_for_file, MusicBrainzRecording, MusicBrainzRelease
from .sidebar import EartagFileList # noqa: F401

@Gtk.Template(resource_path='/app/drey/EarTag/ui/identifyitemrow.ui')
class EartagIdentifyItemRow(Adw.ExpanderRow):
    """
    Representation of files recordings for the identify dialog.
    """
    __gtype_name__ = 'EartagIdentifyItem'

    def __init__(self):
        super().__init__()
        self._bindings = []
        self.obj = None

        self.recordings = Gio.ListStore(type=MusicBrainzRecording)
        self.releases = Gio.ListStore(type=MusicBrainzRecording)

        self.connect('on_destroy', self.unbind)

    def bind_to_file(self, file):
        self.file = file

        self._bindings = [
            self.file.bind_property('front_cover_path', self.cover_image, 'cover_path'),
            self.file.bind_property('title', self, 'title'),
        ]
        self._connections = [
            self.file.connect('notify::artist', self.update_subtitle),
            self.file.connect('notify::album', self.update_subtitle),
        ]

    def unbind(self, *args):
        for row in self.recording_rows + self.release_rows:
            row.unbind()

        self.releases.splice(0, self.releases.get_n_items(), [])
        for rec in self.recordings:
            rec.dispose()
        self.recordings.splice(0, self.recordings.get_n_items(), [])

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

    def update_subtitle(self, *args):
        self._subtitle = self.file.artist + ' • ' + self.file.album
        self.set_subtitle(self._subtitle)

@Gtk.Template(resource_path='/app/drey/EarTag/ui/identifymusicbrainzrow.ui')
class EartagIdentifyMusicBrainzRow(Adw.ActionRow):
    """
    Representation of MusicBrainz recordings/releases for the ItemRow
    dropdowns.
    """
    __gtype_name__ = 'EartagIdentifyMusicBrainzRow'

    def __init__(self):
        super().__init__()
        self._bindings = []
        self.obj = None

    def bind_to_obj(self, obj):
        """Takes a MusicBrainzRecording or MusicBrainzRelease and binds to it."""
        self.obj = obj
        self.unbind()
        self._bindings = [
            self.obj.bind_property('thumbnail_path', self.cover_image, 'cover_path'),
            self.obj.bind_property('title', self, 'title'),
        ]
        self._connections = [
            self.obj.connect('notify::artist', self.update_subtitle),
            self.obj.connect('notify::album', self.update_subtitle),
        ]
        self.update_subtitle()

    def unbind(self):
        for binding in self._bindings:
            binding.unbind()

        for conn in self._connections:
            self.obj.disconnect(conn)

        self.obj = None

    def update_subtitle(self, *args):
        self._subtitle = self.obj.artist + ' • ' + self.obj.album
        self.set_subtitle(self._subtitle)

@Gtk.Template(resource_path='/app/drey/EarTag/ui/identify.ui')
class EartagIdentifyDialog(Adw.Window):
    __gtype_name__ = 'EartagIdentifyDialog'

    id_progress = Gtk.Template.Child()
    selected_files_filelist = Gtk.Template.Child()

    cancel_button = Gtk.Template.Child()
    rename_button = Gtk.Template.Child()

    def __init__(self, window):
        super().__init__(modal=True, transient_for=window)
        self.parent = window
        self.file_manager = window.file_manager
        self.identified_files = 0
        self.identify_task = EartagBackgroundTask(self.identify_files)

        self.identify_task.bind_property(
            'progress', self.id_progress, 'fraction'
        )
        self.identify_task.connect('notify::progress', self.update_progress)
        self.identify_task.connect('task-done', self.on_done)

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        if self.identify_task.is_running:
            self.identify_task.stop()
        else:
            self.files = None
            self.close()

    @Gtk.Template.Callback()
    def do_identify(self, *args):
        self.rename_button.set_sensitive(False)

        for widget in self.selected_files_filelist._widgets.values():
            widget.acoustid_info_stack.set_visible_child(widget.acoustid_loading_icon)
            widget.acoustid_info_stack.set_visible(True)

        self.files = list(self.selected_files_filelist.filter_model).copy()
        self._identify_order = [file.id for file in self.files]
        self.results = {}
        self.identify_task.reset()
        self.identify_task.run()

    def identify_files(self, *args, **kwargs):
        progress_step = 1 / len(self.files)

        for file in self.files:
            if self.identify_task.halt:
                self.identify_task.emit_task_done()
                return
            GLib.idle_add(
                lambda *args: self.selected_files_filelist._widgets[file.id].
                    acoustid_loading_icon.start()
            )
            try:
                identify_result = acoustid_identify_file(file)
            except:
                self.results[file.id] = 0.00
            else:
                if identify_result:
                    self.results[file.id] = identify_result
                    self.identified_files += 1
                else:
                    self.results[file.id] = 0.00
            self.identify_task.increment_progress(progress_step)

        self.identify_task.emit_task_done()

    def update_progress(self, task, *args):
        fid = self._identify_order[round(task.progress * len(self.files))-1]
        if fid not in self.results:
            return
        widget = self.selected_files_filelist._widgets[fid]
        widget.acoustid_loading_icon.stop()
        widget.acoustid_info_label.set_label("{:0.2f}%".format(self.results[fid]*100))
        widget.acoustid_info_stack.set_visible_child(widget.acoustid_info_label)

    def on_done(self, task, *args):
        self.file_manager.emit('refresh-needed')
        self.parent.toast_overlay.add_toast(
            Adw.Toast.new(_("Identified {identified} out of {total} tracks").format(
                identified=self.identified_files, total=len(self.files)
            ))
        )
        self.files = None
        self.identify_task = None
        self.close()
