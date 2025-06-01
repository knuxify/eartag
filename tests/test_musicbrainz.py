"""
Tests MusicBrainz functions.
"""

from src.musicbrainz import (
    MusicBrainzRecording,
    acoustid_identify_file,
    # 	make_request,
)
from src.backends.file_mutagen_id3 import EartagFileMutagenID3
from .common import dummy_file  # noqa: F401; flake8 doesn't understand fixtures

import time
import pytest
import os

NOT_FOUND_STR = "Could not find one of the required releases (did something move at MusicBrainz, or do we have no internet?)"  # noqa: E501


@pytest.mark.asyncio
@pytest.mark.networked_tests
async def test_musicbrainz_onerel():
    # Recording with one release, no cover path

    # https://musicbrainz.org/recording/cad1f61b-a1f1-4d00-9e01-bcd193eac54b
    rec = await MusicBrainzRecording.new_for_id("cad1f61b-a1f1-4d00-9e01-bcd193eac54b")
    assert rec, NOT_FOUND_STR
    rec.sort_releases()
    # https://musicbrainz.org/release/46fee5ba-49cb-4ebd-a6bc-71bbf03a210d
    assert (
        rec.release.release_id == "46fee5ba-49cb-4ebd-a6bc-71bbf03a210d"
    ), NOT_FOUND_STR

    await rec.release.download_thumbnail_async()
    assert not rec.release.thumbnail_path

    await rec.release.download_covers_async()
    assert not rec.front_cover_path
    assert not rec.back_cover_path


@pytest.mark.asyncio
@pytest.mark.networked_tests
async def test_musicbrainz_multirel():
    # Recording with multiple releases, each with its own tracklists, and with
    # different names (but still under one release group).
    # Also a pretty good test for exotic title characters...
    # https://musicbrainz.org/recording/812aed4e-776f-41d5-aefc-bad0e9226526
    rec = await MusicBrainzRecording.new_for_id("812aed4e-776f-41d5-aefc-bad0e9226526")
    assert rec, NOT_FOUND_STR
    assert rec._release == MusicBrainzRecording.SELECT_RELEASE_FIRST
    try:
        rec.release
    except ValueError:
        pass
    else:
        raise AssertionError

    rec.sort_releases()

    # streaming release, https://musicbrainz.org/release/5cfa8773-e8b4-4a5d-b858-4d8230aa27ed
    rel1 = None
    # bandcamp release, https://musicbrainz.org/release/acdcb0a3-3d4d-4eb8-b7f5-c0749d003e8c
    rel2 = None
    for release in rec.available_releases:
        if release.release_id == "5cfa8773-e8b4-4a5d-b858-4d8230aa27ed":
            rel1 = release
        if release.release_id == "acdcb0a3-3d4d-4eb8-b7f5-c0749d003e8c":
            rel2 = release
    assert rel1, NOT_FOUND_STR
    assert rel2, NOT_FOUND_STR

    rec.release = rel1
    assert rec.release == rel1
    assert rec.tracknumber == 1
    assert rec.totaltracknumber == 12
    assert rec.album == "Effective. Power"

    rec.release = rel2
    assert rec.release == rel2
    assert rec.tracknumber == 2
    assert rec.totaltracknumber == 14
    assert rec.album == "effective. Power لُلُصّبُلُلصّبُررً ॣ ॣh ॣ ॣ 冗"


@pytest.mark.asyncio
@pytest.mark.networked_tests
async def test_musicbrainz_covers():
    # Release with front and back cover
    # https://musicbrainz.org/recording/0d9dfe92-f7a9-482e-a94f-5e49d5ebd145
    rec = await MusicBrainzRecording.new_for_id("0d9dfe92-f7a9-482e-a94f-5e49d5ebd145")
    assert rec, NOT_FOUND_STR
    rec.sort_releases()

    # https://musicbrainz.org/release/2a335fce-7750-444a-b511-f912fa1a165e
    rel = None
    for r in rec.available_releases:
        if r.release_id == "2a335fce-7750-444a-b511-f912fa1a165e":
            rel = r
            break
    assert rel, NOT_FOUND_STR

    try:
        rel.front_cover_path
    except ValueError:
        pass
    else:
        raise AssertionError

    try:
        rel.back_cover_path
    except ValueError:
        pass
    else:
        raise AssertionError

    await rel.download_covers_async()
    assert rel.front_cover_path
    assert rel.back_cover_path


@pytest.mark.asyncio
@pytest.mark.networked_tests
async def test_musicbrainz_file_set(
    dummy_file,  # noqa: F811; flake8 doesn't understand fixtures
):
    """Tests the MusicBrainz file wrappers."""

    # Test with not enough data
    try:
        await MusicBrainzRecording.get_recordings_for_file(dummy_file)
    except ValueError:
        pass
    else:
        raise AssertionError

    # Test with dummy data
    dummy_file.title = "Royal Blue Walls"
    dummy_file.artist = "Jane Remover"

    recordings = await MusicBrainzRecording.get_recordings_for_file(dummy_file)
    assert recordings
    assert len(recordings) > 0

    # https://musicbrainz.org/recording/4f734ae1-c363-454e-939e-a1964ae23d0b
    rec = None
    for r in recordings:
        if r.recording_id == "4f734ae1-c363-454e-939e-a1964ae23d0b":
            rec = r
            break
    assert rec, NOT_FOUND_STR

    # https://musicbrainz.org/release/e1e584c2-a1a3-4fa1-8ddb-b7f972f3a8e4
    rel = None
    for r in rec.available_releases:
        if r.release_id == "e1e584c2-a1a3-4fa1-8ddb-b7f972f3a8e4":
            rel = r
            break
    assert rel, NOT_FOUND_STR

    rec.release = rel

    await rel.download_covers_async()

    rec.apply_data_to_file(dummy_file)

    assert dummy_file.title == "Royal Blue Walls"
    assert dummy_file.artist == "Jane Remover"
    assert dummy_file.album == "Royal Blue Walls"
    assert dummy_file.albumartist == "Jane Remover"
    assert dummy_file.tracknumber == 1
    assert dummy_file.totaltracknumber == 2

    assert dummy_file.front_cover_path
    assert not dummy_file.back_cover_path


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

    file = os.path.join(os.path.dirname(__file__), "Sneaky_Snitch.mp3")
    if not os.path.exists(file):
        # FIXME: This used to use the make_request function from the musicbrainz module;
        # however, we have since switched to a QueuedDownloader and that function has been
        # dropped. When we get around to re-enabling this test, fix this.
        # data = make_request(
        #	"https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sneaky%20Snitch.mp3",
        #	raw=True,
        #)  # noqa: E501
        with open(file, "wb") as file_writable:
            file_writable.write(data)
    return EartagFileMutagenID3(file)


@pytest.mark.skip(
    reason="Currently broken, looks like it's misidentifying the track; not our fault"
)  # noqa: E501
@pytest.mark.asyncio
@pytest.mark.networked_tests
async def test_acoustid_identify(acoustid_file):
    """Tests the AcoustID identification function."""
    ident = await acoustid_identify_file(acoustid_file)
    assert ident
    assert ident[1]
    ident[1].apply_data_to_file(acoustid_file)
    assert acoustid_file.title == "Sneaky Snitch"
    assert acoustid_file.artist == "Kevin MacLeod"
    assert acoustid_file.album == "Mystery"
