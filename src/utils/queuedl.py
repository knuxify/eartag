# SPDX-License-Identifier: MIT
"""
Code for generic queued downloader.
"""

import asyncio
import aiohttp
from aiohttp_retry import RetryClient
from enum import Enum
from tempfile import NamedTemporaryFile
from typing import Union
import time


try:
    from .. import VERSION
except ImportError:  # handle test suite import
    from tests.common import VERSION

    USER_AGENT = (
        f"Ear Tag (Test suite)/{VERSION} (https://gitlab.gnome.org/World/eartag)"
    )
else:
    USER_AGENT = f"Ear Tag/{VERSION} (https://gitlab.gnome.org/World/eartag)"


CHUNK_SIZE = 1024 * 1024  # 1MB


class EartagDownloaderMode(Enum):
    MODE_TEXT = 0
    MODE_JSON = 1
    MODE_FILE = 2


class EartagQueuedDownloader:
    """
    Generic queued downloader. Fetches data from a remote URL and can either
    store it in a cache (for JSON/text data) or save to a tempfile (for files).
    """

    def __init__(
        self,
        mode: EartagDownloaderMode,
        simultaneous_downloads: int = 3,
        throttle: bool = False,
    ):
        """Initializes a queued downloader."""
        self.mode = mode
        # Key - URL, value - data. Value of False is equivalent to an error.
        self.cache = {}
        self.semaphore = asyncio.Semaphore(simultaneous_downloads)
        self.throttle = throttle
        self._last_request = time.time()

    def __del__(self):
        try:
            for val in self.cache.values():
                del val
            del self.cache
        except AttributeError:
            pass

    async def download(self, url: str):
        """Perform a download for the given URL."""
        if url in self.cache:
            # If the URL is cached, just return the data
            return self.get_cached(url)

        async with self.semaphore:
            if self.throttle:
                cur_time = time.time()
                if (cur_time - self._last_request) < 1000:
                    await asyncio.sleep((1000 - (cur_time - self._last_request)) / 1000)

            async with aiohttp.ClientSession() as session:
                async with RetryClient(client_session=session) as retry_session:
                    async with retry_session.get(
                        url, timeout=60, headers={"User-Agent": USER_AGENT}
                    ) as response:
                        if response.status != 200:
                            data = False
                        else:
                            if self.mode == EartagDownloaderMode.MODE_TEXT:
                                data = await response.text()

                            elif self.mode == EartagDownloaderMode.MODE_JSON:
                                try:
                                    data = await response.json()
                                except:
                                    data = False

                            elif self.mode == EartagDownloaderMode.MODE_FILE:
                                tempfile = NamedTemporaryFile()
                                async for chunk in response.content.iter_chunked(
                                    CHUNK_SIZE
                                ):
                                    tempfile.write(chunk)
                                tempfile.flush()
                                data = tempfile

                        self.cache[url] = data

        return data

    def get_cached(self, url: str) -> Union[str, dict, NamedTemporaryFile, bool]:
        """
        Get the value of a cached URL.

        The output value type depends on the selected mode:

        * MODE_TEXT: str
        * MODE_JSON: dict
        * MODE_FILE: NamedTemporaryFile

        If the URL failed to download or was not found on the server,
        False is returned. If the URL is not cached, None is returned.
        """
        return self.cache.get(url, None)
