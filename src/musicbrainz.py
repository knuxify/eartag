"""
Contains code for interacting with the MusicBrainz API.
"""

import asyncio
import json
import os.path
import time
import traceback
import urllib
import urllib.parse
import urllib.request
from typing import List, Self

# HACK: The Gst backend of audioread, which is used by acoustid, is not very
# happy when the GLib async event loop policy is set up.
# Force-disable the Gst backend.
import audioread

audioread._gst_available = lambda: False
import acoustid

from gi.repository import GObject, GLib

from ._async import event_loop
from .utils.queuedl import EartagQueuedDownloader, EartagDownloaderMode

try:
    from . import ACOUSTID_API_KEY, VERSION
except ImportError:  # handle test suite import
    from tests.common import ACOUSTID_API_KEY, VERSION, config
else:
    from .config import config

from .utils import simplify_string, simplify_compare, title_case_preserve_uppercase

LAST_REQUEST = 0


mb_query = EartagQueuedDownloader(
    EartagDownloaderMode.MODE_JSON, simultaneous_downloads=1, throttle=True
)


def build_url(endpoint, id="", **kwargs):
    """Builds a MusicBrainz API endpoint URL."""
    args = []
    for argname, argdata in kwargs.items():
        if isinstance(argdata, list) or isinstance(argdata, tuple):
            argdata = "+".join(argdata)
        elif argname == "query" and isinstance(argdata, dict):
            argdata = " AND ".join([f"{k}:{v}" for k, v in argdata.items() if v])
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


class MusicBrainzRecording(GObject.Object):
    __gtype_name__ = "MusicBrainzRecording"

    SELECT_RELEASE_FIRST = -1

    def __init__(self, data: dict):
        super().__init__()
        self._recording_id = data["id"]
        self.mb_data = data
        self._available_releases = None
        self._release = MusicBrainzRecording.SELECT_RELEASE_FIRST

        if "releases" in data:
            self._fetch_available_releases()

        if len(self._available_releases) == 1:
            self._release = self._available_releases[0]
        elif len(self._available_releases) == 0:
            self._release = None

    def dispose(self):
        self.release.dispose()

    @property
    def available_releases(self):
        if self._available_releases is None:
            self._fetch_available_releases()
        return self._available_releases

    def _fetch_available_releases(self):
        """Fill the self.available_releases list with releases (as MusicBrainzRelease objects)."""
        if "releases" not in self.mb_data:
            print("Warning: run fetch_full_data_async() to get release data")
            return []

        available_releases = [
            MusicBrainzRelease(rel) for rel in self.mb_data["releases"]
        ]

        # Prefer albums, then EPs, then singles, then others.
        sort_key = {"album": 0, "ep": 1, "single": 2, "other": 3}
        available_releases.sort(key=lambda rel: sort_key.get(rel.group.primary_type, 4))

        # Move unofficial releases and compilations to the end of the list.
        available_releases.sort(
            key=lambda rel: int(rel.status != "official")
        )  # official = 0, unofficial = 1
        available_releases.sort(
            key=lambda rel: int("compilation" in rel.group.secondary_types)
        )  # not compilation = 0, compilation = 1

        self._available_releases = available_releases

    async def fetch_full_data_async(self):
        """Get full data; this is required for some properties."""
        self.mb_data = await mb_query.download(
            build_url(
                "recording",
                self._recording_id,
                inc=("releases", "genres", "artist-credits", "media", "release-groups"),
            )
        )

    @staticmethod
    async def new_for_id(recording_id: str) -> Self:
        """Create a new MusicBrainzRecording object with the given ID."""
        data = await mb_query.download(
            build_url(
                "recording",
                recording_id,
                inc=("releases", "genres", "artist-credits", "media", "release-groups"),
            )
        )
        return MusicBrainzRecording(data)

    @staticmethod
    async def get_recordings_for_file(file, overrides: dict = None) -> List[Self]:
        """
        Search for recordings matching information extracted from the file.

        Returns a list of MusicBrainzRecording files.
        """

        if overrides:
            title = overrides.get("title", file.props.title)
            artist = overrides.get("artist", file.props.artist)
            album = overrides.get("album", file.props.album)
        else:
            title = file.props.title
            artist = file.props.artist
            album = file.props.album

        if not title:
            raise ValueError("Not enough data for query; title is needed")

        # Query MusicBrainz based on the available metadata
        async def _query_recordings(_title, _artist, _album):
            _data = await mb_query.download(
                build_url(
                    "recording",
                    "",
                    query={
                        "recording": _title,
                        "artist": _artist,
                        "release": _album,
                    },
                )
            )
            return [
                r
                for r in _data.get("recordings", [])
                if r.get("score") >= config["musicbrainz-confidence-treshold"]
                or simplify_string(r.get("title", "")) == simplify_string(_title)
                and simplify_string(r.get("artist-credits", [])[0].get("name", ""))
                == simplify_string(_artist)
            ]

        search_data = {}
        # For convenience, each possible "method" of querying is numbered;
        # the number increases with each query iteration. This is done so that
        # once one of the methods works, we can quickly break out of the loop.
        fetch_method = 0
        while not search_data:

            # Method 0. Perform a regular query with all the parameters.
            if fetch_method == 0:
                search_data = await _query_recordings(title, artist, album)

            # Method 1. Perform a query without the album, if we are given one.
            elif fetch_method == 1:
                if album:
                    search_data = await _query_recordings(title, artist, "")

            # Method 2. Simplify title and artist.
            elif fetch_method == 2:
                search_data = await _query_recordings(
                    simplify_string(title),
                    simplify_string(artist),
                    simplify_string(album),
                )

            # Method 3. Same as 2, but without album, if we are given one.
            elif fetch_method == 3:
                if album:
                    search_data = await _query_recordings(
                        simplify_string(title), simplify_string(artist), ""
                    )

            # Once we have exhausted all methods, return empty data.
            else:
                return []

            fetch_method += 1

        # Convert the search results to MusicBrainzRecording objects
        ret = []
        for r in search_data:
            try:
                rec = MusicBrainzRecording(r)
            except:
                traceback.print_exc()
                continue

            # The data we get from the search results is partial and doesn't include
            # useful information like releases, so we need to fetch it after the fact:
            await rec.fetch_full_data_async()

            # If there are multiple releases available, try to pick the one that matches
            # the most file metadata (album and track number)
            if len(rec.available_releases) > 1:
                rels = rec.available_releases.copy()

                # Check 1. Check if the album title matches
                if album:
                    rels_q = [rel for rel in rels if album == rel.title]
                    # Check 1.5. Check if the simplified album title matches
                    if not rels_q and simplify_string(album):
                        rels_q = [
                            rel
                            for rel in rels
                            if simplify_string(album) == simplify_string(rel.title)
                        ]
                    # These two lines ensure that we don't end up with 0 releases post-query;
                    # they are present in the remaining checks as well
                    if rels_q:
                        rels = rels_q

                # Check 2. Check if the release date matches
                releasedate = file.props.releasedate
                if releasedate:
                    rels_q = [rel for rel in rels if releasedate == rel.releasedate]
                    # Check 2.5: Check if the release year matches
                    if not rels_q and len(releasedate) >= 4:
                        rels_q = [
                            rel
                            for rel in rels
                            if releasedate[:4] == rel.releasedate[:4]
                        ]
                    if rels_q:
                        rels = rels_q

                # Check 3. Check if the total track number matches
                totaltracknumber = file.props.totaltracknumber
                if totaltracknumber:
                    rels_q = [
                        rel
                        for rel in rels
                        if (
                            rel.totaltracknumber
                            and totaltracknumber == rel.totaltracknumber
                        )
                        or not rel.totaltracknumber
                    ]
                    if rels_q:
                        rels = rels_q

                # Sort from oldest to newest
                rels.sort(key=lambda rel: rel.releasedate)

                # The first remaining release wins
                if rels:
                    rec._release = rels[0]

                del rels

            ret.append(rec)

        # Sort the resulting recordings by which one matches our file the best
        def _rec_file_cmp(rec) -> int:
            out = 0
            for prop in (
                "title",
                "artist",
                "album",
                "releasedate",
                "tracknumber",
                "totaltracknumber",
            ):
                if file.has_tag(prop):
                    out += int(file.get_property(prop) == rec.get_property(prop))

            return out

        ret.sort(
            key=_rec_file_cmp, reverse=True
        )  # The larger the number, the more tag matches

        return ret

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
        file.props.musicbrainz_trackid = self.media.get(
            "tracks", self.media.get("track")
        )[0]["id"]
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

    @property
    def media(self):
        """Shorthand for the "media" property of the current release."""
        return self.release.mb_data.get("media")[0]

    @GObject.Property(type=int)
    def tracknumber(self):
        # Weird MusicBrainz bug: In search queries it's "track", in direct
        # by-ID queries it's "tracks".
        try:
            return int(self.media.get("tracks", self.media.get("track"))[0]["number"])
        except ValueError:
            # HACK until we properly support vinyl track numbers.
            return 0

    @GObject.Property(type=int)
    def totaltracknumber(self):
        try:
            return int(self.media["track-count"])
        except ValueError:
            # HACK until we properly support vinyl track numbers.
            return 0

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
        return f"MusicBrainzRecording {self.recording_id} ({self.title} - {self.artist} ({self.disambiguation}))"

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

    def __init__(self, release_data):
        super().__init__()
        self.mb_data = release_data

        self.thumbnail_dl_task = None

        self.group = MusicBrainzReleaseGroup(self.mb_data["release-group"])

        self.thumbnail = EartagCAACover("release", self.release_id, "thumbnail")
        self.front_cover = EartagCAACover("release", self.release_id, "front")
        self.back_cover = EartagCAACover("release", self.release_id, "back")

    @staticmethod
    async def new_for_id(id):
        data = await mb_query.download(
            build_url(
                "release",
                id,
                inc=[
                    "artist-credits",
                    "recordings",
                    "release-groups",
                    "genres",
                    "media",
                ],
            )
        )
        return MusicBrainzRelease(data)

    @GObject.Property(type=str)
    def release_id(self):
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

    @GObject.Property(type=str)
    def status(self):
        if "status" in self.mb_data and self.mb_data["status"]:
            return self.mb_data["status"].lower()
        return "official"

    @GObject.Property(type=str)
    def disambiguation(self):
        return "; ".join(
            [
                x
                for x in (
                    self.mb_data["media"][0].get("format", None),
                    self.mb_data.get("disambiguation", None),
                )
                if x
            ]
        )

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
                "Covers have not been downloaded yet; run download_covers_async()"
            )
        if not self.front_cover.props.path:
            return self.group.front_cover_path
        return self.front_cover.props.path

    @GObject.Property(type=str)
    def back_cover_path(self):
        if not self.back_cover.props.loaded:
            raise ValueError(
                "Covers have not been downloaded yet; run download_covers_async()"
            )
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
        if not self.front_cover.props.path:
            await self.group.front_cover.download()
        self.notify("front-cover-path")
        await self.back_cover.download()
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

    def __init__(self, relgroup_data):
        super().__init__()
        self._releases = None

        groupid = relgroup_data["id"]

        self.mb_data = relgroup_data

        self.thumbnail = EartagCAACover("release-group", self.relgroup_id, "thumbnail")
        self.front_cover = EartagCAACover("release-group", self.relgroup_id, "front")

    @staticmethod
    async def _fetch_full_data(groupid):
        return await mb_query.download(
            build_url("release-group", groupid, inc=["releases"])
        )

    @staticmethod
    async def new_for_id(id):
        data = await MusicBrainzReleaseGroup._fetch_full_data(id)
        return MusicBrainzReleaseGroup(relgroup_data=data)

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
            return [t.lower() for t in self.mb_data.get("secondary-types", [])]
        except AttributeError:
            return []

    @GObject.Property
    def release_ids(self):
        return [r["id"] for r in self.mb_data["releases"]]

    @GObject.Property
    def releases(self):
        if not self._releases:
            raise ValueError(
                "Releases have not been initialized yet; run get_releases_async()"
            )
        return self._releases

    async def get_releases_async(self):
        if not self._releases:
            self._releases = [
                await MusicBrainzRelease.new_for_id(id) for id in self.release_ids
            ]

    @GObject.Property(type=str)
    def thumbnail_path(self):
        return self.thumbnail.props.path

    @GObject.Property(type=str)
    def front_cover_path(self):
        if not self.front_cover.props.loaded:
            raise ValueError(
                "Covers have not been downloaded yet; run download_covers_async()"
            )
        return self.front_cover.props.path

    def __eq__(self, other):
        if not isinstance(other, MusicBrainzReleaseGroup):
            return False
        return self.relgroup_id == other.relgroup_id

    def __hash__(self):
        return hash(self.relgroup_id)


async def acoustid_identify_file(file):
    """
    Uses AcoustID and Chromaprint to identify a track's data.

    Returns a tuple containing the confidence and MusicBrainzRecording
    object for the file, or (0.0, None) if it couldn't be found.
    """
    try:
        results = await asyncio.to_thread(
            acoustid.match, ACOUSTID_API_KEY, file.path, parse=False
        )
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
        rec = await MusicBrainzRecording.new_for_id(musicbrainz_id)
        return (acoustid_data["score"], rec)

    return (0.0, None)
