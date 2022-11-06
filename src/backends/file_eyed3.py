# file.py
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
import tempfile
import magic
import mimetypes

import eyed3
eyed3.log.setLevel("ERROR")

from .file import EartagFile

class EartagFileEyed3(EartagFile):
    """EartagFile handler that uses eyed3. Used for mp3 files."""
    __gtype_name__ = 'EartagFileEyed3'

    _cover_path = None
    e3_file = None
    _supports_album_covers = True
    coverart_tempfile = None

    def __init__(self, path):
        super().__init__(path)
        self.e3_file = eyed3.load(path)
        if not self.e3_file.tag:
            self.e3_file.initTag()
            self.e3_file.tag.save()
        self.load_cover()

        for prop in self.handled_properties:
            self.notify(prop)
        self.notify('is_modified')

    def save(self):
        if self.e3_file:
            self.e3_file.tag.save()
        self.mark_as_unmodified()

    def __del__(self, *args):
        if self.coverart_tempfile:
            self.coverart_tempfile.close()
        self.e3_file = None

    # Cover-art support

    @GObject.Property(type=str)
    def cover_path(self):
        return self._cover_path

    @cover_path.setter
    def cover_path(self, value):
        self._cover_path = value
        mime_type = magic.from_file(value, mime=True)
        with open(value, 'rb') as cover_art:
            # TODO: We currently set the cover to both 0 (OTHER) and
            # 3 (FRONT_COVER). It would be nice to allow the user to
            # select one of these only.
            cover_art_data = cover_art.read()
            self.e3_file.tag.images.set(0, cover_art_data, mime_type)
            self.e3_file.tag.images.set(3, cover_art_data, mime_type)
        self.mark_as_modified()

    def load_cover(self):
        """Loads the album cover from the file."""
        cover = None
        mime_type = None
        images = list(self.e3_file.tag.images)
        for image in images:
            if image.picture_type in [0, 3]: # OTHER, FRONT_COVER
                cover = image
                mime_type = image.mime_type
                picture = image.image_data
                self.cover_picture_type = image.picture_type
                break

        # We create a temporary file with the image cover so that it can be
        # loaded by GtkImage. No point in trying to set up fancy GdkPixbuf
        # machinery.
        if cover:
            self.coverart_tempfile = tempfile.NamedTemporaryFile(
                suffix=mimetypes.guess_extension(mime_type)
            )
            self.coverart_tempfile.write(picture)
            self.coverart_tempfile.flush()
            self._cover_path = self.coverart_tempfile.name
        else:
            self.coverart_tempfile = None
            self._cover_path = None
        self.notify('cover_path')

    # Main properties

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def length(self):
        return self.e3_file.info.time_secs

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def bitrate(self):
        # in kbps
        return self.e3_file.info.bit_rate[1]

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def channels(self):
        # Unfortunately eyed3 does not provide the exact channel count;
        # this guesses it based on the mode
        mode = self.e3_file.info.mode
        if mode == 'Mono':
            return 1
        # This is not a typo - we're trying to catch "Stereo" and "stereo" here
        elif 'tereo' in mode:
            return 2
        return 0

    @GObject.Property(type=str, flags=GObject.ParamFlags.READABLE)
    def filetype(self):
        return 'mp3' # we only handle mp3 files with eyed3

    @GObject.Property(type=str)
    def title(self):
        if self.e3_file.tag.title:
            return self.e3_file.tag.title
        return ''

    @title.setter
    def title(self, value):
        if value != (self.e3_file.tag.title or ''):
            self.e3_file.tag.title = value
            if value != None:
                self.mark_as_modified()

    @GObject.Property(type=str)
    def artist(self):
        if self.e3_file.tag.artist:
            return self.e3_file.tag.artist
        return ''

    @artist.setter
    def artist(self, value):
        if value != (self.e3_file.tag.artist or ''):
            self.e3_file.tag.artist = value
            self.mark_as_modified()

    @GObject.Property(type=int)
    def tracknumber(self):
        if self.e3_file.tag.track_num:
            return int(self.e3_file.tag.track_num[0] or -1)
        return None

    @tracknumber.setter
    def tracknumber(self, value):
        self.e3_file.tag.track_num = (value, self.e3_file.tag.track_num[1])
        self.mark_as_modified()

    @GObject.Property(type=int)
    def totaltracknumber(self):
        if self.e3_file.tag.track_num:
            return int(self.e3_file.tag.track_num[1] or -1)
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        self.e3_file.tag.track_num = (self.e3_file.tag.track_num[0], value)
        self.mark_as_modified()

    @GObject.Property(type=str)
    def album(self):
        if self.e3_file.tag.album:
            return self.e3_file.tag.album
        return ''

    @album.setter
    def album(self, value):
        self.e3_file.tag.album = value
        self.mark_as_modified()

    @GObject.Property(type=str)
    def albumartist(self):
        if self.e3_file.tag.album_artist:
            return self.e3_file.tag.album_artist
        return ''

    @albumartist.setter
    def albumartist(self, value):
        self.e3_file.tag.album_artist = value
        self.mark_as_modified()

    @GObject.Property(type=str)
    def genre(self):
        if self.e3_file.tag.genre:
            return self.e3_file.tag.genre.name
        return ''

    @genre.setter
    def genre(self, value):
        self.e3_file.tag.genre = eyed3.id3.Genre(name=value, id=None)
        self.mark_as_modified()

    @GObject.Property(type=int)
    def releaseyear(self):
        if self.e3_file.tag.release_date:
            return self.e3_file.tag.release_date.year
        return None

    @releaseyear.setter
    def releaseyear(self, value):
        try:
            # set TDRL tag
            self.e3_file.tag.release_date = int(value)
            # set TDRC tag. Many applications use this for release 
            # date regardless of the fact that this value is rarely 
            # known, and release dates are more correct
            self.e3_file.tag.recording_date = int(value)
        except ValueError:
            # eyed3 is very loud about "incorrect release dates". Shut it up.
            pass
        self.mark_as_modified()

    @GObject.Property(type=str)
    def comment(self):
        if self.e3_file.tag.comments:
            return self.e3_file.tag.comments[0].text
        return ''

    @comment.setter
    def comment(self, value):
        self.e3_file.tag.comments.set(value)
        self.mark_as_modified()
