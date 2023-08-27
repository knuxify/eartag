"""
Contains code for interacting with the MusicBrainz API.
"""

import acoustid
import json
import magic
import mimetypes
import traceback
import tempfile
import urllib
import urllib.parse
import urllib.request

from gi.repository import GObject

try:
    from . import ACOUSTID_API_KEY, VERSION
except ImportError:  # handle test suite import
    from tests.common import ACOUSTID_API_KEY, VERSION
    USER_AGENT = f'Ear Tag (Test suite)/{VERSION} (https://gitlab.gnome.org/World/eartag)'
    TEST_SUITE = True
else:
    USER_AGENT = f'Ear Tag/{VERSION} (https://gitlab.gnome.org/World/eartag)'
    TEST_SUITE = False

def title_case_preserve_uppercase(text: str):
    return ' '.join([
        x.isupper() and x or x.capitalize()
        for x in text.split(' ')
    ])

def make_request(url, raw=False):
    """Wrapper for urllib.request.Request that handles the setup."""
    headers = {"User-Agent": USER_AGENT}
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request) as data_raw:
            if raw:
                data = data_raw.read()
            else:
                data = json.loads(data_raw.read())
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        elif e.code == 503:
            # TODO: retry?
            return None
        else:
            traceback.print_exc()
            return None
    except:
        traceback.print_exc()
        return None

    return data

def build_url(endpoint, id='', **kwargs):
    """Builds a MusicBrainz API endpoint URL."""
    args = []
    for argname, argdata in kwargs.items():
        if isinstance(argdata, list) or isinstance(argdata, tuple):
            argdata = "+".join(argdata)
        args.append(f'{argname}={urllib.parse.quote(argdata, encoding="utf-8")}')
    if id:
        return f'https://musicbrainz.org/ws/2/{endpoint}/{id}?{"&".join(args)}&fmt=json'
    return f'https://musicbrainz.org/ws/2/{endpoint}?{"&".join(args)}&fmt=json'

def get_recordings_for_file(file):
    """
    Takes an EartagFile and returns a list of MusicBrainzRecording objects
    that might match the query.
    """
    if not file.title or not file.artist:
        raise ValueError("Not enough data for a query; need at least title and artist")

    query_data = {
        'recording': file.title,
        'artist': file.artist,
        'release': file.album or '',
    }

    search_data = make_request(
        build_url('recording', '', query=' AND '.join(
            [f'{k}:{urllib.parse.quote_plus(v)}' for k, v in query_data.items() if v]
        ))
    )

    if 'recordings' not in search_data or not search_data['recordings']:
        return []

    return [
        MusicBrainzRecording(r['id'], file) for r in search_data['recordings']
        if r['score'] >= 75
    ]

class MusicBrainzRecording(GObject.Object):
    __gtype_name__ = 'MusicBrainzRecording'

    SELECT_RELEASE_FIRST = -1

    def __init__(self, recording_id=None, file=None):
        super().__init__()
        self._recording_id = None
        if file:
            self._album = file.album
        else:
            self._album = None
        self._release = MusicBrainzRecording.SELECT_RELEASE_FIRST
        self.recording_id = recording_id

    def dispose(self):
        self.release.dispose()

    def update_data(self):
        """Updates the internal data struct."""
        self.mb_data = make_request(
            build_url('recording', self._recording_id,
                inc=('releases', 'genres', 'artist-credits', 'media')
            )
        )

        self.available_releases = self.get_releases()
        if len(self.available_releases) == 1:
            self.release = self.available_releases[0]
        elif self._album:
            album_rels = [r for r in self.available_releases if r.title == self._album]
            if len(album_rels) == 1:
                self.release = album_rels[0]

    def apply_data_to_file(self, file):
        """
        Takes an EartagFile and applies the data from this recording to it.
        """
        self.release.update_covers()
        for prop in ('title', 'artist', 'album', 'genre', 'albumartist', 'releasedate',
                'tracknumber', 'totaltracknumber', 'front_cover_path', 'back_cover_path'):
            if self.get_property(prop):
                file.set_property(prop, self.get_property(prop))

    @GObject.Property(type=str)
    def recording_id(self):
        """ID of the MusicBrainz recording."""
        return self._recording_id

    @recording_id.setter
    def recording_id(self, value):
        if self._recording_id == value:
            return
        self._recording_id = value
        if value:
            self.update_data()

    def get_releases(self):
        """Returns a list of MusicBrainzRelease object that match the file."""
        releases = []
        for release in self.mb_data['releases']:
            releases.append(MusicBrainzRelease(release))
        return releases

    @GObject.Property()
    def release(self):
        """The MusicBrainz Release for this recording."""
        if self._release == MusicBrainzRecording.SELECT_RELEASE_FIRST:
            raise ValueError("Multiple releases available, select one first")
        return self._release

    @release.setter
    def release(self, value):
        self._release = value

    @GObject.Property(type=str)
    def title(self):
        return self.mb_data['title']

    @GObject.Property(type=str)
    def artist(self):
        return self.mb_data['artist-credit'][0]['name']

    @GObject.Property(type=str)
    def album(self):
        return self.release.title

    @GObject.Property(type=str)
    def albumartist(self):
        return self.release.artist

    @GObject.Property(type=str)
    def genre(self):
        if 'genres' in self.mb_data and self.mb_data['genres']:
            return title_case_preserve_uppercase(self.mb_data['genres'][0]['name'])
        return self.release.genre

    @GObject.Property(type=int)
    def tracknumber(self):
        return int(self.release.mb_data['media'][0]['tracks'][0]['number'])

    @GObject.Property(type=int)
    def totaltracknumber(self):
        return int(self.release.mb_data['media'][0]['track-count'])

    @GObject.Property(type=str)
    def releasedate(self):
        return self.release.releasedate

    @GObject.Property(type=str)
    def thumbnail_path(self):
        return self.release.thumbnail_path

    @GObject.Property(type=str)
    def front_cover_path(self):
        return self.release.front_cover_path

    @GObject.Property(type=str)
    def back_cover_path(self):
        return self.release.back_cover_path

class MusicBrainzRelease(GObject.Object):
    __gtype_name__ = 'MusicBrainzRelease'

    NEED_UPDATE_COVER = -2

    cover_cache = {}

    def __init__(self, release_data):
        super().__init__()
        self.mb_data = release_data
        self.cover_tempfiles = {
            'thumbnail': None,
            'front': MusicBrainzRelease.NEED_UPDATE_COVER,
            'back': MusicBrainzRelease.NEED_UPDATE_COVER
        }
        self.update_thumbnail()

    """
    def dispose(self):
        for tempfile in self.cover_tempfiles.values():
            if tempfile:
                tempfile.close()
    """

    @GObject.Property(type=str)
    def release_id(self):
        return self.mb_data['id']

    @GObject.Property(type=str)
    def title(self):
        return self.mb_data['title']

    @GObject.Property(type=str)
    def artist(self):
        return self.mb_data['artist-credit'][0]['name']

    @GObject.Property(type=str)
    def genre(self):
        if 'genres' in self.mb_data and self.mb_data['genres']:
            return title_case_preserve_uppercase(self.mb_data['genres'][0]['name'])
        return ''

    @GObject.Property(type=str)
    def releasedate(self):
        if 'first-release-date' in self.mb_data:
            return self.mb_data['first-release-date']
        return ''

    @GObject.Property(type=str)
    def thumbnail_path(self):
        if not self.cover_tempfiles['thumbnail']:
            return ''
        return self.cover_tempfiles['thumbnail'].name

    @GObject.Property(type=str)
    def front_cover_path(self):
        if not self.cover_tempfiles['front']:
            return ''
        elif self.cover_tempfiles['front'] == MusicBrainzRelease.NEED_UPDATE_COVER:
            raise ValueError("Covers have not been downloaded yet; run update_covers()")
        return self.cover_tempfiles['front'].name

    @GObject.Property(type=str)
    def back_cover_path(self):
        if not self.cover_tempfiles['back']:
            return ''
        elif self.cover_tempfiles['back'] == MusicBrainzRelease.NEED_UPDATE_COVER:
            raise ValueError("Covers have not been downloaded yet; run update_covers()")
        return self.cover_tempfiles['back'].name

    def update_thumbnail(self):
        """Downloads the thumbnail for the release from coverartarchive.org"""
        url = f'https://coverartarchive.org/release/{self.release_id}/front-250'
        if url in MusicBrainzRelease.cover_cache:
            self.cover_tempfiles['thumbnail'] = MusicBrainzRelease.cover_cache[url]
            return

        data = make_request(url, raw=True)
        if not data:
            return

        cover_extension = mimetypes.guess_extension(magic.from_buffer(data, mime=True))
        self.cover_tempfiles['thumbnail'] = tempfile.NamedTemporaryFile(
            suffix=cover_extension
        )
        self.cover_tempfiles['thumbnail'].write(data)
        self.cover_tempfiles['thumbnail'].flush()
        MusicBrainzRelease.cover_cache[url] = self.cover_tempfiles['thumbnail']

    def update_covers(self):
        """Downloads the covers for the release from coverartarchive.org"""
        for cover in ('front', 'back'):
            url = f'https://coverartarchive.org/release/{self.release_id}/{cover}'
            if TEST_SUITE:
                # For the test suite, we don't want to download the full-size images,
                # because this takes a significant amount of time and bandwidth -
                # not ideal for rapid testing.
                url += '-250'
            if url in MusicBrainzRelease.cover_cache:
                self.cover_tempfiles[cover] = MusicBrainzRelease.cover_cache[url]
                continue

            data = make_request(url, raw=True)
            if not data:
                self.cover_tempfiles[cover] = ''
                continue

            cover_extension = mimetypes.guess_extension(magic.from_buffer(data, mime=True))
            self.cover_tempfiles[cover] = tempfile.NamedTemporaryFile(
                suffix=cover_extension
            )
            self.cover_tempfiles[cover].write(data)
            self.cover_tempfiles[cover].flush()
            MusicBrainzRelease.cover_cache[url] = self.cover_tempfiles[cover]


def update_from_musicbrainz(file):
    """
    Takes an EartagFile with MusicBrainz ID tags set and updates the tags
    of the file to match.
    """
    if not file.musicbrainz_recording_id:
        raise ValueError("Missing recording_id")

    if not file.musicbrainz_release_id:
        raise ValueError("Missing release_id")

    rec = MusicBrainzRecording(file.musicbrainz_recording_id)
    if not rec:
        return False

    if len(rec.available_releases) > 1:
        rel = None
        for r in rec.available_releases:
            if r.release_id == file.musicbrainz_release_id:
                rel = r
                break
        if not rel:
            rel = rec.available_releases[0]
            rec.release = rel
            file.musicbrainz_release_id = rel.release_id
    else:
        rel = rec.release

    if not rel:
        return False

    rec.apply_data_to_file(file)

    return True


def acoustid_identify_file(file):
    """
    Uses AcoustID and Chromaprint to identify a track's data, and
    fills it automatically. Returns False if a track could not be
    identified, the match confidence percentage otherwise.
    """
    try:
        results = acoustid.match(ACOUSTID_API_KEY, file.path, parse=False)
        if 'results' not in results or not results['results']:
            print(results)
            return False
    except:
        traceback.print_exc()
        return False

    acoustid_data = results['results'][0]

    musicbrainz_id = acoustid_data['recordings'][0]['id']

    rec = MusicBrainzRecording(musicbrainz_id)
    rec.apply_data_to_file(file)

    return acoustid_data['score']
