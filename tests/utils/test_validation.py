from unittest.mock import patch

import pytest

from src.utils.validation import (
    is_valid_music_file,
    is_valid_image_file,
    is_valid_file,
    is_valid_music_file_async,
    is_valid_image_file_async,
    is_valid_file_async,
    VALID_AUDIO_MIMES,
)

EXAMPLES_DIRECTORY = "tests/backends/examples"

example_mp3 = f"{EXAMPLES_DIRECTORY}/example.mp3"


@pytest.mark.asyncio
async def test_path_not_found():
    assert is_valid_music_file("/eartag/not-found") is False
    assert await is_valid_music_file_async("/eartag/not-found") is False


@pytest.mark.asyncio
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
async def test_valid_music_file(file_name):
    assert is_valid_music_file(f"{EXAMPLES_DIRECTORY}/{file_name}") is True
    assert await is_valid_music_file_async(f"{EXAMPLES_DIRECTORY}/{file_name}") is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "file_name",
    ["cover.jpg", "cover.png", "cover.jp2", "cover.webp", "cover.bmp"],
)
async def test_valid_image_file(file_name):
    assert is_valid_image_file(f"{EXAMPLES_DIRECTORY}/{file_name}") is True
    assert await is_valid_image_file_async(f"{EXAMPLES_DIRECTORY}/{file_name}") is True


@pytest.mark.asyncio
@patch("filetype.match", lambda *a, **b: None)
@patch("mimetypes.guess_type", lambda *a, **b: [])
async def test_magic_returns_no_file_type():
    assert is_valid_file(example_mp3, VALID_AUDIO_MIMES, no_cache=True) is False
    assert (
        await is_valid_file_async(example_mp3, VALID_AUDIO_MIMES, no_cache=True)
        is False
    )


class FakeMatch:
    mime = "audio/invalid"


@pytest.mark.asyncio
@patch("filetype.match", lambda *a, **b: FakeMatch())
@patch("mimetypes.guess_type", lambda *a, **b: ["audio/invalid2"])
async def test_file_type_not_in_valid_mime_types():
    assert is_valid_file(example_mp3, VALID_AUDIO_MIMES, no_cache=True) is False
    assert (
        await is_valid_file_async(example_mp3, VALID_AUDIO_MIMES, no_cache=True)
        is False
    )
