# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import GObject
import mutagen

from .file import EartagFile

class EartagFileMutagenCommon(EartagFile):
    """Base class for Mutagen-based backends."""
    __gtype_name__ = 'EartagFileMutagenCommon'

    def __init__(self, path):
        super().__init__(path)
        self.coverart_tempfile = None
        self.mg_file = None
        self.load_from_file(path)

    def load_from_file(self, path):
        self.mg_file = mutagen.File(path)

    def save(self):
        """Saves the changes to the file."""
        self.mg_file.save()
        self.setup_original_values()
        self.mark_as_unmodified()

    def on_remove(self, *args):
        self.mg_file = None

    def _cleanup_cover(self):
        """Common cleanup steps after delete_cover."""
        if self.coverart_tempfile:
            self.coverart_tempfile.close()
        self._cover_path = ''
        self.mark_as_modified('cover_path')
        self.notify('cover-path')

    # Main properties

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def length(self):
        return int(self.mg_file.info.length)

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def bitrate(self):
        # in bps, needs conversion
        try:
            return int(round(self.mg_file.info.bitrate / 1000, 0))
        except AttributeError:
            # For some files, Mutagen can't tell the bitrate
            return -1

    @GObject.Property(type=int, flags=GObject.ParamFlags.READABLE)
    def channels(self):
        return self.mg_file.info.channels
