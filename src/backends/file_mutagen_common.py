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

import mutagen

from .file import EartagFile

class EartagFileMutagenCommon(EartagFile):
    """Base class for Mutagen-based backends."""
    __gtype_name__ = 'EartagFileMutagenCommon'

    def __init__(self, path):
        super().__init__(path)
        self.mg_file = None
        self.mg_file = mutagen.File(path)
        self.coverart_tempfile = None

    def save(self):
        """Saves the changes to the file."""
        self.mg_file.save()
        self.mark_as_unmodified()

    def __del__(self, *args):
        self.mg_file = None

    # Main properties

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def length(self):
        return int(self.mg_file.info.length)

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def bitrate(self):
        # in bps, needs conversion
        return int(round(self.mg_file.info.bitrate / 1000, 0))

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def channels(self):
        return self.mg_file.info.channels
