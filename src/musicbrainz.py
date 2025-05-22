"""
Contains code for interacting with the MusicBrainz API.
"""

import json
import os.path
import time
import traceback
import urllib
import urllib.parse
import urllib.request

# HACK: The Gst backend of audioread, which is used by acoustid, is not very
# happy when the GLib async event loop policy is set up.
# Force-disable the Gst backend.
import audioread

audioread._gst_available = lambda: False
import acoustid

from gi.repository import GObject, GLib

from .main import event_loop
from .utils.queuedl import EartagQueuedDownloader, EartagDownloaderMode

try:
    from . import ACOUSTID_API_KEY, VERSION
except ImportError:  # handle test suite import
    from tests.common import ACOUSTID_API_KEY, VERSION, config

    USER_AGENT = (
        f"Ear Tag (Test suite)/{VERSION} (https://gitlab.gnome.org/World/eartag)"
    )
    TEST_SUITE = True
else:
    from .config import config

    USER_AGENT = f"Ear Tag/{VERSION} (https://gitlab.gnome.org/World/eartag)"
    TEST_SUITE = False

if TEST_SUITE:
    # Terrible hack. Tests do not have a GLib context, so idle_add calls
    # get happily ignored; thus, we override GLib.idle_add so that the functions
    # are called immediately. This is not a problem in the test suite (we only
    # need to do this because changing a property that is bound to an UI element
    # can cause UI crashes).
    GLib.idle_add = lambda x, *args, **kwargs: x(*args, **kwargs)

from .utils import simplify_string, simplify_compare, title_case_preserve_uppercase

LAST_REQUEST = 0


def make_request(url, raw=False, _recursion=0):
    """Wrapper for urllib.request.Request that handles the setup."""
    global LAST_REQUEST

    if _recursion > 3:
        return None

    # MusicBrainz requires a cooldown of max. 1 request per second.
    # Try to adjust to this cooldown as best as possible.
    while (time.time() - LAST_REQUEST) <= 1:
        time.sleep(0.1)

    LAST_REQUEST = time.time()

    headers = {"User-Agent": USER_AGENT}
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as data_raw:
            if raw:
                data = data_raw.read()
            else:
                data = json.loads(data_raw.read())
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        elif e.code == 503:
            time.sleep(3)
            return make_request(url, raw=raw, _recursion=(_recursion + 1))
        else:
            print("Exception encountered during request for URL:", url)
            traceback.print_exc()
            return None
    except urllib.error.URLError:
        time.sleep(3)
        return make_request(url, raw=raw, _recursion=(_recursion + 1))
    except:
        traceback.print_exc()
        return None

    return data


def build_url(endpoint, id="", **kwargs):
    """Builds a MusicBrainz API endpoint URL."""
    args = []
    for argname, argdata in kwargs.items():
        if isinstance(argdata, list) or isinstance(argdata, tuple):
            argdata = "+".join(argdata)
        args.append(f'{argname}={urllib.parse.quote(argdata, encoding="utf-8")}')
    if id:
        return f'https://musicbrainz.org/ws/2/{endpoint}/{id}?{"&".join(args)}&fmt=json'
    return f'https://musicbrainz.org/ws/2/{endpoint}?{"&".join(args)}&fmt=json'


class EartagCAACover(GObject.Object):
    """Represents a cover art from the Cover Art Archive."""

    path = GObject.Property(type=str, default="")
    loaded = GObject.Property(type=bool, default=False)

    cover_downloader = EartagQueuedDownloader(mode=EartagDownloaderMode.MODE_FILE)

    def __init__(
        self, item_type: str, item_id: str, cover_type: str, cover_size: int = -1
    ):
        """
        Initialize the CAACover object.

        :param item_type: Type of item to download the cover for (release, release-group)
        :param item_id: ID of the item to download the cover for
        :param cover_type: Type of the cover to download: thumbnail, front, back
        :param cover_size: Size of the cover to download: 0, 250, 500, 1200, 2000 (max size)
        """
        super().__init__()

        if cover_size == -1:
            cover_size = int(config.get_enum("musicbrainz-cover-size"))
        if cover_size not in (0, 250, 500, 1200, 2000):
            raise ValueError("Cover size must be one of 0, 250, 500, 1200, 2000")
        if cover_type not in ("thumbnail", "front", "back"):
            raise ValueError("Cover type must be one of thumbnail, front, back")
        if cover_type == "back" and item_type == "release-group":
            raise ValueError("Back cover is not supported for release groups")

        self.item_type = item_type
        self.item_id = item_id

        if cover_type == "thumbnail":
            self.cover_type = "front"
            self.cover_size = 250
        else:
            self.cover_type = cover_type
            self.cover_size = cover_size

    @property
    def url(self):
        """The URL to the cover."""
        url = f"https://coverartarchive.org/{self.item_type}/{self.item_id}/{self.cover_type}"
        if self.cover_size not in (0, 2000):
            url += f"-{self.cover_size}"
        return url

    async def download(self):
        try:
            tempfile = await EartagCAACover.cover_downloader.download(self.url)
        except Exception as e:
            print(e)
            tempfile = False
        if tempfile:
            self.props.path = tempfile.name
        self.props.loaded = True


def get_recordings_for_file(file):
    """
    Takes an EartagFile and returns a list of MusicBrainzRecording objects
    that might match the query.
    """
    if not file.title or not file.artist:
        raise ValueError("Not enough data for a query; need at least title and artist")

    query_data = {
        "recording": file.title,
        "artist": file.artist,
        "release": file.album or "",
    }

    search_data = make_request(
        build_url(
            "recording",
            "",
            query=" AND ".join([f"{k}:{v}" for k, v in query_data.items() if v]),
        )
    )

    if (
        not search_data
        or "recordings" not in search_data
        or not search_data["recordings"]
    ):
        # Try to use simplified title/artist:
        query_data["title"] = simplify_string(file.title)
        if not query_data["title"]:
            return []
        query_data["artist"] = simplify_string(file.title)
        if not query_data["artist"]:
            return []

        search_data = make_request(
            build_url(
                "recording",
                "",
                query=" AND ".join([f"{k}:{v}" for k, v in query_data.items() if v]),
            )
        )
        if (
            not search_data
            or "recordings" not in search_data
            or not search_data["recordings"]
        ):
            return []

    ret = []
    for r in search_data["recordings"]:
        if r["score"] < config["musicbrainz-confidence-treshold"]:
            continue

        try:
            rec = MusicBrainzRecording(r["id"], file=file)
        except ValueError:
            continue

        if file.album:
            _break = False
            for rel in rec.available_releases:
                if rel.title == file.album or simplify_compare(rel.title, file.album):
                    ret.insert(0, rec)
                    rec.release = rel
                    rec.available_releases.insert(
                        0, rec.available_releases.pop(rec.available_releases.index(rel))
                    )
                    _break = True
                    break
            if _break:
                continue

        ret.append(rec)

    return ret


class MusicBrainzRecording(GObject.Object):
    __gtype_name__ = "MusicBrainzRecording"

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
            build_url(
                "recording",
                self._recording_id,
                inc=("releases", "genres", "artist-credits", "media", "release-groups"),
            )
        )

        if not self.mb_data or "title" not in self.mb_data or not self.mb_data["title"]:
            raise ValueError("Could not get recording data")

        self.available_releases = self.get_releases()

        # Sort available releases by usefulness. Prefer albums (digital),
        # then albums (physical media), then singles, then compilations.
        comps = []
        for rel in self.available_releases.copy():
            if rel.status != "official":
                self.available_releases.remove(rel)
                comps.append(rel)
                continue
            if "compilation" in rel.group.secondary_types:
                self.available_releases.remove(rel)
                comps.append(rel)
                continue

        rels = []
        for reltype in ("album", "ep", "single", "other"):
            checked_ids = []
            for rel in self.available_releases + comps:
                if rel.group.relgroup_id in checked_ids:
                    continue
                if rel.group.primary_type == reltype:
                    rels.append(rel)
                    checked_ids.append(rel.group.relgroup_id)

        missing = [rel for rel in self.available_releases if rel not in rels]
        rels = rels + missing

        if self._album:
            for rel in rels.copy():
                if rel.title == self._album or simplify_compare(rel.title, self._album):
                    rels.insert(0, rels.pop(rels.index(rel)))

        self.available_releases = rels

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

        try:
            self.release
        except ValueError:
            pass
        else:
            for rel in self.available_releases:
                if rel == self.release:
                    continue

    def apply_data_to_file(self, file):
        """
        Takes an EartagFile and applies the data from this recording to it.
        """
        try:
            self.release
        except ValueError:
            print("No release")
            return False

        # Covers are downloaded by the identify process ahead of time

        for prop in (
            "title",
            "artist",
            "album",
            "genre",
            "albumartist",
            "releasedate",
            "tracknumber",
            "totaltracknumber",
            "front_cover_path",
            "back_cover_path",
        ):
            if self.get_property(prop):
                file.set_property(prop, self.get_property(prop))

        file.props.musicbrainz_recordingid = self.recording_id
        file.props.musicbrainz_albumid = self.release.release_id
        file.props.musicbrainz_releasegroupid = self.release.group.relgroup_id
        file.props.musicbrainz_trackid = self.release.mb_data["media"][0]["tracks"][0][
            "id"
        ]
        file.props.musicbrainz_artistid = self.mb_data["artist-credit"][0]["artist"][
            "id"
        ]

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
        if "releases" in self.mb_data:
            for release in self.mb_data["releases"]:
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

        # Update everything that depends on the release:
        for prop in (
            "album",
            "albumartist",
            "genre",
            "tracknumber",
            "totaltracknumber",
            "releasedate",
            "thumbnail_path",
            "front_cover_path",
            "back_cover_path",
        ):
            self.notify(prop)

    @GObject.Property(type=str)
    def title(self):
        return self.mb_data["title"]

    @GObject.Property(type=str)
    def artist(self):
        return self.mb_data["artist-credit"][0]["name"]

    @GObject.Property(type=str)
    def album(self):
        return self.release.title

    @GObject.Property(type=str)
    def albumartist(self):
        return self.release.artist

    @GObject.Property(type=str)
    def genre(self):
        if "genres" in self.mb_data and self.mb_data["genres"]:
            return title_case_preserve_uppercase(self.mb_data["genres"][0]["name"])
        return self.release.genre

    @GObject.Property(type=int)
    def tracknumber(self):
        return int(self.release.mb_data["media"][0]["tracks"][0]["number"])

    @GObject.Property(type=int)
    def totaltracknumber(self):
        return int(self.release.mb_data["media"][0]["track-count"])

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
        return (
            f"MusicBrainzRecording {self.recording_id} ({self.title} - {self.artist})"
        )

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if not isinstance(other, MusicBrainzRecording):
            return False
        return self.recording_id == other.recording_id

    def __hash__(self):
        return hash(self.recording_id)


class MusicBrainzRelease(GObject.Object):
    __gtype_name__ = "MusicBrainzRelease"

    NEED_UPDATE_COVER = -2

    cover_cache = {}
    full_data_cache = {}
    obj_cache = {}  # id: MusicBrainzRelease

    def __init__(self, release_data, from_id=False):
        super().__init__()
        self.mb_data = release_data
        self._from_id = from_id

        # Get full release data
        if self.release_id not in MusicBrainzRelease.full_data_cache:
            MusicBrainzRelease.full_data_cache[self.release_id] = make_request(
                build_url(
                    "release",
                    self.release_id,
                    inc=[
                        "artist-credits",
                        "recordings",
                        "release-groups",
                        "genres",
                        "media",
                    ],
                )
            )

        self.thumbnail_dl_task = None

        self.full_data = MusicBrainzRelease.full_data_cache[self.release_id]
        if from_id:
            self.mb_data = self.full_data

        if self.release_id not in MusicBrainzRelease.obj_cache:
            MusicBrainzRelease.obj_cache[self.release_id] = self

        self.group = MusicBrainzReleaseGroup(self.mb_data["release-group"])

        self.thumbnail = EartagCAACover("release", self.release_id, "thumbnail")
        self.front_cover = EartagCAACover("release", self.release_id, "front")
        self.back_cover = EartagCAACover("release", self.release_id, "back")

    @staticmethod
    def setup_from_id(id):
        if id in MusicBrainzRelease.obj_cache:
            return MusicBrainzRelease.obj_cache[id]
        return MusicBrainzRelease(release_data={}, from_id=id)

    @GObject.Property(type=str)
    def release_id(self):
        if self._from_id:
            return self._from_id
        return self.mb_data["id"]

    @GObject.Property(type=str)
    def title(self):
        return self.mb_data["title"]

    @GObject.Property(type=str)
    def artist(self):
        return self.mb_data["artist-credit"][0]["name"]

    @GObject.Property(type=str)
    def genre(self):
        if "genres" in self.mb_data and self.mb_data["genres"]:
            return title_case_preserve_uppercase(self.mb_data["genres"][0]["name"])
        return ""

    @GObject.Property(type=str)
    def releasedate(self):
        if "first-release-date" in self.group.mb_data:
            return self.group.mb_data["first-release-date"]
        if "date" in self.mb_data:
            return self.mb_data["date"]
        return ""

    @GObject.Property(type=int)
    def totaltracknumber(self):
        return int(self.mb_data["media"][0]["track-count"])

    @property
    def tracks(self):
        return self.full_data["media"][0]["tracks"]

    @GObject.Property(type=str)
    def status(self):
        if "status" in self.mb_data and self.mb_data["status"]:
            return self.mb_data["status"].lower()
        return "official"

    @GObject.Property(type=str)
    def disambiguation(self):
        return self.mb_data["disambiguation"]

    # Covers

    @GObject.Property(type=str)
    def thumbnail_path(self):
        if not self.thumbnail.props.path:
            return self.group.thumbnail_path
        return self.thumbnail.props.path

    @GObject.Property(type=bool, default=False)
    def thumbnail_loaded(self):
        return self.thumbnail.props.loaded

    @GObject.Property(type=str)
    def front_cover_path(self):
        if not self.front_cover.props.loaded:
            raise ValueError(
                "Covers have not been downloaded yet; run download_covers()"
            )
        if not self.front_cover.props.path:
            return self.group.front_cover_path
        return self.front_cover.props.path

    @GObject.Property(type=str)
    def back_cover_path(self):
        if not self.back_cover.props.loaded:
            raise ValueError(
                "Covers have not been downloaded yet; run download_covers()"
            )
        if not self.back_cover.props.path:
            return self.group.back_cover_path
        return self.back_cover.props.path

    def queue_thumbnail_download(self):
        """Queues a download of the thumbnail for the release from coverartarchive.org"""
        if (
            self.thumbnail_dl_task
            and not self.thumbnail.props.loaded
            and not self.thumbnail_dl_task.done()
        ):
            self.thumbnail_dl_task.cancel()
        self.thumbnail_dl_task = event_loop.create_task(self.download_thumbnail_async())

    async def download_thumbnail_async(self):
        """Downloads the covers for the release from coverartarchive.org"""
        await self.thumbnail.download()
        if not self.thumbnail.props.loaded:
            await self.group.thumbnail.download()
        self.notify("thumbnail-path")
        self.notify("thumbnail-loaded")

    async def download_covers_async(self):
        """Downloads the covers for the release from coverartarchive.org"""
        await self.front_cover.download()
        if not self.front_cover.props.loaded:
            await self.group.front_cover.download()
        self.notify("front-cover-path")
        await self.back_cover.download()
        if not self.back_cover.props.loaded:
            await self.group.back_cover.download()
        self.notify("back-cover-path")

    @classmethod
    def clear_tempfiles(cls):
        """Closes all cover tempfiles."""
        # TODO FIXME

    def __str__(self):
        return f"MusicBrainzRelease {self.release_id} ({self.title} - {self.artist})"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if not isinstance(other, MusicBrainzRelease):
            return False
        return self.release_id == other.release_id

    def __hash__(self):
        return hash(self.release_id)


class MusicBrainzReleaseGroup(GObject.Object):
    """A container for release group information, as found in the release query."""

    __gtype_name__ = "MusicBrainzReleaseGroup"

    NO_COVER = -2

    full_data_cache = {}
    obj_cache = {}

    def __init__(self, relgroup_data, from_id=False):
        super().__init__()
        self._releases = None

        if relgroup_data:
            groupid = relgroup_data["id"]
        elif from_id:
            groupid = from_id

        if groupid not in MusicBrainzReleaseGroup.full_data_cache:
            MusicBrainzReleaseGroup.full_data_cache[groupid] = make_request(
                build_url("release-group", groupid, inc=["releases"])
            )

        if not MusicBrainzReleaseGroup.full_data_cache[groupid]:
            MusicBrainzReleaseGroup.full_data_cache[groupid] = relgroup_data

        self.mb_data = MusicBrainzReleaseGroup.full_data_cache[groupid]

        if groupid not in MusicBrainzReleaseGroup.obj_cache:
            MusicBrainzReleaseGroup.obj_cache[groupid] = self

        self.thumbnail = EartagCAACover("release-group", self.relgroup_id, "thumbnail")
        self.front_cover = EartagCAACover("release-group", self.relgroup_id, "front")

    @staticmethod
    def setup_from_id(id):
        if id in MusicBrainzReleaseGroup.obj_cache:
            return MusicBrainzReleaseGroup.obj_cache[id]
        return MusicBrainzReleaseGroup({}, from_id=id)

    @GObject.Property(type=str)
    def relgroup_id(self):
        return self.mb_data["id"]

    @GObject.Property(type=str)
    def primary_type(self):
        try:
            return self.mb_data["primary-type"].lower()
        except AttributeError:
            return "other"

    @GObject.Property(type=str)
    def secondary_types(self):
        try:
            return [t.lower() for t in self.mb_data["secondary-types"]]
        except AttributeError:
            return []

    @GObject.Property
    def release_ids(self):
        return [r["id"] for r in self.mb_data["releases"]]

    @GObject.Property
    def releases(self):
        if not self._releases:
            self._releases = [
                MusicBrainzRelease.setup_from_id(id) for id in self.release_ids
            ]
        return self._releases

    @GObject.Property(type=str)
    def thumbnail_path(self):
        return self.thumbnail.props.path

    @GObject.Property(type=str)
    def front_cover_path(self):
        if not self.front_cover.props.loaded:
            raise ValueError(
                "Covers have not been downloaded yet; run download_covers()"
            )
        return self.front_cover.props.path

    def __eq__(self, other):
        if not isinstance(other, MusicBrainzReleaseGroup):
            return False
        return self.relgroup_id == other.relgroup_id

    def __hash__(self):
        return hash(self.relgroup_id)


def acoustid_identify_file(file):
    """
    Uses AcoustID and Chromaprint to identify a track's data.

    Returns a tuple containing the confidence and MusicBrainzRecording
    object for the file, or (0.0, None) if it couldn't be found.
    """
    try:
        results = acoustid.match(ACOUSTID_API_KEY, file.path, parse=False)
        if "results" not in results or not results["results"]:
            return (0.0, None)
    except:
        print(
            f"Error while getting AcoustID match for {os.path.basename(file.path)} ({file.id}):"
        )
        traceback.print_exc()
        print("Continuing without match. (This is not a fatal error!)")
        return (0.0, None)

    acoustid_data = results["results"][0]

    if acoustid_data["score"] * 100 < config["acoustid-confidence-treshold"]:
        return (0.0, None)

    if "recordings" in acoustid_data:
        musicbrainz_id = acoustid_data["recordings"][0]["id"]
        rec = MusicBrainzRecording(musicbrainz_id, file=file)

        return (acoustid_data["score"], rec)

    return (0.0, None)
