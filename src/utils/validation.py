# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

import os.path
import magic
import mimetypes

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


def is_valid_music_file(path):
    return is_valid_file(path, VALID_AUDIO_MIMES)


def is_valid_image_file(path):
    return is_valid_file(path, VALID_IMAGE_MIMES)


def is_valid_file(path, valid_mime_types):
    """
    Takes a path to a file and returns True if it's supported, False otherwise.
    """
    # In Flatpak, some files don't exist; double-check to make sure
    if not os.path.exists(path):
        return False

    mimetype = magic.from_file(path, mime=True)
    if mimetype == "application/octet-stream":
        # Try to guess mimetype from filetype if magic fails
        mimetype = mimetypes.guess_type(path)[0]

    if not mimetype or mimetype not in valid_mime_types:
        return False
    return True
