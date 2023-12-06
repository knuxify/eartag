# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from .file_mutagen_vorbis import EartagFileMutagenVorbis # noqa: F401
from .file_mutagen_id3 import EartagFileMutagenID3 # noqa: F401
from .file_mutagen_mp4 import EartagFileMutagenMP4 # noqa: F401
from .file_mutagen_asf import EartagFileMutagenASF # noqa: F401

from .file import BASIC_TAGS, EXTRA_TAGS, TAG_NAMES # noqa: F401
