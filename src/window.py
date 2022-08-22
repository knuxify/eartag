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
from .file import EartagFileManager
from .sidebar import EartagFileList

from gi.repository import Adw, Gdk, Gio, Gtk, GObject

@Gtk.Template(resource_path='/app/drey/EarTag/ui/discardwarning.ui')
class EartagDiscardWarningDialog(Gtk.MessageDialog):
    __gtype_name__ = 'EartagDiscardWarningDialog'

    def __init__(self, window, paths):
        super().__init__(transient_for=window)
        self.paths = paths
        self.file_manager = window.file_manager

    @Gtk.Template.Callback()
    def on_dbutton_discard(self, *args):
        self.file_manager.load_multiple_files(self.paths, mode=EartagFileManager.LOAD_OVERWRITE)
        self.close()

    @Gtk.Template.Callback()
    def on_dbutton_cancel(self, *args):
        self.close()

    @Gtk.Template.Callback()
    def on_dbutton_save(self, *args):
        if not self.file_manager.save():
            return False
        self.file_manager.load_multiple_files(self.paths, mode=EartagFileManager.LOAD_OVERWRITE)
        self.close()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/closewarning.ui')
class EartagCloseWarningDialog(Gtk.MessageDialog):
    __gtype_name__ = 'EartagCloseWarningDialog'

    def __init__(self, window):
        super().__init__(transient_for=window)
        self.window = window
        self.file_manager = window.file_manager

    @Gtk.Template.Callback()
    def on_button_discard(self, *args):
        self.window.force_close = True
        self.window.close()

    @Gtk.Template.Callback()
    def on_button_cancel(self, *args):
        self.close()

    @Gtk.Template.Callback()
    def on_button_save(self, *args):
        if not self.file_manager.save():
            return False
        self.window.close()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/nofile.ui')
class EartagNoFile(Adw.Bin):
    __gtype_name__ = 'EartagNoFile'

    def __init__(self):
        super().__init__()

    @Gtk.Template.Callback()
    def on_add_file(self, *args):
        window = self.get_native()
        window.open_mode = EartagFileManager.LOAD_OVERWRITE
        window.show_file_chooser()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/window.ui')
class EartagWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'EartagWindow'

    save_button = Gtk.Template.Child()
    window_title = Gtk.Template.Child()
    content_stack = Gtk.Template.Child()
    container_flap = Gtk.Template.Child()
    sidebar_list = Gtk.Template.Child()

    audio_file_filter = Gtk.Template.Child()

    no_file = Gtk.Template.Child()
    file_view = Gtk.Template.Child()

    toast_overlay = Gtk.Template.Child()
    overlay = Gtk.Template.Child()
    drop_highlight_revealer = Gtk.Template.Child()

    force_close = False
    file_chooser = None

    open_mode = EartagFileManager.LOAD_OVERWRITE

    def __init__(self, application, paths=None):
        super().__init__(application=application, title='Ear Tag')

        self.file_manager = EartagFileManager(self)
        self.file_view.set_file_manager(self.file_manager)
        self.sidebar_list.set_file_manager(self.file_manager)
        self.file_manager.bind_property('is_modified', self.save_button, 'sensitive',
                            GObject.BindingFlags.SYNC_CREATE)
        self.file_manager.files.connect('items-changed', self.toggle_fileview)

        if paths:
            self.file_manager.load_multiple_files(paths, mode=EartagFileManager.LOAD_OVERWRITE)

        self.connect('close-request', self.on_close_request)

        self.drop_target = Gtk.DropTarget(
            actions=Gdk.DragAction.COPY,
            formats=Gdk.ContentFormats.new_for_gtype(Gdk.FileList)
            )
        self.drop_target.connect('accept', self.on_drag_accept)
        self.drop_target.connect('enter', self.on_drag_hover)
        self.drop_target.connect('leave', self.on_drag_unhover)
        self.drop_target.connect('drop', self.on_drag_drop)
        self.add_controller(self.drop_target)

    def toggle_fileview(self, *args):
        """
        Shows/hides the fileview/"no files" message depending on opened files.
        """
        if self.file_manager.files.get_n_items() > 0:
            self.content_stack.set_visible_child(self.file_view)
        else:
            self.content_stack.set_visible_child(self.no_file)

    def on_drag_accept(self, target, drop, *args):
        drop.read_value_async(Gdk.FileList, 0, None, self.verify_files_valid)
        return True

    def verify_files_valid(self, drop, task, *args):
        files = drop.read_value_finish(task).get_files()
        for file in files:
            path = file.get_path()
            if not is_valid_music_file(path):
                self.drop_target.reject()
                self.on_drag_unhover()

    def on_drag_hover(self, *args):
        self.drop_highlight_revealer.set_reveal_child(True)
        self.drop_highlight_revealer.set_can_target(True)
        return Gdk.DragAction.COPY

    def on_drag_unhover(self, *args):
        self.drop_highlight_revealer.set_reveal_child(False)
        self.drop_highlight_revealer.set_can_target(False)

    def on_drag_drop(self, drop_target, value, *args):
        files = value.get_files()
        paths = []
        for file in files:
            paths.append(file.get_path())
        self.open_files(paths)
        self.on_drag_unhover()

    def show_file_chooser(self):
        """Shows the file chooser."""
        if self.file_chooser:
            return

        self.file_chooser = Gtk.FileChooserNative(
                                title=_("Open File"),
                                transient_for=self,
                                action=Gtk.FileChooserAction.OPEN,
                                filter=self.audio_file_filter,
                                select_multiple=True
                                )

        self.file_chooser.connect('response', self.open_file_from_dialog)
        self.file_chooser.show()

    def open_files(self, paths):
        """
        Loads the file with the given path. Note that this does not perform
        any validation; caller functions are meant to check for this manually.
        """
        if self.open_mode != EartagFileManager.LOAD_INSERT and self.file_manager._is_modified:
            self.discard_warning = EartagDiscardWarningDialog(self, paths)
            self.discard_warning.show()
            return False

        if len(paths) == 1:
            self.file_manager.load_file(paths[0], mode=self.open_mode)
        else:
            self.file_manager.load_multiple_files(paths, mode=self.open_mode)

    def open_file_from_dialog(self, dialog, response):
        """
        Callback for a FileChooser that takes the response and opens the file
        selected in the dialog.
        """
        self.file_chooser.destroy()
        self.file_chooser = None
        if response == Gtk.ResponseType.ACCEPT:
            paths = []
            for file in list(dialog.get_files()):
                paths.append(file.get_path())
            return self.open_files(paths)

    @Gtk.Template.Callback()
    def show_sidebar(self, *args):
        self.container_flap.set_reveal_flap(True)

    @Gtk.Template.Callback()
    def hide_sidebar(self, *args):
        self.container_flap.set_reveal_flap(False)

    @Gtk.Template.Callback()
    def on_save(self, *args):
        if not self.file_manager.save():
            return False

    @Gtk.Template.Callback()
    def insert_file(self, *args):
        self.open_mode = EartagFileManager.LOAD_INSERT
        self.show_file_chooser()

    def on_close_request(self, *args):
        if self.force_close == False and list(self.file_manager.files) and \
            self.file_manager._is_modified:
            self.close_request_dialog = EartagCloseWarningDialog(self)
            self.close_request_dialog.present()
            return True

class AboutDialog(Gtk.AboutDialog):
    def __init__(self, parent):
        Gtk.AboutDialog.__init__(self)
        self.props.program_name = 'Ear Tag'
        self.props.version = "0.1.1"
        self.props.authors = ['knuxify']
        self.props.artists = ['Igor Dyatlov']
        # TRANSLATORS: Add your name/nickname here
        if _('translator-credits') != 'translator-credits':
            self.props.translators = [_('translator-credits')]
        self.props.copyright = '(C) 2022 knuxify'
        self.props.logo_icon_name = 'app.drey.EarTag'
        self.set_transient_for(parent)
