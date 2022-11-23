from .common import run_backend_tests

from src.backends.file_mutagen_vorbis import EartagFileMutagenVorbis
from src.backends.file_mutagen_mp4 import EartagFileMutagenMP4
from src.backends.file_mutagen_id3 import EartagFileMutagenID3
from src.backends.file_taglib import EartagFileTagLib

def test_backend_mutagen_vorbis():
    run_backend_tests(EartagFileMutagenVorbis, 'flac')
    run_backend_tests(EartagFileMutagenVorbis, 'ogg')

def test_backend_taglib():
    run_backend_tests(EartagFileTagLib, 'wav')

def test_backend_mutagen_id3():
    run_backend_tests(EartagFileMutagenID3, 'mp3')
    run_backend_tests(EartagFileMutagenID3, 'wav')

def test_backend_mutagen_mp4():
    run_backend_tests(EartagFileMutagenMP4, 'm4a', skip_channels=True)
