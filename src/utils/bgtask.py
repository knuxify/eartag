# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.repository import GObject, GLib
import time
import traceback
import asyncio

from .._async import event_loop
from typing import Coroutine


class EartagBackgroundTask(GObject.Object):
    """
    Convenience class for creating tasks that run in the background
    without freezing the UI.

    Provides a "progress" property that can be used by target functions
    to signify a progress change. This is a float from 0 to 1 and is
    passed directly to GtkProgressBar.

    The passed target function must be an async function/coroutine.
    """

    def __init__(self, target: Coroutine, *args, **kwargs):
        super().__init__()
        self._progress = 0
        self.target = target
        self.set_args(args, kwargs)
        self.task = None

    def set_args(self, args=None, kwargs=None):
        if args:
            self.args = args
        else:
            self.args = []
        if kwargs:
            self.kwargs = kwargs
        else:
            self.kwargs = {}

    def wait_for_completion(self):
        while self.task and not self.task.done():
            time.sleep(0.25)

    def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()

    def run(self):
        self.task = asyncio.create_task(self.target(*self.args, **self.kwargs))
        self.task.add_done_callback(self.emit_task_done)

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
        if not self.task:
            return False
        return not self.task.done()

    def reset_progress(self):
        self.props.progress = 0

    def set_progress(self, value):
        """
        Wrapper around self.props.progress that updates the progress.
        """
        self.props.progress = value

    def increment_progress(self, value):
        """
        Wrapper around self.props.progress that increments the progress.
        """
        self.props.progress = self.props.progress + value

    def emit_task_done(self, *args):
        """
        Wrapper around self.emit('task-done').
        """
        self.emit("task-done")
