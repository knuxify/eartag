from src.backends.file import EartagFile
import os
import shutil
import filecmp

prop_to_example_string = {
    'title': 'Example Title',
    'artist': 'Example Artist',
    'album': 'Example Album',
    'albumartist': 'Example Album Artist',
    'tracknumber': 1,
    'totaltracknumber': 99,
    'genre': 'Example Genre',
    'releaseyear': 2022,
    'comment': 'Example Comment'
}

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), 'examples')

def run_backend_tests(file_class, extension, skip_channels=False):
    file_read = file_class(os.path.join(EXAMPLES_DIR, f'example.{extension}'))
    backend_read(file_read, skip_channels)

    shutil.copyfile(
        os.path.join(EXAMPLES_DIR, f'example-notags.{extension}'),
        os.path.join(EXAMPLES_DIR, f'_example-notags-fortest.{extension}')
    )
    file_write = file_class(os.path.join(EXAMPLES_DIR, f'_example-notags-fortest.{extension}'))
    backend_write(file_write, skip_channels)
    os.remove(os.path.join(EXAMPLES_DIR, f'_example-notags-fortest.{extension}'))

def backend_read(file, skip_channels=False):
    """Tests common backend read functions."""
    for prop in file.handled_properties:
        try:
            assert file.get_property(prop) == prop_to_example_string[prop]
        except AssertionError:
            raise ValueError(f'Invalid value for property {prop} (expected {type(prop_to_example_string[prop])} {prop_to_example_string[prop]}, got {type(file.get_property(prop))} {file.get_property(prop)})')

    if file._supports_album_covers:
        try:
            assert filecmp.cmp(file.get_property('cover_path'), os.path.join(EXAMPLES_DIR, f'cover.png'))
        except TypeError:
            raise ValueError('Cover art was not found in the provided file')

    assert file.get_property('is_modified') == False
    if not skip_channels: # mutagen-mp4, at least with the m4a file, has some trouble with this step
        assert file.get_property('channels') == 1
    assert file.get_property('length') == 1
    assert file.get_property('bitrate') != 0

def backend_read_empty(file):
    for prop in file.handled_properties:
        try:
            assert not file.get_property(prop) or (isinstance(file.get_property(prop), int) and file.get_property(prop) == -1)
        except AssertionError:
            raise ValueError(f'example-notags file has {prop} property set to {file.get_property(prop)}; this either means that something is broken in the file, or in the backend.')

    assert file.get_property('is_modified') == False
    assert not file.get_property('cover_path')

def backend_write(file, skip_channels=False):
    """Tests common backend write functions."""
    backend_read_empty(file)

    for prop in file.handled_properties:
        file.set_property(prop, prop_to_example_string[prop])

    if file._supports_album_covers:
        file.set_property('cover_path', os.path.join(EXAMPLES_DIR, f'cover.png'))

    assert file.get_property('is_modified') == True

    file.save()

    file_class = type(file)
    backend_read(file_class(file.path), skip_channels)
