# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import GObject

from .file import EartagFile


class EartagFileMutagenCommon(EartagFile):
    """Base class for Mutagen-based backends."""

    __gtype_name__ = "EartagFileMutagenCommon"

    def __init__(self, path):
        super().__init__(path)
        self.mg_file = None

    def save(self):
        """Saves the changes to the file."""
        self.mg_file.save()
        self.setup_original_values()
        self.mark_as_unmodified()

    def on_remove(self, *args):
        super().on_remove()
        self.mg_file = None

    def delete_all_raw(self):
        self.delete_all()
        if not self.mg_file.tags:
            return
        for tag in dict(self.mg_file.tags).keys():
            del self.mg_file.tags[tag]

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
