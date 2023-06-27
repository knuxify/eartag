# file_mutagen_asf.py
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
import magic
import mimetypes
import tempfile
import struct

import mutagen.asf

from .file_mutagen_common import EartagFileMutagenCommon

# These are copied from the code for Quod Libet's wma handling:
KEY_TO_FRAME = {
    "album": "WM/AlbumTitle",
    "title": "Title",
    "artist": "Author",
    "albumartist": "WM/AlbumArtist",
    "composer": "WM/Composer",
    "lyricist": "WM/Writer",
    "conductor": "WM/Conductor",
    "remixer": "WM/ModifiedBy",
    "producer": "WM/Producer",
    "grouping": "WM/ContentGroupDescription",
    "discsubtitle": "WM/SubTitle",
    "tracknumber": "WM/TrackNumber",
    "totaltracknumber": "WM/TrackNumber",
    "discnumber": "WM/PartOfSet",
    "bpm": "WM/BeatsPerMinute",
    "copyright": "Copyright",
    "isrc": "WM/ISRC",
    "mood": "WM/Mood",
    "encodedby": "WM/EncodedBy",
    "musicbrainz_trackid": "MusicBrainz/Track Id",
    "musicbrainz_releasetrackid": "MusicBrainz/Release Track Id",
    "musicbrainz_albumid": "MusicBrainz/Album Id",
    "musicbrainz_artistid": "MusicBrainz/Artist Id",
    "musicbrainz_albumartistid": "MusicBrainz/Album Artist Id",
    "musicbrainz_trmid": "MusicBrainz/TRM Id",
    "musicip_puid": "MusicIP/PUID",
    "musicbrainz_releasegroupid": "MusicBrainz/Release Group Id",
    "releasedate": "WM/Year",
    "originalartist": "WM/OriginalArtist",
    "originalalbum": "WM/OriginalAlbumTitle",
    "albumsort": "WM/AlbumSortOrder",
    "artistsort": "WM/ArtistSortOrder",
    "albumartistsort": "WM/AlbumArtistSortOrder",
    "genre": "WM/Genre",
    "publisher": "WM/Publisher",
    "website": "WM/AuthorURL",
    "comment": "Description"
}

def unpack_image(data):
    """Unpacks an ASF/WMA picture."""
    # Picture type (this matches ID3 types)
    try:
        (picture_type, size) = struct.unpack_from("<bi", data)
    except struct.error:
        return None

    data = data[5:]

    # Mimetype string
    mime = b""
    while data:
        char, data = data[:2], data[2:]
        if char == b"\x00\x00":
            break
        mime += char
    else:
        return None
    mime = mime.decode("utf-16-le")

    # Description string
    description = b""
    while data:
        char, data = data[:2], data[2:]
        if char == b"\x00\x00":
            break
        description += char
    else:
        return None
    description = description.decode("utf-16-le")

    if size != len(data):
        return None

    return (mime, description, data, picture_type)

def pack_image(image_data, image_type=3, description='thumbnail'):
    """Packs an image into ASF format."""
    size = len(image_data)

    data = struct.pack("<bi", image_type, size)
    data += magic.from_buffer(image_data, mime=True).encode("utf-16-le") + b"\x00\x00"
    data += description.encode("utf-16-le") + b"\x00\x00"
    data += image_data

    return data

class EartagFileMutagenASF(EartagFileMutagenCommon):
    """EartagFile handler that uses mutagen for ASF support."""
    __gtype_name__ = 'EartagFileMutagenASF'
    _supports_album_covers = True
    _supports_full_dates = False

    # Copied from file.py, but excludes totaltracknumber, as ASF tags don't
    # have a way to specify it
    handled_properties = ['title', 'artist', 'album', 'albumartist', 'tracknumber', 'genre',
        'releasedate', 'comment']

    supported_extra_tags = (
        'bpm', 'composer', 'copyright', 'encodedby',
        'mood', 'conductor', 'discnumber', 'publisher',
        'isrc', 'discsubtitle',

        'albumartistsort', 'albumsort', 'artistsort'
    )

    def load_from_file(self, path):
        super().load_from_file(path)
        self.load_cover()
        self.setup_present_extra_tags()
        self.setup_original_values()

    def get_tag(self, tag_name):
        """Gets a tag's value using the KEY_TO_FRAME list as a guideline."""
        try:
            return str(self.mg_file.tags[KEY_TO_FRAME[tag_name.lower()]][0])
        except KeyError:
            return ''

    def set_tag(self, tag_name, value):
        """Sets a tag's value using the KEY_TO_FRAME list as a guideline."""
        frame_name = KEY_TO_FRAME[tag_name.lower()]

        # For float values that do not have numbers after the decimal point,
        # trim the trailing .0
        if tag_name in self.float_properties and value % 1 == 0:
            if value:
                stringified = str(int(value))
            else:
                stringified = ''
        else:
            if value:
                stringified = str(value)
            else:
                stringified = ''

        self.mg_file.tags[frame_name] = [stringified]

    def has_tag(self, tag_name):
        """
        Returns True or False based on whether the tag with the given name is
        present in the file.
        """
        if tag_name == 'totaltracknumber':
            return False
        if tag_name not in KEY_TO_FRAME:
            return False
        frame_name = KEY_TO_FRAME[tag_name.lower()]
        if frame_name in self.mg_file.tags:
            return True
        return False

    def delete_tag(self, tag_name):
        """Deletes the tag with the given name from the file."""
        frame_name = KEY_TO_FRAME[tag_name.lower()]
        if tag_name == 'tracknumber':
            print(frame_name, frame_name in self.mg_file.tags, self.mg_file.tags)
        if frame_name in self.mg_file.tags:
            del self.mg_file.tags[frame_name]
        self.mark_as_modified(tag_name)

    def on_remove(self, *args):
        if self.coverart_tempfile:
            self.coverart_tempfile.close()
        super().on_remove()

    @GObject.Property(type=str)
    def cover_path(self):
        return self._cover_path

    @cover_path.setter
    def cover_path(self, value):
        self._cover_path = value

        with open(value, "rb") as cover_file:
            data = cover_file.read()

        pictures = []
        if 'WM/Picture' in self.mg_file.tags:
            pictures = self.mg_file.tags['WM/Picture']

        # Remove all conflicting covers
        if pictures:
            for picture in pictures.copy():
                picture_type = unpack_image(picture.value)[3]
                if picture_type != 3:
                    pictures.remove(picture)

        packed_data = pack_image(data)
        pictures.append(mutagen.asf.ASFValue(packed_data, mutagen.asf.BYTEARRAY))

        self.mg_file.tags['WM/Picture'] = pictures

        self.mark_as_modified('cover_path')

    def load_cover(self):
        """Loads the cover from the file and saves it to a temporary file."""
        if 'WM/Picture' not in self.mg_file.tags:
            self._cover_path = None
            return None

        pictures = self.mg_file.tags['WM/Picture']

        for picture in pictures:
            raw_data = picture.value
            mime, description, data, picture_type = unpack_image(raw_data)
            if picture_type != 3: # FRONT_COVER
                continue
            break

        cover_extension = mimetypes.guess_extension(mime)

        self.coverart_tempfile = tempfile.NamedTemporaryFile(
            suffix=cover_extension
        )
        self.coverart_tempfile.write(data)
        self.coverart_tempfile.flush()
        self._cover_path = self.coverart_tempfile.name

    @GObject.Property(type=str)
    def releasedate(self):
        return self.get_tag('releasedate')

    @releasedate.setter
    def releasedate(self, value):
        self.validate_date('releasedate', value)
        if value:
            if len(value) >= 4:
                try:
                    self.set_tag('releasedate', value[:4])
                except:
                    self.set_tag('releasedate', '')
            else:
                self.set_tag('releasedate', value)
            self.mark_as_modified('releasedate')
        else:
            self.delete_tag('releasedate')

    @GObject.Property(type=int)
    def totaltracknumber(self):
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        return False
