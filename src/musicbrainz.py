"""
Contains code for interacting with the MusicBrainz API.
"""

import acoustid
import json
import magic
import mimetypes
import tempfile
import time
import traceback
import urllib
import urllib.parse
import urllib.request
import unicodedata
import re

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

# TODO: this should be configurable
ACOUSTID_CONFIDENCE_TRESHOLD = 85
MUSICBRAINZ_CONFIDENCE_TRESHOLD = 85

def title_case_preserve_uppercase(text: str):
    return ' '.join([
        x.isupper() and x or x.capitalize()
        for x in text.split(' ')
    ])

def simplify_string(text: str):
    """
    Returns a "simplified string" that throws away non-alphanumeric
    characters for more accurate searches and comparisons.
    """
    # Step 1: Normalize Unicode characters
    instr = unicodedata.normalize('NFKC', text)
    # Step 2: Only leave lowercase alphanumeric letters
    instr = ''.join([
        l for l in instr.lower() if l.isalnum() or l == ' '
    ]).strip()
    # Step 3: Remove repeating spaces
    instr = re.sub(' +', ' ', instr)

    return instr

def simplify_compare(string1: str, string2: str):
    """
    Compares simplified representations of two strings and returns
    whether they're equal.
    """
    return simplify_string(string1) == simplify_string(string2)

def make_request(url, raw=False, _recursion=0):
    """Wrapper for urllib.request.Request that handles the setup."""
    if _recursion > 3:
        return None

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
            time.sleep(3)
            return make_request(url, raw=raw, _recursion=_recursion+1)
        else:
            traceback.print_exc()
            return None
    except urllib.error.URLError:
        time.sleep(3)
        return make_request(url, raw=raw, _recursion=_recursion+1)
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

    if not search_data or 'recordings' not in search_data or not search_data['recordings']:
        # Try to use simplified title/artist:
        query_data['title'] = simplify_string(file.title)
        if not query_data['title']:
            return []
        query_data['artist'] = simplify_string(file.title)
        if not query_data['artist']:
            return []

        search_data = make_request(
            build_url('recording', '', query=' AND '.join(
                [f'{k}:{urllib.parse.quote_plus(v)}' for k, v in query_data.items() if v]
            ))
        )
        if not search_data or 'recordings' not in search_data or not search_data['recordings']:
            return []

    ret = []
    for r in search_data['recordings']:
        if r['score'] < MUSICBRAINZ_CONFIDENCE_TRESHOLD:
            continue

        try:
            ret.append(MusicBrainzRecording(r['id'], file=file))
        except ValueError:
            pass

    return ret

class MusicBrainzRecording(GObject.Object):
    __gtype_name__ = 'MusicBrainzRecording'

    SELECT_RELEASE_FIRST = -1

    def __init__(self, recording_id=None, release_id=None, file=None):
        super().__init__()
        self._recording_id = None
        self._prefill_release_id = release_id
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
                inc=('releases', 'genres', 'artist-credits', 'media', 'release-groups')
            )
        )

        if not self.mb_data:
            raise ValueError("Could not get recording data")

        self.available_releases = self.get_releases()
        if len(self.available_releases) == 1:
            self.release = self.available_releases[0]
        elif self._album:
            album_rels = [r for r in self.available_releases if r.title == self._album]
            if len(album_rels) == 1:
                self.release = album_rels[0]
        if len(self.available_releases) > 1 and self._prefill_release_id:
            for rel in self.available_releases:
                if rel.release_id == self._prefill_release_id:
                    self.release = rel
                    break

    def apply_data_to_file(self, file):
        """
        Takes an EartagFile and applies the data from this recording to it.
        """
        try:
            self.release
        except ValueError:
            print("No release")
            return False

        self.release.update_covers(if_needed=True)
        for prop in ('title', 'artist', 'album', 'genre', 'albumartist', 'releasedate',
                'tracknumber', 'totaltracknumber', 'front_cover_path', 'back_cover_path'):
            if self.get_property(prop):
                file.set_property(prop, self.get_property(prop))

        file.props.musicbrainz_recordingid = self.recording_id
        file.props.musicbrainz_albumid = self.release.release_id
        file.props.musicbrainz_releasegroupid = self.release.mb_data['release-group']['id']
        file.props.musicbrainz_trackid = self.release.mb_data['media'][0]['tracks'][0]['id']
        file.props.musicbrainz_artistid = self.mb_data['artist-credit'][0]['artist']['id']

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
        if 'releases' in self.mb_data:
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

    def __str__(self):
        return f'MusicBrainzRecording {self.recording_id} ({self.title} - {self.artist})'

class MusicBrainzRelease(GObject.Object):
    __gtype_name__ = 'MusicBrainzRelease'

    NEED_UPDATE_COVER = -2

    cover_cache = {}
    full_data_cache = {}

    def __init__(self, release_data):
        super().__init__()
        self.mb_data = release_data
        self.cover_tempfiles = {
            'thumbnail': None,
            'front': MusicBrainzRelease.NEED_UPDATE_COVER,
            'back': MusicBrainzRelease.NEED_UPDATE_COVER
        }
        self.update_thumbnail()

        # Get full release data
        if self.release_id not in MusicBrainzRelease.full_data_cache:
            MusicBrainzRelease.full_data_cache[self.release_id] = make_request(
                build_url('release', self.release_id, inc=['recordings'])
            )

        self.full_data = MusicBrainzRelease.full_data_cache[self.release_id]

    def dispose(self):
        for tempfile in self.cover_tempfiles.values():
            if tempfile and tempfile != MusicBrainzRelease.NEED_UPDATE_COVER:
                tempfile.close()

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

    @property
    def tracks(self):
        return self.full_data['media'][0]['tracks']

    # Covers

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

    def update_covers(self, if_needed=False):
        """Downloads the covers for the release from coverartarchive.org"""
        if if_needed and self.cover_tempfiles['front'] != MusicBrainzRelease.NEED_UPDATE_COVER:
            return

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

    def __str__(self):
        return f'MusicBrainzRelease {self.release_id} ({self.title} - {self.artist})'


def update_from_musicbrainz(file):
    """
    Takes an EartagFile with MusicBrainz ID tags set and updates the tags
    of the file to match.
    """
    if not file.musicbrainz_recordingid:
        raise ValueError("Missing recording ID")

    if not file.musicbrainz_albumid:
        raise ValueError("Missing album ID")

    try:
        rec = MusicBrainzRecording(file.musicbrainz_recordingid)
    except ValueError:
        return False
    if not rec:
        return False

    if len(rec.available_releases) > 1:
        rel = None
        for r in rec.available_releases:
            if r.release_id == file.musicbrainz_albumid:
                rel = r
                break
        if not rel:
            rel = rec.available_releases[0]
            rec.release = rel
            file.musicbrainz_albumid = rel.release_id
    else:
        rel = rec.release

    if not rel:
        return False

    rec.apply_data_to_file(file)

    return True


def acoustid_identify_file(file):
    """
    Uses AcoustID and Chromaprint to identify a track's data.

    Returns a tuple containing the confidence and MusicBrainzRecording
    object for the file, or (0.0, None) if it couldn't be found.
    """
    try:
        results = acoustid.match(ACOUSTID_API_KEY, file.path, parse=False)
        if 'results' not in results or not results['results']:
            return (0.0, None)
    except:
        traceback.print_exc()
        return (0.0, None)

    acoustid_data = results['results'][0]

    if acoustid_data['score'] * 100 < ACOUSTID_CONFIDENCE_TRESHOLD:
        return (0.0, None)

    if 'recordings' in acoustid_data:
        musicbrainz_id = acoustid_data['recordings'][0]['id']
        rec = MusicBrainzRecording(musicbrainz_id)

        return (acoustid_data['score'], rec)

    return (0.0, None)
