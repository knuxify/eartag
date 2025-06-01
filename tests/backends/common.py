import os
import shutil
import filecmp
import pytest

from src.backends.file import CoverType

# Boilerplate for handling example files

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "examples")
REGENERATE_EXAMPLES = False

# Example files dict, for use with get_test_file (type: filename without extension)
EXAMPLES = {"alltags": "example", "notags": "example-notags"}


class TestFile:
    """Class for generating test files. Use with the "with" keyword."""

    def __init__(self, test_name, extension, example_type, remove=True):
        if example_type not in EXAMPLES:
            raise ValueError(f"Incorrect type {example_type} for get_test_file")
        example = EXAMPLES[example_type]

        source_path = os.path.join(EXAMPLES_DIR, f"{example}.{extension}")
        target_path = os.path.join(EXAMPLES_DIR, f"_{test_name}_{example}.{extension}")
        shutil.copyfile(source_path, target_path)

        self.path = target_path
        self.remove = remove

    def __enter__(self):
        return self.path

    def __exit__(self, type, value, tb):
        if tb:
            return None
        if self.remove:
            os.remove(self.path)


# Example values

prop_to_example_string = {
    "title": "Example Title",
    "artist": "Example Artist",
    "album": "Example Album",
    "albumartist": "Example Album Artist",
    "tracknumber": 1,
    "totaltracknumber": 99,
    "genre": "Example Genre",
    "releasedate": "2022",
    "comment": "Example Comment",
    "bpm": 160,
    "compilation": "Example Compilation",
    "composer": "Example Composer",
    "copyright": "Example Copyright",
    "encodedby": "Example Encoded by",
    "mood": "Example Mood",
    "conductor": "Example Conductor",
    "arranger": "Example Arranger",
    "discnumber": 1,
    "publisher": "Example Publisher",
    "isrc": "Example-ISRC",
    "language": "Example Language",
    "discsubtitle": "Example Disc Subtitle",
    "url": "https://example.com",
    "albumartistsort": "Example Album Artist (sort)",
    "albumsort": "Example Album (sort)",
    "composersort": "Example Composer (sort)",
    "artistsort": "Example Artist (sort)",
    "titlesort": "Example Title (sort)",
    "musicbrainz_artistid": "musicbrainz-artist-id",
    "musicbrainz_albumid": "musicbrainz-album-id",
    "musicbrainz_albumartistid": "musicbrainz-album-artist-id",
    "musicbrainz_trackid": "musicbrainz-track-id",
    "musicbrainz_recordingid": "musicbrainz-recording-id",
    "musicbrainz_releasegroupid": "musicbrainz-release-group-id",
}

# Actual test functions will follow


@pytest.mark.asyncio
async def run_backend_tests(file_class, extension, skip_channels=False):
    # Simple read test
    if not REGENERATE_EXAMPLES:
        file_read = await file_class.new_from_path(
            os.path.join(EXAMPLES_DIR, f"example.{extension}")
        )
        backend_read(file_read, skip_channels)

    # Simple write test
    with TestFile("test_write", extension, "notags") as file_write:
        await backend_write(await file_class.new_from_path(file_write), skip_channels)

    # One-by-one write test
    with TestFile(
        "test_write_individual", extension, "notags"
    ) as file_write_individual:
        await backend_write_individual(
            await file_class.new_from_path(file_write_individual), skip_channels
        )

    # Tag deletion test
    with TestFile("test_delete", extension, "alltags") as file_delete:
        await backend_delete(await file_class.new_from_path(file_delete))

    # delete_all_raw function test
    with TestFile("test_delete_all_raw", extension, "alltags") as file_delete_all_raw:
        backend_delete_all_raw(await file_class.new_from_path(file_delete_all_raw))

    # Make sure tags are deleted when set to empty values
    with TestFile("test_write_empty", extension, "alltags") as file_write_empty:
        await backend_write_empty(
            await file_class.new_from_path(file_write_empty), skip_channels
        )

    # File rename test; do this twice: once for no tags, once for all tags
    with TestFile("test_rename", extension, "notags", remove=False) as file_rename:
        await backend_rename(await file_class.new_from_path(file_rename))
    with TestFile("test_rename", extension, "alltags", remove=False) as file_rename:
        await backend_rename(await file_class.new_from_path(file_rename))

    # Test full-length release date and validation
    if file_class._supports_full_dates:
        with TestFile(
            "test_full_releasedate", extension, "alltags"
        ) as file_full_releasedate:
            await backend_full_releasedate(
                await file_class.new_from_path(file_full_releasedate)
            )

    # Comprehensive cover art test
    if file_class._supports_album_covers:
        with TestFile("test_cover", extension, "notags") as file_cover:
            await backend_test_covers(await file_class.new_from_path(file_cover))


def backend_read(file, skip_channels=False):
    """Tests common backend read functions."""
    for prop in file.handled_properties + file.supported_extra_tags:
        assert (
            file.get_property(prop) == prop_to_example_string[prop]
        ), f"Invalid value for property {prop} (expected {type(prop_to_example_string[prop])} {prop_to_example_string[prop]}, got {type(file.get_property(prop))} {file.get_property(prop)})"  # noqa: E501

        assert file.has_tag(prop), f"tag {prop} not found in file"

    if file._supports_album_covers:
        try:
            assert file.get_property("front_cover_path"), "cover art not found in file"
            assert filecmp.cmp(
                file.get_property("front_cover_path"),
                os.path.join(EXAMPLES_DIR, "cover.png"),
                shallow=False,
            ), "cover art differs from test value"  # noqa: E501

            assert file.get_property("back_cover_path"), "back cover not found in file"
            assert filecmp.cmp(
                file.get_property("back_cover_path"),
                os.path.join(EXAMPLES_DIR, "cover_back.png"),
                shallow=False,
            ), "back cover differs from test value"  # noqa: E501
        except TypeError:
            raise ValueError("cover art not found in file")

    assert file.get_property("is_modified") is False
    if (
        not skip_channels
    ):  # mutagen-mp4, at least with the m4a file, has some trouble with this step
        assert file.get_property("channels") == 1
    assert file.get_property("length") == 1
    assert file.get_property("bitrate") != 0


def backend_read_empty(file, skip_cover=False):
    for prop in file.handled_properties + file.supported_extra_tags:
        try:
            assert not file.get_property(prop)
            assert not file.has_tag(prop)
        except AssertionError:
            raise ValueError(
                f"example-notags file has {prop} property set to {file.get_property(prop)}; this either means that something is broken in the file, or in the backend."  # noqa: E501
            )

    assert file.get_property("is_modified") is False
    if not skip_cover:
        assert not file.get_property("front_cover_path"), file.get_property(
            "front_cover_path"
        )
        assert not file.get_property("back_cover_path"), file.get_property(
            "back_cover_path"
        )


async def backend_write(file, skip_channels=False):
    """Tests common backend write functions."""
    backend_read_empty(file)

    for prop in file.handled_properties + file.supported_extra_tags:
        file.set_property(prop, prop_to_example_string[prop])
        assert file.is_modified
        assert prop in file.modified_tags, prop
        assert file.has_tag(prop), f"tag {prop} not found in file"

    if file._supports_album_covers:
        for cover_filetype in ("jpg", "jp2", "bmp", "webp", "png"):
            file.set_property(
                "front_cover_path",
                os.path.join(EXAMPLES_DIR, f"cover.{cover_filetype}"),
            )
            assert file.get_property("front_cover_path")

            file.set_property(
                "back_cover_path",
                os.path.join(EXAMPLES_DIR, f"cover_back.{cover_filetype}"),
            )
            assert file.get_property("back_cover_path")

    assert file.get_property("is_modified") is True
    props_set = set(tuple(file.handled_properties) + tuple(file.supported_extra_tags))
    if file._supports_album_covers:
        props_set.add("front_cover_path")
        props_set.add("back_cover_path")
    assert set(file.modified_tags) == props_set

    file.save()

    assert file.get_property("is_modified") is False
    assert not file.modified_tags

    file_class = type(file)
    backend_read(await file_class.new_from_path(file.path), skip_channels)

    if REGENERATE_EXAMPLES:
        extension = os.path.splitext(file.path)[1]
        shutil.copyfile(file.path, os.path.join(EXAMPLES_DIR, f"example{extension}"))


async def backend_write_individual(empty_file, skip_channels=False):
    """Tests common backend write functions by writing each property separately."""
    backend_read_empty(empty_file)
    empty_file_path = empty_file.path
    file_class = type(empty_file)
    extension = os.path.splitext(empty_file_path)[1]

    for prop in empty_file.handled_properties:
        new_file_path = os.path.join(
            EXAMPLES_DIR, f"_example-notags-{prop}.{extension}"
        )
        shutil.copyfile(empty_file_path, new_file_path)
        target_value = prop_to_example_string[prop]
        file = await file_class.new_from_path(new_file_path)
        file.set_property(prop, target_value)

        assert file.is_modified
        assert prop in file.modified_tags, prop
        assert file.has_tag(prop), f"tag {prop} not found in file"

        file.save()

        file_read = await file_class.new_from_path(new_file_path)
        assert file_read.get_property(prop) == target_value
        for _prop in empty_file.handled_properties:
            if _prop != prop and prop != "totaltracknumber":
                assert not file.has_tag(_prop), f"file erroneously has tag {prop}"

        os.remove(new_file_path)


async def backend_write_empty(file, skip_channels=False):
    """Tests whether writing empty values removes the tag from the file."""
    for prop in file.handled_properties + file.supported_extra_tags:
        # tracknumber/totaltracknumber have separate handling as they're stored
        # as a single value in pretty much every file format. skip them for now
        if prop in ("tracknumber", "totaltracknumber"):
            continue
        if prop in file.int_properties or prop in file.float_properties:
            file.set_property(prop, 0)
        else:
            file.set_property(prop, "")
        assert not file.has_tag(prop), f"cleared tag {prop} found in file"

    if "totaltracknumber" in file.handled_properties:
        file.set_property("tracknumber", 0)
        file.set_property("totaltracknumber", 0)

        assert not file.has_tag("tracknumber"), "cleared tag tracknumber found in file"

        file.set_property("tracknumber", 1)
        assert file.has_tag("tracknumber")
        file.set_property("totaltracknumber", 1)
        assert file.has_tag("tracknumber")
        file.set_property("tracknumber", 0)
        assert file.has_tag("totaltracknumber")
        file.set_property("totaltracknumber", 0)
        assert not file.has_tag("tracknumber")
        assert not file.has_tag("totaltracknumber")

        file.set_property("tracknumber", 1)
        file.set_property("totaltracknumber", 1)
        file.set_property("totaltracknumber", 0)
        assert file.has_tag("tracknumber")
        file.set_property("tracknumber", 0)
        assert not file.has_tag("tracknumber")

    else:
        file.set_property("tracknumber", 0)
        assert not file.has_tag("tracknumber"), "cleared tag tracknumber found in file"

    assert file.get_property("is_modified") is True

    if file._supports_album_covers:
        file.set_property("front_cover_path", os.path.join(EXAMPLES_DIR, "cover.png"))
        assert file.get_property("front_cover_path")

        file.set_property(
            "back_cover_path", os.path.join(EXAMPLES_DIR, "cover_back.png")
        )
        assert file.get_property("back_cover_path")

    file.save()

    assert file.get_property("is_modified") is False
    assert not file.modified_tags

    file_class = type(file)
    backend_read_empty(await file_class.new_from_path(file.path), skip_cover=True)


async def backend_delete(file):
    """Tests common backend delete functions."""
    for prop in file.handled_properties + file.supported_extra_tags:
        file.delete_tag(prop)
        assert not file.has_tag(prop), f"tag {prop} erroneously found in file"
        assert not file.get_property(
            prop
        ), f"tag {prop} should have been deleted, but has value of {file.get_property(prop)}, {file.mg_file.tags}"  # noqa: E501
        assert prop in file.modified_tags

    assert file.get_property("is_modified") is True

    file.save()

    assert file.get_property("is_modified") is False

    if file._supports_album_covers:
        file.delete_cover(CoverType.FRONT)
        assert not file.has_tag("front-cover-path")
        assert not file.front_cover_path
        assert not file.front_cover.cover_path

        assert file.get_property("is_modified") is True
        file.save()
        assert file.get_property("is_modified") is False

        file.delete_cover(CoverType.BACK)
        assert not file.has_tag("back-cover-path")
        assert not file.back_cover_path
        assert not file.back_cover.cover_path

        assert file.get_property("is_modified") is True
        file.save()
        assert file.get_property("is_modified") is False

    file_class = type(file)
    backend_read_empty(await file_class.new_from_path(file.path))


async def backend_rename(file):
    """Tests the ability of the file to be renamed."""
    original_path = file.props.path
    orig_copy_path = original_path + "-orig"
    shutil.copyfile(original_path, orig_copy_path)
    new_path = original_path + "-moved"

    file.set_property("title", "Moved Title")

    await file.set_path_async(new_path)

    assert not os.path.exists(original_path)
    assert os.path.exists(new_path)
    assert file.props.path == new_path
    assert file.props.title == "Moved Title"
    assert filecmp.cmp(orig_copy_path, new_path, shallow=False)

    file.save()
    filecmp.clear_cache()
    assert not os.path.exists(original_path)
    assert os.path.exists(new_path)
    assert not filecmp.cmp(orig_copy_path, new_path, shallow=False)

    os.remove(orig_copy_path)
    os.remove(new_path)


def backend_delete_all_raw(file):
    """Tests the delete_all_raw function."""
    file.delete_all_raw()
    assert file.is_modified
    for prop in file.handled_properties + file.supported_extra_tags:
        assert not file.has_tag(prop), f"tag {prop} erroneously found in file"
        assert not file.get_property(
            prop
        ), f"tag {prop} should have been deleted, but has value of {file.get_property(prop)}, {file.mg_file.tags}"  # noqa: E501
        assert prop in file.modified_tags


async def backend_full_releasedate(file):
    """Tests various values for the releasedate field."""
    path = file.props.path
    file_class = type(file)
    for value in ("0000", "2022", "2022-01", "2022-01-31"):
        file = await file_class.new_from_path(path)
        file.set_property("releasedate", value)
        assert file.is_modified
        assert file._releasedate_cached == value
        file.save()
        file = await file_class.new_from_path(path)
        assert (
            file.get_property("releasedate") == value
        ), f'Invalid date value (expected "{value}", got "{file.get_property("releasedate")}")'  # noqa: E501


async def backend_test_covers(file):
    """
    Tests cover art functions and asserts they are all in place.
    Must be called on an empty file.
    """

    # Check for presence of required functions

    try:
        file.load_cover
    except AttributeError:
        raise AttributeError("Missing function: load_cover")
    try:
        file.set_cover_path
    except AttributeError:
        raise AttributeError("Missing function: set_cover_path")
    try:
        file.delete_cover
    except AttributeError:
        raise AttributeError("Missing function: delete_cover")
    try:
        assert file._front_cover_path is None
        assert file._back_cover_path is None
    except AttributeError:
        raise AttributeError("Missing _{front,back}_cover_path variables")

    # Set cover art
    front_cover_path = os.path.join(EXAMPLES_DIR, "cover.png")
    file.set_cover_path(CoverType.FRONT, front_cover_path)
    assert file.props.front_cover_path == file._front_cover_path
    assert file.props.front_cover_path == front_cover_path
    assert file.get_property("is_modified") is True
    assert "front_cover_path" in file.modified_tags
    file.save()
    assert file.get_property("is_modified") is False
    assert "front_cover_path" not in file.modified_tags

    # Re-load to make sure cover art is set
    file_class = type(file)
    reloaded_file = await file_class.new_from_path(file.path)
    assert reloaded_file.props.front_cover_path
    assert filecmp.cmp(
        reloaded_file.props.front_cover_path, front_cover_path, shallow=False
    )
    del reloaded_file

    # Set back cover
    back_cover_path = os.path.join(EXAMPLES_DIR, "cover_back.png")
    file.set_cover_path(CoverType.BACK, back_cover_path)
    assert file.props.back_cover_path == file._back_cover_path
    assert file.props.back_cover_path == back_cover_path
    assert file.get_property("is_modified") is True
    assert "back_cover_path" in file.modified_tags
    file.save()
    assert file.get_property("is_modified") is False
    assert "back_cover_path" not in file.modified_tags

    # Re-load to make sure cover art is set
    file_class = type(file)
    reloaded_file = await file_class.new_from_path(file.path)
    assert reloaded_file.props.front_cover_path
    assert filecmp.cmp(
        reloaded_file.props.front_cover_path, front_cover_path, shallow=False
    )
    assert reloaded_file.props.back_cover_path
    assert filecmp.cmp(
        reloaded_file.props.back_cover_path, back_cover_path, shallow=False
    )
    del reloaded_file

    # Delete both covers
    file.delete_cover(CoverType.FRONT, clear_only=False)
    assert not file.props.front_cover_path
    assert not file._front_cover_path
    assert file.props.back_cover_path
    assert file.get_property("is_modified") is True
    assert "front_cover_path" in file.modified_tags
    file.save()
    assert file.get_property("is_modified") is False
    assert "front_cover_path" not in file.modified_tags

    file.delete_cover(CoverType.BACK, clear_only=False)
    assert not file.props.front_cover_path
    assert not file.props.back_cover_path
    assert not file._back_cover_path
    assert file.get_property("is_modified") is True
    assert "back_cover_path" in file.modified_tags
    file.save()
    assert file.get_property("is_modified") is False
    assert "back_cover_path" not in file.modified_tags

    # Delete both covers, now in reverse order!
    file.set_cover_path(CoverType.FRONT, front_cover_path)
    file.set_cover_path(CoverType.BACK, back_cover_path)
    file.save()

    file.delete_cover(CoverType.BACK, clear_only=False)
    assert file.props.front_cover_path
    assert not file.props.back_cover_path
    assert not file._back_cover_path
    assert file.get_property("is_modified") is True
    assert "back_cover_path" in file.modified_tags
    file.save()
    assert file.get_property("is_modified") is False
    assert "back_cover_path" not in file.modified_tags

    file.delete_cover(CoverType.FRONT, clear_only=False)
    assert not file.props.front_cover_path
    assert not file._front_cover_path
    assert not file.props.back_cover_path
    assert file.get_property("is_modified") is True
    assert "front_cover_path" in file.modified_tags
    file.save()
    assert file.get_property("is_modified") is False
    assert "front_cover_path" not in file.modified_tags

    # Add both covers, now in reverse order!
    back_cover_path = os.path.join(EXAMPLES_DIR, "cover_back.png")
    file.set_cover_path(CoverType.BACK, back_cover_path)
    assert file.props.back_cover_path == file._back_cover_path
    assert file.props.back_cover_path == back_cover_path
    assert file.get_property("is_modified") is True
    assert "back_cover_path" in file.modified_tags
    file.save()
    assert file.get_property("is_modified") is False
    assert "back_cover_path" not in file.modified_tags

    file_class = type(file)
    reloaded_file = await file_class.new_from_path(file.path)
    assert not reloaded_file.props.front_cover_path
    assert reloaded_file.props.back_cover_path
    assert filecmp.cmp(
        reloaded_file.props.back_cover_path, back_cover_path, shallow=False
    )
    del reloaded_file

    front_cover_path = os.path.join(EXAMPLES_DIR, "cover.png")
    file.set_cover_path(CoverType.FRONT, front_cover_path)
    assert file.props.front_cover_path == file._front_cover_path
    assert file.props.front_cover_path == front_cover_path
    assert file.get_property("is_modified") is True
    assert "front_cover_path" in file.modified_tags
    file.save()
    assert file.get_property("is_modified") is False
    assert "front_cover_path" not in file.modified_tags

    file_class = type(file)
    reloaded_file = await file_class.new_from_path(file.path)
    assert reloaded_file.props.front_cover_path
    assert reloaded_file.props.back_cover_path
    assert filecmp.cmp(
        reloaded_file.props.front_cover_path, front_cover_path, shallow=False
    )
    assert filecmp.cmp(
        reloaded_file.props.back_cover_path, back_cover_path, shallow=False
    )
    del reloaded_file

    # Test shallow delete (clear_only)
    file.set_cover_path(CoverType.FRONT, front_cover_path)
    file.set_cover_path(CoverType.BACK, back_cover_path)
    file.save()

    file.delete_cover(CoverType.FRONT, clear_only=True)
    assert file.props.front_cover_path
    assert file.get_property("is_modified") is False
    assert "front_cover_path" not in file.modified_tags
    file.save()

    file.delete_cover(CoverType.BACK, clear_only=True)
    assert file.props.back_cover_path
    assert file.get_property("is_modified") is False
    assert "back_cover_path" not in file.modified_tags
    file.save()

    # Test cover objects
    file.set_cover_path(CoverType.FRONT, front_cover_path)
    file.set_cover_path(CoverType.BACK, back_cover_path)
    file.save()

    assert file.front_cover.cover_path == file.front_cover_path
    assert file.back_cover.cover_path == file.back_cover_path
    assert file.front_cover != file.back_cover
