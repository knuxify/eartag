# window.py
#
# Copyright 2022 knuxify
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE X CONSORTIUM BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# Except as contained in this notice, the name(s) of the above copyright
# holders shall not be used in advertising or otherwise to promote the sale,
# use or other dealings in this Software without prior written
# authorization.

from gi.repository import Gtk, Adw
from .fileview import EartagFileView

@Gtk.Template(resource_path='/org/dithernet/Eartag/ui/closewarning.ui')
class EartagCloseWarningDialog(Gtk.MessageDialog):
    __gtype_name__ = 'EartagCloseWarningDialog'

    def __init__(self, window):
        super().__init__(transient_for=window)
        self.window = window

    @Gtk.Template.Callback()
    def on_button_discard(self, *args):
        self.window.force_close = True
        self.window.close()

    @Gtk.Template.Callback()
    def on_button_cancel(self, *args):
        self.close()

    @Gtk.Template.Callback()
    def on_button_save(self, *args):
        self.window.file_view.save()
        self.window.close()

@Gtk.Template(resource_path='/org/dithernet/Eartag/ui/nofile.ui')
class EartagNoFile(Adw.Bin):
    __gtype_name__ = 'EartagNoFile'

    def __init__(self):
        super().__init__()

    @Gtk.Template.Callback()
    def on_add_file(self, *args):
        self.get_native().show_file_chooser()

@Gtk.Template(resource_path='/org/dithernet/Eartag/ui/window.ui')
class EartagWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'EartagWindow'

    save_button = Gtk.Template.Child()
    window_title = Gtk.Template.Child()
    content_stack = Gtk.Template.Child()

    audio_file_filter = Gtk.Template.Child()

    no_file = Gtk.Template.Child()
    file_view = Gtk.Template.Child()

    force_close = False

    def __init__(self, application, path=None):
        super().__init__(application=application, title='Eartag')
        if path:
            self.file_view.file_path = path
            self.file_view.load_file()
        self.connect('close-request', self.on_close_request)

    def show_file_chooser(self):
        """Shows the file chooser."""
        self.file_chooser = Gtk.FileChooserDialog(
                                title=_("Open File"),
                                transient_for=self,
                                action=Gtk.FileChooserAction.OPEN,
                                filter=self.audio_file_filter
                                )
        self.file_chooser.add_buttons(
            _("_Cancel"), Gtk.ResponseType.CANCEL,
            _("_Open"), Gtk.ResponseType.ACCEPT
        )

        self.file_chooser.connect('response', self.open_file_from_dialog)

        self.file_chooser.present()

    def open_file_from_dialog(self, dialog, response):
        """
        Callback for a FileChooser that takes the response and opens the file
        selected in the dialog.
        """
        if response == Gtk.ResponseType.ACCEPT:
            self.file_view.file_path = dialog.get_file().get_path()
            self.file_view.load_file()
        self.file_chooser.destroy()

    @Gtk.Template.Callback()
    def on_save(self, *args):
        self.file_view.save()

    def on_close_request(self, *args):
        if self.force_close == False and self.file_view.file and \
            self.file_view.file._is_modified:
            self.close_request_dialog = EartagCloseWarningDialog(self)
            self.close_request_dialog.present()
            return True

class AboutDialog(Gtk.AboutDialog):
    def __init__(self, parent):
        Gtk.AboutDialog.__init__(self)
        self.props.program_name = 'Eartag'
        self.props.version = "0.1.0"
        self.props.authors = ['knuxify']
        self.props.copyright = '(C) 2022 knuxify'
        self.props.logo_icon_name = 'org.dithernet.Eartag'
        self.set_transient_for(parent)
