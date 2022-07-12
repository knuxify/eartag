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

from .common import is_valid_music_file
from .fileview import EartagFileView

from gi.repository import Adw, Gdk, Gio, Gtk

@Gtk.Template(resource_path='/app/drey/EarTag/ui/discardwarning.ui')
class EartagDiscardWarningDialog(Gtk.MessageDialog):
    __gtype_name__ = 'EartagDiscardWarningDialog'

    def __init__(self, window, file_path):
        super().__init__(transient_for=window)
        self.window = window
        self.file_path = file_path

    @Gtk.Template.Callback()
    def on_dbutton_discard(self, *args):
        self.window.load_file(self.file_path)
        self.close()

    @Gtk.Template.Callback()
    def on_dbutton_cancel(self, *args):
        self.close()

    @Gtk.Template.Callback()
    def on_dbutton_save(self, *args):
        if not self.window.file_view.save():
            return False
        self.window.load_file(self.file_path)
        self.close()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/closewarning.ui')
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
        if not self.window.file_view.save():
            return False
        self.window.close()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/nofile.ui')
class EartagNoFile(Adw.Bin):
    __gtype_name__ = 'EartagNoFile'

    def __init__(self):
        super().__init__()

    @Gtk.Template.Callback()
    def on_add_file(self, *args):
        self.get_native().show_file_chooser()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/window.ui')
class EartagWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'EartagWindow'

    save_button = Gtk.Template.Child()
    window_title = Gtk.Template.Child()
    content_stack = Gtk.Template.Child()

    audio_file_filter = Gtk.Template.Child()

    no_file = Gtk.Template.Child()
    file_view = Gtk.Template.Child()

    toast_overlay = Gtk.Template.Child()
    overlay = Gtk.Template.Child()
    drop_highlight_revealer = Gtk.Template.Child()

    force_close = False

    def __init__(self, application, path=None):
        super().__init__(application=application, title='Eartag')
        if path:
            self.file_view.file_path = path
            self.file_view.load_file()
        self.connect('close-request', self.on_close_request)

        self.drop_target = Gtk.DropTarget(
            actions=Gdk.DragAction.COPY,
            formats=Gdk.ContentFormats.new_for_gtype(Gio.File)
            )
        self.drop_target.connect('accept', self.on_drag_accept)
        self.drop_target.connect('enter', self.on_drag_hover)
        self.drop_target.connect('leave', self.on_drag_unhover)
        self.drop_target.connect('drop', self.on_drag_drop)
        self.add_controller(self.drop_target)

    def on_drag_accept(self, target, drop, *args):
        drop.read_value_async(Gio.File, 0, None, self.verify_file_valid)
        return True

    def verify_file_valid(self, drop, task, *args):
        file = drop.read_value_finish(task)
        path = file.get_path()
        if not is_valid_music_file(path):
            self.drop_target.reject()
            self.on_drag_unhover()

    def on_drag_hover(self, *args):
        self.drop_highlight_revealer.set_reveal_child(True)
        return Gdk.DragAction.COPY

    def on_drag_unhover(self, *args):
        self.drop_highlight_revealer.set_reveal_child(False)

    def on_drag_drop(self, drop_target, value, *args):
        path = value.get_path()
        self.open_file(path)
        self.on_drag_unhover()

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

    def load_file(self, path):
        """
        Loads the file in the file view.

        This function should never be called directly in the UI; use open_file,
        which also checks if any changes won't get discarded.
        """
        self.file_view.file_path = path
        self.file_view.load_file()

    def open_file(self, path):
        """
        Loads the file with the given path. Note that this does not perform
        any validation; caller functions are meant to check for this manually.
        """
        fileview = self.file_view
        if fileview.file and fileview.writable and fileview.file._is_modified:
            self.discard_warning = EartagDiscardWarningDialog(self, path)
            self.discard_warning.show()
            return False
        self.load_file(path)

    def open_file_from_dialog(self, dialog, response):
        """
        Callback for a FileChooser that takes the response and opens the file
        selected in the dialog.
        """
        self.file_chooser.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            file_path = dialog.get_file().get_path()
            return self.open_file(file_path)

    @Gtk.Template.Callback()
    def on_save(self, *args):
        if not self.file_view.save():
            return False

    def on_close_request(self, *args):
        if self.force_close == False and self.file_view.file and \
            self.file_view.file._is_modified:
            self.close_request_dialog = EartagCloseWarningDialog(self)
            self.close_request_dialog.present()
            return True

class AboutDialog(Gtk.AboutDialog):
    def __init__(self, parent):
        Gtk.AboutDialog.__init__(self)
        self.props.program_name = 'Ear Tag'
        self.props.version = "0.1.0"
        self.props.authors = ['knuxify']
        self.props.copyright = '(C) 2022 knuxify'
        self.props.logo_icon_name = 'app.drey.EarTag'
        self.set_transient_for(parent)
