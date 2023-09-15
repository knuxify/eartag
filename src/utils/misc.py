# SPDX-License-Identifier: MIT
# (c) 2023 knuxify and Ear Tag contributors

from itertools import groupby
import re
import unicodedata

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
        length_readable = '{h}∶{m}∶{s}'.format(
            h=str(length_hour).rjust(2, '0'),
            m=str(length_min).rjust(2, '0'),
            s=str(length_sec).rjust(2, '0')
        )
    else:
        length_readable = '{m}∶{s}'.format(
            m=str(length_min).rjust(2, '0'),
            s=str(length_sec).rjust(2, '0')
        )

    return length_readable

def title_case_preserve_uppercase(text: str):
    return ' '.join([
        x.isupper() and x or x.capitalize()
        for x in text.split(' ')
    ])

def simplify_string(text: str):
    """
    Returns a "simplified string" that throws away non-alphanumeric
    characters for more accurate searches and comparisons.
    """
    # Step 1: Normalize Unicode characters
    instr = unicodedata.normalize('NFKC', text)
    # Step 2: Only leave lowercase alphanumeric letters
    instr = ''.join([
        l for l in instr.lower() if l.isalnum() or l == ' '
    ]).strip()
    # Step 3: Remove repeating spaces
    instr = re.sub(' +', ' ', instr)

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
        print(f'\033[1m{frame.filename}:{frame.lineno}\033[0m')
        print(''.join(frame.code_context)) # already includes newlines

    print("--- End trace ---")
