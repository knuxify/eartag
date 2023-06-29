# main.py
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

import sys
import gi
import os.path

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk, Gio

from .common import is_valid_music_file
from .window import EartagWindow
from .filemanager import EartagFileManager

class Application(Adw.Application):
    def __init__(self, version='dev'):
        super().__init__(application_id='app.drey.EarTag',
                         resource_base_path='/app/drey/EarTag',
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.version = version
        self.paths = []
        self.connect('open', self.on_open)

        self.config = Gio.Settings.new('app.drey.EarTag')

    def on_open(self, window, files, *args):
        for file in files:
            path = file.get_path()
            if path:
                if not os.path.exists(path):
                    continue
                if os.path.isdir(path):
                    for _file in os.listdir(path):
                        _fpath = os.path.join(path, _file)
                        if os.path.isfile(_fpath) and is_valid_music_file(_fpath):
                            self.paths.append(_fpath)
                    continue
                elif not is_valid_music_file(path):
                    continue
                self.paths.append(path)
        self.do_activate()

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = EartagWindow(application=self, paths=self.paths)
        self.create_action('about', self.on_about_action, None)

        self.create_action('open_file', self.on_open_file_action, '<Ctrl>o')
        self.create_action('save', self.on_save_action, '<Ctrl>s')
        self.create_action('open_folder', self.on_open_folder_action, '<Ctrl>d')

        self.create_action('next_file', self.on_next_action, '<Alt>Right')
        self.create_action('previous_file', self.on_previous_action, '<Alt>Left')
        self.create_action('close_selected', self.on_close_selected_action, '<Ctrl>w')
        self.create_action('select_all', self.on_select_all_action, '<Ctrl><Shift>a')

        self.create_action('toggle_sidebar', self.on_toggle_sidebar_action, 'F9')
        self.create_action('open_menu', self.on_open_menu_action, 'F10')

        self.save_cover_action = \
            self.create_action('save_cover', self.on_save_cover_action, None)
        self.save_cover_action.set_enabled(False)

        self.rename_action = \
            self.create_action('rename', self.on_rename_action, None)
        self.rename_action.set_enabled(False)

        self.identify_action = \
            self.create_action('identify', self.on_identify_action, None)
        self.identify_action.set_enabled(False)

        self.create_action('quit', self.on_quit_action, '<Ctrl>q')

        win.present()
        self._ = _

    def create_action(self, name, callback, accel=None):
        """ Add an Action and connect to a callback """
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if accel:
            self.set_accels_for_action(f'app.{name}', (accel, None))
        return action

    def on_save_action(self, widget, _):
        self.get_active_window().file_manager.save()

    def on_save_cover_action(self, widget, _):
        self.get_active_window().save_cover()

    def on_rename_action(self, widget, _):
        self.get_active_window().show_rename_dialog()

    def on_identify_action(self, widget, _):
        self.get_active_window().show_acoustid_dialog()

    def on_about_action(self, widget, _):
        about = Adw.AboutWindow(
            application_name="Ear Tag",
            application_icon="app.drey.EarTag",
            developers=["knuxify"],
            artists=["Jakub Steiner", "Igor Dyatlov"],
            license_type=Gtk.License.MIT_X11,
            issue_url="https://gitlab.gnome.org/World/eartag/-/issues",
            version=self.version,
            website="https://gitlab.gnome.org/World/eartag"
        )

        if self._('translator-credits') != 'translator-credits':
            # TRANSLATORS: Add your name/nickname here
            about.props.translator_credits = self._('translator-credits')

        lib_versions = []

        lib_versions.append(f"gtk4: {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}") # noqa: E501
        lib_versions.append(f"libadwaita: {Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}") # noqa: E501

        import magic
        try:
            lib_versions.append(f"libmagic: {magic.version()}")
        except NotImplementedError:
            lib_versions.append("libmagic: version data N/A")
        import mutagen
        lib_versions.append(f"mutagen: {mutagen.version_string}")
        import PIL
        lib_versions.append(f"pillow: {PIL.__version__}")

        lib_version_str = '\n - '.join(lib_versions)

        opened_file_list = []
        for file in self.props.active_window.file_manager.files:
            opened_file_list.append(f'{os.path.split(file.path)[-1]}, {magic.from_file(file.path, mime=True)}, {file.__gtype_name__}') # noqa: E501

        opened_file_list_str = '\n - '.join(opened_file_list) or 'None'

        about.set_debug_info(f'''Ear Tag {self.version}

Running in Flatpak: {os.path.exists('/.flatpak-info') and 'YES' or 'NO'}

Dependency versions:
 - {lib_version_str}

Opened files:
 - {opened_file_list_str}''')

        about.set_modal(True)
        about.set_transient_for(self.props.active_window)

        about.present()

    def on_open_file_action(self, widget, _):
        window = self.get_active_window()
        window.open_mode = EartagFileManager.LOAD_OVERWRITE
        window.show_file_chooser()

    def on_open_folder_action(self, widget, _):
        window = self.get_active_window()
        window.open_mode = EartagFileManager.LOAD_OVERWRITE
        window.show_file_chooser(folders=True)

    def on_next_action(self, *args):
        win = self.props.active_window
        win.sidebar.select_next()

    def on_previous_action(self, *args):
        win = self.props.active_window
        win.sidebar.select_previous()

    def on_close_selected_action(self, *args):
        win = self.props.active_window
        if win.file_manager.files:
            win.sidebar.remove_selected()
        else:
            win.close()

    def on_select_all_action(self, *args):
        win = self.props.active_window
        if win.container_stack.get_visible_child() != win.container_flap:
            return
        if win.sidebar.file_list.all_selected():
            win.select_multiple_button.set_active(False)
            win.sidebar.file_list.unselect_all()
            win.file_manager.emit('select-first')
        else:
            win.select_multiple_button.set_active(True)
            win.sidebar.file_list.select_all()

    def on_toggle_sidebar_action(self, *args):
        win = self.props.active_window
        if win.container_flap.get_folded():
            if win.container_flap.get_reveal_flap():
                win.hide_sidebar()
            else:
                win.show_sidebar()
        else:
            win.sidebar.file_list.grab_focus()

    def on_open_menu_action(self, *args):
        win = self.props.active_window
        if win.container_stack.get_visible_child() == win.container_flap:
            win.primary_menu_button.activate()
        else:
            win.empty_primary_menu_button.activate()

    def on_quit_action(self, *args):
        win = self.props.active_window
        win.close()

def main(version):
    app = Application(version)
    return app.run(sys.argv)
