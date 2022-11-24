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
import os.path
import taglib
import magic
import mimetypes

from .file import EartagFile

TAGNAME_TO_DICTENTRY = {
    'title': 'TITLE',
    'artist': 'ARTIST',
    'album': 'ALBUM',
    'albumartist': 'ALBUMARTIST',
    'genre': 'GENRE',
    'releaseyear': 'DATE',
    'comment': 'COMMENT'
}

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

    def get_tag(self, tag_name):
        """Gets a tag's value using the TAGNAME_TO_DICTENTRY list as a guideline."""
        try:
            return self.tl_file.tags[TAGNAME_TO_DICTENTRY[tag_name.lower()]][0]
        except (KeyError, IndexError):
            return ''

    def set_tag(self, tag_name, value):
        """Sets a tag's value using the TAGNAME_TO_DICTENTRY list as a guideline."""
        self.tl_file.tags[TAGNAME_TO_DICTENTRY[tag_name.lower()]] = [str(value)]

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
        return self.tl_file.channels

    @GObject.Property(type=str, flags=GObject.ParamFlags.READABLE)
    def filetype(self):
        mimetype = magic.from_file(self.path, mime=True)
        mimetype_ext = mimetypes.guess_extension(mimetype)
        if not mimetype_ext:
            mimetype_ext = os.path.splitext(self.path)[-1]
        return mimetype_ext.replace('.', '')

    @GObject.Property(type=int)
    def tracknumber(self):
        if 'TRACKNUMBER' in self.tl_file.tags:
            if '/' in self.tl_file.tags['TRACKNUMBER'][0]:
                return int(self.tl_file.tags['TRACKNUMBER'][0].split('/')[0])
            return int(self.tl_file.tags['TRACKNUMBER'][0])
        return None

    @tracknumber.setter
    def tracknumber(self, value):
        if self.totaltracknumber:
            self.tl_file.tags['TRACKNUMBER'] = ['{n}/{t}'.format(
                n=str(value), t=str(self.totaltracknumber))
            ]
        else:
            self.tl_file.tags['TRACKNUMBER'] = [str(value)]
        self.mark_as_modified()

    @GObject.Property(type=int)
    def totaltracknumber(self):
        if 'TRACKNUMBER' in self.tl_file.tags:
            if '/' in self.tl_file.tags['TRACKNUMBER'][0]:
                return int(self.tl_file.tags['TRACKNUMBER'][0].split('/')[1])
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        if self.tracknumber:
            self.tl_file.tags['TRACKNUMBER'] = ['{n}/{t}'.format(
                n=str(self.tracknumber), t=str(value))
            ]
        else:
            self.tl_file.tags['TRACKNUMBER'] = ['0/{t}'.format(t=str(value))]
        self.mark_as_modified()
