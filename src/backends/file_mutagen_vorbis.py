# file_mutagen_vorbis.py
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
from PIL import Image

from mutagen.flac import FLAC, Picture, error as FLACError
from mutagen.oggvorbis import OggVorbis

from .file import EartagFile

class EartagFileMutagenVorbis(EartagFile):
    """EartagFile handler that uses mutagen for Voris Comment support."""
    __gtype_name__ = 'EartagFileMutagenVorbis'

    mg_file = None
    _supports_album_covers = True
    cover_picture = None
    _cover_path = None
    coverart_tempfile = None

    def __init__(self, path):
        super().__init__(path)
        if mimetypes.guess_type(path)[0] == 'audio/flac' or \
                magic.Magic(mime=True).from_file(path) == 'audio/flac':
            self.mg_file = FLAC(path)
        else:
            self.mg_file = OggVorbis(path)

        self.load_cover()

    def _get_tag(self, tag_name):
        """Tries the lowercase, then uppercase representation of the tag."""
        try:
            return self.mg_file.tags[tag_name.lower()][0]
        except KeyError:
            try:
                return self.mg_file.tags[tag_name.upper()][0]
            except KeyError:
                return ''

    def save(self):
        """Saves the changes to the file."""
        if self.mg_file:
            self.mg_file.save()
        self.mark_as_unmodified()

    def __del__(self, *args):
        if self.coverart_tempfile:
            self.coverart_tempfile.close()
        self.mg_file = None

    # Main properties

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def length(self):
        return self.mg_file.info.length

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def bitrate(self):
        # in bps, needs conversion
        return round(self.mg_file.info.bitrate / 1000, 0)

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def channels(self):
        return self.mg_file.info.channels

    @GObject.Property(type=str, flags=GObject.ParamFlags.READABLE)
    def filetype(self):
        mimetype = magic.Magic(mime=True).from_file(self.path)
        if mimetype == 'audio/flac':
            return 'flac'
        else:
            return 'ogg'

    @GObject.Property(type=str)
    def cover_path(self):
        return self._cover_path

    @cover_path.setter
    def cover_path(self, value):
        self._cover_path = value

        with open(value, "rb") as cover_file:
            data = cover_file.read()

        # shamelessly stolen from https://stackoverflow.com/questions/1996577/how-can-i-get-the-depth-of-a-jpg-file
        mode_to_bpp = {"1": 1, "L": 8, "P": 8, "RGB": 24, "RGBA": 32, "CMYK": 32, "YCbCr": 24, "LAB": 24, "HSV": 24, "I": 32, "F": 32}

        picture = Picture()
        picture.data = data
        picture.type = 17
        picture.mime = magic.Magic(mime=True).from_file(value)
        img = Image.open(value)
        picture.width = img.width
        picture.height = img.height
        picture.depth = mode_to_bpp[img.mode]

        picture_data = picture.write()
        encoded_data = base64.b64encode(picture_data)
        vcomment_value = encoded_data.decode("ascii")

        self.mg_file["metadata_block_picture"] = [vcomment_value]

        self.mark_as_modified()

    def load_cover(self):
        """Loads cover data from file."""
        for b64_data in self.mg_file.get("metadata_block_picture", []):
            try:
                data = base64.b64decode(b64_data)
            except (TypeError, ValueError):
                continue

            try:
                self.cover_picture = Picture(data)
            except FLACError:
                continue

            cover_extension = mimetypes.guess_extension(self.cover_picture.mime)

            self.coverart_tempfile = tempfile.NamedTemporaryFile(
                suffix=cover_extension
            )
            self.coverart_tempfile.write(self.cover_picture.data)
            self.coverart_tempfile.flush()
            self._cover_path = self.coverart_tempfile.name
        self.notify('cover_path')

    @GObject.Property(type=str)
    def title(self):
        return self._get_tag('title')

    @title.setter
    def title(self, value):
        self.mg_file.tags['title'] = value
        self.mark_as_modified()

    @GObject.Property(type=str)
    def artist(self):
        return self._get_tag('artist')

    @artist.setter
    def artist(self, value):
        self.mg_file.tags['artist'] = value
        self.mark_as_modified()

    @GObject.Property(type=int)
    def tracknumber(self):
        if 'TRACKNUMBER' in self.mg_file.tags:
            if '/' in self.mg_file.tags['TRACKNUMBER'][0]:
                return int(self.mg_file.tags['TRACKNUMBER'][0].split('/')[0])
            return int(self.mg_file.tags['TRACKNUMBER'][0])
        return None

    @tracknumber.setter
    def tracknumber(self, value):
        if self.totaltracknumber:
            self.mg_file.tags['TRACKNUMBER'] = ['{n}/{t}'.format(
                n=str(value), t=str(self.totaltracknumber))
            ]
        else:
            self.mg_file.tags['TRACKNUMBER'] = [str(value)]
        self.mark_as_modified()

    @GObject.Property(type=int)
    def totaltracknumber(self):
        if 'TRACKNUMBER' in self.mg_file.tags:
            if '/' in self.mg_file.tags['TRACKNUMBER'][0]:
                return int(self.mg_file.tags['TRACKNUMBER'][0].split('/')[1])
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        if self.tracknumber:
            self.mg_file.tags['TRACKNUMBER'] = ['{n}/{t}'.format(
                n=str(self.tracknumber), t=str(value))
            ]
        else:
            self.mg_file.tags['TRACKNUMBER'] = ['0/{t}'.format(t=str(value))]
        self.mark_as_modified()

    @GObject.Property(type=str)
    def album(self):
        return self._get_tag('album')

    @album.setter
    def album(self, value):
        self.mg_file.tags['album'] = value
        self.mark_as_modified()

    @GObject.Property(type=str)
    def albumartist(self):
        return self._get_tag('ALBUMARTIST')

    @albumartist.setter
    def albumartist(self, value):
        self.mg_file.tags['ALBUMARTIST'] = [value]
        self.mark_as_modified()

    @GObject.Property(type=str)
    def genre(self):
        return self._get_tag('genre')

    @genre.setter
    def genre(self, value):
        self.mg_file.tags['genre'] = value
        self.mark_as_modified()

    @GObject.Property(type=int)
    def releaseyear(self):
        return self._get_tag('date')

    @releaseyear.setter
    def releaseyear(self, value):
        if value >= 0:
            self.mg_file.tags['date'] = str(value)
        else:
            self.mg_file.tags['date'] = ''
        self.mark_as_modified()

    @GObject.Property(type=str)
    def comment(self):
        return self._get_tag('DESCRIPTION')

    @comment.setter
    def comment(self, value):
        self.mg_file.tags['DESCRIPTION'] = value
        self.mark_as_modified()
