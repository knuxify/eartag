import pytest
from unittest.mock import patch

from src.utils.validation import is_valid_image_file

EXAMPLES_DIRECTORY = "tests/backends/examples"

cover_png = f"{EXAMPLES_DIRECTORY}/cover.png"


def test_path_not_found():
    assert is_valid_image_file("/eartag/not-found") is False


@pytest.mark.parametrize(
    "file_name",
    ["aconcagua.jpg", "cover.png"],
)
def test_valid_image_file(file_name):
    assert is_valid_image_file(f"{EXAMPLES_DIRECTORY}/{file_name}") is True


@patch("magic.from_file")
def test_magic_fails_to_get_file_type(mock_magic_from_file):
    mock_magic_from_file.return_value = "application/octet-stream"

    assert is_valid_image_file(cover_png) is True


@patch("magic.from_file")
def test_magic_returns_no_file_type(mock_magic_from_file):
    mock_magic_from_file.return_value = False

    assert is_valid_image_file(cover_png) is False


@patch("magic.from_file")
def test_file_type_not_in_valid_mime_types(mock_magic_from_file):
    mock_magic_from_file.return_value = "image/invalid"

    assert is_valid_image_file(cover_png) is False
