import pytest

from src.utils.misc import cleanup_filename, FILENAME_BANNED_CHARS, BANNED_FILENAMES


@pytest.mark.parametrize("banned_character", FILENAME_BANNED_CHARS)
def test_replace_banned_character_with_underscore(banned_character):
    filename = f"a{banned_character}b{banned_character}c"
    assert cleanup_filename(filename) == "a_b_c"


def test_replace_two_different_banned_characters_with_underscore():
    filename = f"a{FILENAME_BANNED_CHARS[0]}b{FILENAME_BANNED_CHARS[1]}c"
    assert cleanup_filename(filename) == "a_b_c"


@pytest.mark.parametrize(
    "filename",
    [
        "/a/b/c ",
        "/a/b/ c",
        "/a/b/ c ",
        "/a/b /c",
        "/a/ b/c",
        "/a/ b /c",
        "/a /b/c",
        "/ a/b/c",
        "/ a /b/c",
        "/a / b/ c ",
    ],
)
def test_strip_spaces(filename):
    assert cleanup_filename(filename, full_path=True) == "/a/b/c"


@pytest.mark.parametrize("banned_filename", BANNED_FILENAMES)
def test_add_underscore_prefix_to_banned_file_name(banned_filename):
    assert cleanup_filename(f"/{banned_filename}", full_path=True) == f"/_{banned_filename}"


def test_replace_point_point_with_underscores():
    assert cleanup_filename("/../example.mp3", full_path=True) == "/__/example.mp3"


def test_replace_last_point_point_with_underscores():
    assert cleanup_filename("/example.mp3.", full_path=True) == "/example.mp3_"


def test_replace_last_point_with_underscores():
    assert cleanup_filename("/example.mp3.", full_path=True) == "/example.mp3_"


def test_trim_too_long_file_path():
    too_long_file_path = "a" * 250
    trimmed_file_path = too_long_file_path[-249:]
    actual = f"/{too_long_file_path}/example.mp3"
    expected = f"/{trimmed_file_path}/example.mp3"
    assert cleanup_filename(actual, full_path=True) == expected


def test_trim_too_long_file_name():
    too_long_file_name = ("a" * 250) + ".mp3"
    assert len(too_long_file_name) == 254
    trimmed_file_name = ("a" * 246) + ".mp3"
    assert len(trimmed_file_name) == 250
    actual = f"/music/{too_long_file_name}"
    expected = f"/music/{trimmed_file_name}"
    assert cleanup_filename(actual, full_path=True) == expected
