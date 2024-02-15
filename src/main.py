# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

import sys
import gi
import os.path

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Adw, Gtk, Gio

from . import APP_ID, APP_GRESOURCE_PATH
from .utils.validation import is_valid_music_file
from .window import EartagWindow
from .filemanager import EartagFileManager


class Application(Adw.Application):
    def __init__(self, version="dev", devel=False):
        super().__init__(
            application_id=APP_ID,
            resource_base_path=APP_GRESOURCE_PATH,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.version = version
        self.devel = devel
        self.paths = []
        self.connect("open", self.on_open)

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
            win = EartagWindow(application=self, paths=self.paths, devel=self.devel)
        self.create_action("settings", self.on_settings_action, None)
        self.create_action("about", self.on_about_action, None)

        self.create_action("open_file", self.on_open_file_action, "<Ctrl>o")
        self.create_action("save", self.on_save_action, "<Ctrl>s")
        self.create_action("open_folder", self.on_open_folder_action, "<Ctrl>d")

        self.create_action("next_file", self.on_next_action, "<Alt>Right")
        self.create_action("previous_file", self.on_previous_action, "<Alt>Left")
        self.create_action("close_selected", self.on_close_selected_action, "<Ctrl>w")
        self.create_action("select_all", self.on_select_all_action, "<Ctrl><Shift>a")

        self.create_action("toggle_sidebar", self.on_toggle_sidebar_action, "F9")
        self.create_action("open_menu", self.on_open_menu_action, "F10")

        self.rename_action = self.create_action("rename", self.on_rename_action, None)
        self.rename_action.set_enabled(False)

        self.extract_action = self.create_action(
            "extract", self.on_extract_action, None
        )
        self.extract_action.set_enabled(False)

        self.identify_action = self.create_action(
            "identify", self.on_identify_action, None
        )
        self.identify_action.set_enabled(False)

        self.undo_all_action = self.create_action(
            "undo_all", self.on_undo_all_action, None
        )
        self.undo_all_action.set_enabled(False)

        self.delete_all_tags_action = self.create_action(
            "delete_all_tags", self.on_delete_all_tags_action, None
        )
        self.delete_all_tags_action.set_enabled(False)

        self.create_action("quit", self.on_quit_action, "<Ctrl>q")

        win.present()
        self._ = _

    def create_action(self, name, callback, accel=None):
        """Add an Action and connect to a callback"""
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if accel:
            self.set_accels_for_action(f"app.{name}", (accel, None))
        return action

    def on_save_action(self, widget, _):
        self.get_active_window().file_manager.save()

    def on_rename_action(self, widget, _):
        self.get_active_window().show_rename_dialog()

    def on_identify_action(self, widget, _):
        self.get_active_window().show_identify_dialog()

    def on_settings_action(self, widget, _):
        self.get_active_window().show_settings_dialog()

    def on_extract_action(self, widget, _):
        self.get_active_window().show_extract_dialog()

    def on_undo_all_action(self, widget, _):
        self.get_active_window().undo_all()

    def on_delete_all_tags_action(self, widget, _):
        self.get_active_window().show_delete_all_tags_dialog()

    def on_about_action(self, widget, _):
        version_str = self.version
        if self.devel:
            version_str += " (dev)"

        about = Adw.AboutWindow(
            application_name=self._("Ear Tag"),
            application_icon=APP_ID,
            developers=["knuxify"],
            artists=["Jakub Steiner", "Igor Dyatlov"],
            license_type=Gtk.License.MIT_X11,
            issue_url="https://gitlab.gnome.org/World/eartag/-/issues",
            version=version_str,
            website="https://gitlab.gnome.org/World/eartag",
        )

        if self._("translator-credits") != "translator-credits":
            # TRANSLATORS: Add your name/nickname here
            about.props.translator_credits = self._("translator-credits")

        lib_versions = []

        lib_versions.append(
            f"gtk4: {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"  # noqa: E501
        )
        lib_versions.append(
            f"libadwaita: {Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}"  # noqa: E501
        )

        import magic

        try:
            lib_versions.append(f"libmagic: {magic.version()}")
        except NotImplementedError:
            lib_versions.append("libmagic: version data N/A")
        import mutagen

        lib_versions.append(f"mutagen: {mutagen.version_string}")
        import PIL

        lib_versions.append(f"pillow: {PIL.__version__}")

        lib_version_str = "\n - ".join(lib_versions)

        opened_file_list = []
        for file in self.props.active_window.file_manager.files:
            opened_file_list.append(
                f"{file.path}, {magic.from_file(file.path, mime=True)}, {file.__gtype_name__}"
            )  # noqa: E501

        opened_file_list_str = "\n - ".join(opened_file_list) or "None"

        about.set_debug_info(
            f"""Ear Tag {self.version}{' (Development version)' if self.devel else ''}

Running in Flatpak: {os.path.exists('/.flatpak-info') and 'YES' or 'NO'}

Dependency versions:
 - {lib_version_str}

Opened files:
 - {opened_file_list_str}"""
        )

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
        win.select_next()

    def on_previous_action(self, *args):
        win = self.props.active_window
        win.select_previous()

    def on_close_selected_action(self, *args):
        win = self.props.active_window
        if win.file_manager.files:
            win.remove_selected()
        else:
            win.close()

    def on_select_all_action(self, *args):
        win = self.props.active_window
        if win.container_stack.get_visible_child() != win.split_view:
            return
        if win.file_manager.all_selected():
            if win.file_manager.files.get_n_items() == 1:
                if not win.select_multiple_button.get_active():
                    win.select_multiple_button.set_active(True)
                    return
            win.select_multiple_button.set_active(False)
            win.file_manager.unselect_all()
            win.file_manager.emit("select-first")
        else:
            win.select_multiple_button.set_active(True)
            win.file_manager.select_all()

    def on_toggle_sidebar_action(self, *args):
        win = self.props.active_window
        if win.split_view.get_collapsed():
            if win.split_view.get_show_sidebar():
                win.hide_sidebar()
            else:
                win.show_sidebar()
        else:
            win.sidebar_file_list.grab_focus()

    def on_open_menu_action(self, *args):
        win = self.props.active_window
        if win.container_stack.get_visible_child() == win.split_view:
            win.primary_menu_button.activate()
        else:
            win.empty_primary_menu_button.activate()

    def on_quit_action(self, *args):
        win = self.props.active_window
        win.close()


def main(version, devel):
    app = Application(version, devel)
    return app.run(sys.argv)
