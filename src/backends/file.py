# backends/file.py
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
