from unittest.mock import patch

import pytest

from src.utils.validation import (
    is_valid_music_file,
    is_valid_image_file,
    is_valid_file,
    VALID_AUDIO_MIMES,
)

EXAMPLES_DIRECTORY = "tests/backends/examples"

example_mp3 = f"{EXAMPLES_DIRECTORY}/example.mp3"


def test_path_not_found():
    assert is_valid_music_file("/eartag/not-found") is False


@pytest.mark.parametrize(
    "file_name",
    [
        "example.flac",
        "example.m4a",
        "example.mp3",
        "example.ogg",
        "example.wav",
        "example.wma",
    ],
)
def test_valid_music_file(file_name):
    assert is_valid_music_file(f"{EXAMPLES_DIRECTORY}/{file_name}") is True


@pytest.mark.parametrize(
    "file_name",
    ["aconcagua.jpg", "cover.png"],
)
def test_valid_image_file(file_name):
    assert is_valid_image_file(f"{EXAMPLES_DIRECTORY}/{file_name}") is True


@patch("magic.from_file")
def test_magic_fails_to_get_file_type(mock_magic_from_file):
    mock_magic_from_file.return_value = "application/octet-stream"

    assert is_valid_file(example_mp3, VALID_AUDIO_MIMES) is True


@patch("magic.from_file")
def test_magic_returns_no_file_type(mock_magic_from_file):
    mock_magic_from_file.return_value = False

    assert is_valid_file(example_mp3, VALID_AUDIO_MIMES) is False


@patch("magic.from_file")
def test_file_type_not_in_valid_mime_types(mock_magic_from_file):
    mock_magic_from_file.return_value = "audio/invalid"

    assert is_valid_file(example_mp3, VALID_AUDIO_MIMES) is False
