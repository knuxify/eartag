# SPDX-License-Identifier: MIT
"""
Helper script to regenerate examples.
"""

import asyncio
import os.path
import shutil

from .common import backend_write

from src.backends.file_mutagen_vorbis import EartagFileMutagenVorbis
from src.backends.file_mutagen_mp4 import EartagFileMutagenMP4
from src.backends.file_mutagen_id3 import EartagFileMutagenID3
from src.backends.file_mutagen_asf import EartagFileMutagenASF


async def regenerate_examples():
    for extension, filetype in {
        "ogg": EartagFileMutagenVorbis,
        "flac": EartagFileMutagenVorbis,
        "mp3": EartagFileMutagenID3,
        "wav": EartagFileMutagenID3,
        "m4a": EartagFileMutagenMP4,
        "wma": EartagFileMutagenASF,
    }.items():
        examples_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")
        filename_notags = os.path.join(examples_dir, "example-notags." + extension)
        filename = os.path.join(examples_dir, "example." + extension)
        shutil.copy(filename_notags, filename)
        file = await filetype.new_from_path(filename)
        await backend_write(file, skip_channels=True)


if __name__ == "__main__":
    asyncio.run(regenerate_examples())
