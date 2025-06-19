# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GObject, GdkPixbuf, GLib
import filecmp
import io
import os
import re
import shutil
import tempfile
import uuid
import asyncio
import hashlib
from PIL import Image

BASIC_TAGS = (
    "title", "artist", "album", "albumartist", "tracknumber",
    "totaltracknumber", "genre", "releasedate", "comment"
)  # fmt: skip

EXTRA_TAGS = (
    "bpm", "compilation", "composer", "copyright", "encodedby",
    "mood", "conductor", "arranger", "discnumber", "publisher",
    "isrc", "language", "discsubtitle", "url",

    "albumartistsort", "albumsort", "composersort", "artistsort",
    "titlesort",

    "musicbrainz_artistid", "musicbrainz_albumid",
    "musicbrainz_albumartistid", "musicbrainz_trackid",
    "musicbrainz_recordingid", "musicbrainz_releasegroupid"
)  # fmt: skip

VALID_TAGS = BASIC_TAGS + EXTRA_TAGS


class CoverType:
    FRONT = 0
    BACK = 1


# Workaround for tests not having the _ variable available
try:
    _
except NameError:
    _ = lambda x: x  # noqa: E731

# Human-readable tag names
TAG_NAMES = {
    "length": _("Length"),
    "bitrate": _("Bitrate"),

    "title": _("Title"),
    "artist": _("Artist"),
    "album": _("Album"),
    "albumartist": _("Album artist"),
    "tracknumber": _("Track number"),
    "totaltracknumber": _("Total tracks"),
    "genre": _("Genre"),
    "releasedate": _("Release date"),
    "comment": _("Comment"),

    "none": _("(Select a tag)"),
    # TRANSLATORS: Short for "beats per minute".
    "bpm": _("BPM"),
    "compilation": _("Compilation"),
    "composer": _("Composer"),
    "copyright": _("Copyright"),
    "encodedby": _("Encoded by"),
    "mood": _("Mood"),
    # TRANSLATORS: Orchestra conductor
    "conductor": _("Conductor"),
    "arranger": _("Arranger"),
    "discnumber": _("Disc number"),
    "publisher": _("Publisher"),
    "isrc": "ISRC",
    "language": _("Language"),
    "discsubtitle": _("Disc subtitle"),
    "url": _("Website/URL"),

    # TRANSLATORS: This is a sort tag, as in, a tag that dictates how music
    # software should treat this tag when sorting.
    "albumartistsort": _("Album artist (sort)"),
    # TRANSLATORS: This is a sort tag, as in, a tag that dictates how music
    # software should treat this tag when sorting.
    "albumsort": _("Album (sort)"),
    # TRANSLATORS: This is a sort tag, as in, a tag that dictates how music
    # software should treat this tag when sorting.
    "composersort": _("Composer (sort)"),
    # TRANSLATORS: This is a sort tag, as in, a tag that dictates how music
    # software should treat this tag when sorting.
    "artistsort": _("Artist (sort)"),
    # TRANSLATORS: This is a sort tag, as in, a tag that dictates how music
    # software should treat this tag when sorting.
    "titlesort": _("Title (sort)"),

    "musicbrainz_artistid": _("MusicBrainz Artist ID"),
    "musicbrainz_albumid": _("MusicBrainz Album ID"),
    "musicbrainz_albumartistid": _("MusicBrainz Album Artist ID"),
    "musicbrainz_trackid": _("MusicBrainz Release Track ID"),
    "musicbrainz_recordingid": _("MusicBrainz Recording ID"),
    "musicbrainz_releasegroupid": _("MusicBrainz Release Group ID"),
}  # fmt: skip


class EartagFileCover:
    """This class is only used for comparing two covers on two files."""

    #: File comparison cache used by ._filecmp()
    _filecmp_cache = {}

    def __init__(self, cover_path):
        self.cover_path = cover_path
        self.cover_hash = None
        if cover_path:
            self.update_cover()

    def update_cover(self):
        if not self.cover_path:
            return

        # Load using Pillow
        with Image.open(self.cover_path) as img:
            # Save some metadata for file comparisons
            self.cover_meta = {
                "size": (img.width, img.height),
                "format": img.format,
                "mode": img.mode,
            }

            def img_to_pixbuf(img: Image) -> GdkPixbuf.Pixbuf:
                """Convert a Pillow image to a GdkPixbuf."""

                # Pillow's raw image data is returned as a list of tuples
                # with (R, G, B) values. This function converts them into
                # GBytes.
                data = GLib.Bytes.new(bytes(x for xs in img.getdata() for x in xs))

                return GdkPixbuf.Pixbuf.new_from_bytes(
                    data,
                    GdkPixbuf.Colorspace.RGB,
                    img.has_transparency_data,
                    8,
                    img.width,
                    img.height,
                    img.width * 3,
                )

            img_rgb = img.convert("RGB")

            img_small = img_rgb.copy()
            img_small.thumbnail((48, 48))

            self.cover_small = img_to_pixbuf(img_small)
            del img_small

            img_large = img_rgb.copy()
            img_large.thumbnail((192, 192))

            self.cover_large = img_to_pixbuf(img_large)
            del img_large

            del img_rgb

    @classmethod
    def _filecmp(cls, path1: str, path2: str):
        """
        Custom cached file comparison implementation.

        filecmp already does caching, but it only applies it when the
        file signatures match. We expect the files to not change mid-way through
        them being opened, so we can skip this check and save an IO operation.
        """
        if (path1, path2) in cls._filecmp_cache:
            return cls._filecmp_cache[(path1, path2)]
        elif (path2, path1) in cls._filecmp_cache:
            return cls._filecmp_cache[(path2, path1)]

        def _do_cmp(path1, path2):
            bufsize = 8*1024
            with open(path1, "rb") as fp1, open(path2, "rb") as fp2:
                while True:
                    b1 = fp1.read(bufsize)
                    b2 = fp2.read(bufsize)
                    if b1 != b2:
                        return False
                    if not b1:
                        return True

        ret = _do_cmp(path1, path2)

        cls._filecmp_cache[(path1, path2)] = ret
        cls._filecmp_cache[(path2, path1)] = ret

        return ret

    def __eq__(self, other):
        if not isinstance(other, EartagFileCover):
            return False
        if self.cover_path and other.cover_path:
            # If covers are present in both files, check metadata first, and only
            # if the metadata is the same, perform a file comparison.
            # The result of the comparison is cached to avoid blocking IO operations
            # whenever a diff is done.
            try:
                return self.cover_meta == other.cover_meta or EartagFileCover._filecmp(
                    self.cover_path, other.cover_path
                )
            except FileNotFoundError:
                return False
        else:
            if self.cover_path == other.cover_path:
                return True
            else:
                return False

    def is_empty(self):
        return not bool(self.cover_path)


class EartagFile(GObject.Object):
    """
    Generic base for GObject wrappers that provide information about a music
    file.

    The following functions are implemented by the subclasses:
      - save() - saves the changes to a file.
      - get_tag(tag_name) - gets the tag with the given name. The name matches
                            the property name of the tag in this object.
      - set_tag(tag_name, value) - gets the tag with the given name. The name
                           matches the property name of the tag in this object.

    Do not use get_tag and set_tag directly in the code; use get_property and
    set_property instead.
    """

    __gtype_name__ = "EartagFile"

    handled_properties = BASIC_TAGS
    int_properties = ("tracknumber", "totaltracknumber", "discnumber")
    float_properties = ("bpm",)
    supported_extra_tags = []
    _supports_album_covers = False
    _is_modified = False
    _is_writable = False
    _has_error = False

    def __init__(self, path):
        """Initializes an EartagFile for the given file path."""
        super().__init__()
        self.notify("supports-album-covers")
        self._path = path
        self.update_writability()
        self._front_cover = None
        self._front_cover_path = None
        self._back_cover = None
        self._back_cover_path = None
        self.front_cover_tempfile = None
        self.back_cover_tempfile = None
        self.modified_tags = []
        self.original_values = {}
        self._error_fields = []
        self._releasedate_cached = None
        self.id = str(uuid.uuid4())  # Internal ID used for keeping track of files
        self.connect("notify::front-cover-path", self._update_front_cover)
        self.connect("notify::back-cover-path", self._update_back_cover)

    @classmethod
    async def new_from_path(cls, path):
        """Create a new EartagFile instance for the file with the given path."""
        file = cls(path)
        await file.load_from_file(path)
        return file

    def on_remove(self, *args):
        if self.front_cover_tempfile:
            self.front_cover_tempfile.close()
        if self.back_cover_tempfile:
            self.back_cover_tempfile.close()

    def save(self):
        """Saves tag changes to the file. Must be implemented by the backend."""
        raise NotImplementedError

    def get_tag(self, tag_name):
        """Gets a tag for a specific property. Must be implemented by the backend."""
        raise NotImplementedError

    def set_tag(self, tag_name, value):
        """Sets a tag for a specific property. Must be implemented by the backend."""
        raise NotImplementedError

    def has_tag(self, tag_name):
        """Returns whether a tag is present in a file. Must be implemented by the backend."""
        raise NotImplementedError

    def delete_tag(self, tag_name):
        """Deletes the tag from the file. Must be implemented by the backend."""
        raise NotImplementedError

    def delete_all_raw(self):
        """
        Completely removes all metadata, including information that Ear Tag cannot
        read. Implementations must call the regular delete_all function first.
        This is used by the "clear all tags" option.

        Must be implemented by the backend.
        """
        raise NotImplementedError

    def delete_all(self):
        """Deletes all present tags."""
        for tag in self.present_tags:
            self.delete_tag(tag)
        for cover_type in (CoverType.FRONT, CoverType.BACK):
            self.delete_cover(cover_type)

    @property
    def present_tags(self) -> list:
        """Returns a list of present tags."""
        present_tags = []
        for tag in self.handled_properties:
            if self.has_tag(tag):
                present_tags.append(tag)
        return present_tags + self.present_extra_tags

    def setup_present_extra_tags(self):
        """
        For performance reasons, each file keeps a list of present extra tags.
        This is used by the fileview to determine which rows to display for
        extra tags.
        """
        self.present_extra_tags = []

        for tag in self.supported_extra_tags:
            if self.has_tag(tag):
                self.present_extra_tags.append(tag)

    def setup_original_values(self):
        """
        Sets up the list of original values to compare new values against.
        Run this every time the file is loaded or saved.

        Call this only after setup_present_extra_tags and load_cover have been called.
        """
        self.original_values = {}
        for tag in set(tuple(self.handled_properties) + tuple(self.present_extra_tags)):
            value = self.get_property(tag)
            if tag in self.int_properties + self.float_properties and value is None:
                self.original_values[tag] = 0
            else:
                self.original_values[tag] = self.get_property(tag)
        if self._supports_album_covers:
            self.original_values["front_cover_path"] = self.get_property(
                "front_cover_path"
            )
            self.original_values["back_cover_path"] = self.get_property(
                "back_cover_path"
            )

    def update_writability(self):
        """
        Checks if the file is writable and sets the writable property
        accordingly.
        """
        try:
            writable_check = open(self.path, "a")
            writable_check.close()
        except OSError:
            self._is_writable = False
        else:
            self._is_writable = True
        self.notify("is_writable")

    def set_error(self, field, has_error):
        """Sets an error for the given field."""
        if not has_error and field in self._error_fields:
            self._error_fields.remove(field)
        elif has_error and field not in self._error_fields:
            self._error_fields.append(field)

        self._has_error = has_error
        self.notify("has-error")

    @GObject.Signal(arg_types=(str,))
    def modified(self, tag):
        if not tag:
            return

        new_value = self.get_property(tag)
        if tag in self.supported_extra_tags:
            if new_value and tag not in self.present_extra_tags:
                self.present_extra_tags.append(tag)
            elif not new_value and tag in self.present_extra_tags:
                self.present_extra_tags.remove(tag)

        if tag in self.original_values:
            old_value = self.original_values[tag]
            if old_value == new_value or (not old_value and not new_value):
                if tag in self.modified_tags:
                    self.modified_tags.remove(tag)
            elif tag not in self.modified_tags:
                self.modified_tags.append(tag)
        elif not new_value:
            if tag in self.modified_tags:
                self.modified_tags.remove(tag)
        elif tag not in self.modified_tags:
            self.modified_tags.append(tag)

        if not self.modified_tags:
            self._is_modified = False
            self.notify("is_modified")

    @GObject.Property(type=str)
    def path(self):
        """Full path to the file."""
        return self._path

    @path.setter
    def path(self, value):
        """Moves the file to the new location."""
        raise ValueError("Use set_path_async to change the file path.")

    async def set_path_async(self, value: str):
        """
        Moves the file to the new location.
        (Internal function that does not notify the path property; used by the
        rename UI to prevent crashes.)
        """
        if value == self._path:
            return

        modifications = {}
        for tag in self.modified_tags:
            modifications[tag] = self.get_property(tag)

        await asyncio.to_thread(shutil.move, self._path, value)
        self._path = value
        await self.load_from_file(value)

        for tag, tag_value in modifications.items():
            self.set_property(tag, tag_value)

    async def reload(self):
        """Reloads the file and discards all modifications."""
        await self.load_from_file(self.props.path)
        for prop in (
            BASIC_TAGS
            + tuple(self.supported_extra_tags)
            + ("front_cover_path", "back_cover_path")
        ):
            self.notify(prop)

        self.mark_as_unmodified()

    def mark_as_modified(self, tag, notify_prop: bool = False):
        if not self._is_modified:
            self._is_modified = True
            self.notify("is_modified")
        if notify_prop:
            self.notify(tag)
        self.emit("modified", tag)

    def mark_as_unmodified(self):
        if self._is_modified:
            self._is_modified = False
            self.notify("is_modified")
        self.emit("modified", None)
        self.modified_tags = []

    def mark_tag_as_unmodified(self, tag):
        was_modified = bool(self.modified_tags)
        try:
            self.modified_tags.remove(tag)
        except ValueError:
            return
        if bool(self.modified_tags) != was_modified:
            self._is_modified = bool(self.modified_tags)
            self.notify("is_modified")
        self.emit("modified", None)

    def undo_all(self):
        """Undo all changes."""
        for tag in self.modified_tags.copy():
            if tag in self.original_values:
                self.set_property(tag, self.original_values[tag])
            else:
                self.delete_tag(tag)
        self.mark_as_unmodified()

    def reset_to_original(self):
        """Resets to original values."""
        for tag, value in self.original_values.items():
            self.set_property(tag, value)
        self.mark_as_unmodified()

    @GObject.Property(type=bool, default=False)
    def is_modified(self):
        """Returns whether the values have been modified or not."""
        return self._is_modified

    @GObject.Property(type=bool, default=False)
    def has_error(self):
        """Returns whether or not there's an error with the file's values."""
        return self._has_error

    @GObject.Property(type=bool, default=False)
    def supports_album_covers(self):
        """Returns whether album covers are supported."""
        return self._supports_album_covers

    @GObject.Property(type=bool, default=False)
    def is_writable(self):
        """Returns whether the file can be written to."""
        return self._is_writable

    # Cover art handling functions

    @property
    def front_cover(self):
        """Gets raw cover data. This is usually used for comparisons between two files."""
        if not self._supports_album_covers:
            return False

        if not self._front_cover:
            self._front_cover = EartagFileCover(self._front_cover_path)
        elif self._front_cover.cover_path != self._front_cover_path:
            self._front_cover.cover_path = self._front_cover_path
            self._front_cover.update_cover()
        return self._front_cover

    def _update_front_cover(self, *args):
        return self.front_cover  # handles all updates

    @property
    def back_cover(self):
        """Gets raw cover data. This is usually used for comparisons between two files."""
        if not self._supports_album_covers:
            return False

        if not self._back_cover:
            self._back_cover = EartagFileCover(self._back_cover_path)
        elif self._back_cover.cover_path != self._back_cover_path:
            self._back_cover.cover_path = self._back_cover_path
            self._back_cover.update_cover()
        return self._back_cover

    def _update_back_cover(self, *args):
        return self.back_cover  # handles all updates

    def get_cover(self, cover_type: CoverType):
        """Gets a cover for the given cover type."""
        if cover_type == CoverType.FRONT:
            return self.front_cover
        elif cover_type == CoverType.BACK:
            return self.back_cover
        raise ValueError("Incorrect cover type")

    def get_cover_path(self, cover_type: CoverType):
        """Gets a cover path for the given cover type."""
        if cover_type == CoverType.FRONT:
            return self.front_cover_path
        elif cover_type == CoverType.BACK:
            return self.back_cover_path
        raise ValueError("Incorrect cover type")

    def _get_cover_tempfile_for_type(self, cover_type: CoverType):
        """Returns the cover tempfile for the given cover type."""
        if cover_type == CoverType.FRONT:
            return self.front_cover_tempfile
        elif cover_type == CoverType.BACK:
            return self.back_cover_tempfile
        raise ValueError("Incorrect cover type")

    async def create_cover_tempfile(self, cover_type: CoverType, data, extension):
        """Writes data to the cover tempfile for the given cover type."""
        _tempfile = tempfile.NamedTemporaryFile(suffix=extension)

        def _write_cover(tmp):
            tmp.write(data)
            tmp.flush()

        await asyncio.to_thread(_write_cover, _tempfile)

        if cover_type == CoverType.FRONT:
            self.front_cover_tempfile = _tempfile
            self._front_cover_path = _tempfile.name
        elif cover_type == CoverType.BACK:
            self.back_cover_tempfile = _tempfile
            self._back_cover_path = _tempfile.name

    def _cleanup_front_cover(self):
        """Common cleanup steps after delete_front_cover."""
        self._front_cover_path = ""
        self.mark_as_modified("front_cover_path")
        self.notify("front-cover-path")

    def _cleanup_back_cover(self):
        """Common cleanup steps after delete_back_cover."""
        self._back_cover_path = ""
        self.mark_as_modified("back_cover_path")
        self.notify("back-cover-path")

    def _cleanup_cover(self, cover_type: CoverType):
        """Common cleanup steps after delete_cover."""
        if cover_type == CoverType.FRONT:
            return self._cleanup_front_cover()
        elif cover_type == CoverType.BACK:
            return self._cleanup_back_cover()
        raise ValueError

    @GObject.Property(type=str)
    def front_cover_path(self):
        if not self._supports_album_covers:
            return None
        return self._front_cover_path

    @front_cover_path.setter
    def front_cover_path(self, value):
        if not self._supports_album_covers:
            return None
        self.set_cover_path(CoverType.FRONT, value)

    @GObject.Property(type=str)
    def back_cover_path(self):
        if not self._supports_album_covers:
            return None
        return self._back_cover_path

    @back_cover_path.setter
    def back_cover_path(self, value):
        if not self._supports_album_covers:
            return None
        self.set_cover_path(CoverType.BACK, value)

    # Properties, used for bindings; backends must implement get_tag and set_tag options
    # that take these property names, or redefine the properties

    @GObject.Property(type=str, flags=GObject.ParamFlags.READABLE)
    def filetype(self):
        return os.path.splitext(self.path)[-1]

    @GObject.Property(type=str)
    def title(self):
        return self.get_tag("title")

    @title.setter
    def title(self, value):
        if value:
            self.set_tag("title", value)
            self.mark_as_modified("title")
        elif self.has_tag("title"):
            self.delete_tag("title")

    @GObject.Property(type=str)
    def artist(self):
        return self.get_tag("artist")

    @artist.setter
    def artist(self, value):
        if value:
            self.set_tag("artist", value)
            self.mark_as_modified("artist")
        elif self.has_tag("artist"):
            self.delete_tag("artist")

    @GObject.Property(type=int)
    def tracknumber(self):
        value = self.get_tag("tracknumber")
        if value:
            return int(value)
        return None

    @tracknumber.setter
    def tracknumber(self, value):
        if value:
            self.set_tag("tracknumber", int(value))
            self.mark_as_modified("tracknumber")
        else:
            self.delete_tag("tracknumber")

    @GObject.Property(type=int)
    def totaltracknumber(self):
        value = self.get_tag("totaltracknumber")
        if value:
            return int(value)
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        if value:
            self.set_tag("totaltracknumber", int(value))
            self.mark_as_modified("totaltracknumber")
        else:
            self.delete_tag("totaltracknumber")

    @GObject.Property(type=str)
    def album(self):
        return self.get_tag("album")

    @album.setter
    def album(self, value):
        if value:
            self.set_tag("album", value)
            self.mark_as_modified("album")
        elif self.has_tag("album"):
            self.delete_tag("album")

    @GObject.Property(type=str)
    def albumartist(self):
        return self.get_tag("albumartist")

    @albumartist.setter
    def albumartist(self, value):
        if value:
            self.set_tag("albumartist", value)
            self.mark_as_modified("albumartist")
        elif self.has_tag("albumartist"):
            self.delete_tag("albumartist")

    @GObject.Property(type=str)
    def genre(self):
        return self.get_tag("genre")

    @genre.setter
    def genre(self, value):
        if value:
            self.set_tag("genre", value)
            self.mark_as_modified("genre")
        elif self.has_tag("genre"):
            self.delete_tag("genre")

    # Release dates have custom handling, as invalid values don't get
    # saved correctly, so we only save valid ones to the file itself,
    # and the rest it stored internally:

    def validate_date(self, field, value):
        if not value:
            self.set_error(field, False)
            return

        has_error = True
        if "-" in value:
            for format in (
                "^[0-9]{4}$",
                "^[0-9]{4}-[0-9]{2}$",
                "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
            ):
                if re.match(format, value):
                    has_error = False
                    break
        else:
            has_error = False

        self.set_error(field, has_error)

    @GObject.Property(type=str)
    def releasedate(self):
        if not self._releasedate_cached and self.has_tag("releasedate"):
            value = self.get_tag("releasedate")
            if value and len(value) > 10:
                value = value[:10]
            self._releasedate_cached = value
        return self._releasedate_cached

    @releasedate.setter
    def releasedate(self, value):
        self.validate_date("releasedate", value)
        self._releasedate_cached = value
        if "releasedate" not in self._error_fields:
            if value:
                self.set_tag("releasedate", value)
            elif self.has_tag("releasedate"):
                self._releasedate_cached = None
                self.delete_tag("releasedate")
        self.mark_as_modified("releasedate")

    @GObject.Property(type=str)
    def comment(self):
        return self.get_tag("comment")

    @comment.setter
    def comment(self, value):
        if value:
            self.set_tag("comment", value)
            self.mark_as_modified("comment")
        elif self.has_tag("comment"):
            self.delete_tag("comment")

    # Additional tag properties.

    @GObject.Property(type=float)
    def bpm(self):
        if "bpm" in self.supported_extra_tags:
            value = self.get_tag("bpm")
            if value:
                # Some BPMs can be floating point values, so we treat this as a float
                try:
                    return float(self.get_tag("bpm"))
                except ValueError:
                    return None
        return None

    @bpm.setter
    def bpm(self, value):
        if "bpm" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("bpm", float(value))
            self.mark_as_modified("bpm")
        elif self.has_tag("bpm"):
            self.delete_tag("bpm")

    @GObject.Property(type=str)
    def compilation(self):
        if "compilation" in self.supported_extra_tags:
            return self.get_tag("compilation")
        return None

    @compilation.setter
    def compilation(self, value):
        if "compilation" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("compilation", value)
            self.mark_as_modified("compilation")
        elif self.has_tag("compilation"):
            self.delete_tag("compilation")

    @GObject.Property(type=str)
    def composer(self):
        if "composer" in self.supported_extra_tags:
            return self.get_tag("composer")
        return None

    @composer.setter
    def composer(self, value):
        if "composer" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("composer", value)
            self.mark_as_modified("composer")
        elif self.has_tag("composer"):
            self.delete_tag("composer")

    @GObject.Property(type=str)
    def copyright(self):
        if "copyright" in self.supported_extra_tags:
            return self.get_tag("copyright")
        return None

    @copyright.setter
    def copyright(self, value):
        if "copyright" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("copyright", value)
            self.mark_as_modified("copyright")
        elif self.has_tag("copyright"):
            self.delete_tag("copyright")

    @GObject.Property(type=str)
    def encodedby(self):
        if "encodedby" in self.supported_extra_tags:
            return self.get_tag("encodedby")
        return None

    @encodedby.setter
    def encodedby(self, value):
        if "encodedby" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("encodedby", value)
            self.mark_as_modified("encodedby")
        elif self.has_tag("encodedby"):
            self.delete_tag("encodedby")

    @GObject.Property(type=str)
    def mood(self):
        if "mood" in self.supported_extra_tags:
            return self.get_tag("mood")
        return None

    @mood.setter
    def mood(self, value):
        if "mood" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("mood", value)
            self.mark_as_modified("mood")
        elif self.has_tag("mood"):
            self.delete_tag("mood")

    @GObject.Property(type=str)
    def conductor(self):
        if "conductor" in self.supported_extra_tags:
            return self.get_tag("conductor")
        return None

    @conductor.setter
    def conductor(self, value):
        if "conductor" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("conductor", value)
            self.mark_as_modified("conductor")
        elif self.has_tag("conductor"):
            self.delete_tag("conductor")

    @GObject.Property(type=str)
    def arranger(self):
        if "arranger" in self.supported_extra_tags:
            return self.get_tag("arranger")
        return None

    @arranger.setter
    def arranger(self, value):
        if "arranger" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("arranger", value)
            self.mark_as_modified("arranger")
        elif self.has_tag("arranger"):
            self.delete_tag("arranger")

    @GObject.Property(type=int)
    def discnumber(self):
        if "discnumber" in self.supported_extra_tags:
            value = self.get_tag("discnumber")
            if value:
                return int(value)
        return None

    @discnumber.setter
    def discnumber(self, value):
        if "discnumber" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("discnumber", int(value))
            self.mark_as_modified("discnumber")
        elif self.has_tag("discnumber"):
            self.delete_tag("discnumber")

    @GObject.Property(type=str)
    def publisher(self):
        if "publisher" in self.supported_extra_tags:
            return self.get_tag("publisher")
        return None

    @publisher.setter
    def publisher(self, value):
        if "publisher" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("publisher", value)
            self.mark_as_modified("publisher")
        elif self.has_tag("publisher"):
            self.delete_tag("publisher")

    @GObject.Property(type=str)
    def isrc(self):
        if "isrc" in self.supported_extra_tags:
            return self.get_tag("isrc")
        return None

    @isrc.setter
    def isrc(self, value):
        if "isrc" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("isrc", value)
            self.mark_as_modified("isrc")
        elif self.has_tag("isrc"):
            self.delete_tag("isrc")

    @GObject.Property(type=str)
    def language(self):
        if "language" in self.supported_extra_tags:
            return self.get_tag("language")
        return None

    @language.setter
    def language(self, value):
        if "language" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("language", value)
            self.mark_as_modified("language")
        elif self.has_tag("language"):
            self.delete_tag("language")

    @GObject.Property(type=str)
    def discsubtitle(self):
        if "discsubtitle" in self.supported_extra_tags:
            return self.get_tag("discsubtitle")
        return None

    @discsubtitle.setter
    def discsubtitle(self, value):
        if "discsubtitle" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("discsubtitle", value)
            self.mark_as_modified("discsubtitle")
        elif self.has_tag("discsubtitle"):
            self.delete_tag("discsubtitle")

    # Sort order tags

    @GObject.Property(type=str)
    def albumartistsort(self):
        if "albumartistsort" in self.supported_extra_tags:
            return self.get_tag("albumartistsort")
        return None

    @albumartistsort.setter
    def albumartistsort(self, value):
        if "albumartistsort" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("albumartistsort", value)
            self.mark_as_modified("albumartistsort")
        elif self.has_tag("albumartistsort"):
            self.delete_tag("albumartistsort")

    @GObject.Property(type=str)
    def albumsort(self):
        if "albumsort" in self.supported_extra_tags:
            return self.get_tag("albumsort")
        return None

    @albumsort.setter
    def albumsort(self, value):
        if "albumsort" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("albumsort", value)
            self.mark_as_modified("albumsort")
        elif self.has_tag("albumsort"):
            self.delete_tag("albumsort")

    @GObject.Property(type=str)
    def composersort(self):
        if "composersort" in self.supported_extra_tags:
            return self.get_tag("composersort")
        return None

    @composersort.setter
    def composersort(self, value):
        if "composersort" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("composersort", value)
            self.mark_as_modified("composersort")
        elif self.has_tag("composersort"):
            self.delete_tag("composersort")

    @GObject.Property(type=str)
    def artistsort(self):
        if "artistsort" in self.supported_extra_tags:
            return self.get_tag("artistsort")
        return None

    @artistsort.setter
    def artistsort(self, value):
        if "artistsort" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("artistsort", value)
            self.mark_as_modified("artistsort")
        elif self.has_tag("artistsort"):
            self.delete_tag("artistsort")

    @GObject.Property(type=str)
    def titlesort(self):
        if "titlesort" in self.supported_extra_tags:
            return self.get_tag("titlesort")
        return None

    @titlesort.setter
    def titlesort(self, value):
        if "titlesort" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("titlesort", value)
            self.mark_as_modified("titlesort")
        elif self.has_tag("titlesort"):
            self.delete_tag("titlesort")

    @GObject.Property(type=str)
    def url(self):
        if "url" in self.supported_extra_tags:
            return self.get_tag("url")
        return None

    @url.setter
    def url(self, value):
        if "url" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("url", value)
            self.mark_as_modified("url")
        elif self.has_tag("url"):
            self.delete_tag("url")

    # MusicBrainz tags

    @GObject.Property(type=str)
    def musicbrainz_artistid(self):
        if "musicbrainz_artistid" in self.supported_extra_tags:
            return self.get_tag("musicbrainz_artistid")
        return None

    @musicbrainz_artistid.setter
    def musicbrainz_artistid(self, value):
        if "musicbrainz_artistid" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("musicbrainz_artistid", value)
            self.mark_as_modified("musicbrainz_artistid")
        elif self.has_tag("musicbrainz_artistid"):
            self.delete_tag("musicbrainz_artistid")

    @GObject.Property(type=str)
    def musicbrainz_albumid(self):
        if "musicbrainz_albumid" in self.supported_extra_tags:
            return self.get_tag("musicbrainz_albumid")
        return None

    @musicbrainz_albumid.setter
    def musicbrainz_albumid(self, value):
        if "musicbrainz_albumid" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("musicbrainz_albumid", value)
            self.mark_as_modified("musicbrainz_albumid")
        elif self.has_tag("musicbrainz_albumid"):
            self.delete_tag("musicbrainz_albumid")

    @GObject.Property(type=str)
    def musicbrainz_albumartistid(self):
        if "musicbrainz_albumartistid" in self.supported_extra_tags:
            return self.get_tag("musicbrainz_albumartistid")
        return None

    @musicbrainz_albumartistid.setter
    def musicbrainz_albumartistid(self, value):
        if "musicbrainz_albumartistid" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("musicbrainz_albumartistid", value)
            self.mark_as_modified("musicbrainz_albumartistid")
        elif self.has_tag("musicbrainz_albumartistid"):
            self.delete_tag("musicbrainz_albumartistid")

    @GObject.Property(type=str)
    def musicbrainz_trackid(self):
        if "musicbrainz_trackid" in self.supported_extra_tags:
            return self.get_tag("musicbrainz_trackid")
        return None

    @musicbrainz_trackid.setter
    def musicbrainz_trackid(self, value):
        if "musicbrainz_trackid" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("musicbrainz_trackid", value)
            self.mark_as_modified("musicbrainz_trackid")
        elif self.has_tag("musicbrainz_trackid"):
            self.delete_tag("musicbrainz_trackid")

    @GObject.Property(type=str)
    def musicbrainz_recordingid(self):
        if "musicbrainz_recordingid" in self.supported_extra_tags:
            return self.get_tag("musicbrainz_recordingid")
        return None

    @musicbrainz_recordingid.setter
    def musicbrainz_recordingid(self, value):
        if "musicbrainz_recordingid" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("musicbrainz_recordingid", value)
            self.mark_as_modified("musicbrainz_recordingid")
        elif self.has_tag("musicbrainz_recordingid"):
            self.delete_tag("musicbrainz_recordingid")

    @GObject.Property(type=str)
    def musicbrainz_releasegroupid(self):
        if "musicbrainz_releasegroupid" in self.supported_extra_tags:
            return self.get_tag("musicbrainz_releasegroupid")
        return None

    @musicbrainz_releasegroupid.setter
    def musicbrainz_releasegroupid(self, value):
        if "musicbrainz_releasegroupid" not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag("musicbrainz_releasegroupid", value)
            self.mark_as_modified("musicbrainz_releasegroupid")
        elif self.has_tag("musicbrainz_releasegroupid"):
            self.delete_tag("musicbrainz_releasegroupid")

    @GObject.Property(type=str)
    def none(self):
        return ""

    @none.setter
    def none(self, value):
        return ""
