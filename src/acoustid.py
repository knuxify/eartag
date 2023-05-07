# acoustid.py
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

def identify_file(file):
    """
    Uses AcoustID and Chromaprint to identify a track's data, and
    fills it automatically. Returns False if a track could not be
    identified, True otherwise.
    """
    results = acoustid.match(ACOUSTID_API_KEY, file.path, parse=False)
    if 'results' not in results or not results['results']:
        return False

    acoustid_data = results['results'][0]

    musicbrainz_id = acoustid_data['recordings'][0]['id']

    headers = {"User-Agent": f'Ear Tag {VERSION} (https://gitlab.gnome.org/knuxify/eartag)'}
    musicbrainz_request = urllib.request.Request(
        f'https://musicbrainz.org/ws/2/recording/{musicbrainz_id}?inc=releases+genres+artist-credits+media&fmt=json', # noqa: E501
        headers=headers
    )
    try:
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
        file.cover_path = coverart_tempfile.name
    file.releasedate = musicbrainz_data['first-release-date']

    return True

@Gtk.Template(resource_path='/app/drey/EarTag/ui/acoustid.ui')
class EartagAcoustIDDialog(Adw.Window):
    __gtype_name__ = 'EartagAcoustIDDialog'

    id_progress = Gtk.Template.Child()

    def __init__(self, window):
        super().__init__(modal=True, transient_for=window)
        self.parent = window
        self.file_manager = window.file_manager
        self.identified_files = 0
        self.identify_task = EartagBackgroundTask(self.identify_files)

        self.identify_task.bind_property(
            'progress', self.id_progress, 'fraction'
        )
        self.identify_task.connect('task-done', self.on_done)

        self.files = list(self.file_manager.selected_files).copy()

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        self.files = None
        self.close()

    @Gtk.Template.Callback()
    def do_identify(self, *args):
        self.set_sensitive(False)

        self.identify_task.reset()
        self.identify_task.run()

    def identify_files(self, *args, **kwargs):
        progress_step = 1 / len(self.files)

        for file in self.files:
            if identify_file(file):
                self.identified_files += 1
            self.identify_task.increment_progress(progress_step)

        self.identify_task.emit_task_done()

    def on_done(self, task, *args):
        self.file_manager.emit('refresh-needed')
        self.file_manager.unselect_all()
        self.file_manager.select_file(self.files[0])
        self.parent.toast_overlay.add_toast(
            Adw.Toast.new(_("Identified {identified} out of {total} tracks").format(
                identified=self.identified_files, total=len(self.files)
            ))
        )
        self.files = None
        self.identify_task = None
        self.close()
