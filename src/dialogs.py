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

from gi.repository import Adw, Gtk, GLib

@Gtk.Template(resource_path='/app/drey/EarTag/ui/dialogs/closewarning.ui')
class EartagCloseWarningDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagCloseWarningDialog'

    def __init__(self, window):
        super().__init__(modal=True, transient_for=window)
        self.window = window
        self.file_manager = window.file_manager

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == 'discard':
            self.window.force_close = True
            self.window.close()
        elif response == 'save':
            if not self.file_manager.save():
                return False
            self.window.close()
        self.close()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/dialogs/discardwarning.ui')
class EartagDiscardWarningDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagDiscardWarningDialog'

    def __init__(self, window, paths):
        super().__init__(modal=True, transient_for=window)
        self.paths = paths
        self.file_manager = window.file_manager

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == 'save':
            if not self.file_manager.save():
                return False
        if response != 'cancel':
            self.file_manager.load_files(
                self.paths,
                mode=self.file_manager.LOAD_OVERWRITE
            )
        self.close()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/dialogs/removaldiscardwarning.ui')
class EartagRemovalDiscardWarningDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagRemovalDiscardWarningDialog'

    def __init__(self, file_manager, file):
        super().__init__(modal=True, transient_for=file_manager.window)
        self.file_manager = file_manager
        self.file = file

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        if response == 'save':
            if not self.file_manager.save():
                return False
        if response != 'cancel':
            self.file_manager.remove(self.file, force_discard=True)
        self.file = None
        self.close()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/dialogs/loadingfailure.ui')
class EartagLoadingFailureDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagLoadingFailureDialog'

    def __init__(self, window, filename):
        super().__init__(modal=True, transient_for=window)
        self.set_body(self.get_body().format(f=filename))

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        self.close()

@Gtk.Template(resource_path='/app/drey/EarTag/ui/dialogs/renamefailure.ui')
class EartagRenameFailureDialog(Adw.MessageDialog):
    __gtype_name__ = 'EartagRenameFailureDialog'

    def __init__(self, window, filename):
        super().__init__(modal=True, transient_for=window)
        self.set_body(self.get_body().format(f=filename))

    @Gtk.Template.Callback()
    def handle_response(self, dialog, response):
        self.close()
