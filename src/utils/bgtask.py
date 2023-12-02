# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import GObject, GLib
import threading
import time


class EartagBackgroundTask(GObject.Object):
    """
    Convenience class for creating tasks that run in the background
    without freezing the UI.

    Provides a "progress" property that can be used by target functions
    to signify a progress change. This is a float from 0 to 1 and is
    passed directly to GtkProgressBar.

    Also provides an optional "halt" property; target functions can
    check for this property to stop an operation early.

    Remember to pass all code that interacts with GTK through
    GLib.idle_add().
    """

    def __init__(self, target, *args, **kwargs):
        super().__init__()
        self._progress = 0
        self.target = target
        self.reset(args, kwargs)

    def wait_for_completion(self):
        while self.thread.is_alive():
            time.sleep(0.25)

    def stop(self):
        self.halt = True
        self.wait_for_completion()
        self.halt = False

    def run(self):
        self.thread.start()

    def reset(self, args=[], kwargs=[]):
        """Re-creates the inner thread with new args and kwargs."""
        self._is_done = False
        self.thread = None
        self.halt = False
        self.failed = False
        if args and kwargs:
            self.thread = threading.Thread(
                target=self.target, daemon=True, args=args, kwargs=kwargs
            )
        elif args:
            self.thread = threading.Thread(target=self.target, daemon=True, args=args)
        elif kwargs:
            self.thread = threading.Thread(
                target=self.target, daemon=True, kwargs=kwargs
            )
        else:
            self.thread = threading.Thread(target=self.target, daemon=True)

    @GObject.Property(type=float, minimum=0, maximum=1)
    def progress(self):
        """
        Float from 0 to 1 signifying the current progress of the operation.
        When the task is done, this automatically resets to 0.

        This value is set by the target function.
        """
        return self._progress

    @progress.setter
    def progress(self, value):
        self._progress = value

    @GObject.Signal
    def task_done(self):
        self.reset_progress()
        self._is_done = True

    @GObject.Property(type=bool, default=False)
    def is_running(self):
        if not self.thread:
            return False
        return self.thread.is_alive()

    def reset_progress(self):
        self.props.progress = 0

    def set_progress_threadsafe(self, value):
        """
        Wrapper around self.props.progress that updates the progress, wrapped
        around GLib.idle_add. This is the preferred way for users to set the
        progress variable.
        """
        GLib.idle_add(self.set_property, "progress", value)

    def increment_progress(self, value):
        """
        Wrapper around self.props.progress that increments the progress, wrapped
        around GLib.idle_add. This is the preferred way for users to increment the
        progress variable.
        """
        self.set_progress_threadsafe(self.props.progress + value)

    def emit_task_done(self):
        """
        Wrapper around self.emit('task-done') that is wrapped around
        GLib.idle_add. This is the preferred way for users to emit the
        task-done signal.
        """
        GLib.idle_add(self.emit, "task-done")
