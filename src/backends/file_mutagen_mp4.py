# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import GObject
import base64
import magic
import mimetypes
import io
from PIL import Image

from mutagen.mp4 import MP4Cover

from .file import CoverType
from .file_mutagen_common import EartagFileMutagenCommon

EMPTY_COVER = MP4Cover(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQIW2NgAAIAAAUAAR4f7BQAAAAASUVORK5CYII="  # noqa: E501
    ),
    MP4Cover.FORMAT_PNG,
)


# These are copied from the code for Mutagen's EasyMP4 functions:
KEY_TO_FRAME = {
    "title": "\xa9nam",
    "album": "\xa9alb",
    "artist": "\xa9ART",
    "albumartist": "aART",
    "releasedate": "\xa9day",
    "comment": "\xa9cmt",
    "description": "desc",
    "grouping": "\xa9grp",
    "genre": "\xa9gen",
    "copyright": "cprt",
    "albumsort": "soal",
    "albumartistsort": "soaa",
    "artistsort": "soar",
    "titlesort": "sonm",
    "composersort": "soco",
    "tracknumber": "trkn",
    "totaltracknumber": "trkn",
    "cover": "covr",
    "copyright": "cprt",
    "bpm": "tmpo",
    "composer": "\xa9wrt",
    "encodedby": "\xa9enc",  # might be \xa9too
    "discnumber": "disk",

    "conductor": "----:com.apple.iTunes:CONDUCTOR",
    "discsubtitle": "----:com.apple.iTunes:DISCSUBTITLE",
    "language": "----:com.apple.iTunes:LANGUAGE",
    "mood": "----:com.apple.iTunes:MOOD",

    "musicbrainz_recordingid": "----:com.apple.iTunes:MusicBrainz Track Id",
    "musicbrainz_artistid": "----:com.apple.iTunes:MusicBrainz Artist Id",
    "musicbrainz_albumid": "----:com.apple.iTunes:MusicBrainz Album Id",
    "musicbrainz_albumartistid": "----:com.apple.iTunes:MusicBrainz Album Artist Id",
    "musicbrainz_releasegroupid": "----:com.apple.iTunes:MusicBrainz Release Group Id",
    "musicbrainz_trackid": "----:com.apple.iTunes:MusicBrainz Release Track Id",
}  # fmt: skip

# Annoyingly, there's no central MP4 tag standard; most software just tries to
# do what iTunes does (or did at some point... apparently they've had since 2005
# or even earlier to figure it out...)


class EartagFileMutagenMP4(EartagFileMutagenCommon):
    """EartagFile handler that uses mutagen for MP4 support."""

    __gtype_name__ = "EartagFileMutagenMP4"
    _supports_album_covers = True
    _supports_full_dates = True

    supported_extra_tags = (
        "bpm", "composer", "copyright", "encodedby",
        "mood", "conductor", "discnumber", "language", "discsubtitle",

        "albumartistsort", "albumsort", "composersort", "artistsort",
        "titlesort",

        "musicbrainz_artistid", "musicbrainz_albumid",
        "musicbrainz_albumartistid", "musicbrainz_trackid",
        "musicbrainz_recordingid", "musicbrainz_releasegroupid"
    )  # fmt: skip

    async def load_from_file(self, path):
        await super().load_from_file(path)
        if self.mg_file.tags is None:
            self.mg_file.add_tags()
        await self.load_cover()
        self.setup_present_extra_tags()
        self.setup_original_values()

    def get_tag(self, tag_name):
        """Gets a tag's value using the KEY_TO_FRAME list as a guideline."""
        frame_name = KEY_TO_FRAME[tag_name.lower()]
        try:
            if frame_name.startswith("----"):
                return self.mg_file.tags[frame_name][0].decode("utf-8") or ""
            elif tag_name in self.int_properties:
                return self.mg_file.tags[frame_name][0]
            else:
                return self.mg_file.tags[frame_name][0] or ""
        except KeyError:
            return ""

    def set_tag(self, tag_name, value):
        """Sets a tag's value using the KEY_TO_FRAME list as a guideline."""
        frame_name = KEY_TO_FRAME[tag_name.lower()]
        if frame_name.startswith("----"):
            self.mg_file.tags[frame_name] = [value.encode("utf-8")]
        elif tag_name in ("bpm", "discnumber"):
            self.mg_file.tags[frame_name] = [int(value)]
        else:
            self.mg_file.tags[frame_name] = [str(value)]

    def has_tag(self, tag_name):
        """
        Returns True or False based on whether the tag with the given name is
        present in the file.
        """
        if tag_name == "totaltracknumber":
            return bool(self.totaltracknumber)
        if tag_name not in KEY_TO_FRAME:
            return False
        frame_name = KEY_TO_FRAME[tag_name.lower()]
        if frame_name in self.mg_file.tags:
            return True
        return False

    def delete_tag(self, tag_name):
        """Deletes the tag with the given name from the file."""
        frame_name = KEY_TO_FRAME[tag_name.lower()]
        if tag_name.lower() == "releasedate":
            self._releasedate_cached = ""
        if frame_name in self.mg_file.tags:
            del self.mg_file.tags[frame_name]
        self.mark_as_modified(tag_name, notify_prop=True)

    def delete_cover(self, cover_type: CoverType, clear_only=False):
        """Deletes the cover from the file."""
        if "covr" not in self.mg_file.tags:
            if not clear_only:
                self._cleanup_cover(cover_type)
            return

        cover_val = self.mg_file.tags["covr"]
        if not cover_val:
            if not clear_only:
                self._cleanup_cover(cover_type)
            return

        if cover_type == CoverType.FRONT:
            if len(cover_val) == 1:
                del self.mg_file.tags["covr"]
                if not clear_only:
                    self._cleanup_cover(cover_type)
                return
            elif len(cover_val) >= 2:
                cover_val[0] = EMPTY_COVER

        elif cover_type == CoverType.BACK:
            if len(cover_val) == 1:
                if not clear_only:
                    self._cleanup_cover(cover_type)
                return
            elif len(cover_val) == 2:
                cover_val = [cover_val[0]]
            elif len(cover_val) > 2:
                cover_val[1] = EMPTY_COVER

        try:
            if cover_val[0] == EMPTY_COVER and cover_val[1] == EMPTY_COVER:
                cover_val = []
        except IndexError:
            pass

        self.mg_file.tags["covr"] = cover_val

        if not clear_only:
            self._cleanup_cover(cover_type)

    def on_remove(self, *args):
        super().on_remove()

    def set_cover_path(self, cover_type: CoverType, value):
        if not value:
            self.delete_cover()
            return

        # Only PNG is allowed. For other types, convert to PNG first.
        if magic.from_file(value, mime=True) == "image/png":
            with open(value, "rb") as cover_file:
                data = cover_file.read()
        else:
            with Image.open(value) as img:
                out = io.BytesIO()
                img.save(out, format="PNG")
                data = out.getvalue()

        with open(value, "rb") as cover_file:
            data = cover_file.read()

        cover_val = []
        if "covr" in self.mg_file.tags:
            cover_val = self.mg_file.tags["covr"]

        if cover_type == CoverType.FRONT:
            try:
                cover_val[0] = MP4Cover(data, MP4Cover.FORMAT_PNG)
            except IndexError:
                cover_val.append(MP4Cover(data, MP4Cover.FORMAT_PNG))
            self.mg_file.tags["covr"] = cover_val
            self._front_cover_path = value
            self.mark_as_modified("front_cover_path")

        elif cover_type == CoverType.BACK:
            # I can't figure out how to specify a back cover in MP4 tags -
            # I found one forum post on a closed-source tagger's forum that
            # claims MP4 supports front and back covers, but I can't find
            # anything in Mutagen that would allow me to specify which one
            # to use... so we just set the second cover in the cover list
            # instead.
            if len(cover_val) == 0:
                # In general, this should never happen... if someone is setting
                # a back cover, then they probably set a front cover as well,
                # but let's handle this just in case.
                #
                # Set the front cover to a transparent 1x1 pixel.
                cover_val = [EMPTY_COVER, MP4Cover(data, MP4Cover.FORMAT_PNG)]
            elif len(cover_val) == 1:
                cover_val.append(MP4Cover(data, MP4Cover.FORMAT_PNG))
            elif len(cover_val) >= 2:
                cover_val[1] = MP4Cover(data, MP4Cover.FORMAT_PNG)

            self.mg_file.tags["covr"] = cover_val
            self._back_cover_path = value
            self.mark_as_modified("back_cover_path")

    async def load_cover(self):
        """Loads the cover from the file and saves it to a temporary file."""
        if "covr" not in self.mg_file.tags or not self.mg_file.tags["covr"]:
            self._front_cover_path = None
            self._back_cover_path = None
            return None

        picture = self.mg_file.tags["covr"][0]
        if picture != EMPTY_COVER:
            if picture.imageformat == MP4Cover.FORMAT_JPEG:
                cover_extension = ".jpg"
            elif picture.imageformat == MP4Cover.FORMAT_PNG:
                cover_extension = ".png"
            else:
                cover_extension = mimetypes.guess_extension(
                    magic.from_buffer(picture, mime=True)
                )

            await self.create_cover_tempfile(CoverType.FRONT, picture, cover_extension)

        try:
            picture_back = self.mg_file.tags["covr"][1]
            assert picture_back != EMPTY_COVER
        except (AssertionError, IndexError):
            pass
        else:
            if picture_back.imageformat == MP4Cover.FORMAT_JPEG:
                cover_extension = ".jpg"
            elif picture_back.imageformat == MP4Cover.FORMAT_PNG:
                cover_extension = ".png"
            else:
                cover_extension = mimetypes.guess_extension(
                    magic.from_buffer(picture_back, mime=True)
                )

            await self.create_cover_tempfile(CoverType.BACK, picture_back, cover_extension)

    @GObject.Property(type=str)
    def releasedate(self):
        if not self._releasedate_cached:
            self._releasedate_cached = self.get_tag("releasedate")
        return self._releasedate_cached

    @releasedate.setter
    def releasedate(self, value):
        if value:
            self.validate_date("releasedate", value)
            self._releasedate_cached = value
            if "releasedate" not in self._error_fields:
                self.set_tag("releasedate", value)
        else:
            self.delete_tag("releasedate")
        self.mark_as_modified("releasedate")

    @GObject.Property(type=int)
    def tracknumber(self):
        if "trkn" not in self.mg_file.tags:
            return None

        return int(self.mg_file.tags["trkn"][0][0])

    @tracknumber.setter
    def tracknumber(self, value):
        if int(value) == -1 or not value:
            value = 0
        if self.totaltracknumber:
            self.mg_file.tags["trkn"] = [(int(value), int(self.totaltracknumber))]
        else:
            if value:
                self.mg_file.tags["trkn"] = [(int(value), 0)]
            elif self.has_tag("tracknumber"):
                self.delete_tag("tracknumber")
        self.mark_as_modified("tracknumber")

    @GObject.Property(type=int)
    def totaltracknumber(self):
        if "trkn" not in self.mg_file.tags:
            return None

        tracknum_raw = self.mg_file.tags["trkn"][0]
        if len(tracknum_raw) > 1:
            return int(tracknum_raw[1])
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        if int(value) == -1 or not value:
            value = 0

        if self.tracknumber:
            self.mg_file.tags["trkn"] = [(int(self.tracknumber), int(value))]
        else:
            if value:
                self.mg_file.tags["trkn"] = [(0, int(value))]
            elif self.has_tag("tracknumber"):
                self.delete_tag("tracknumber")
        self.mark_as_modified("totaltracknumber")

    @GObject.Property(type=int)
    def discnumber(self):
        if "disk" not in self.mg_file.tags and "DISK" not in self.mg_file.tags:
            return None

        try:
            return int(self.mg_file.tags["disk"][0][0])
        except KeyError:
            return int(self.mg_file.tags["DISK"][0][0])

    @discnumber.setter
    def discnumber(self, value):
        if int(value) == -1 or not value:
            value = 0

        if value:
            self.mg_file.tags["disk"] = [(int(value), 0)]
        elif self.has_tag("discnumber"):
            self.delete_tag("discnumber")
        self.mark_as_modified("discnumber")
