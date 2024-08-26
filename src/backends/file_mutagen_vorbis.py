# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import GObject
import base64
import magic
import mimetypes
from PIL import Image

from mutagen.flac import FLAC, Picture, error as FLACError
from mutagen.id3 import PictureType

from .file import CoverType
from .file_mutagen_common import EartagFileMutagenCommon


class EartagFileMutagenVorbis(EartagFileMutagenCommon):
    """EartagFile handler that uses mutagen for Voris Comment support."""

    __gtype_name__ = "EartagFileMutagenVorbis"
    _supports_album_covers = True
    _supports_full_dates = True

    # There's an official standard and semi-official considerations for tags,
    # plus some more documents linked from https://wiki.xiph.org/VorbisComment;
    # this only covers tags mentioned there.
    supported_extra_tags = (
        "composer", "copyright", "encodedby", "mood", "discnumber", "publisher",
        "isrc",

        "albumartistsort", "albumsort", "composersort", "artistsort", "titlesort",

        "musicbrainz_artistid", "musicbrainz_albumid",
        "musicbrainz_albumartistid", "musicbrainz_trackid",
        "musicbrainz_recordingid", "musicbrainz_releasegroupid"
    )  # fmt: skip

    _replaces = {
        "releasedate": "date",
        # There"s also ENCODED-BY, but confusingly it represents... the person doing the encoding?
        "encodedby": "encoder",
        # Matching Picard behavior:
        "musicbrainz_trackid": "musicbrainz_releasetrackid",
        "musicbrainz_recordingid": "musicbrainz_trackid"
    }  # fmt: skip

    def load_from_file(self, path):
        super().load_from_file(path)
        self.load_cover()
        self.setup_present_extra_tags()
        self.setup_original_values()

    def get_tag(self, tag_name):
        """Tries the lowercase, then uppercase representation of the tag."""
        if tag_name.lower() in self._replaces:
            tag_name = self._replaces[tag_name.lower()]
        try:
            if tag_name in self.int_properties:
                return self.mg_file.tags[tag_name.lower()][0]
            else:
                return self.mg_file.tags[tag_name.lower()][0] or ""
        except KeyError:
            try:
                if tag_name in self.int_properties:
                    return self.mg_file.tags[tag_name.upper()][0]
                else:
                    return self.mg_file.tags[tag_name.upper()][0] or ""
            except KeyError:
                if tag_name in self.int_properties:
                    return None
                else:
                    return ""

    def set_tag(self, tag_name, value):
        """Sets the tag with the given name to the given value."""
        if tag_name.lower() in self._replaces:
            tag_name = self._replaces[tag_name.lower()]
        if tag_name.upper() in self.mg_file.tags:
            self.mg_file.tags[tag_name.upper()] = str(value)
        else:
            self.mg_file.tags[tag_name] = str(value)

    def has_tag(self, tag_name):
        """
        Returns True or False based on whether the tag with the given name is
        present in the file.
        """
        if tag_name == "totaltracknumber":
            return bool(self.totaltracknumber)
        elif tag_name == "encodedby":
            if "encoder" in self.mg_file.tags:
                return bool(self.mg_file.tags["encoder"][0])
            elif "ENCODER" in self.mg_file.tags:
                return bool(self.mg_file.tags["ENCODER"][0])
            else:
                return False
        if tag_name.lower() in self._replaces:
            tag_name = self._replaces[tag_name.lower()]
        if tag_name in self.mg_file.tags or tag_name.upper() in self.mg_file.tags:
            return True
        return False

    def delete_tag(self, tag_name):
        """Deletes the tag with the given name from the file."""
        _original_tag_name = tag_name
        if tag_name.lower() == "releasedate":
            self._releasedate_cached = ""
        if tag_name.lower() in self._replaces:
            tag_name = self._replaces[tag_name.lower()]
        if tag_name in self.mg_file.tags:
            del self.mg_file.tags[tag_name]
        self.mark_as_modified(_original_tag_name, notify_prop=True)

    def delete_cover(self, cover_type: CoverType, clear_only=False):
        if cover_type == CoverType.FRONT:
            pictypes = (PictureType.OTHER, PictureType.COVER_FRONT)
        elif cover_type == CoverType.BACK:
            pictypes = (PictureType.COVER_BACK,)
        else:
            raise ValueError

        if isinstance(self.mg_file, FLAC):
            pic_list = list(self.mg_file.pictures)
            for _pic in pic_list.copy():
                if _pic.type in pictypes:
                    pic_list.remove(_pic)

            # There's no way to remove a picture, so we have to clear and re-add
            # all the existing ones:
            self.mg_file.clear_pictures()
            for _pic in pic_list:
                self.mg_file.add_picture(_pic)

        pic_list = list(self.mg_file.get("metadata_block_picture", []))
        for b64_data in pic_list.copy():
            try:
                data = base64.b64decode(b64_data)
            except (TypeError, ValueError):
                continue

            try:
                cover_picture = Picture(data)
            except FLACError:
                continue

            if cover_picture.type in pictypes:
                pic_list.remove(b64_data)

        self.mg_file["metadata_block_picture"] = pic_list

        if not clear_only:
            self._cleanup_cover(cover_type)

    def on_remove(self, *args):
        super().on_remove()

    def set_cover_path(self, cover_type: CoverType, value):
        if not value:
            return self.delete_cover(cover_type)

        if cover_type == CoverType.FRONT:
            pictype = PictureType.COVER_FRONT
            prop = "front_cover_path"
            self._front_cover_path = value
        elif cover_type == CoverType.BACK:
            pictype = PictureType.COVER_BACK
            prop = "back_cover_path"
            self._back_cover_path = value
        else:
            raise ValueError

        with open(value, "rb") as cover_file:
            data = cover_file.read()

        # shamelessly stolen from
        # https://stackoverflow.com/questions/1996577/how-can-i-get-the-depth-of-a-jpg-file
        mode_to_bpp = {
            "1": 1,
            "L": 8,
            "P": 8,
            "RGB": 24,
            "RGBA": 32,
            "CMYK": 32,
            "YCbCr": 24,
            "LAB": 24,
            "HSV": 24,
            "I": 32,
            "F": 32,
        }

        picture = Picture()
        picture.data = data
        picture.type = pictype
        picture.mime = magic.from_file(value, mime=True)
        img = Image.open(value)
        picture.width = img.width
        picture.height = img.height
        picture.depth = mode_to_bpp[img.mode]

        # Remove all conflicting pictures
        self.delete_cover(cover_type, clear_only=True)

        if isinstance(self.mg_file, FLAC):
            self.mg_file.add_picture(picture)

        picture_data = picture.write()
        encoded_data = base64.b64encode(picture_data)
        vcomment_value = encoded_data.decode("ascii")
        if "metadata_block_picture" in self.mg_file:
            self.mg_file["metadata_block_picture"] = [
                vcomment_value
            ] + self.mg_file["metadata_block_picture"]
        else:
            self.mg_file["metadata_block_picture"] = [vcomment_value]

        self.mark_as_modified(prop)

    def _load_cover(self, cover_type: CoverType):
        """Loads cover data from file."""
        if cover_type == CoverType.FRONT:
            prop = "front_cover_path"
        elif cover_type == CoverType.BACK:
            prop = "back_cover_path"
        else:
            raise ValueError

        # See https://mutagen.readthedocs.io/en/latest/user/vcomment.html.
        # There are three ways to get the cover image:

        # 1. Using `mutagen.flac.FLAC.pictures`
        if isinstance(self.mg_file, FLAC) and self.mg_file.pictures:
            picture = None
            picture_cover = None
            picture_other = None
            picture_back = None

            if cover_type == CoverType.FRONT:
                for _picture in self.mg_file.pictures:
                    if _picture.type == PictureType.COVER_FRONT:
                        picture_cover = _picture

                    elif _picture.type == PictureType.OTHER:
                        picture_other = _picture

                if picture_cover:
                    picture = picture_cover
                elif picture_other:
                    picture = picture_other
                else:
                    self.notify("front_cover_path")

                if picture:
                    cover_extension = mimetypes.guess_extension(picture.mime)
                    self.create_cover_tempfile(
                        cover_type, picture.data, cover_extension
                    )
            elif cover_type == CoverType.BACK:
                for _picture in self.mg_file.pictures:
                    if _picture.type == PictureType.COVER_BACK:
                        picture_back = _picture
                        break

                if picture_back:
                    cover_extension = mimetypes.guess_extension(picture_back.mime)
                    self.create_cover_tempfile(
                        cover_type, picture_back.data, cover_extension
                    )

        # 2. Using metadata_block_picture
        elif self.mg_file.get("metadata_block_picture", []):
            cover_front = None
            covers_other = []
            cover_back = None

            for b64_data in self.mg_file.get("metadata_block_picture", []):
                try:
                    data = base64.b64decode(b64_data)
                except (TypeError, ValueError):
                    continue

                try:
                    cover_picture = Picture(data)
                except FLACError:
                    continue

                if cover_type == CoverType.FRONT:
                    if cover_picture.type == PictureType.COVER_FRONT:
                        cover_front = cover_picture
                        break
                    elif cover_picture.type == PictureType.OTHER:
                        covers_other.append(cover_picture)

                elif cover_type == CoverType.BACK:
                    if cover_picture.type == PictureType.COVER_BACK:
                        cover_back = cover_picture
                        break

            if not cover_front and covers_other:
                cover_front = covers_other[0]

            if cover_front:
                cover_extension = mimetypes.guess_extension(cover_front.mime)
                self.create_cover_tempfile(
                    CoverType.FRONT, cover_front.data, cover_extension
                )

            if cover_back:
                cover_extension = mimetypes.guess_extension(cover_back.mime)
                self.create_cover_tempfile(
                    CoverType.BACK, cover_back.data, cover_extension
                )

        # 3. Using the coverart field (and optionally covermime)
        elif cover_type == CoverType.FRONT:
            covers = self.mg_file.get("coverart", [])
            mimes = self.mg_file.get("coverartmime", [])

            n = 0
            for cover in covers:
                try:
                    data = base64.b64decode(cover.encode("ascii"))
                except (TypeError, ValueError):
                    continue

                if not data:
                    continue

                cover_extension = mimetypes.guess_extension(
                    magic.from_buffer(data, mime=True)
                )
                if not cover_extension and mimes and len(mimes) == len(covers):
                    cover_extension = mimes[n]

                self.create_cover_tempfile(cover_type, data, cover_extension)
                n += 1

        self.notify(prop)

    def load_cover(self):
        for cover_type in (CoverType.FRONT, CoverType.BACK):
            self._load_cover(cover_type)

    @GObject.Property(type=int)
    def tracknumber(self):
        tracknum_raw = self.get_tag("tracknumber")
        if not tracknum_raw:
            return None
        if "/" in tracknum_raw:
            return int(tracknum_raw.split("/")[0])
        return int(tracknum_raw)

    @tracknumber.setter
    def tracknumber(self, value):
        if self.totaltracknumber:
            self.set_tag(
                "tracknumber",
                "{n}/{t}".format(n=str(value), t=str(self.totaltracknumber)),
            )
        else:
            if value:
                self.set_tag("tracknumber", str(value))
            elif self.has_tag("tracknumber"):
                self.delete_tag("tracknumber")
        self.mark_as_modified("tracknumber")

    @GObject.Property(type=int)
    def totaltracknumber(self):
        tracknum_raw = self.get_tag("tracknumber")
        if not tracknum_raw:
            return None
        if "/" in tracknum_raw:
            return int(tracknum_raw.split("/")[1])
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        if self.tracknumber:
            self.set_tag(
                "tracknumber", "{n}/{t}".format(n=str(self.tracknumber), t=str(value))
            )
        else:
            if value:
                self.set_tag("tracknumber", "0/{t}".format(t=str(value)))
            elif self.has_tag("tracknumber"):
                self.delete_tag("tracknumber")
        self.mark_as_modified("totaltracknumber")

    @GObject.Property(type=int)
    def discnumber(self):
        discnum_raw = self.get_tag("discnumber")
        if not discnum_raw:
            return None
        if "/" in discnum_raw:
            return int(discnum_raw.split("/")[0])
        return int(discnum_raw)

    @discnumber.setter
    def discnumber(self, value):
        if value:
            self.set_tag("discnumber", str(value))
        elif self.has_tag("discnumber"):
            self.delete_tag("discnumber")
        self.mark_as_modified("discnumber")
