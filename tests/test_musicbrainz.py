"""
Tests MusicBrainz functions.
"""

from src.musicbrainz import (MusicBrainzRecording, MusicBrainzRelease,
    get_recordings_for_file, update_from_musicbrainz,
    acoustid_identify_file, make_request)
from src.backends.file_mutagen_id3 import EartagFileMutagenID3
from .common import dummy_file

import pytest
import os

NOT_FOUND_STR = 'Could not find one of the required releases (did something move at MusicBrainz, or do we have no internet?'  # noqa: E501

@pytest.mark.networked_tests
def test_musicbrainz_onerel():
    # Recording with one release, no cover path

    # https://musicbrainz.org/recording/cad1f61b-a1f1-4d00-9e01-bcd193eac54b
    rec = MusicBrainzRecording('cad1f61b-a1f1-4d00-9e01-bcd193eac54b')
    assert rec, NOT_FOUND_STR
    # https://musicbrainz.org/release/46fee5ba-49cb-4ebd-a6bc-71bbf03a210d
    assert rec.release.release_id == '46fee5ba-49cb-4ebd-a6bc-71bbf03a210d', NOT_FOUND_STR
    assert not rec.release.thumbnail_path
    rec.release.update_covers()
    assert not rec.front_cover_path
    assert not rec.back_cover_path

@pytest.mark.networked_tests
def test_musicbrainz_multirel():
    # Recording with multiple releases, each with its own tracklists, and with
    # different names (but still under one release group).
    # Also a pretty good test for exotic title characters...
    # https://musicbrainz.org/recording/812aed4e-776f-41d5-aefc-bad0e9226526
    rec = MusicBrainzRecording('812aed4e-776f-41d5-aefc-bad0e9226526')
    assert rec, NOT_FOUND_STR
    assert rec._release == MusicBrainzRecording.SELECT_RELEASE_FIRST
    try: rec.release
    except ValueError: pass
    else: raise AssertionError

    rel1 = None  # streaming release, https://musicbrainz.org/release/5cfa8773-e8b4-4a5d-b858-4d8230aa27ed
    rel2 = None  # bandcamp release, https://musicbrainz.org/release/acdcb0a3-3d4d-4eb8-b7f5-c0749d003e8c
    for release in rec.available_releases:
        if release.release_id == '5cfa8773-e8b4-4a5d-b858-4d8230aa27ed':
            rel1 = release
        if release.release_id == 'acdcb0a3-3d4d-4eb8-b7f5-c0749d003e8c':
            rel2 = release
    assert rel1, NOT_FOUND_STR
    assert rel2, NOT_FOUND_STR

    rec.release = rel1
    assert rec.release == rel1
    assert rec.tracknumber == 1
    assert rec.totaltracknumber == 12
    assert rec.album == 'Effective. Power'
    assert not rec.thumbnail_path

    rec.release = rel2
    assert rec.release == rel2
    assert rec.tracknumber == 2
    assert rec.totaltracknumber == 14
    assert rec.album == 'effective. Power لُلُصّبُلُلصّبُررً ॣ ॣh ॣ ॣ 冗'
    assert rec.thumbnail_path

@pytest.mark.networked_tests
def test_musicbrainz_covers():
    # Release with front and back cover
    # https://musicbrainz.org/recording/0d9dfe92-f7a9-482e-a94f-5e49d5ebd145
    rec = MusicBrainzRecording('0d9dfe92-f7a9-482e-a94f-5e49d5ebd145')
    assert rec, NOT_FOUND_STR

    # https://musicbrainz.org/release/2a335fce-7750-444a-b511-f912fa1a165e
    rel = None
    for r in rec.available_releases:
        if r.release_id == '2a335fce-7750-444a-b511-f912fa1a165e':
            rel = r
            break
    assert rel, NOT_FOUND_STR

    try: rel.front_cover_path
    except ValueError: pass
    else: raise AssertionError

    try: rel.back_cover_path
    except ValueError: pass
    else: raise AssertionError

    rel.update_covers()
    assert rel.front_cover_path
    assert rel.back_cover_path

@pytest.mark.networked_tests
def test_musicbrainz_file_set(dummy_file):
    """Tests the MusicBrainz file wrappers."""

    # Test with not enough data
    try: get_recordings_for_file(dummy_file)
    except ValueError: pass
    else: raise AssertionError

    # Test with dummy data
    dummy_file.title = 'Lips'
    dummy_file.artist = 'Jane Remover'

    recordings = get_recordings_for_file(dummy_file)
    assert recordings
    assert len(recordings) == 1

    # https://musicbrainz.org/recording/e7bff259-a244-4cd9-986c-60ad162ae4df
    rec = None
    for r in recordings:
        if r.recording_id == 'e7bff259-a244-4cd9-986c-60ad162ae4df':
            rec = r
            break
    assert rec, NOT_FOUND_STR

    # https://musicbrainz.org/release/57c61c03-438e-4b62-b53f-38bbee7d82f6
    rel = None
    for r in rec.available_releases:
        if r.release_id == '57c61c03-438e-4b62-b53f-38bbee7d82f6':
            rel = r
            break
    assert rel, NOT_FOUND_STR

    rec.apply_data_to_file(dummy_file)

    assert dummy_file.title == 'Lips'
    assert dummy_file.artist == 'Jane Remover'
    assert dummy_file.album == 'Lips'
    assert dummy_file.albumartist == 'Jane Remover'
    assert dummy_file.tracknumber == 1
    assert dummy_file.totaltracknumber == 1
    assert dummy_file.front_cover_path
    assert not dummy_file.back_cover_path

@pytest.mark.networked_tests
def test_musicbrainz_file_update(dummy_file):
    """Tests updating a file's tags."""

    dummy_file.props.musicbrainz_recordingid = ''
    dummy_file.props.musicbrainz_albumid = ''

    try: update_from_musicbrainz(dummy_file)
    except ValueError: pass
    else: raise AssertionError

    dummy_file.props.musicbrainz_recordingid = 'e7bff259-a244-4cd9-986c-60ad162ae4df'
    dummy_file.props.musicbrainz_albumid = '57c61c03-438e-4b62-b53f-38bbee7d82f6'
    assert dummy_file.props.musicbrainz_recordingid
    assert dummy_file.props.musicbrainz_albumid

    assert update_from_musicbrainz(dummy_file)

    assert dummy_file.title == 'Lips'
    assert dummy_file.artist == 'Jane Remover'
    assert dummy_file.album == 'Lips'
    assert dummy_file.albumartist == 'Jane Remover'

@pytest.fixture
def acoustid_file():
    # The AcoustID requires an actual file to identify. For this test, we use
    # Kevin MacLeod's "Sneaky Snitch", since it's pretty well recognized by AcoustID,
    # and since we can just download it directly off the server without having to
    # bundle all 5.5mb of it in the repo. (We already have enough examples as-is...)
    # Also, it's freely licensed, meaning we can use it just fine, as long as the
    # following notice is kept:
    #
    # "Sneaky Snitch" Kevin MacLeod (incompetech.com)
    # Licensed under Creative Commons: By Attribution 4.0 License
    # http://creativecommons.org/licenses/by/4.0/

    file = os.path.join(os.path.dirname(__file__), 'Sneaky_Snitch.mp3')
    if not os.path.exists(file):
        # We steal the MusicBrain module's download function since it's neat!
        data = make_request('https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sneaky%20Snitch.mp3', raw=True)  # noqa: E501
        with open(file, 'wb') as file_writable:
            file_writable.write(data)
    return EartagFileMutagenID3(file)

@pytest.mark.networked_tests
def test_acoustid_identify(acoustid_file):
    """Tests the AcoustID identification function."""
    assert acoustid_identify_file(acoustid_file)
    assert acoustid_file.title == 'Sneaky Snitch'
    assert acoustid_file.artist == 'Kevin MacLeod'
    assert acoustid_file.album == 'Mystery'