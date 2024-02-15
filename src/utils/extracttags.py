# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from ..backends.file import BASIC_TAGS, EXTRA_TAGS

import re

VALID_TAGS = BASIC_TAGS + EXTRA_TAGS + ("length", "bitrate")


def extract_tags_from_filename(
    filename: str, placeholder: str, positions: bool = False
) -> dict:
    """
    Takes a filename and a placeholder string and splits the filename
    up into a dict containing tag data.
    """
    # Step 1. Split placeholder string into static strings and placeholders.
    placeholder_split = [x for x in re.split("({.*?})", placeholder) if x]

    tags = []

    # Step 2. Generate regex rule from the placeholders. This replaces every
    # valid placeholder found with a Regex capture group.
    pattern = "^"
    for element in placeholder_split:
        if element.startswith("{") and element.endswith("}"):
            tag = element[1:-1]
            if tag in VALID_TAGS and tag not in tags:
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
