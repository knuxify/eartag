# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from gi.events import GLibEventLoopPolicy

policy = GLibEventLoopPolicy()
event_loop = policy.get_event_loop()
event_loop.set_exception_handler(None)  # set default exception handler
