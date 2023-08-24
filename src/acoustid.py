# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from . import ACOUSTID_API_KEY, VERSION
import acoustid
import json
import urllib
import tempfile
import traceback
import magic
import mimetypes
from gi.repository import Adw, Gtk, GLib

from .common import EartagBackgroundTask
from .sidebar import EartagFileList # noqa: F401

def identify_file(file):
    """
    Uses AcoustID and Chromaprint to identify a track's data, and
    fills it automatically. Returns False if a track could not be
    identified, the match confidence percentage otherwise.
    """
    try:
        results = acoustid.match(ACOUSTID_API_KEY, file.path, parse=False)
        if 'results' not in results or not results['results']:
            return False
    except:
        return False

    acoustid_data = results['results'][0]

    musicbrainz_id = acoustid_data['recordings'][0]['id']

    headers = {"User-Agent": f'Ear Tag {VERSION} (https://gitlab.gnome.org/World/eartag)'}
    try:
        musicbrainz_request = urllib.request.Request(
            f'https://musicbrainz.org/ws/2/recording/{musicbrainz_id}?inc=releases+genres+artist-credits+media&fmt=json', # noqa: E501
            headers=headers
        )
        with urllib.request.urlopen(musicbrainz_request) as musicbrainz_data_raw:
            musicbrainz_data = json.loads(musicbrainz_data_raw.read())
            assert 'error' not in musicbrainz_data
    except:
        traceback.print_exc()
        return False

    has_releases = False
    if 'releases' in musicbrainz_data and musicbrainz_data['releases']:
        has_releases = True

        musicbrainz_release = musicbrainz_data['releases'][0]

        coverart_request = urllib.request.Request(
            f'https://coverartarchive.org/release/{musicbrainz_release["id"]}/front',
            headers=headers
        )
        has_coverart = True
        try:
            with urllib.request.urlopen(coverart_request) as coverart_data_raw:
                coverart_data = coverart_data_raw.read()
        except:
            has_coverart = False
            pass

    file.title = acoustid_data['recordings'][0]['title']
    file.artist = acoustid_data['recordings'][0]['artists'][0]['name']

    if has_releases:
        file.album = musicbrainz_release['title']
        if musicbrainz_release['artist-credit']:
            file.albumartist = musicbrainz_release['artist-credit'][0]['artist']['name']
        if 'media' in musicbrainz_release and musicbrainz_release['media'] and \
                'tracks' in musicbrainz_release['media'][0]:
            file.tracknumber = int(musicbrainz_release['media'][0]['tracks'][0]['number'])
            file.totaltracknumber = musicbrainz_release['media'][0]['track-count']

    if 'genres' in musicbrainz_data and musicbrainz_data['genres']:
        file.genre = ' '.join([
            x.isupper() and x or x.capitalize()
            for x in musicbrainz_data['genres'][0]['name'].split(' ')
        ])
    elif has_releases and 'genres' in musicbrainz_release and musicbrainz_release['genres']:
        file.genre = ' '.join([
            x.isupper() and x or x.capitalize()
            for x in musicbrainz_release['genres'][0]['name'].split(' ')
        ])

    if has_coverart:
        cover_extension = mimetypes.guess_extension(magic.from_buffer(coverart_data))
        coverart_tempfile = tempfile.NamedTemporaryFile(
            suffix=cover_extension
        )
        coverart_tempfile.write(coverart_data)
        coverart_tempfile.flush()
        file.front_cover_path = coverart_tempfile.name
    file.releasedate = musicbrainz_data['first-release-date']

    return acoustid_data['score']

@Gtk.Template(resource_path='/app/drey/EarTag/ui/acoustid.ui')
class EartagAcoustIDDialog(Adw.Window):
    __gtype_name__ = 'EartagAcoustIDDialog'

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
        if not self.selected_files_filelist.file_manager:
            self.selected_files_filelist.set_file_manager(self.file_manager)
            self.selected_files_filelist.setup_for_selected()

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
                lambda *args: self.selected_files_filelist._widgets[file.id].\
                    acoustid_loading_icon.start()
            )
            try:
                identify_result = identify_file(file)
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
