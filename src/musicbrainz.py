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

from gi.repository import GObject

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
            return make_request(url, raw=raw, _recursion=(_recursion + 1))
        else:
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
                if rel.cover_tempfiles["thumbnail"]:
                    rel.cover_tempfiles["thumbnail"].close()

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
        return id(self)


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
        self.cover_tempfiles = {
            "thumbnail": None,
            "front": MusicBrainzRelease.NEED_UPDATE_COVER,
            "back": MusicBrainzRelease.NEED_UPDATE_COVER,
        }

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

        self.full_data = MusicBrainzRelease.full_data_cache[self.release_id]
        if from_id:
            self.mb_data = self.full_data

        if self.release_id not in MusicBrainzRelease.obj_cache:
            MusicBrainzRelease.obj_cache[self.release_id] = self

        self.group = MusicBrainzReleaseGroup(self.mb_data["release-group"])

        self.update_thumbnail()

    @staticmethod
    def setup_from_id(id):
        if id in MusicBrainzRelease.obj_cache:
            return MusicBrainzRelease.obj_cache[id]
        return MusicBrainzRelease(release_data={}, from_id=id)

    def dispose(self):
        for temp in self.cover_tempfiles.values():
            if temp and temp != MusicBrainzRelease.NEED_UPDATE_COVER:
                temp.close()

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
        if not self.cover_tempfiles["thumbnail"]:
            return self.group.thumbnail_path
        return self.cover_tempfiles["thumbnail"].name

    @GObject.Property(type=str)
    def front_cover_path(self):
        if not self.cover_tempfiles["front"]:
            return self.group.front_cover_path
        elif self.cover_tempfiles["front"] == MusicBrainzRelease.NEED_UPDATE_COVER:
            raise ValueError("Covers have not been downloaded yet; run update_covers()")
        return self.cover_tempfiles["front"].name

    @GObject.Property(type=str)
    def back_cover_path(self):
        if not self.cover_tempfiles["back"]:
            return ""
        elif self.cover_tempfiles["back"] == MusicBrainzRelease.NEED_UPDATE_COVER:
            raise ValueError("Covers have not been downloaded yet; run update_covers()")
        return self.cover_tempfiles["back"].name

    def update_thumbnail(self):
        """Downloads the thumbnail for the release from coverartarchive.org"""
        url = f"https://coverartarchive.org/release/{self.release_id}/front-250"
        if url in MusicBrainzRelease.cover_cache:
            self.cover_tempfiles["thumbnail"] = MusicBrainzRelease.cover_cache[url]
            self.notify("thumbnail-path")
            return

        if not self.full_data["cover-art-archive"]["front"]:
            MusicBrainzRelease.cover_cache[url] = None
            # Try to get thumbnail for group instead
            self.group.update_thumbnail()
            return

        data = make_request(url, raw=True)
        if not data:
            # Try to get thumbnail for group instead
            self.group.update_thumbnail()
            return

        cover_extension = mimetypes.guess_extension(magic.from_buffer(data, mime=True))
        self.cover_tempfiles["thumbnail"] = tempfile.NamedTemporaryFile(
            suffix=cover_extension
        )
        self.cover_tempfiles["thumbnail"].write(data)
        self.cover_tempfiles["thumbnail"].flush()
        MusicBrainzRelease.cover_cache[url] = self.cover_tempfiles["thumbnail"]
        self.notify("thumbnail-path")

    def update_covers(self, if_needed=False):
        """Downloads the covers for the release from coverartarchive.org"""
        if (
            if_needed
            and self.cover_tempfiles["front"] != MusicBrainzRelease.NEED_UPDATE_COVER
        ):
            return

        self.group.update_covers(if_needed)

        if config.get_enum("musicbrainz-cover-size") == 0:
            self.cover_tempfiles["front"] = ""
            self.cover_tempfiles["back"] = ""
            self.notify("front-cover-path")
            self.notify("back-cover-path")
            return

        for cover in ("front", "back"):
            url = f"https://coverartarchive.org/release/{self.release_id}/{cover}"

            if not self.full_data["cover-art-archive"][cover]:
                MusicBrainzRelease.cover_cache[url] = None
                self.cover_tempfiles[cover] = ""
                self.notify(f"{cover}-cover-path")
                continue

            if config.get_enum("musicbrainz-cover-size") in (250, 500, 1200):
                url += "-" + str(config.get_enum("musicbrainz-cover-size"))

            if url in MusicBrainzRelease.cover_cache:
                if MusicBrainzRelease.cover_cache[url]:
                    self.cover_tempfiles[cover] = MusicBrainzRelease.cover_cache[url]
                else:
                    self.cover_tempfiles[cover] = ""
                self.notify(f"{cover}-cover-path")
                continue

            data = make_request(url, raw=True)
            if not data:
                self.cover_tempfiles[cover] = ""
                continue

            cover_extension = mimetypes.guess_extension(
                magic.from_buffer(data, mime=True)
            )
            self.cover_tempfiles[cover] = tempfile.NamedTemporaryFile(
                suffix=cover_extension
            )
            self.cover_tempfiles[cover].write(data)
            self.cover_tempfiles[cover].flush()
            MusicBrainzRelease.cover_cache[url] = self.cover_tempfiles[cover]
            self.notify(f"{cover}-cover-path")

    @classmethod
    def clear_tempfiles(cls):
        """Closes all cover tempfiles."""
        for tmp in cls.cover_cache:
            try:
                tmp.close()
            except AttributeError:
                pass

    def __str__(self):
        return f"MusicBrainzRelease {self.release_id} ({self.title} - {self.artist})"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if not isinstance(other, MusicBrainzRelease):
            return False
        return self.release_id == other.release_id

    def __hash__(self):
        return id(self)


class MusicBrainzReleaseGroup(GObject.Object):
    """A container for release group information, as found in the release query."""

    __gtype_name__ = "MusicBrainzReleaseGroup"

    NO_COVER = -2

    cover_cache = {}
    full_data_cache = {}
    obj_cache = {}

    def __init__(self, relgroup_data, from_id=False):
        super().__init__()
        self._releases = None
        self.cover_tempfiles = {
            "thumbnail": None,
            "front": MusicBrainzRelease.NEED_UPDATE_COVER,
        }

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
        if not self.cover_tempfiles["thumbnail"]:
            self.update_thumbnail()
        if self.cover_tempfiles["thumbnail"] == MusicBrainzReleaseGroup.NO_COVER:
            return ""
        return self.cover_tempfiles["thumbnail"].name

    @GObject.Property(type=str)
    def front_cover_path(self):
        if (
            not self.cover_tempfiles["front"]
            or self.cover_tempfiles["front"] == MusicBrainzReleaseGroup.NO_COVER
        ):
            return ""
        elif self.cover_tempfiles["front"] == MusicBrainzRelease.NEED_UPDATE_COVER:
            raise ValueError("Covers have not been downloaded yet; run update_covers()")
        return self.cover_tempfiles["front"].name

    def update_thumbnail(self):
        """Downloads the thumbnail for the release from coverartarchive.org"""
        url = f"https://coverartarchive.org/release-group/{self.relgroup_id}/front-250"
        if url in MusicBrainzRelease.cover_cache:
            self.cover_tempfiles["thumbnail"] = MusicBrainzRelease.cover_cache[url]
            self.notify("thumbnail-path")
            return

        data = make_request(url, raw=True)
        if not data:
            self.cover_tempfiles["thumbnail"] = MusicBrainzReleaseGroup.NO_COVER
            self.notify("thumbnail-path")
            return

        cover_extension = mimetypes.guess_extension(magic.from_buffer(data, mime=True))
        self.cover_tempfiles["thumbnail"] = tempfile.NamedTemporaryFile(
            suffix=cover_extension
        )
        self.cover_tempfiles["thumbnail"].write(data)
        self.cover_tempfiles["thumbnail"].flush()
        MusicBrainzRelease.cover_cache[url] = self.cover_tempfiles["thumbnail"]
        self.notify("thumbnail-path")

    def update_covers(self, if_needed=False):
        """Downloads the covers for the release from coverartarchive.org"""
        if (
            if_needed
            and self.cover_tempfiles["front"] != MusicBrainzRelease.NEED_UPDATE_COVER
        ):
            return

        if config.get_enum("musicbrainz-cover-size") == 0:
            self.cover_tempfiles["front"] = ""
            return

        url = f"https://coverartarchive.org/release-group/{self.relgroup_id}/front"

        if config.get_enum("musicbrainz-cover-size") in (250, 500, 1200):
            url += "-" + str(config.get_enum("musicbrainz-cover-size"))

        if url in MusicBrainzRelease.cover_cache:
            if MusicBrainzRelease.cover_cache[url]:
                self.cover_tempfiles["front"] = MusicBrainzRelease.cover_cache[url]
            else:
                self.cover_tempfiles["front"] = ""
            self.notify("front-cover-path")
            return

        data = make_request(url, raw=True)
        if not data:
            self.cover_tempfiles["front"] = MusicBrainzReleaseGroup.NO_COVER
            self.notify("front-cover-path")
            return

        cover_extension = mimetypes.guess_extension(magic.from_buffer(data, mime=True))
        self.cover_tempfiles["front"] = tempfile.NamedTemporaryFile(
            suffix=cover_extension
        )
        self.cover_tempfiles["front"].write(data)
        self.cover_tempfiles["front"].flush()
        MusicBrainzRelease.cover_cache[url] = self.cover_tempfiles["front"]
        self.notify("front-cover-path")

    @classmethod
    def clear_tempfiles(cls):
        """Closes all cover tempfiles."""
        for tmp in cls.cover_cache:
            try:
                tmp.close()
            except AttributeError:
                pass

    def __eq__(self, other):
        if not isinstance(other, MusicBrainzReleaseGroup):
            return False
        return self.relgroup_id == other.relgroup_id

    def __hash__(self):
        return id(self)


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
        traceback.print_exc()
        return (0.0, None)

    acoustid_data = results["results"][0]

    if acoustid_data["score"] * 100 < config["acoustid-confidence-treshold"]:
        return (0.0, None)

    if "recordings" in acoustid_data:
        musicbrainz_id = acoustid_data["recordings"][0]["id"]
        rec = MusicBrainzRecording(musicbrainz_id, file=file)

        return (acoustid_data["score"], rec)

    return (0.0, None)
