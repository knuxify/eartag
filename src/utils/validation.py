# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

import aiofiles
import aiofiles.os
import os.path
import filetype
from filetype.types import AUDIO as audio_matchers
from filetype.types import IMAGE as image_matchers
from filetype.types import VIDEO as video_matchers
from filetype.types.base import Type
import mimetypes

from collections.abc import Iterable
from typing import Union, Optional

VALID_AUDIO_MIMES = (
    "application/ogg",
    "application/x-ogg",
    "audio/aac",
    "audio/flac",
    "audio/mp3",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/x-flac",
    "audio/x-m4a",
    "audio/x-mp3",
    "audio/x-mpeg",
    "audio/x-ms-wma",
    "audio/x-vorbis+ogg",
    "audio/x-wav",
    "video/mp4",
    "video/x-ms-asf",
    "video/x-wmv",
)

VALID_IMAGE_MIMES = (
    # Supported natively by most formats:
    "image/jpg",
    "image/jpeg",
    "image/png",
    # Converted using Pillow:
    "image/bmp",
    "image/jp2",
    "image/webp",
)

# Custom filetype.py filetypes for formats it doesn't usually support


class ImprovedMP3(Type):
    """
    Improved MP3 filetype from latest main branch;
    see https://github.com/h2non/filetype.py/blob/master/filetype/types/audio.py
    """

    MIME = "audio/mpeg"
    EXTENSION = "mp3"

    def __init__(self):
        super(ImprovedMP3, self).__init__(
            mime=ImprovedMP3.MIME, extension=ImprovedMP3.EXTENSION
        )

    def match(self, buf):
        if len(buf) > 2:
            if buf[0] == 0x49 and buf[1] == 0x44 and buf[2] == 0x33:
                return True

            if buf[0] == 0xFF:
                if (
                    buf[1] == 0xE2  # MPEG 2.5 with error protection
                    or buf[1] == 0xE3  # MPEG 2.5 w/o error protection
                    or buf[1] == 0xF2  # MPEG 2 with error protection
                    or buf[1] == 0xF3  # MPEG 2 w/o error protection
                    or buf[1] == 0xFA  # MPEG 1 with error protection
                    or buf[1] == 0xFB  # MPEG 1 w/o error protection
                ):
                    return True
        return False


class Wma(Type):
    """Implements the WMA audio type matcher."""

    MIME = "audio/x-ms-wma"
    EXTENSION = "wma"

    def __init__(self):
        super(Wma, self).__init__(mime=Wma.MIME, extension=Wma.EXTENSION)

    def match(self, buf):
        if len(buf) > 14:
            if (
                buf[0] == 0x30
                and buf[1] == 0x26
                and buf[2] == 0xB2
                and buf[3] == 0x75
                and buf[4] == 0x8E
                and buf[5] == 0x66
                and buf[6] == 0xCF
                and buf[7] == 0x11
                and buf[8] == 0xA6
                and buf[9] == 0xD9
                and buf[10] == 0x00
                and buf[11] == 0xAA
                and buf[12] == 0x00
                and buf[13] == 0x62
                and buf[14] == 0xCE
                and buf[15] == 0x6C
            ):
                return True
        return False


CUSTOM_MATCHERS = (ImprovedMP3(), Wma())
FILETYPE_MATCHERS = CUSTOM_MATCHERS + audio_matchers + image_matchers + video_matchers

_mimetype_cache = {}


def get_mimetype_buffer(data):
    """Get mimetype from buffer."""
    return filetype.match(data, matchers=FILETYPE_MATCHERS)


def get_mimetype(
    path: Union[str, os.PathLike],
    no_extension_guess: bool = False,
    no_cache: bool = False,
) -> Optional[str]:
    """
    Return the mimetype (or None) for the file with the given path or data.

    :param path: Path to the file (or buffer data).
    :param no_extension_guess: If True, skips guessing the filetype from the extension.
    :param no_cache: Skip the mimetype cache.
    """
    if not no_cache:
        if path in _mimetype_cache:
            return _mimetype_cache[path]

    mimetype = filetype.match(path, matchers=FILETYPE_MATCHERS)

    ret = None
    if mimetype:
        ret = mimetype.mime
    elif not no_extension_guess:
        # Try to guess mimetype from file extension if filetype match fails
        guess = mimetypes.guess_type(path)
        if guess and guess[0]:
            ret = guess[0]

    if not no_cache:
        _mimetype_cache[path] = ret

    return ret


async def get_mimetype_async(
    path: Union[str, os.PathLike],
    no_extension_guess: bool = False,
    no_cache: bool = False,
) -> Optional[str]:
    """
    Return the mimetype (or None) for the file with the given path or data.

    Async-safe version of get_mimetype.

    :param path: Path to the file (or buffer data).
    :param no_extension_guess: If True, skips guessing the filetype from the extension.
    :param no_cache: Skip the mimetype cache.
    """
    if not no_cache:
        if path in _mimetype_cache:
            return _mimetype_cache[path]

    async with aiofiles.open(path, "rb") as file:
        mimetype = get_mimetype_buffer(await file.read(2048))

    ret = None
    if mimetype:
        ret = mimetype.mime
    elif not no_extension_guess:
        # Try to guess mimetype from file extension if filetype match fails
        guess = mimetypes.guess_type(path)
        if guess and guess[0]:
            ret = guess[0]

    if not no_cache:
        _mimetype_cache[path] = ret

    return ret


def is_valid_file(
    path: Union[str, os.PathLike],
    valid_mime_types: Iterable[str],
    no_cache: bool = False,
):
    """
    Takes a path to a file and returns True if it's supported, False otherwise.
    """
    # In Flatpak, some files don't exist; double-check to make sure
    if not os.path.exists(path):
        return False

    mimetype = get_mimetype(path, no_cache=no_cache)

    if not mimetype or mimetype not in valid_mime_types:
        return False
    return True


def is_valid_music_file(path: Union[str, os.PathLike], no_cache: bool = False):
    """Check if the file at the provided path is a supported audio file."""
    return is_valid_file(path, VALID_AUDIO_MIMES, no_cache=no_cache)


def is_valid_image_file(path: Union[str, os.PathLike], no_cache: bool = False):
    """Check if the file at the provided path is a supported image file."""
    return is_valid_file(path, VALID_IMAGE_MIMES, no_cache=no_cache)


async def is_valid_file_async(
    path: Union[str, os.PathLike],
    valid_mime_types: Iterable[str],
    no_cache: bool = False,
):
    """
    Takes a path to a file and returns True if it's supported, False otherwise.

    Async version of is_valid_file.
    """
    # In Flatpak, some files don't exist; double-check to make sure
    if not await aiofiles.os.path.exists(path):
        return False

    mimetype = await get_mimetype_async(path, no_cache=no_cache)

    if not mimetype or mimetype not in valid_mime_types:
        return False
    return True


async def is_valid_music_file_async(
    path: Union[str, os.PathLike], no_cache: bool = False
):
    """Check if the file at the provided path is a supported audio file."""
    return await is_valid_file_async(path, VALID_AUDIO_MIMES, no_cache=no_cache)


async def is_valid_image_file_async(
    path: Union[str, os.PathLike], no_cache: bool = False
):
    """Check if the file at the provided path is a supported image file."""
    return await is_valid_file_async(path, VALID_IMAGE_MIMES, no_cache=no_cache)
