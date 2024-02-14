from src.utils.guesstags import guess_tags_from_filename

import pytest


def test_empty_filename():
    assert guess_tags_from_filename("", "{tracknumber} - {title}") == {}


def test_match_track_number_and_title():
    tags = guess_tags_from_filename("02 - Pais E Filhos", "{tracknumber} - {title}")
    assert tags == {"tracknumber": "02", "title": "Pais E Filhos"}


def test_tags_with_positions():
    tags = guess_tags_from_filename(
        "02 - Pais E Filhos", "{tracknumber} - {title}", positions=True
    )
    assert tags == {"tracknumber": ("02", (0, 2)), "title": ("Pais E Filhos", (5, 18))}


def test_tag_include_curly_braces():
    assert guess_tags_from_filename(
        "02 - {Pais E Filhos}", "{tracknumber} - {title}"
    ) == {"tracknumber": "02", "title": "{Pais E Filhos}"}


def test_unicode_characters():
    tags = guess_tags_from_filename("02 - Pais E Filhos 👍", "{tracknumber} - {title}")
    assert tags == {"tracknumber": "02", "title": "Pais E Filhos 👍"}


def test_unicode_characters_with_positions():
    tags = guess_tags_from_filename(
        "02 - Pais E Filhos 👍", "{tracknumber} - {title}", positions=True
    )
    assert tags == {
        "tracknumber": ("02", (0, 2)),
        "title": ("Pais E Filhos 👍", (5, 23)),
    }


malformed_placeholder_cases = [
    "",
    "{}",
    "{tracknumber} - {not_existing_placeholder}",
    "{not_existing_placeholder} - {title}",
    "tracknumber}",
    "tracknumber} - {title}",
    "{tracknumber} - title}",
    "{tracknumber",
    "{tracknumber - {title}",
    "{tracknumber} - {title",
    "{tracknumber} - {{title}}",
    "{tracknumber} - {title} - {tracknumber}",
]


@pytest.mark.parametrize("placeholder", malformed_placeholder_cases)
def test_malformed_placeholder(placeholder):
    assert guess_tags_from_filename("02 - Pais E Filhos", placeholder) == {}
