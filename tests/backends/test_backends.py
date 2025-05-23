from .common import run_backend_tests
import pytest

from src.backends.file_mutagen_vorbis import EartagFileMutagenVorbis
from src.backends.file_mutagen_mp4 import EartagFileMutagenMP4
from src.backends.file_mutagen_id3 import EartagFileMutagenID3
from src.backends.file_mutagen_asf import EartagFileMutagenASF


@pytest.mark.asyncio
async def test_backend_mutagen_vorbis():
    await run_backend_tests(EartagFileMutagenVorbis, "flac")
    await run_backend_tests(EartagFileMutagenVorbis, "ogg")


@pytest.mark.asyncio
async def test_backend_mutagen_id3():
    await run_backend_tests(EartagFileMutagenID3, "mp3")
    await run_backend_tests(EartagFileMutagenID3, "wav")


@pytest.mark.asyncio
async def test_backend_mutagen_mp4():
    await run_backend_tests(EartagFileMutagenMP4, "m4a", skip_channels=True)


@pytest.mark.asyncio
async def test_backend_mutagen_asf():
    await run_backend_tests(EartagFileMutagenASF, "wma")
