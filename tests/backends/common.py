from src.backends.file import EartagFile
import os
import shutil

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

def run_backend_tests(file_class, extension):
    examples_dir = os.path.join(os.path.dirname(__file__), 'examples')
    file_read = file_class(os.path.join(examples_dir, f'example.{extension}'))
    backend_read(file_read)

    shutil.copyfile(
        os.path.join(examples_dir, f'example-notags.{extension}'),
        os.path.join(examples_dir, f'_example-notags-fortest.{extension}')
    )
    file_write = file_class(os.path.join(examples_dir, f'_example-notags-fortest.{extension}'))
    backend_write(file_write)
    os.remove(os.path.join(examples_dir, f'_example-notags-fortest.{extension}'))

def backend_read(file):
    """Tests common backend read functions."""
    for prop in EartagFile.handled_properties:
        try:
            assert file.get_property(prop) == prop_to_example_string[prop]
        except AssertionError:
            raise ValueError(f'Invalid value for property {prop} (expected {type(prop_to_example_string[prop])} {prop_to_example_string[prop]}, got {type(file.get_property(prop))} {file.get_property(prop)})')

    assert file.get_property('is_modified') == False
    assert file.get_property('channels') == 1
    assert file.get_property('length') == 1
    # There's no exact way for us to know the bitrate, it differs between
    # each file...

def backend_write(file):
    """Tests common backend write functions."""
    for prop in EartagFile.handled_properties:
        assert file.get_property(prop) != prop_to_example_string[prop]

    for prop in EartagFile.handled_properties:
        file.set_property(prop, prop_to_example_string[prop])

    file.save()

    file_class = type(file)
    backend_read(file_class(file.path))
