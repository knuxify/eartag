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
import tempfile
import magic
import mimetypes
from PIL import Image

from mutagen.flac import FLAC, Picture, error as FLACError
from mutagen.oggvorbis import OggVorbis
from mutagen.id3 import PictureType

from .file_mutagen_common import EartagFileMutagenCommon

class EartagFileMutagenVorbis(EartagFileMutagenCommon):
    """EartagFile handler that uses mutagen for Voris Comment support."""
    __gtype_name__ = 'EartagFileMutagenVorbis'
    _supports_album_covers = True

    # There's an official standard and semi-official considerations for tags,
    # plus some more documents linked from https://wiki.xiph.org/VorbisComment;
    # this only covers tags mentioned there.
    supported_extra_tags = (
        'composer', 'copyright', 'encodedby', 'mood', 'discnumber', 'publisher',
        'isrc',

        'albumartistsort', 'albumsort', 'composersort', 'artistsort', 'titlesort'
    )

    _replaces = {
        'releaseyear': 'date',
        'encodedby': 'encoder' # There's also ENCODED-BY, but confusingly it represents... the person doing the encoding?
    }

    def __init__(self, path):
        super().__init__(path)
        self._cover_path = None
        self.coverart_tempfile = None
        self.load_cover()

    def get_tag(self, tag_name):
        """Tries the lowercase, then uppercase representation of the tag."""
        if tag_name.lower() in self._replaces:
            tag_name = self._replaces[tag_name.lower()]
        try:
            return self.mg_file.tags[tag_name.lower()][0]
        except KeyError:
            try:
                return self.mg_file.tags[tag_name.upper()][0]
            except KeyError:
                return None

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
        if tag_name == 'totaltracknumber':
            return bool(self.totaltracknumber)
        if tag_name.lower() in self._replaces:
            tag_name = self._replaces[tag_name.lower()]
        if tag_name in self.mg_file.tags or tag_name.upper() in self.mg_file.tags:
            return True
        return False

    def delete_tag(self, tag_name):
        """Deletes the tag with the given name from the file."""
        if tag_name.lower() in self._replaces:
            tag_name = self._replaces[tag_name.lower()]
        if tag_name in self.mg_file.tags:
            del self.mg_file.tags[tag_name]
        self.mark_as_modified()

    def __del__(self, *args):
        if self.coverart_tempfile:
            self.coverart_tempfile.close()
        super().__del__()

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
        picture.mime = magic.from_file(value, mime=True)
        img = Image.open(value)
        picture.width = img.width
        picture.height = img.height
        picture.depth = mode_to_bpp[img.mode]

        if isinstance(self.mg_file, FLAC):
            picture.type = PictureType.COVER_FRONT
            for _pic in self.mg_file.pictures:
                if _pic.type in (PictureType.COVER_FRONT, PictureType.OTHER):
                    self.mg_file.pictures.remove(_pic)
            self.mg_file.add_picture(picture)
        else:
            picture_data = picture.write()
            encoded_data = base64.b64encode(picture_data)
            vcomment_value = encoded_data.decode("ascii")

            self.mg_file["metadata_block_picture"] = [vcomment_value]

        self.mark_as_modified()

    def load_cover(self):
        """Loads cover data from file."""
        # See https://mutagen.readthedocs.io/en/latest/user/vcomment.html.
        # There are three ways to get the cover image:

        # 1. Using `mutagen.flac.FLAC.pictures`
        if isinstance(self.mg_file, FLAC) and self.mg_file.pictures:
            picture_cover = None
            picture_other = None

            # We run this in two loops so that we can prio
            for picture in self.mg_file.pictures:
                if picture.type == PictureType.COVER_FRONT:
                    picture_cover = picture

                elif picture.type == PictureType.OTHER:
                    picture_other = picture
                    return

            if picture_cover:
                picture = picture_cover
            elif picture_other:
                picture = picture_other
            else:
                self.notify('cover_path')
                return


            cover_extension = mimetypes.guess_extension(picture.mime)
            self.coverart_tempfile = tempfile.NamedTemporaryFile(
                suffix=cover_extension
            )
            self.coverart_tempfile.write(picture.data)
            self.coverart_tempfile.flush()
            self._cover_path = self.coverart_tempfile.name

        # 2. Using metadata_block_picture
        elif self.mg_file.get("metadata_block_picture", []):
            for b64_data in self.mg_file.get("metadata_block_picture", []):
                try:
                    data = base64.b64decode(b64_data)
                except (TypeError, ValueError):
                    continue

                try:
                    cover_picture = Picture(data)
                except FLACError:
                    continue

                cover_extension = mimetypes.guess_extension(cover_picture.mime)

                self.coverart_tempfile = tempfile.NamedTemporaryFile(
                    suffix=cover_extension
                )
                self.coverart_tempfile.write(cover_picture.data)
                self.coverart_tempfile.flush()
                self._cover_path = self.coverart_tempfile.name

        # 3. Using the coverart field (and optionally covermime)
        else:
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

                self.coverart_tempfile = tempfile.NamedTemporaryFile(
                    suffix=cover_extension
                )
                self.coverart_tempfile.write(data)
                self.coverart_tempfile.flush()
                self._cover_path = self.coverart_tempfile.name
                n += 1

        self.notify('cover_path')

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

    @GObject.Property(type=int)
    def releaseyear(self):
        _date = self.get_tag('date')
        if _date:
            try:
                return int(_date[:4])
            except:
                return None
        return None

    @releaseyear.setter
    def releaseyear(self, value):
        if value >= 0:
            self.mg_file.tags['date'] = str(value)
        else:
            self.mg_file.tags['date'] = ''
        self.mark_as_modified()
