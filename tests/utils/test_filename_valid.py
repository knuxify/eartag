import os.path

import pytest

from src.utils.misc import filename_valid, FILENAME_BANNED_CHARS, BANNED_FILENAMES


def test_empty_filename():
    assert filename_valid("") is False


def test_filename_not_normalized():
    assert filename_valid("music/misc/../example.mp3") is False


def test_filename_without_path():
    assert filename_valid("example.mp3") is True


def test_filename_with_path_separator_when_fullpath_is_disallowed():
    assert filename_valid("/example.mp3") is False


@pytest.mark.parametrize("banned_character", FILENAME_BANNED_CHARS)
def test_filename_containing_banned_character(banned_character):
    assert filename_valid(f"example.mp3{banned_character}") is False


@pytest.mark.parametrize("banned_filename", BANNED_FILENAMES)
def test_banned_filename(banned_filename):
    assert filename_valid(banned_filename) is False


def test_filename_starting_with_relative_parent_directory():
    assert filename_valid("../example.mp3") is False


def test_filename_ending_with_period():
    assert filename_valid("example.mp3.") is False


@pytest.mark.parametrize("filename_with_space", ["example.mp3 ", " example.mp3"])
def test_filename_with_spaces(filename_with_space):
    assert filename_valid(filename_with_space) is False


def test_filename_with_path_deeper_than_255_levels():
    filename = "a" * 256
    assert filename_valid(filename) is False


@pytest.mark.parametrize("filename", ["music//example.mp3", "example.mp3/"])
def test_filename_not_normalized_when_paths_are_allowed(filename):
    assert filename_valid(filename, allow_path=True) is False


def test_filename_with_path_separator_when_paths_are_allowed():
    assert filename_valid("music/example.mp3", allow_path=True) is True


banned_chars_except_path_separator = list(FILENAME_BANNED_CHARS)
banned_chars_except_path_separator.remove(os.path.sep)


@pytest.mark.parametrize("banned_character", banned_chars_except_path_separator)
def test_filename_containing_banned_character_when_paths_are_allowed(banned_character):
    assert filename_valid(f"example.mp3{banned_character}", allow_path=True) is False


@pytest.mark.parametrize("banned_filename", BANNED_FILENAMES)
def test_banned_filename_when_paths_are_allowed(banned_filename):
    assert filename_valid(f"music/{banned_filename}", allow_path=True) is False


def test_filename_ending_with_period_when_paths_are_allowed():
    assert filename_valid("music/example.mp3.", allow_path=True) is False


@pytest.mark.parametrize("filename_with_space", ["music/example.mp3 ", " music/example.mp3"])
def test_filename_with_spaces_when_paths_are_allowed(filename_with_space):
    assert filename_valid(filename_with_space, allow_path=True) is False


def test_filename_with_path_deeper_than_255_levels_when_paths_are_allowed():
    filename = "music/" + ("a" * 256)
    assert filename_valid(filename, allow_path=True) is False
