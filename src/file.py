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
import eyed3
import magic
import mimetypes
import os.path
import taglib
import tempfile

eyed3.log.setLevel("ERROR")

class EartagFile(GObject.Object):
    """
    Generic base for GObject wrappers that provide information about a music
    file.

    The following functions are implemented by the subclasses:
      - save() - saves the changes to a file.
    """
    __gtype_name__ = 'EartagFile'

    handled_properties = ['title', 'artist', 'album', 'albumartist', 'tracknumber', 'totaltracknumber', 'genre', 'releaseyear', 'comment']
    _supports_album_covers = False
    _is_modified = False

    def __init__(self, path):
        """Initializes an EartagFile for the given file path."""
        super().__init__()
        self.notify('supports-album-covers')
        self.path = path

    def mark_as_modified(self):
        self._is_modified = True
        self.notify('is_modified')

    def mark_as_unmodified(self):
        self._is_modified = False
        self.notify('is_modified')

    @GObject.Property(type=bool, default=False)
    def is_modified(self):
        """Returns whether the values have been modified or not."""
        return self._is_modified

    @GObject.Property(type=bool, default=False)
    def supports_album_covers(self):
        """Returns whether album covers are supported."""
        return self._supports_album_covers


class EartagFileEyed3(EartagFile):
    """EartagFile handler that uses eyed3. Used for mp3 files."""
    __gtype_name__ = 'EartagFileEyed3'

    _cover_path = None
    e3_file = None
    _supports_album_covers = True

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
        mime_type = magic.Magic(mime=True).from_file(value)
        with open(value, 'rb') as cover_art:
            # TODO: We currently set the cover to 0 (OTHER), we should give
            # the user the option to use FRONT_COVER, with the necessary
            # warnings about incompatibilities, etc.
            self.e3_file.tag.images.set(0, cover_art.read(), mime_type)
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

    @GObject.Property(type=str)
    def tracknumber(self):
        if self.e3_file.tag.track_num:
            return str(self.e3_file.tag.track_num[0])
        return ''

    @tracknumber.setter
    def tracknumber(self, value):
        self.e3_file.tag.track_num = (value, self.e3_file.tag.track_num[1])
        self.mark_as_modified()

    @GObject.Property(type=str)
    def totaltracknumber(self):
        if self.e3_file.tag.track_num:
            return str(self.e3_file.tag.track_num[1])
        return ''

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
            return self.e3_file.tag.genre
        return ''

    @genre.setter
    def genre(self, value):
        self.e3_file.tag.genre = value
        self.mark_as_modified()

    @GObject.Property(type=str)
    def releaseyear(self):
        if self.e3_file.tag.release_date:
            return self.e3_file.tag.release_date
        return ''

    @releaseyear.setter
    def releaseyear(self, value):
        try:
            self.e3_file.tag.release_date = int(value)
        except ValueError:
            # eyed3 is very loud about "incorrect release dates". Shut it up.
            pass
        self.mark_as_modified()

    @GObject.Property(type=str)
    def comment(self):
        if self.e3_file.tag.comments:
            return self.e3_file.tag.comments[0]
        return ''

    @comment.setter
    def comment(self, value):
        self.e3_file.tag.comments[0] = value
        self.mark_as_modified()

class EartagFileTagLib(EartagFile):
    """EartagFile handler that uses pytaglib. Used for non-mp3 files."""
    __gtype_name__ = 'EartagFileTagLib'

    tl_file = None
    _supports_album_covers = False

    def __init__(self, path):
        super().__init__(path)
        self.tl_file = taglib.File(path)

        for prop in self.handled_properties:
            self.notify(prop)
        self.notify('is_modified')

    def save(self):
        """Saves the changes to the file."""
        if self.tl_file:
            self.tl_file.save()
        self.mark_as_unmodified()

    def __del__(self, *args):
        if self.tl_file:
            self.tl_file.close()

    # Main properties

    @GObject.Property(type=str)
    def cover_path(self):
        # No cover art support :(
        return None

    @GObject.Property(type=str)
    def title(self):
        if 'TITLE' in self.tl_file.tags:
            return self.tl_file.tags['TITLE'][0]
        return ''

    @title.setter
    def title(self, value):
        self.tl_file.tags['TITLE'] = [value]
        self.mark_as_modified()

    @GObject.Property(type=str)
    def artist(self):
        if 'ARTIST' in self.tl_file.tags:
            return self.tl_file.tags['ARTIST'][0]
        return ''

    @artist.setter
    def artist(self, value):
        self.tl_file.tags['ARTIST'] = [value]
        self.mark_as_modified()

    @GObject.Property(type=str)
    def tracknumber(self):
        if 'TRACKNUMBER' in self.tl_file.tags:
            if '/' in self.tl_file.tags['TRACKNUMBER'][0]:
                return self.tl_file.tags['TRACKNUMBER'][0].split('/')[0]
            return self.tl_file.tags['TRACKNUMBER'][0]
        return ''

    @tracknumber.setter
    def tracknumber(self, value):
        if self.totaltracknumber:
            self.tl_file.tags['TRACKNUMBER'] = ['{n}/{t}'.format(
                n=str(value), t=str(self.totaltracknumber))
            ]
        else:
            self.tl_file.tags['TRACKNUMBER'] = [str(value)]
        self.mark_as_modified()

    @GObject.Property(type=str)
    def totaltracknumber(self):
        if 'TRACKNUMBER' in self.tl_file.tags:
            if '/' in self.tl_file.tags['TRACKNUMBER'][0]:
                return self.tl_file.tags['TRACKNUMBER'][0].split('/')[1]
        return ''

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        if self.tracknumber:
            self.tl_file.tags['TRACKNUMBER'] = ['{n}/{t}'.format(
                n=str(self.tracknumber), t=str(value))
            ]
        else:
            self.tl_file.tags['TRACKNUMBER'] = ['0/{t}'.format(t=str(value))]
        self.mark_as_modified()

    @GObject.Property(type=str)
    def album(self):
        if 'ALBUM' in self.tl_file.tags:
            return self.tl_file.tags['ALBUM'][0]
        return ''

    @album.setter
    def album(self, value):
        self.tl_file.tags['ALBUM'] = [value]
        self.mark_as_modified()

    @GObject.Property(type=str)
    def albumartist(self):
        if 'ALBUMARTIST' in self.tl_file.tags:
            return self.tl_file.tags['ALBUMARTIST'][0]
        return ''

    @albumartist.setter
    def albumartist(self, value):
        self.tl_file.tags['ALBUMARTIST'] = [value]
        self.mark_as_modified()

    @GObject.Property(type=str)
    def genre(self):
        if 'GENRE' in self.tl_file.tags:
            return self.tl_file.tags['GENRE'][0]
        return ''

    @genre.setter
    def genre(self, value):
        self.tl_file.tags['GENRE'] = [value]
        self.mark_as_modified()

    @GObject.Property
    def releaseyear(self):
        if 'DATE' in self.tl_file.tags and self.tl_file.tags['DATE']:
            return self.tl_file.tags['DATE'][0]
        return None

    @releaseyear.setter
    def releaseyear(self, value):
        self.tl_file.tags['DATE'] = [value]
        self.mark_as_modified()

    @GObject.Property(type=str)
    def comment(self):
        if 'COMMENT' in self.tl_file.tags:
            return self.tl_file.tags['COMMENT'][0]
        return ''

    @comment.setter
    def comment(self, value):
        self.tl_file.tags['COMMENT'] = [value]
        self.mark_as_modified()


def eartagfile_from_path(path):
    """Returns an EartagFile subclass for the provided file."""
    if not os.path.exists(path):
        raise ValueError

    if mimetypes.guess_type(path)[0] == 'audio/mpeg' or \
        magic.Magic(mime=True).from_file(path) == 'audio/mpeg':
        return EartagFileEyed3(path)
    return EartagFileTagLib(path)
