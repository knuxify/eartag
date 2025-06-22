"""
Contains code for interacting with the MusicBrainz API.
"""

import asyncio
import os
import traceback
import urllib
import urllib.parse
import urllib.request
from typing import List, Self, Optional, Tuple

from gi.repository import GObject

from ._async import event_loop
from .utils.queuedl import EartagQueuedDownloader, EartagDownloaderMode
from .backends.file import EartagFile
from .logger import logger

try:
    # HACK: The Gst backend of audioread, which is used by acoustid, is not very
    # happy when the GLib async event loop policy is set up.
    # Force-disable the Gst backend.
    import audioread

    audioread._gst_available = lambda: False
except ImportError:
    fpcalc = os.environ.get("FPCALC", "fpcalc")
    import shutil

    if not shutil.which(fpcalc):
        logger.warning(
            "Neither audioread nor fpcalc are available, acoustid matches may be affected"
        )

import acoustid

try:
    from . import ACOUSTID_API_KEY
except ImportError:  # handle test suite import
    from tests.common import ACOUSTID_API_KEY, config
else:
    from .config import config

from .utils import simplify_string, title_case_preserve_uppercase

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
        args.append(f"{argname}={urllib.parse.quote(argdata, encoding='utf-8')}")
    if id:
        return f"https://musicbrainz.org/ws/2/{endpoint}/{id}?{'&'.join(args)}&fmt=json"
    return f"https://musicbrainz.org/ws/2/{endpoint}?{'&'.join(args)}&fmt=json"


class EartagCAACover(GObject.Object):
    """Represents a cover art from the Cover Art Archive."""

    path = GObject.Property(type=str, default="")
    loaded = GObject.Property(type=bool, default=False)

    cover_downloader = EartagQueuedDownloader(mode=EartagDownloaderMode.MODE_FILE)

    def __init__(self, item_type: str, item_id: str, cover_type: str, cover_size: int = -1):
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

    @classmethod
    def clear_tempfiles(cls):
        return cls.cover_downloader.clear_tempfiles()


class MusicBrainzRecording(GObject.Object):
    __gtype_name__ = "MusicBrainzRecording"

    SELECT_RELEASE_FIRST = -1

    def __init__(self, data: dict):
        super().__init__()
        self._recording_id = data["id"]
        self.mb_data = data
        self._available_releases = None
        self._release = MusicBrainzRecording.SELECT_RELEASE_FIRST

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
            logger.error("No releases in data, this should never happen!")
            return []

        available_releases = [MusicBrainzRelease(rel) for rel in self.mb_data["releases"]]

        self._available_releases = available_releases

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

        logger.debug(
            f"Getting recordings for file {os.path.basename(file.path)}; overrides: {overrides}"
        )

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
                and simplify_string(r.get("artist-credit", [{}])[0].get("name", ""))
                == simplify_string(_artist)
            ]

        search_data = []
        search_data_ids = set()
        # For convenience, each possible "method" of querying is numbered;
        # the number increases with each query iteration. This is done so that
        # once one of the methods works, we can quickly break out of the loop.
        fetch_method = 0
        got_useful_result = False
        while True:
            # Method 0. Perform a regular query with all the parameters.
            if fetch_method == 0:
                logger.debug("  - Method 0: regular query with all parameters")
                new_search_data = await _query_recordings(title, artist, album)

            # Method 1. Perform a query without the album, if we are given one.
            elif fetch_method == 1:
                if album:
                    logger.debug("  - Method 1: query with no album")
                    new_search_data = await _query_recordings(title, artist, "")
                else:
                    logger.debug("  - Method 1 (skipped): query with no album")

            # Method 2. Simplify title and artist.
            elif fetch_method == 2:
                if (
                    simplify_string(title) != title
                    and simplify_string(artist) != artist
                    and (simplify_string(album) != album or not album)
                ):
                    logger.debug("  - Method 2: query with simplified tags")
                    new_search_data = await _query_recordings(
                        simplify_string(title),
                        simplify_string(artist),
                        simplify_string(album),
                    )
                else:
                    logger.debug("  - Method 2 (skipped): query with simplified tags")

            # Method 3. Same as 2, but without album, if we are given one.
            elif fetch_method == 3:
                if album and simplify_string(title) != title and simplify_string(artist) != artist:
                    logger.debug("  - Method 3: query with simplified tags and no album")
                    new_search_data = await _query_recordings(
                        simplify_string(title), simplify_string(artist), ""
                    )
                else:
                    logger.debug("  - Method 3 (skipped): query with simplified tags and no album")

            # Once we have exhausted all methods, return empty data.
            else:
                logger.debug("  - Ran out of methods.")
                break

            search_data += [r for r in new_search_data if r.get("id") not in search_data_ids]
            search_data_ids = search_data_ids.union(set([r.get("id") for r in new_search_data]))
            fetch_method += 1

            logger.debug(f"    Found {len(new_search_data)} new results (total {len(search_data)})")

            # Filter out non-useful results; if we didn't get anything that seems
            # correct, continue to the next method.
            for r in new_search_data:
                for _rel_data in r.get("releases", []):
                    if _rel_data.get("status", "Official") == "Official":
                        if "Compilation" not in _rel_data.get("release-group", {}).get(
                            "secondary-types", []
                        ):
                            got_useful_result = True
                            break

            if got_useful_result:
                logger.debug("  ... got useful result!")
                break
            else:
                logger.debug("  ... no useful result, trying next method")

        # Convert the search results to MusicBrainzRecording objects
        ret = []
        for r in search_data:
            try:
                rec = MusicBrainzRecording(r)
            except:  # noqa: E722
                logger.error("Error while parsing MusicBrainz recording data")
                traceback.print_exc()
                continue

            # Sort releases in the recording
            rec.sort_releases(file=file)

            ret.append(rec)

        logger.debug(f"Found {len(ret)} recordings")
        logger.debug(f"Recordings before sorting: \n{ret}")

        # Sort the recordings by usefulness.

        def dict_diff(dict_a, dict_b, show_value_diff=True):
            result = {}
            result["added"] = {k: dict_b[k] for k in set(dict_b) - set(dict_a)}
            result["removed"] = {k: dict_a[k] for k in set(dict_a) - set(dict_b)}
            if show_value_diff:
                common_keys = set(dict_a) & set(dict_b)
                result["value_diffs"] = {
                    k: (dict_a[k], dict_b[k]) for k in common_keys if dict_a[k] != dict_b[k]
                }
            return result

        # Move video recordings to the end
        ret.sort(key=lambda rec: int(rec.mb_data.get("video", False) or False))

        # Prefer recordings with earlier release date; tracks with no release date are moved to the end
        ret.sort(key=lambda rec: rec.releasedate or "Z")

        # Prefer recordings with more legitimate releases
        def _release_sort(rec) -> int:
            out = 0
            for rel in rec.mb_data.get("releases", []):
                if rel["status"] == "Official" and "Compilation" not in rel.get(
                    "release_group", {}
                ).get("secondary-types", []):
                    out += 1
            return out

        ret.sort(key=lambda rec: _release_sort(rec), reverse=True)

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

        ret.sort(key=_rec_file_cmp, reverse=True)  # The larger the number, the more tag matches

        logger.debug(f"Recordings after sorting: \n{ret}")

        return ret

    def sort_releases(self, file: Optional[EartagFile] = None):
        """Sort available releases and pick the best matching one."""
        album = file.props.album if file else ""
        releasedate = file.props.releasedate if file else ""
        totaltracknumber = file.props.totaltracknumber if file else ""

        # If there are no releases, set release to None
        if len(self.available_releases) == 0:
            self._release = None

        # If there is only one release, pick it
        elif len(self.available_releases) == 1:
            self._release = self.available_releases[0]

        # If there are multiple releases available, try to pick the one that matches
        # the most file metadata (album and track number)
        elif len(self.available_releases) > 1:
            rels = self.available_releases.copy()

            ## First, sort the releases:

            # Sort from oldest to newest. We append "zz-zz" to year-only releasedates in the sorting key
            # to make sure that full release dates take precedence.
            rels.sort(
                key=lambda rel: (
                    rel.releasedate if len(rel.releasedate) > 4 else rel.releasedate + "-zz-zz"
                )
            )

            # Prefer albums, then EPs, then singles, then others.
            sort_key = {"album": 0, "ep": 1, "single": 2, "other": 3}
            rels.sort(key=lambda rel: sort_key.get(rel.group.primary_type, 4))

            # Prefer digital releases over physical releases
            sort_key = {"Digital Media": 0, "CD": 1, "Casette": 2, "Vinyl": 3}
            rels.sort(key=lambda rel: sort_key.get(rel.format, 4))

            # Move unofficial releases and compilations to the end of the list.
            rels.sort(
                key=lambda rel: int(
                    rel.status != "official" or "compilation" in rel.group.secondary_types
                )  # official = 0, unofficial = 1
            )

            _original_rels = rels.copy()

            ## If we have information about the release based on metadata, drop releases
            ## that don't match them, unless we end up with no releases

            # Check 1. Check if the album title matches
            if album:
                rels_q = [rel for rel in rels if album == rel.title]
                # Check 1.5. Check if the simplified album title matches
                if not rels_q and simplify_string(album):
                    rels_q = [
                        rel for rel in rels if simplify_string(album) == simplify_string(rel.title)
                    ]
                # These two lines ensure that we don't end up with 0 releases post-query;
                # they are present in the remaining checks as well
                if rels_q:
                    rels = rels_q

            # Check 2. Check if the release date matches
            if releasedate:
                rels_q = [rel for rel in rels if releasedate == rel.releasedate]
                # Check 2.5: Check if the release year matches
                if not rels_q and len(releasedate) >= 4:
                    rels_q = [rel for rel in rels if releasedate[:4] == rel.releasedate[:4]]
                if rels_q:
                    rels = rels_q

            # Check 3. Check if the total track number matches
            if totaltracknumber:
                rels_q = [
                    rel
                    for rel in rels
                    if (rel.totaltracknumber and totaltracknumber == rel.totaltracknumber)
                    or not rel.totaltracknumber
                ]
                if rels_q:
                    rels = rels_q

            # If we end up with no releases somehow, go back to pre-heuristic releases
            if not rels:
                rels = _original_rels

            # The first remaining release wins
            self._release = rels[0]

            # Save sorted releases to available_releases for later algorithms to re-use
            self._available_releases = rels

            del rels

    def apply_data_to_file(self, file):
        """
        Takes an EartagFile and applies the data from this recording to it.
        """
        try:
            self.release  # noqa: B018
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
        file.props.musicbrainz_trackid = self.media.get("tracks", self.media.get("track"))[0]["id"]
        file.props.musicbrainz_artistid = self.mb_data.get(
            "artist-credit-id", self.mb_data["artist-credit"][0]["artist"]["id"]
        )

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
            "title",
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
        try:
            # Use title from selected release
            return self.release.mb_data["media"][0]["track"][0]["title"]
        except (IndexError, KeyError, TypeError):
            return self.mb_data["title"]

    @GObject.Property(type=str)
    def artist(self):
        return self.mb_data["artist-credit"][0]["name"]

    @GObject.Property(type=str)
    def album(self):
        if self.release is not None:
            return self.release.title
        return ""

    @GObject.Property(type=str)
    def albumartist(self):
        if self.release is not None:
            return self.release.artist
        return ""

    @GObject.Property(type=str)
    def genre(self):
        if self.release is not None:
            if "genres" in self.mb_data and self.mb_data["genres"]:
                return title_case_preserve_uppercase(self.mb_data["genres"][0]["name"])
            return self.release.genre
        return ""

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
        if self.release is not None:
            return self.release.releasedate
        return ""

    @GObject.Property(type=str)
    def disambiguation(self):
        return self.mb_data.get("disambiguation", "")

    @GObject.Property(type=str)
    def thumbnail_path(self):
        if self.release is not None:
            return self.release.thumbnail_path
        return ""

    @GObject.Property(type=str)
    def front_cover_path(self):
        if self.release is not None:
            return self.release.front_cover_path
        return ""

    @GObject.Property(type=str)
    def back_cover_path(self):
        if self.release is not None:
            return self.release.back_cover_path
        return ""

    async def download_covers_async(self):
        """Downloads the covers for the release from coverartarchive.org"""
        return await self.release.download_covers_async()

    def __str__(self):
        if self.disambiguation:
            return f"MusicBrainzRecording {self.recording_id} ({self.title} - {self.artist} ({self.disambiguation}))"
        return f"MusicBrainzRecording {self.recording_id} ({self.title} - {self.artist})"

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
        if "date" in self.mb_data:
            return self.mb_data["date"]
        if "first-release-date" in self.group.mb_data:
            return self.group.mb_data["first-release-date"]
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
    def format(self):
        return self.mb_data["media"][0].get("format", "")

    @GObject.Property(type=str)
    def disambiguation(self):
        return "; ".join(
            [
                x
                for x in (
                    self.props.format,
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
            raise ValueError("Covers have not been downloaded yet; run download_covers_async()")
        if not self.front_cover.props.path:
            return self.group.front_cover_path
        return self.front_cover.props.path

    @GObject.Property(type=str)
    def back_cover_path(self):
        if not self.back_cover.props.loaded:
            raise ValueError("Covers have not been downloaded yet; run download_covers_async()")
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

    def __str__(self):
        return f"MusicBrainzRelease {self.release_id} ({self.title} - {self.artist} ({self.disambiguation}))"

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

        self.mb_data = relgroup_data

        self.thumbnail = EartagCAACover("release-group", self.relgroup_id, "thumbnail")
        self.front_cover = EartagCAACover("release-group", self.relgroup_id, "front")

    @staticmethod
    async def _fetch_full_data(groupid):
        return await mb_query.download(build_url("release-group", groupid, inc=["releases"]))

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
            raise ValueError("Releases have not been initialized yet; run get_releases_async()")
        return self._releases

    async def get_releases_async(self):
        if not self._releases:
            self._releases = [await MusicBrainzRelease.new_for_id(id) for id in self.release_ids]

    @GObject.Property(type=str)
    def thumbnail_path(self):
        return self.thumbnail.props.path

    @GObject.Property(type=str)
    def front_cover_path(self):
        if not self.front_cover.props.loaded:
            raise ValueError("Covers have not been downloaded yet; run download_covers_async()")
        return self.front_cover.props.path

    def __eq__(self, other):
        if not isinstance(other, MusicBrainzReleaseGroup):
            return False
        return self.relgroup_id == other.relgroup_id

    def __hash__(self):
        return hash(self.relgroup_id)


async def acoustid_identify_file(file) -> Tuple[float, "MusicBrainzRecording"]:
    """
    Uses AcoustID and Chromaprint to identify a track's data.

    Returns a tuple containing the confidence and MusicBrainzRecording
    object for the file, or (0.0, None) if it couldn't be found.
    """
    logger.debug(f"Running AcoustID identification for file {os.path.basename(file.path)}")

    try:
        results = await asyncio.to_thread(acoustid.match, ACOUSTID_API_KEY, file.path, parse=False)
        if "results" not in results or not results["results"]:
            return (0.0, None)
    except:  # noqa: E722
        logger.warning(
            f"Error while getting AcoustID match for {os.path.basename(file.path)} ({file.id}):"
        )
        traceback.print_exc()
        logger.warning("Continuing without match. (This is not a fatal error!)")
        return (0.0, None)

    acoustid_data = results["results"][0]

    logger.debug(f"AcoustID identification result: {acoustid_data['score']}")

    if acoustid_data["score"] * 100 < config["acoustid-confidence-treshold"]:
        return (0.0, None)

    if "recordings" in acoustid_data:
        musicbrainz_id = acoustid_data["recordings"][0]["id"]
        logger.debug(f"AcoustID matched recording is {musicbrainz_id}")
        rec = await MusicBrainzRecording.new_for_id(musicbrainz_id)
        rec.sort_releases()  # Sort releases in the recording
        return (acoustid_data["score"], rec)

    logger.debug("No recordings in AcoustID result")
    return (0.0, None)
