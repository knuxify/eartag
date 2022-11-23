# file_mutagen_mp4.py
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

from gi.repository import GObject
import base64
import magic
import mimetypes
import tempfile

from mutagen.mp4 import MP4Cover

from .file_mutagen_common import EartagFileMutagenCommon

# These are copied from the code for Mutagen's EasyMP4 functions:
KEY_TO_FRAME = {
    'title': '\xa9nam',
    'album': '\xa9alb',
    'artist': '\xa9ART',
    'albumartist': 'aART',
    'releaseyear': '\xa9day',
    'comment': '\xa9cmt',
    'description': 'desc',
    'grouping': '\xa9grp',
    'genre': '\xa9gen',
    'copyright': 'cprt',
    'albumsort': 'soal',
    'albumartistsort': 'soaa',
    'artistsort': 'soar',
    'titlesort': 'sonm',
    'composersort': 'soco',
    'tracknumber': 'trkn',
    'cover': 'covr'
}

class EartagFileMutagenMP4(EartagFileMutagenCommon):
    """EartagFile handler that uses mutagen for MP4 support."""
    __gtype_name__ = 'EartagFileMutagenMP4'
    _supports_album_covers = True

    def __init__(self, path):
        super().__init__(path)
        if not self.mg_file.tags:
            self.mg_file.add_tags()
        self.load_cover()
        print(self.mg_file.tags)

    def get_tag(self, tag_name):
        """Gets a tag's value using the KEY_TO_FRAME list as a guideline."""
        try:
            return self.mg_file.tags[KEY_TO_FRAME[tag_name.lower()]][0]
        except KeyError:
            return ''

    def set_tag(self, tag_name, value):
        """Sets a tag's value using the KEY_TO_FRAME list as a guideline."""
        frame_name = KEY_TO_FRAME[tag_name.lower()]
        self.mg_file.tags[frame_name] = [str(value)]

    @GObject.Property(type=str)
    def cover_path(self):
        return self._cover_path

    @cover_path.setter
    def cover_path(self, value):
        self._cover_path = value

        with open(value, "rb") as cover_file:
            data = cover_file.read()

        self.mg_file.tags['covr'] = (MP4Cover(data, MP4Cover.FORMAT_PNG),)

        self.mark_as_modified()

    def load_cover(self):
        """Loads the cover from the file and saves it to a temporary file."""
        picture_data = None

        if 'covr' not in self.mg_file.tags:
            self._cover_path = None
            return None

        picture = self.mg_file.tags['covr'][0]

        if picture.imageformat == MP4Cover.FORMAT_JPEG:
            cover_extension = '.jpg'
        elif picture.imageformat == MP4Cover.FORMAT_PNG:
            cover_extension = '.png'
        else:
            cover_extension = mimetypes.guess_extension(magic.from_buffer(picture, mime=True))

        self.coverart_tempfile = tempfile.NamedTemporaryFile(
            suffix=cover_extension
        )
        self.coverart_tempfile.write(picture)
        self.coverart_tempfile.flush()
        self._cover_path = self.coverart_tempfile.name

    @GObject.Property(type=int)
    def tracknumber(self):
        if 'trkn' not in self.mg_file.tags:
            return None

        return int(self.mg_file.tags['trkn'][0][0])

    @tracknumber.setter
    def tracknumber(self, value):
        if int(value) == -1:
            value = 0
        if self.totaltracknumber:
            self.mg_file.tags['trkn'] = [(int(value), int(self.totaltracknumber))]
        else:
            self.mg_file.tags['trkn'] = [(int(value), 0)]
        self.mark_as_modified()

    @GObject.Property(type=int)
    def totaltracknumber(self):
        if 'trkn' not in self.mg_file.tags:
            return None

        tracknum_raw = self.mg_file.tags['trkn'][0]
        if len(tracknum_raw) > 1:
            return int(tracknum_raw[1])
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        if int(value) == -1:
            value = 0

        if self.tracknumber:
            self.mg_file.tags['trkn'] = [(int(self.tracknumber), int(value))]
        else:
            self.mg_file.tags['trkn'] = [(0, int(value))]
        self.mark_as_modified()
