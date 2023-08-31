"""
Contains common test fixtures.
"""

from src.backends.file import EartagFile, CoverType
import pytest
import os

def get_version_from_meson():
    # this is the worst possible way to do this
    meson_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'meson.build')
    with open(meson_file) as meson_data:
        version = meson_data.read().split('\n')[1].split(':')[1][2:-2]
    return version

VERSION = get_version_from_meson()
ACOUSTID_API_KEY = "b'Kqy8kqI8"

class EartagDummyFile(EartagFile):
    """Dummy backend for tests."""
    __gtype_name__ = 'EartagDummyFile'

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

    def __init__(self, path):
        super().__init__(path)
        self.tags = {}
        self.setup_present_extra_tags()
        self.setup_original_values()

    def save(self):
        self.setup_original_values()
        self.mark_as_unmodified()

    def get_tag(self, tag_name):
        return self.tags[tag_name] if tag_name in self.tags else ''

    def set_tag(self, tag_name, value):
        self.tags[tag_name] = value

    def has_tag(self, tag_name):
        return tag_name in self.tags

    def delete_tag(self, tag_name):
        if tag_name in self.tags:
            del self.tags[tag_name]
            self.mark_as_modified(tag_name)

    def load_cover(self):
        pass

    def delete_cover(self, cover_type: CoverType, clear_only=False):
        if not clear_only:
            self._cleanup_cover(cover_type)

    def set_cover_path(self, cover_type, value):
        if not value:
            self.delete_cover(cover_type)
        if cover_type == CoverType.FRONT:
            self._front_cover_path = value
        elif cover_type == CoverType.BACK:
            self._back_cover_path = value
        else:
            raise ValueError

@pytest.fixture
def dummy_file():
    # This file is not used for the backend, but we set it just in case
    file = os.path.join(os.path.dirname(__file__), 'backend', 'examples', 'example.mp3')
    return EartagDummyFile(file)
