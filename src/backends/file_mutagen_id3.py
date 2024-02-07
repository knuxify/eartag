# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import GObject
import magic
import mimetypes

import mutagen.id3
from mutagen.id3 import PictureType

from .file import CoverType
from .file_mutagen_common import EartagFileMutagenCommon

# These are copied from the code for Mutagen's EasyID3 functions:
KEY_TO_FRAME = {
    'album': 'TALB',
    'bpm': 'TBPM',
    'compilation': 'TCMP',
    'composer': 'TCOM',
    'copyright': 'TCOP',
    'encodedby': 'TENC',
    'genre': 'TCON',
    'lyricist': 'TEXT',
    'length': 'TLEN',
    'media': 'TMED',
    'mood': 'TMOO',
    'grouping': 'TIT1',
    'title': 'TIT2',
    'version': 'TIT3',
    'artist': 'TPE1',
    'albumartist': 'TPE2',
    'conductor': 'TPE3',
    'arranger': 'TPE4',
    'discnumber': 'TPOS',
    'publisher': 'TPUB',
    'tracknumber': 'TRCK',
    'totaltracknumber': 'TRCK',
    'author': 'TOLY',
    'albumartistsort': 'TSO2',
    'albumsort': 'TSOA',
    'composersort': 'TSOC',
    'artistsort': 'TSOP',
    'titlesort': 'TSOT',
    'isrc': 'TSRC',
    'discsubtitle': 'TSST',
    'language': 'TLAN',
    'comment': 'COMM::eng',
    'url': 'WXXX:',
}

KEY_TO_FRAME_CLASS = {
    'album': mutagen.id3.TALB,
    'bpm': mutagen.id3.TBPM,
    'compilation': mutagen.id3.TCMP,
    'composer': mutagen.id3.TCOM,
    'copyright': mutagen.id3.TCOP,
    'encodedby': mutagen.id3.TENC,
    'lyricist': mutagen.id3.TEXT,
    'length': mutagen.id3.TLEN,
    'media': mutagen.id3.TMED,
    'mood': mutagen.id3.TMOO,
    'grouping': mutagen.id3.TIT1,
    'title': mutagen.id3.TIT2,
    'version': mutagen.id3.TIT3,
    'artist': mutagen.id3.TPE1,
    'albumartist': mutagen.id3.TPE2,
    'conductor': mutagen.id3.TPE3,
    'arranger': mutagen.id3.TPE4,
    'discnumber': mutagen.id3.TPOS,
    'publisher': mutagen.id3.TPUB,
    'tracknumber': mutagen.id3.TRCK,
    'author': mutagen.id3.TOLY,
    'albumartistsort': mutagen.id3.TSO2,
    'albumsort': mutagen.id3.TSOA,
    'composersort': mutagen.id3.TSOC,
    'artistsort': mutagen.id3.TSOP,
    'titlesort': mutagen.id3.TSOT,
    'isrc': mutagen.id3.TSRC,
    'discsubtitle': mutagen.id3.TSST,
    'language': mutagen.id3.TLAN,
    'comment': mutagen.id3.COMM,
    'url': mutagen.id3.WXXX
}

FREEFORM_KEYS = {
    'musicbrainz_artistid': 'MusicBrainz Artist Id',
    'musicbrainz_albumid': 'MusicBrainz Album Id',
    'musicbrainz_albumartistid': 'MusicBrainz Album Artist Id',
    'musicbrainz_trackid': 'MusicBrainz Release Track Id',
    'musicbrainz_releasegroupid': 'MusicBrainz Release Group Id'
}

class EartagFileMutagenID3(EartagFileMutagenCommon):
    """EartagFile handler that uses mutagen for ID3 support."""
    __gtype_name__ = 'EartagFileMutagenID3'
    _supports_album_covers = True
    _supports_full_dates = True

    supported_extra_tags = (
        'bpm', 'compilation', 'composer', 'copyright', 'encodedby',
        'mood', 'conductor', 'arranger', 'discnumber', 'publisher',
        'isrc', 'language', 'discsubtitle', 'url',

        'albumartistsort', 'albumsort', 'composersort', 'artistsort',
        'titlesort',

        'musicbrainz_artistid', 'musicbrainz_albumid',
        'musicbrainz_albumartistid', 'musicbrainz_trackid',
        'musicbrainz_recordingid', 'musicbrainz_releasegroupid'
    )

    def load_from_file(self, path):
        super().load_from_file(path)
        if not self.mg_file.tags:
            try:
                self.mg_file.add_tags()
            except (mutagen.id3._util.error, mutagen.wave.error):
                pass
        self.load_cover()
        self.setup_present_extra_tags()
        self.setup_original_values()

        # Work around ID3v1 handling issues. Mutagen assumes ID3v1.1, which
        # uses the last bit of the comment field as a track number. There
        # doesn't seem to be a way to check if a file is ID3v1 or ID3v1.1,
        # but we can make an educated guess based on the length of the ID3v1
        # comment field - if it goes the entire 29 characters, then it's
        # fairly likely to be 30 characters long.
        #
        # (I assume, by the extremely vague description of the header on
        # id3.org, that an ID3v1 comment field would go up to 28 characters,
        # as the last bit would be 0 (tags are supposed to end with 0s)...)

        if 'COMM:ID3v1 Comment:eng' in self.mg_file.tags and \
                len(self.mg_file.tags['COMM:ID3v1 Comment:eng'].text[0]) == 29:
            self.set_tag('tracknumber', '')

    def get_tag(self, tag_name):
        """Gets a tag's value using the KEY_TO_FRAME list as a guideline."""
        tag_name = tag_name.lower()

        if tag_name in KEY_TO_FRAME:
            try:
                return self.mg_file.tags[KEY_TO_FRAME[tag_name]].text[0]
            except KeyError:
                return ''
        elif tag_name in FREEFORM_KEYS:
            try:
                return self.mg_file.tags['TXXX:' + FREEFORM_KEYS[tag_name]].text[0]
            except KeyError:
                return ''
        elif tag_name == 'musicbrainz_recordingid':
            for key, frame in list(self.mg_file.tags.items()):
                if frame.FrameID == 'UFID' and frame.owner == 'http://musicbrainz.org':
                    return self.mg_file.tags[key].data.decode('ascii', 'ignore')
            return ''

        raise ValueError

    def set_tag(self, tag_name, value):
        """Sets a tag's value using the KEY_TO_FRAME list as a guideline."""
        tag_name = tag_name.lower()

        if tag_name in KEY_TO_FRAME:
            frame_name = KEY_TO_FRAME[tag_name.lower()]
            frame_class = KEY_TO_FRAME_CLASS[tag_name.lower()]

            # For float values that do not have numbers after the decimal point,
            # trim the trailing .0
            if tag_name in self.float_properties and value % 1 == 0:
                stringified = str(int(value))
            else:
                stringified = str(value)

            self.mg_file.tags.setall(frame_name, [frame_class(encoding=3, text=[stringified])])
        elif tag_name in FREEFORM_KEYS:
            txxx = mutagen.id3.TXXX(encoding=3, desc=FREEFORM_KEYS[tag_name], text=[value])
            self.mg_file.tags.setall('TXXX:' + FREEFORM_KEYS[tag_name], [txxx])
        elif tag_name == 'musicbrainz_recordingid':
            ufid = mutagen.id3.UFID(owner='http://musicbrainz.org', data=bytes(value, 'ascii'))
            self.mg_file.tags.add(ufid)
        else:
            raise ValueError

    def has_tag(self, tag_name):
        """
        Returns True or False based on whether the tag with the given name is
        present in the file.
        """
        if not self.mg_file.tags:
            return False
        if tag_name == 'totaltracknumber':
            return bool(self.totaltracknumber)
        elif tag_name == 'releasedate':
            return 'TDRC' in self.mg_file.tags or 'TDOR' in self.mg_file.tags
        elif tag_name == 'url':
            return bool(self.props.url)
        elif tag_name == 'comment':
            return bool(self.props.comment)
        elif tag_name in KEY_TO_FRAME:
            frame_name = KEY_TO_FRAME[tag_name.lower()]
            return frame_name in self.mg_file.tags
        elif tag_name in FREEFORM_KEYS:
            return 'TXXX:' + FREEFORM_KEYS[tag_name] in self.mg_file.tags
        elif tag_name == 'musicbrainz_recordingid':
            for key, frame in list(self.mg_file.tags.items()):
                if frame.FrameID == 'UFID' and frame.owner == 'http://musicbrainz.org':
                    return True
            return False

        return False

    def delete_tag(self, tag_name):
        """Deletes the tag with the given name from the file."""
        if tag_name.lower() == 'releasedate':
            self.mg_file.tags.delall('TDRC')
            self.mg_file.tags.delall('TDOR')
            self._releasedate_cached = ''
        elif tag_name.lower() == 'url':
            self.mg_file.tags.delall('WXXX')
            self.mg_file.tags.delall('WXXX:')
            self.mg_file.tags.delall('TXXX:purl')
        elif tag_name.lower() == 'comment':
            self.mg_file.tags.delall('COMM::XXX')
            self.mg_file.tags.delall('COMM::eng')
            self.mg_file.tags.delall('TXXX:comment')
        elif tag_name.lower() in KEY_TO_FRAME:
            frame_name = KEY_TO_FRAME[tag_name.lower()]
            self.mg_file.tags.delall(frame_name)
        elif tag_name.lower() in FREEFORM_KEYS:
            self.mg_file.tags.delall('TXXX:' + FREEFORM_KEYS[tag_name.lower()])
        elif tag_name.lower() == 'musicbrainz_recordingid':
            for key, frame in list(self.mg_file.tags.items()):
                if frame.FrameID == 'UFID' and frame.owner == 'http://musicbrainz.org':
                    del self.mg_file.tags[key]

        self.mark_as_modified(tag_name)

    def delete_cover(self, cover_type: CoverType, clear_only=False):
        """Delets the cover of the specified type from the file."""
        if cover_type == CoverType.FRONT:
            pictypes = (PictureType.OTHER, PictureType.COVER_FRONT)
        elif cover_type == CoverType.BACK:
            pictypes = (PictureType.COVER_BACK, )
        else:
            raise ValueError

        for tag in dict(self.mg_file.tags).copy().keys():
            if tag.startswith('APIC') and self.mg_file.tags[tag].type in pictypes:
                del self.mg_file.tags[tag]

        if not clear_only:
            self._cleanup_cover(cover_type)

    def on_remove(self, *args):
        super().on_remove()

    def set_cover_path(self, cover_type: CoverType, value):
        if not value:
            return self.delete_cover(cover_type)

        if cover_type == CoverType.FRONT:
            prop = 'front_cover_path'
            self._front_cover_path = value
        elif cover_type == CoverType.BACK:
            prop = 'back_cover_path'
            self._back_cover_path = value
        else:
            raise ValueError

        with open(value, "rb") as cover_file:
            data = cover_file.read()

        mime = magic.from_file(value, mime=True)

        # Remove conflicting covers
        self.delete_cover(cover_type, clear_only=True)

        if cover_type == CoverType.FRONT:
            self.mg_file.tags.add(
                mutagen.id3.APIC(
                    encoding=3, desc='Front Cover', mime=mime, data=data,
                    type=PictureType.COVER_FRONT
                )
            )

            self.mg_file.tags.add(
                mutagen.id3.APIC(
                    encoding=3, desc='Cover', mime=mime, data=data,
                    type=PictureType.OTHER
                )
            )

        elif cover_type == CoverType.BACK:
            self.mg_file.tags.add(
                mutagen.id3.APIC(
                    encoding=3, desc='Back Cover', mime=mime, data=data,
                    type=PictureType.COVER_BACK
                )
            )

        self.mark_as_modified(prop)

    def load_cover(self):
        """Loads the covers from the file and saves them to a temporary file."""
        front_picture = None
        back_picture = None

        pictures = self.mg_file.tags.getall('APIC')
        # Loop twice, first to get cover art (preferred), second to get "other"

        for picture in pictures:
            if picture.type == PictureType.COVER_FRONT:
                front_picture = picture
                break

        if not front_picture:
            for picture in pictures:
                if picture.type == PictureType.OTHER:
                    front_picture = picture
                    break

        if front_picture:
            cover_extension = mimetypes.guess_extension(front_picture.mime)
            self.create_cover_tempfile(
                CoverType.FRONT, front_picture.data, cover_extension
            )

        # Get back cover
        for picture in pictures:
            if picture.type == PictureType.COVER_BACK:
                back_picture = picture
                break

        if back_picture:
            cover_extension = mimetypes.guess_extension(back_picture.mime)
            self.create_cover_tempfile(
                CoverType.BACK, back_picture.data, cover_extension
            )

    @GObject.Property(type=int)
    def tracknumber(self):
        tracknum_raw = self.get_tag('tracknumber')
        if not tracknum_raw:
            return None

        if '/' in tracknum_raw:
            return int(tracknum_raw.split('/')[0])
        return int(tracknum_raw)

    @tracknumber.setter
    def tracknumber(self, value):
        if self.totaltracknumber:
            self.set_tag('tracknumber',
                '{n}/{t}'.format(n=str(value), t=str(self.totaltracknumber))
            )
        else:
            if value:
                self.set_tag('tracknumber', value)
            elif self.has_tag('tracknumber'):
                self.delete_tag('tracknumber')
        self.mark_as_modified('tracknumber')

    @GObject.Property(type=int)
    def totaltracknumber(self):
        tracknum_raw = self.get_tag('tracknumber')
        if not tracknum_raw:
            return None

        if '/' in tracknum_raw:
            return int(tracknum_raw.split('/')[1])
        return None

    @totaltracknumber.setter
    def totaltracknumber(self, value):
        if self.tracknumber:
            self.set_tag('tracknumber',
                '{n}/{t}'.format(n=str(self.tracknumber), t=str(value))
            )
        else:
            if value:
                self.set_tag('tracknumber', '0/{t}'.format(t=str(value)))
            elif self.has_tag('tracknumber'):
                self.delete_tag('tracknumber')
        self.mark_as_modified('totaltracknumber')

    @GObject.Property()
    def genre(self):
        if 'TCON' not in self.mg_file.tags:
            return None
        genre_raw = self.mg_file.tags['TCON']
        if genre_raw and genre_raw.genres:
            return genre_raw.genres[0]
        return None

    @genre.setter
    def genre(self, value):
        if value:
            try:
                genre_raw = self.mg_file.tags['TCON']
            except KeyError:
                self.mg_file.tags.add(mutagen.id3.TCON(encoding=3, text=[value]))
            else:
                genre_raw.encoding = 3
                genre_raw.genres = [value]
        else:
            self.delete_tag('genre')
        self.mark_as_modified('genre')

    @GObject.Property()
    def comment(self):
        if 'COMM::XXX' in self.mg_file.tags:
            return self.mg_file.tags['COMM::XXX'].text[0]
        elif 'COMM::eng' in self.mg_file.tags:
            return self.mg_file.tags['COMM::eng'].text[0]
        elif 'TXXX:comment' in self.mg_file.tags:
            return self.mg_file.tags['TXXX:comment'].text[0]
        return None

    @comment.setter
    def comment(self, value):
        if value:
            self.mg_file.tags.setall('COMM',
                [mutagen.id3.COMM(encoding=3, lang='eng', desc='', text=[str(value)])]
            )
        else:
            self.delete_tag('comment')
        self.mark_as_modified('comment')

    # These set both TDRC (date) and TDOR (original date) for compatibility.
    @GObject.Property(type=str)
    def releasedate(self):
        if not self._releasedate_cached and self.has_tag('releasedate'):
            value = ''
            if 'TDRC' in self.mg_file.tags:
                value = self.mg_file.tags['TDRC'].text[0].text
            elif 'TDOR' in self.mg_file.tags:
                value = self.mg_file.tags['TDOR'].text[0].text
            self._releasedate_cached = value
        return self._releasedate_cached

    @releasedate.setter
    def releasedate(self, value):
        self.validate_date('releasedate', value)
        self._releasedate_cached = value
        if not value:
            self.delete_tag('releasedate')
        elif 'releasedate' not in self._error_fields:
            self.mg_file.tags.setall('TDRC', [mutagen.id3.TDRC(encoding=3, text=[str(value)])])
            if 'TDOR' not in self.mg_file.tags or \
                    self.mg_file.tags['TDOR'] == self.mg_file.tags['TDRC']:
                self.mg_file.tags.setall('TDOR', [mutagen.id3.TDOR(encoding=3, text=[str(value)])])
        self.mark_as_modified('releasedate')

    @GObject.Property(type=int)
    def discnumber(self):
        discnum_raw = self.get_tag('discnumber')
        if not discnum_raw:
            return None

        if '/' in discnum_raw:
            return int(discnum_raw.split('/')[0])
        return int(discnum_raw)

    @discnumber.setter
    def discnumber(self, value):
        if value:
            self.set_tag('discnumber', f'{value}/{value}')
        elif self.has_tag('discnumber'):
            self.delete_tag('discnumber')
        self.mark_as_modified('discnumber')

    @GObject.Property(type=str)
    def url(self):
        if 'WXXX' in self.mg_file.tags:
            return self.mg_file.tags['WXXX'].url
        elif 'WXXX:' in self.mg_file.tags:
            return self.mg_file.tags['WXXX:'].url
        elif 'TXXX:purl' in self.mg_file.tags:
            return self.mg_file.tags['TXXX:purl'].text[0]
        return None

    @url.setter
    def url(self, value):
        if value:
            self.mg_file.tags.setall('TXXX:purl',
                [mutagen.id3.TXXX(encoding=3, desc='purl', text=str(value))]
            )
            self.mg_file.tags.setall('WXXX',
                [mutagen.id3.WXXX(encoding=3, desc='', url=str(value))]
            )
            self.mark_as_modified('url')
        else:
            self.delete_tag('url')
