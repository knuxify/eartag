# file_mutagen_id3.py
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

from mutagen.easyid3 import EasyID3
from mutagen.id3 import PictureType
import mutagen.id3

from .file_mutagen_common import EartagFileMutagenCommon

# These are copied from the code for Mutagen's EasyID3 functions:
KEY_TO_FRAME = {
    'album': 'TALB',
    'bpm': 'TBPM',
    'compilation': 'TCMP',
    'composer': 'TCOM',
    'copyright': 'TCOP',
    'encodedby': 'TENC',
    'lyricist': 'TEXT',
    'length': 'TLEN',
    'media': 'TMED',
    'mood': 'TMOO',
    'grouping': 'TIT1',
    'title': 'TIT2',
    'version': 'TIT3',
    'artist': 'TPE1',
    'albumartist': 'TPE2',
    'conductor': 'TPE3',
    'arranger': 'TPE4',
    'discnumber': 'TPOS',
    'organization': 'TPUB',
    'tracknumber': 'TRCK',
    'author': 'TOLY',
    'albumartistsort': 'TSO2',
    'albumsort': 'TSOA',
    'composersort': 'TSOC',
    'artistsort': 'TSOP',
    'titlesort': 'TSOT',
    'isrc': 'TSRC',
    'discsubtitle': 'TSST',
    'language': 'TLAN',
    'comment': 'COMM::eng'
}

KEY_TO_FRAME_CLASS = {
    'album': mutagen.id3.TALB,
    'bpm': mutagen.id3.TBPM,
    'compilation': mutagen.id3.TCMP,
    'composer': mutagen.id3.TCOM,
    'copyright': mutagen.id3.TCOP,
    'encodedby': mutagen.id3.TENC,
    'lyricist': mutagen.id3.TEXT,
    'length': mutagen.id3.TLEN,
    'media': mutagen.id3.TMED,
    'mood': mutagen.id3.TMOO,
    'grouping': mutagen.id3.TIT1,
    'title': mutagen.id3.TIT2,
    'version': mutagen.id3.TIT3,
    'artist': mutagen.id3.TPE1,
    'albumartist': mutagen.id3.TPE2,
    'conductor': mutagen.id3.TPE3,
    'arranger': mutagen.id3.TPE4,
    'discnumber': mutagen.id3.TPOS,
    'organization': mutagen.id3.TPUB,
    'tracknumber': mutagen.id3.TRCK,
    'author': mutagen.id3.TOLY,
    'albumartistsort': mutagen.id3.TSO2,
    'albumsort': mutagen.id3.TSOA,
    'composersort': mutagen.id3.TSOC,
    'artistsort': mutagen.id3.TSOP,
    'titlesort': mutagen.id3.TSOT,
    'isrc': mutagen.id3.TSRC,
    'discsubtitle': mutagen.id3.TSST,
    'language': mutagen.id3.TLAN,
    'comment': mutagen.id3.COMM
}

class EartagFileMutagenID3(EartagFileMutagenCommon):
    """EartagFile handler that uses mutagen for ID3 support."""
    __gtype_name__ = 'EartagFileMutagenID3'
    _supports_album_covers = False

    def __init__(self, path):
        super().__init__(path)
        if not self.mg_file.tags:
            self.mg_file.add_tags()

    def get_tag(self, tag_name):
        """Gets a tag's value using the KEY_TO_FRAME list as a guideline."""
        try:
            return self.mg_file.tags[KEY_TO_FRAME[tag_name.lower()]].text[0]
        except KeyError:
            return ''

    def set_tag(self, tag_name, value):
        """Sets a tag's value using the KEY_TO_FRAME list as a guideline."""
        frame_name = KEY_TO_FRAME[tag_name.lower()]
        frame_class = KEY_TO_FRAME_CLASS[tag_name.lower()]
        self.mg_file.tags.setall(frame_name, [frame_class(encoding=3, text=[str(value)])])

    @GObject.Property(type=int)
    def tracknumber(self):
        tracknum_raw = self.get_tag('tracknumber')
        if not tracknum_raw:
            return None

        if '/' in tracknum_raw:
            return int(tracknum_raw.split('/')[0])
        return int(tracknum_raw)

    @tracknumber.setter
    def tracknumber(self, value):
        if self.totaltracknumber:
            self.set_tag('tracknumber',
                '{n}/{t}'.format(n=str(value), t=str(self.totaltracknumber))
            )
        else:
            self.set_tag('tracknumber', value)
        self.mark_as_modified()

    @GObject.Property(type=int)
    def totaltracknumber(self):
        tracknum_raw = self.get_tag('tracknumber')
        if not tracknum_raw:
            return None

        if '/' in tracknum_raw:
            return int(tracknum_raw.split('/')[1])
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        if self.tracknumber:
            self.set_tag('tracknumber',
                '{n}/{t}'.format(n=str(self.tracknumber), t=str(value))
            )
        else:
            self.set_tag('tracknumber', '0/{t}'.format(t=str(value)))
        self.mark_as_modified()

    @GObject.Property()
    def genre(self):
        if 'TCON' not in self.mg_file.tags:
            return None
        genre_raw = self.mg_file.tags['TCON']
        if genre_raw and genre_raw.genres:
            return genre_raw.genres[0]
        return None

    @genre.setter
    def genre(self, value):
        try:
            genre_raw = self.mg_file.tags['TCON']
        except KeyError:
            self.mg_file.tags.add(mutagen.id3.TCON(encoding=3, text=[value]))
        else:
            genre_raw.encoding = 3
            genre_raw.frames = [value]
        self.mark_as_modified()

    @GObject.Property()
    def comment(self):
        if 'COMM::XXX' in self.mg_file.tags:
            return self.mg_file.tags['COMM::XXX'].text[0]
        elif 'COMM::eng' in self.mg_file.tags:
            return self.mg_file.tags['COMM::eng'].text[0]
        return None

    @comment.setter
    def comment(self, value):
        self.mg_file.tags.setall('COMM', [mutagen.id3.COMM(encoding=3, lang='eng', desc='', text=[str(value)])])
        self.mark_as_modified()

    # These set both TDRC (date) and TDOR (original date) for compatibility.
    @GObject.Property(type=int)
    def releaseyear(self):
        _date = None
        if 'TDRC' in self.mg_file.tags:
            _date = int(self.mg_file.tags['TDRC'].text[0].year)
        elif 'TDOR' in self.mg_file.tags:
            _date = int(self.mg_file.tags['TDOR'].text[0].year)

        return _date

    @releaseyear.setter
    def releaseyear(self, value):
        self.mg_file.tags.setall('TDRC', [mutagen.id3.TDRC(encoding=3, text=[str(value)])])
        if 'TDOR' not in self.mg_file.tags or self.mg_file.tags['TDOR'] == self.mg_file.tags['TDRC']:
            self.mg_file.tags.setall('TDOR', [mutagen.id3.TDOR(encoding=3, text=[str(value)])])

        self.mark_as_modified()
