# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from . import APP_GRESOURCE_PATH

from gi.repository import Adw, Gtk, Pango

PLACEHOLDER_COLORS = [
    (53, 132, 228),  # @blue_3
    (51, 209, 122),  # @green_3
    (246, 211, 45),  # @yellow_3
    (255, 120, 0),   # @orange_3
    (224, 27, 36),   # @red_3
    (145, 65, 172),  # @purple_3
    (152, 106, 68),  # @brown_3
]

class EartagGuessRow(Gtk.Box):
    __gtype_name__ = 'EartagGuessRow'


@Gtk.Template(resource_path=f'{APP_GRESOURCE_PATH}/ui/guess.ui')
class EartagGuessDialog(Adw.Window):
    """Dialog for guessing selected files' tags from their filename."""
    __gtype_name__ = 'EartagGuessDialog'

    custom_entry = Gtk.Template.Child()

    guess_presets = [
        '{artist} - {title}'
        '{tracknumber} {title}'
        '{tracknumber} {artist} - {title}'
    ]

    def __init__(self, parent):
        super().__init__(modal=True, transient_for=parent)
        self.custom_entry.set_text('testing')
        attrs = Pango.AttrList()
        color = PLACEHOLDER_COLORS[0]
        color_attr = Pango.attr_foreground_new((color[0]+1)*256, (color[1]+1)*256, (color[2]+1)*256)
        color_attr.start_index = 0
        color_attr.end_index = 5
        attrs.insert(color_attr)
        self.custom_entry.set_attributes(attrs)

    @Gtk.Template.Callback()
    def on_cancel(self, *args):
        self.close()

    @Gtk.Template.Callback()
    def do_apply(self, *args):
        pass
