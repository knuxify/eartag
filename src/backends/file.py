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
import filecmp

class EartagFileCover:
    """This class is only used for comparing two covers on two files."""
    def __init__(self, cover_path):
        self.cover_path = cover_path
        if cover_path:
            with open(cover_path, 'rb') as cover_file:
                self.cover_data = cover_file.read()

    def __eq__(self, other):
        if not isinstance(other, EartagFileCover):
            return False
        if self.cover_path and other.cover_path:
            return filecmp.cmp(self.cover_path, other.cover_path)
        else:
            return not other.cover_path

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
    _is_writable = False

    def __init__(self, path):
        """Initializes an EartagFile for the given file path."""
        super().__init__()
        self.notify('supports-album-covers')
        self.path = path
        self.update_writability()
        self._cover_path = None

    def update_writability(self):
        """
        Checks if the file is writable and sets the writable property
        accordingly.
        """
        try:
            writable_check = open(self.path, 'a')
            writable_check.close()
        except OSError:
            self._is_writable = False
        else:
            self._is_writable = True
        self.notify('is_writable')

    @property
    def cover(self):
        """Gets raw cover data. This is usually used for comparisons between two files."""
        if not self._supports_album_covers:
            return False

        return EartagFileCover(self.cover_path)

    @GObject.Signal
    def modified(self):
        pass

    def mark_as_modified(self):
        if not self._is_modified:
            self._is_modified = True
            self.notify('is_modified')
            self.emit('modified')

    def mark_as_unmodified(self):
        if self._is_modified:
            self._is_modified = False
            self.notify('is_modified')
            self.emit('modified')

    @GObject.Property(type=bool, default=False)
    def is_modified(self):
        """Returns whether the values have been modified or not."""
        return self._is_modified

    @GObject.Property(type=bool, default=False)
    def supports_album_covers(self):
        """Returns whether album covers are supported."""
        return self._supports_album_covers

    @GObject.Property(type=bool, default=False)
    def is_writable(self):
        """Returns whether the file can be written to."""
        return self._is_writable
