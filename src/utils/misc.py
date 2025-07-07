# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from itertools import groupby
import re
import unicodedata
import os


def all_equal(iterable):
    """
    Check if all elements in a list are equal. Source:
    https://stackoverflow.com/questions/3844801/check-if-all-elements-in-a-list-are-identical
    """
    g = groupby(iterable)
    return next(g, True) and not next(g, False)


def find_in_model(model, item):
    """
    Gets the position of an item in the model, or -1 if not found.
    Replacement for .find function in models that don't have it.
    """
    i = 0
    while True:
        found = model.get_item(i)
        if not found:
            break
        if found == item:
            return i
        i += 1
    return -1


def is_float(value):
    """Checks if the given value is a valid float."""
    try:
        float(value)
    except ValueError:
        return False
    return True


def get_readable_length(length):
    """Returns human-readable version of the length, given in seconds."""
    length_min, length_sec = divmod(int(length), 60)
    length_hour, length_min = divmod(length_min, 60)

    if length_hour:
        length_readable = "{h}∶{m}∶{s}".format(
            h=str(length_hour).rjust(2, "0"),
            m=str(length_min).rjust(2, "0"),
            s=str(length_sec).rjust(2, "0"),
        )
    else:
        length_readable = "{m}∶{s}".format(
            m=str(length_min).rjust(2, "0"), s=str(length_sec).rjust(2, "0")
        )

    return length_readable


def title_case_preserve_uppercase(text: str):
    return " ".join([x.isupper() and x or x.capitalize() for x in text.split(" ")])


def simplify_string(text: str):
    """
    Returns a "simplified string" that throws away non-alphanumeric
    characters for more accurate searches and comparisons.
    """
    # Step 1: Normalize Unicode characters
    instr = unicodedata.normalize("NFKC", text)
    # Step 2: Only leave lowercase alphanumeric letters
    instr = "".join(
        [letter for letter in instr.lower() if letter.isalnum() or letter == " "]
    ).strip()
    # Step 3: Remove repeating spaces
    instr = re.sub(" +", " ", instr)

    return instr


def simplify_compare(string1: str, string2: str):
    """
    Compares simplified representations of two strings and returns
    whether they're equal.
    """
    return simplify_string(string1) == simplify_string(string2)


def reg_and_simple_cmp(string1: str, string2: str):
    return string1 == string2 or simplify_compare(string1, string2)


def inspect_prettyprint(stack):
    """
    Convenience function that pretty-prints the results of inspect.stack().

    This is not used anywhere in the program; it's only here for debugging
    purposes, since inspect is a pretty useful tool for finding optimization
    issues, and ends up being used quite frequently.
    """
    print("--- Inspect trace: ---")

    for frame in stack:
        print(f"\033[1m{frame.filename}:{frame.lineno}\033[0m")
        print("".join(frame.code_context))  # already includes newlines

    print("--- End trace ---")


# https://stackoverflow.com/questions/1976007/what-characters-are-forbidden-in-windows-and-linux-directory-names#31976060
FILENAME_BANNED_CHARS = ("/", "\\", ":", "*", "?", '"', "<", ">", "|", "\t")
BANNED_FILENAMES = (
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
)


def cleanup_filename(filename: str, allow_path: bool = False, full_path: bool = False) -> str:
    """
    Takes a filename or path and returns a cleaned up version (that is,
    one where invalid characters or tricks like ../ are ignored).
    """
    if full_path:
        allow_path = True

    banned_chars = list(FILENAME_BANNED_CHARS)
    if allow_path and os.path.sep in banned_chars:
        banned_chars.remove(os.path.sep)

    for char in banned_chars:
        filename = filename.replace(char, "_")

    if full_path:
        filename_clean = os.path.sep
    else:
        if filename.startswith(os.path.sep):
            filename = filename[1:]
        filename_clean = ""

    filename_split = filename.split(os.path.sep)
    for i in range(len(filename_split)):
        # Strip out leading/trailing spaces
        f = filename_split[i].strip()

        if f == "":
            continue

        # Fix too long filenames; 255 is a common limit, we leave some
        # space for safety
        if len(f) > 249:
            if i == (len(filename_split) - 1):
                # If we're dealing with a filename, keep the extension
                f, ext = os.path.splitext(f)
                f = f[(-249 + len(ext) - 1) :] + ext
            else:
                f = f[-249:]

        # Misc. cleanup steps
        if f in BANNED_FILENAMES:
            filename_clean += f"_{f}"
        elif f == "..":
            filename_clean += "__"
        elif f.endswith("."):
            filename_clean += f[:-1] + "_"
        else:
            filename_clean += f
        filename_clean += os.path.sep
    filename_clean = filename_clean[:-1]

    return filename_clean


def filename_valid(filename: str, allow_path: bool = False, full_path: bool = False) -> bool:
    """Returns whether or not a filename is valid."""
    if filename != os.path.normpath(filename):
        return False

    banned_chars = list(FILENAME_BANNED_CHARS)
    if allow_path and os.path.sep in banned_chars:
        banned_chars.remove(os.path.sep)

    if not full_path and filename.startswith(os.path.sep):
        return False

    for char in banned_chars:
        if char in filename:
            return False

    for f in filename.split(os.path.sep):
        if f in BANNED_FILENAMES + ("..",) or f.endswith(".") or f != f.strip() or len(f) > 255:
            return False

    return True


def file_is_sandboxed(path: str) -> bool:
    """
    Takes a path and returns whether or not the file is sandboxed.

    This is a best-guess based on the path, and has only really been tested
    to work under Flatpak.
    """
    return bool(re.match("^/run/user/[0-9].*/doc", path))


def natural_compare(a: str, b: str) -> int:
    """
    Compares two strings using the "natural/human sorting" algorithm.

    This returns an integer, satisfying similar constraints to GLib's collate
    functions: 0 if both strings are the same, 1 if a > b, and -1 if a < b.
    """
    # Adapted from https://stackoverflow.com/a/8940266
    convert = lambda text: int(text) if text.isdigit() else text.lower()  # noqa: E731
    alphanum_key = lambda key: [convert(c) for c in re.split("([0-9]+)", key)]  # noqa: E731
    sort = sorted([a, b], key=alphanum_key)

    if sort[0] == sort[1]:
        return 0
    if sort[0] is a:
        return -1
    return 1


def safe_int(value: int | str | None) -> int | None:
    """Wrapper around int() that handles invalid values gracefully."""
    if isinstance(value, int):
        return value
    elif isinstance(value, str):
        value = value.strip()
    elif not value:
        return 0

    try:
        return int(value)
    except ValueError:
        return 0


def safe_float(value: int | float | str | None) -> float | None:
    """Wrapper around int() that handles invalid values gracefully."""
    if isinstance(value, float):
        return value
    elif isinstance(value, str):
        value = value.strip()
    elif not value:
        return 0.0

    try:
        return float(value)
    except ValueError:
        return 0.0


def iter_selection_model(model, position: int = -1, n_items: int = -1):
    """Iterate over the selected items in a selection model."""
    if (position >= 0 and n_items < 0) or (n_items >= 0 and position < 0):
        raise ValueError("Both position and n_items must be set")

    if position >= 0 and n_items >= 0:
        selection = model.get_selection_range(position, n_items)
    else:
        selection = model.get_selection()
    for i in range(selection.get_size()):
        pos = selection.get_nth(i)
        yield model.get_item(pos)
