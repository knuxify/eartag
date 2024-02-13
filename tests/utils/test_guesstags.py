from src.utils.guesstags import guess_tags_from_filename


def test_empty_filename():
    assert guess_tags_from_filename('', '') == {}


def test_empty_placeholder():
    assert guess_tags_from_filename('02 - Pais E Filhos', '') == {}


def test_match_track_number_and_title():
    tags = guess_tags_from_filename('02 - Pais E Filhos', '{tracknumber} - {title}')
    assert tags == {
        'tracknumber': '02',
        'title': 'Pais E Filhos'
    }


def test_tags_with_positions():
    tags = guess_tags_from_filename('02 - Pais E Filhos', '{tracknumber} - {title}', positions=True)
    assert tags == {
        'tracknumber': ('02', (0, 2)),
        'title': ('Pais E Filhos', (5, 18))
    }


def test_placeholder_is_empty_braces():
    assert guess_tags_from_filename('Pais E Filhos', '{}') == {}


def test_non_existent_placeholder():
    assert guess_tags_from_filename('02 - Pais E Filhos', '{tracknumber} - {not_existing_placeholder}') == {}


def test_placeholder_without_opening_brace():
    assert guess_tags_from_filename('02 - Pais E Filhos', 'tracknumber}') == {}


def test_placeholder_without_closing_brace():
    assert guess_tags_from_filename('02 - Pais E Filhos', '{tracknumber') == {}


def test_placeholder_appears_more_than_once():
    assert guess_tags_from_filename('02 - Pais E Filhos - 10', '{tracknumber} - {title} - {tracknumber}') == {}


def test_unicode_characters():
    tags = guess_tags_from_filename('02 - Pais E Filhos 👍', '{tracknumber} - {title}')
    assert tags == {
        'tracknumber': '02',
        'title': 'Pais E Filhos 👍'
    }

def test_unicode_characters_with_positions():
    tags = guess_tags_from_filename('02 - Pais E Filhos 👍', '{tracknumber} - {title}', positions=True)
    assert tags == {
        'tracknumber': ('02', (0, 2)),
        'title': ('Pais E Filhos 👍', (5, 23))
    }

