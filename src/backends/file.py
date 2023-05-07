# backends/file.py
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

import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GObject, GdkPixbuf
import filecmp
import os
import re
import shutil
import uuid

BASIC_TAGS = (
    'title', 'artist', 'album', 'albumartist', 'tracknumber',
    'totaltracknumber', 'genre', 'releasedate', 'comment'
)

EXTRA_TAGS = (
    'bpm', 'compilation', 'composer', 'copyright', 'encodedby',
    'mood', 'conductor', 'arranger', 'discnumber', 'publisher',
    'isrc', 'language', 'discsubtitle', 'url',

    'albumartistsort', 'albumsort', 'composersort', 'artistsort',
    'titlesort'
)

# Workaround for tests not having the _ variable available
try:
    _
except NameError:
    _ = lambda x: x

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
        "titlesort": _("Title (sort)")
    }


class EartagFileCover:
    """This class is only used for comparing two covers on two files."""
    def __init__(self, cover_path):
        self.cover_path = cover_path
        if cover_path:
            self.update_cover()

    def update_cover(self):
        with open(self.cover_path, 'rb') as cover_file:
            self.cover_data = cover_file.read()

        self.cover_small = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            self.cover_path,
            48,
            48,
            True
        )

        self.cover_large = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            self.cover_path,
            196,
            196,
            True
        )

    def __eq__(self, other):
        if not isinstance(other, EartagFileCover):
            return False
        if self.cover_path and other.cover_path:
            try:
                return filecmp.cmp(self.cover_path, other.cover_path)
            except FileNotFoundError:
                return False
        else:
            if self.cover_path == other.cover_path:
                return True
            else:
                return False

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
    __gtype_name__ = 'EartagFile'

    handled_properties = ('title', 'artist', 'album', 'albumartist', 'tracknumber',
        'totaltracknumber', 'genre', 'releasedate', 'comment')
    int_properties = ('tracknumber', 'totaltracknumber', 'bpm', 'discnumber')
    _supports_album_covers = False
    _is_modified = False
    _is_writable = False
    _has_error = False

    def __init__(self, path):
        """Initializes an EartagFile for the given file path."""
        super().__init__()
        self.notify('supports-album-covers')
        self._path = path
        self.update_writability()
        self._cover = None
        self._cover_path = None
        self.modified_tags = []
        self.original_values = {}
        self._error_fields = []
        self._releasedate_cached = None
        self.id = str(uuid.uuid4()) # Internal ID used for keeping track of files

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
            self.original_values[tag] = self.get_property(tag)
        if self._supports_album_covers:
            self.original_values['cover_path'] = self.get_property('cover_path')

    def update_writability(self):
        """
        Checks if the file is writable and sets the writable property
        accordingly.
        """
        try:
            writable_check = open(self.path, 'a')
            writable_check.close()
        except OSError:
            self._is_writable = False
        else:
            self._is_writable = True
        self.notify('is_writable')

    def set_error(self, field, has_error):
        """Sets an error for the given field."""
        if not has_error and field in self._error_fields:
            self._error_fields.remove(field)
        elif has_error and field not in self._error_fields:
            self._error_fields.append(field)

        self._has_error = has_error
        self.notify('has-error')

    def __del__(self, *args):
        self._cover = None
        super.__del__(*args)

    @property
    def cover(self):
        """Gets raw cover data. This is usually used for comparisons between two files."""
        if not self._supports_album_covers:
            return False

        if not self._cover:
            self._cover = EartagFileCover(self.cover_path)
        elif self._cover.cover_path != self.cover_path:
            self._cover.cover_path = self.cover_path
            self._cover.update_cover()
        return self._cover

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
            self.notify('is_modified')

    @GObject.Property(type=str)
    def path(self):
        """Full path to the file."""
        return self._path

    @path.setter
    def path(self, value):
        """Moves the file to the new location."""
        modifications = {}
        for tag in self.modified_tags:
            modifications[tag] = self.get_property(tag)

        shutil.move(self._path, value)
        self._path = value
        self.load_from_file(value)

        for tag, tag_value in modifications.items():
            self.set_property(tag, tag_value)

    def mark_as_modified(self, tag):
        if not self._is_modified:
            self._is_modified = True
            self.notify('is_modified')
        self.emit('modified', tag)

    def mark_as_unmodified(self):
        if self._is_modified:
            self._is_modified = False
            self.notify('is_modified')
        self.emit('modified', None)
        self.modified_tags = []

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

    # Properties, used for bindings; backends must implement get_tag and set_tag options
    # that take these property names, or redefine the properties

    @GObject.Property(type=str, flags=GObject.ParamFlags.READABLE)
    def filetype(self):
        return os.path.splitext(self.path)[-1]

    @GObject.Property(type=str)
    def cover_path(self):
        return None

    @GObject.Property(type=str)
    def title(self):
        return self.get_tag('title')

    @title.setter
    def title(self, value):
        if value:
            self.set_tag('title', value)
            self.mark_as_modified('title')
        elif self.has_tag('title'):
            self.delete_tag('title')

    @GObject.Property(type=str)
    def artist(self):
        return self.get_tag('artist')

    @artist.setter
    def artist(self, value):
        if value:
            self.set_tag('artist', value)
            self.mark_as_modified('artist')
        elif self.has_tag('artist'):
            self.delete_tag('artist')

    @GObject.Property(type=int)
    def tracknumber(self):
        value = self.get_tag('tracknumber')
        if value:
            return int(value)
        return None

    @tracknumber.setter
    def tracknumber(self, value):
        if value:
            self.set_tag('tracknumber', int(value))
        else:
            self.set_tag('tracknumber', None)
        self.mark_as_modified('tracknumber')

    @GObject.Property(type=int)
    def totaltracknumber(self):
        value = self.get_tag('totaltracknumber')
        if value:
            return int(value)
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        if value:
            self.set_tag('totaltracknumber', int(value))
        else:
            self.set_tag('totaltracknumber', None)
        self.mark_as_modified('totaltracknumber')

    @GObject.Property(type=str)
    def album(self):
        return self.get_tag('album')

    @album.setter
    def album(self, value):
        if value:
            self.set_tag('album', value)
            self.mark_as_modified('album')
        elif self.has_tag('album'):
            self.delete_tag('album')

    @GObject.Property(type=str)
    def albumartist(self):
        return self.get_tag('albumartist')

    @albumartist.setter
    def albumartist(self, value):
        if value:
            self.set_tag('albumartist', value)
            self.mark_as_modified('albumartist')
        elif self.has_tag('albumartist'):
            self.delete_tag('albumartist')

    @GObject.Property(type=str)
    def genre(self):
        return self.get_tag('genre')

    @genre.setter
    def genre(self, value):
        if value:
            self.set_tag('genre', value)
            self.mark_as_modified('genre')
        elif self.has_tag('genre'):
            self.delete_tag('genre')

    # Release dates have custom handling, as invalid values don't get
    # saved correctly, so we only save valid ones to the file itself,
    # and the rest it stored internally:

    def validate_date(self, field, value):
        if not value:
            self.set_error(field, False)
            return

        has_error = True
        if '-' in value:
            for format in ('^[0-9]{4}$', '^[0-9]{4}-[0-9]{2}$',
                    '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'):
                if re.match(format, value):
                    has_error = False
                    break
        else:
            has_error = False

        self.set_error(field, has_error)

    @GObject.Property(type=str)
    def releasedate(self):
        if not self._releasedate_cached:
            value = self.get_tag('releasedate')
            if value and len(value) > 10:
                value = value[:10]
            self._releasedate_cached = value
        return self._releasedate_cached

    @releasedate.setter
    def releasedate(self, value):
        self.validate_date('releasedate', value)
        self._releasedate_cached = value
        if 'releasedate' not in self._error_fields:
            if value:
                self.set_tag('releasedate', value)
            elif self.has_tag('releasedate'):
                self.delete_tag('releasedate')
        self.mark_as_modified('releasedate')

    @GObject.Property(type=str)
    def comment(self):
        return self.get_tag('comment')

    @comment.setter
    def comment(self, value):
        if value:
            self.set_tag('comment', value)
            self.mark_as_modified('comment')
        elif self.has_tag('comment'):
            self.delete_tag('comment')

    # Additional tag properties.

    @GObject.Property(type=float)
    def bpm(self):
        if 'bpm' in self.supported_extra_tags:
            value = self.get_tag('bpm')
            if value:
                # Some BPMs can be floating point values, so we treat this as a float
                try:
                    return float(self.get_tag('bpm'))
                except ValueError:
                    return 0
        return None

    @bpm.setter
    def bpm(self, value):
        if 'bpm' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('bpm', float(value))
            self.mark_as_modified('bpm')
        elif self.has_tag('bpm'):
            self.delete_tag('bpm')

    @GObject.Property(type=str)
    def compilation(self):
        if 'compilation' in self.supported_extra_tags:
            return self.get_tag('compilation')
        return None

    @compilation.setter
    def compilation(self, value):
        if 'compilation' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('compilation', value)
            self.mark_as_modified('compilation')
        elif self.has_tag('compilation'):
            self.delete_tag('compilation')

    @GObject.Property(type=str)
    def composer(self):
        if 'composer' in self.supported_extra_tags:
            return self.get_tag('composer')
        return None

    @composer.setter
    def composer(self, value):
        if 'composer' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('composer', value)
            self.mark_as_modified('composer')
        elif self.has_tag('composer'):
            self.delete_tag('composer')

    @GObject.Property(type=str)
    def copyright(self):
        if 'copyright' in self.supported_extra_tags:
            return self.get_tag('copyright')
        return None

    @copyright.setter
    def copyright(self, value):
        if 'copyright' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('copyright', value)
            self.mark_as_modified('copyright')
        elif self.has_tag('copyright'):
            self.delete_tag('copyright')

    @GObject.Property(type=str)
    def encodedby(self):
        if 'encodedby' in self.supported_extra_tags:
            return self.get_tag('encodedby')
        return None

    @encodedby.setter
    def encodedby(self, value):
        if 'encodedby' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('encodedby', value)
            self.mark_as_modified('encodedby')
        elif self.has_tag('encodedby'):
            self.delete_tag('encodedby')

    @GObject.Property(type=str)
    def mood(self):
        if 'mood' in self.supported_extra_tags:
            return self.get_tag('mood')
        return None

    @mood.setter
    def mood(self, value):
        if 'mood' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('mood', value)
            self.mark_as_modified('mood')
        elif self.has_tag('mood'):
            self.delete_tag('mood')

    @GObject.Property(type=str)
    def conductor(self):
        if 'conductor' in self.supported_extra_tags:
            return self.get_tag('conductor')
        return None

    @conductor.setter
    def conductor(self, value):
        if 'conductor' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('conductor', value)
            self.mark_as_modified('conductor')
        elif self.has_tag('conductor'):
            self.delete_tag('conductor')

    @GObject.Property(type=str)
    def arranger(self):
        if 'arranger' in self.supported_extra_tags:
            return self.get_tag('arranger')
        return None

    @arranger.setter
    def arranger(self, value):
        if 'arranger' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('arranger', value)
            self.mark_as_modified('arranger')
        elif self.has_tag('arranger'):
            self.delete_tag('arranger')

    @GObject.Property(type=int)
    def discnumber(self):
        if 'discnumber' in self.supported_extra_tags:
            value = self.get_tag('discnumber')
            if value:
                return int(value)
        return None

    @discnumber.setter
    def discnumber(self, value):
        if 'discnumber' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('discnumber', int(value))
            self.mark_as_modified('discnumber')
        elif self.has_tag('discnumber'):
            self.delete_tag('discnumber')

    @GObject.Property(type=str)
    def publisher(self):
        if 'publisher' in self.supported_extra_tags:
            return self.get_tag('publisher')
        return None

    @publisher.setter
    def publisher(self, value):
        if 'publisher' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('publisher', value)
            self.mark_as_modified('publisher')
        elif self.has_tag('publisher'):
            self.delete_tag('publisher')

    @GObject.Property(type=str)
    def isrc(self):
        if 'isrc' in self.supported_extra_tags:
            return self.get_tag('isrc')
        return None

    @isrc.setter
    def isrc(self, value):
        if 'isrc' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('isrc', value)
            self.mark_as_modified('isrc')
        elif self.has_tag('isrc'):
            self.delete_tag('isrc')

    @GObject.Property(type=str)
    def language(self):
        if 'language' in self.supported_extra_tags:
            return self.get_tag('language')
        return None

    @language.setter
    def language(self, value):
        if 'language' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('language', value)
            self.mark_as_modified('language')
        elif self.has_tag('language'):
            self.delete_tag('language')

    @GObject.Property(type=str)
    def discsubtitle(self):
        if 'discsubtitle' in self.supported_extra_tags:
            return self.get_tag('discsubtitle')
        return None

    @discsubtitle.setter
    def discsubtitle(self, value):
        if 'discsubtitle' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('discsubtitle', value)
            self.mark_as_modified('discsubtitle')
        elif self.has_tag('discsubtitle'):
            self.delete_tag('discsubtitle')

    # Sort order tags

    @GObject.Property(type=str)
    def albumartistsort(self):
        if 'albumartistsort' in self.supported_extra_tags:
            return self.get_tag('albumartistsort')
        return None

    @albumartistsort.setter
    def albumartistsort(self, value):
        if 'albumartistsort' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('albumartistsort', value)
            self.mark_as_modified('albumartistsort')
        elif self.has_tag('albumartistsort'):
            self.delete_tag('albumartistsort')

    @GObject.Property(type=str)
    def albumsort(self):
        if 'albumsort' in self.supported_extra_tags:
            return self.get_tag('albumsort')
        return None

    @albumsort.setter
    def albumsort(self, value):
        if 'albumsort' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('albumsort', value)
            self.mark_as_modified('albumsort')
        elif self.has_tag('albumsort'):
            self.delete_tag('albumsort')

    @GObject.Property(type=str)
    def composersort(self):
        if 'composersort' in self.supported_extra_tags:
            return self.get_tag('composersort')
        return None

    @composersort.setter
    def composersort(self, value):
        if 'composersort' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('composersort', value)
            self.mark_as_modified('composersort')
        elif self.has_tag('composersort'):
            self.delete_tag('composersort')

    @GObject.Property(type=str)
    def artistsort(self):
        if 'artistsort' in self.supported_extra_tags:
            return self.get_tag('artistsort')
        return None

    @artistsort.setter
    def artistsort(self, value):
        if 'artistsort' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('artistsort', value)
            self.mark_as_modified('artistsort')
        elif self.has_tag('artistsort'):
            self.delete_tag('artistsort')

    @GObject.Property(type=str)
    def titlesort(self):
        if 'titlesort' in self.supported_extra_tags:
            return self.get_tag('titlesort')
        return None

    @titlesort.setter
    def titlesort(self, value):
        if 'titlesort' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('titlesort', value)
            self.mark_as_modified('titlesort')
        elif self.has_tag('titlesort'):
            self.delete_tag('titlesort')

    @GObject.Property(type=str)
    def url(self):
        if 'url' in self.supported_extra_tags:
            return self.get_tag('url')
        return None

    @url.setter
    def url(self, value):
        if 'url' not in self.supported_extra_tags:
            return None
        if value:
            self.set_tag('url', value)
            self.mark_as_modified('url')
        elif self.has_tag('url'):
            self.delete_tag('url')

    @GObject.Property(type=str)
    def none(self):
        return ''

    @none.setter
    def none(self, value):
        return ''
