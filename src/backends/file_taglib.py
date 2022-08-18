# file-taglib.py
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
import taglib
import magic
import mimetypes

from .file import EartagFile

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

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def length(self):
        return self.tl_file.length

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def bitrate(self):
        # in kbps
        return self.tl_file.bitrate

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def channels(self):
        channels = self.tl_file.channels

    @GObject.Property(type=str, flags=GObject.ParamFlags.READABLE)
    def filetype(self):
        mimetype = magic.Magic(mime=True).from_file(self.path)
        return mimetypes.guess_extension(mimetype).replace('.', '')

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
