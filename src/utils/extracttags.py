# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from ..backends.file import VALID_TAGS

import os.path
import re

EXTRACTABLE_TAGS = VALID_TAGS + ("length", "bitrate")


def extract_tags_from_filename(
    filename: str, placeholder: str, positions: bool = False, strip_common_suffixes: bool = False
) -> dict:
    """
    Takes a filename and a placeholder string and splits the filename
    up into a dict containing tag data.
    """
    filename = os.path.splitext(os.path.basename(filename))[0]

    # Step 0. Strip common suffixes.
    if strip_common_suffixes:
        # Modern yt-dlp: square brackets with ID inside
        # (could be YouTube ID, or longer for e.g. SoundCloud,
        # so we don't limit it)
        if filename.endswith("]"):
            try:
                filename_stripped = re.match(r"(.*?) \[(.*)\]", filename).group(1)
                assert filename_stripped
            except (AssertionError, AttributeError, IndexError):
                pass
            else:
                filename = filename_stripped

        # Old youtube-dl: "-" and then YouTube ID. To minimize
        # the likelihood for misdetections, we only check for
        # YouTube IDs that have numbers or special characters
        # in them.
        try:
            if re.match(r"-([A-Za-z0-9_\-]{11})", filename[-12:]) and re.search(
                r"[0-9_\-]", filename[-11:]
            ):
                filename = filename[:-12]
        except IndexError:
            pass

    # Step 1. Split placeholder string into static strings and placeholders.
    placeholder_split = [x for x in re.split("({.*?})", placeholder) if x]

    tags = []

    # Step 2. Generate regex rule from the placeholders. This replaces every
    # valid placeholder found with a Regex capture group.
    pattern = "^"
    for element in placeholder_split:
        if element.startswith("{") and element.endswith("}"):
            tag = element[1:-1]
            if tag in EXTRACTABLE_TAGS and tag not in tags:
                pattern += f"(?P<{tag}>.*?)"
                tags.append(tag)
                continue
        pattern += re.escape(element)
    pattern += "$"

    # Pango attributes (used for syntax highlighting) use offsets calculated
    # in bytes, not Python characters, so we encode the pattern and filename
    # to UTF-8 so that the returned group positions match the byte count.
    pattern = pattern.encode("utf-8")
    filename = filename.encode("utf-8")

    match = re.match(pattern, filename)

    if not match:
        return {}

    out = {}

    for tag in tags:
        tag_matched = match.group(tag)
        if tag_matched:
            tag_value = tag_matched.decode("utf-8")
            if positions:
                out[tag] = (tag_value, match.span(tag))
            else:
                out[tag] = tag_value

    return out
