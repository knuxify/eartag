# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

import os.path
import magic
import mimetypes

VALID_AUDIO_MIMES = (
    'application/ogg',
    'application/x-ogg',
    'audio/aac',
    'audio/flac',
    'audio/mp3',
    'audio/mp4',
    'audio/mpeg',
    'audio/ogg',
    'audio/wav',
    'audio/x-flac',
    'audio/x-m4a',
    'audio/x-mp3',
    'audio/x-mpeg',
    'audio/x-ms-wma',
    'audio/x-vorbis+ogg',
    'audio/x-wav',
    'video/mp4',
    'video/x-ms-asf',
    'video/x-wmv'
    )

def is_valid_music_file(path):
    """
    Takes a path to a file and returns True if it's supported, False otherwise.
    """
    # In Flatpak, some files don't exist; double-check to make sure
    if not os.path.exists(path):
        return False

    mimetype = magic.from_file(path, mime=True)
    if mimetype == 'application/octet-stream':
        # Try to guess mimetype from filetype if magic fails
        mimetype = mimetypes.guess_type(path)[0]

    if not mimetype or mimetype not in VALID_AUDIO_MIMES:
        return False
    return True

def is_valid_image_file(path):
    """
    Takes a path to a file and returns True if it's supported, False otherwise.
    """
    # In Flatpak, some files don't exist; double-check to make sure
    if not os.path.exists(path):
        return False

    mimetype = magic.from_file(path, mime=True)
    if mimetype == 'application/octet-stream':
        # Try to guess mimetype from filetype if magic fails
        mimetype = mimetypes.guess_type(path)[0]

    if not mimetype or mimetype not in ['image/jpeg', 'image/png']:
        return False
    return True
