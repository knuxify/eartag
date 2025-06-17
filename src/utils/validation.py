# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

import os.path
import filetype
from filetype.types import AUDIO as audio_matchers
from filetype.types import IMAGE as image_matchers
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


_mimetype_cache = {}


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

    mimetype = filetype.match(path, matchers=(audio_matchers + image_matchers))

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


def get_mimetype_buffer(data):
    """Get mimetype from buffer."""
    return filetype.match(data, matchers=(filetype.types.AUDIO + filetype.types.IMAGE))


def is_valid_music_file(path: Union[str, os.PathLike], no_cache: bool = False):
    """Check if the file at the provided path is a supported audio file."""
    return is_valid_file(path, VALID_AUDIO_MIMES, no_cache=no_cache)


def is_valid_image_file(path: Union[str, os.PathLike], no_cache: bool = False):
    """Check if the file at the provided path is a supported image file."""
    return is_valid_file(path, VALID_IMAGE_MIMES, no_cache=no_cache)


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
