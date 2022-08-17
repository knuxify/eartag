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

import magic
import mimetypes
import os.path

from .backends import EartagFileEyed3, EartagFileTagLib, EartagFileMutagenVorbis

def eartagfile_from_path(path):
    """Returns an EartagFile subclass for the provided file."""
    if not os.path.exists(path):
        raise ValueError

    mimetypes_guess = mimetypes.guess_type(path)[0]
    magic_guess = magic.Magic(mime=True).from_file(path)

    is_type = lambda type: mimetypes_guess == type or magic_guess == type

    if is_type('audio/mpeg'):
        return EartagFileEyed3(path)
    elif is_type('audio/flac') or is_type('audio/ogg'):
        try:
            import mutagen
        except ImportError:
            print("mutagen unavailable, using taglib to handle ogg/flac!")
        else:
            return EartagFileMutagenVorbis(path)
    return EartagFileTagLib(path)
