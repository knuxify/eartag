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
import taglib
import tempfile

class EartagFile(GObject.Object):
    """GObject wrapper that provides information about a file."""
    __gtype_name__ = 'EartagFile'

    handled_properties = ['title', 'artist', 'album', 'albumartist', 'comment']
    _is_modified = False
    _is_cover_modified = False

    def __init__(self, path):
        """Initializes an EartagFile for the given file path."""
        super().__init__()
        try:
            self.tl_file = taglib.File(path)
        except OSError:
            # TODO: display some kind of user-friendly warning about this
            raise ValueError

        if mimetypes.guess_type(path)[0] == 'audio/mpeg':
            # We're dealing with an mp3 file, use eyed3 for coverart
            self.eyed3_file = eyed3.load(path)
            if not self.eyed3_file.tag:
                self.eyed3_file.initTag()
                self.eyed3_file.tag.save()

        for prop in self.handled_properties:
            self.notify(prop)
        self.notify('is_modified')

        self.load_cover()

    def __del__(self, *args):
        if self.image_file:
            self.image_file.close()
        if self.eyed3_file:
            self.eyed3_file.close()
        self.tl_file.close()

    def save(self):
        """Saves the changes to the file."""
        self.tl_file.save()
        if self.eyed3_file and self._is_cover_modified:
            self.eyed3_file.tag.save()
        self._is_modified = False
        self.notify('is_modified')

    def set_modified(self):
        self._is_modified = True
        self.notify('is_modified')

    @GObject.Property(type=bool, default=False)
    def is_modified(self):
        """Returns whether the values have been modified or not."""
        return self._is_modified

    def load_cover(self):
        """Loads the album cover from the file."""
        cover = None
        mime_type = None
        if self.eyed3_file:
            images = list(self.eyed3_file.tag.images)
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
            self.image_file = tempfile.NamedTemporaryFile(
                suffix=mimetypes.guess_extension(mime_type)
            )
            self.image_file.write(picture)
            self._cover_path = self.image_file.name
            print(self._cover_path)
        else:
            self.image_file = None
            self._cover_path = None
            self.cover_picture_type = 0
        self.notify('cover_path')
        self.set_modified()

    # GObject properties

    @GObject.Property(type=str)
    def cover_path(self):
        return self._cover_path

    @cover_path.setter
    def cover_path(self, value):
        self._cover_path = value
        mime_type = magic.Magic(mime=True).from_file(value)
        with open(value, 'rb') as cover_art:
            self.eyed3_file.tag.images.set(0, cover_art.read(), mime_type)
        self.set_modified()
        self._is_cover_modified = True

    @GObject.Property(type=str)
    def title(self):
        if 'TITLE' in self.tl_file.tags:
            return self.tl_file.tags['TITLE'][0]
        return ''

    @title.setter
    def set_title(self, value):
        self.tl_file.tags['TITLE'] = [value]
        self.set_modified()

    @GObject.Property(type=str)
    def artist(self):
        if 'ARTIST' in self.tl_file.tags:
            return self.tl_file.tags['ARTIST'][0]
        return ''

    @artist.setter
    def set_artist(self, value):
        self.tl_file.tags['ARTIST'] = [value]
        self.set_modified()

    @GObject.Property(type=str)
    def album(self):
        if 'ALBUM' in self.tl_file.tags:
            return self.tl_file.tags['ALBUM'][0]
        return ''

    @album.setter
    def set_album(self, value):
        self.tl_file.tags['ALBUM'] = [value]
        self.set_modified()

    @GObject.Property(type=str)
    def albumartist(self):
        if 'ALBUMARTIST' in self.tl_file.tags:
            return self.tl_file.tags['ALBUMARTIST'][0]
        return ''

    @albumartist.setter
    def set_albumartist(self, value):
        self.tl_file.tags['ALBUMARTIST'] = [value]
        self.set_modified()

    @GObject.Property(type=str)
    def comment(self):
        if 'COMMENT' in self.tl_file.tags:
            return self.tl_file.tags['COMMENT'][0]
        return ''

    @comment.setter
    def set_comment(self, value):
        self.tl_file.tags['COMMENT'] = [value]
        self.set_modified()
