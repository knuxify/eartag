import os
import shutil
import filecmp

# Boilerplate for handling example files

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), 'examples')

# Example files dict, for use with get_test_file (type: filename without extension)
EXAMPLES = {
    "alltags": "example",
    "notags": "example-notags"
    }

class TestFile:
    """Class for generating test files. Use with the "with" keyword."""

    def __init__(self, test_name, extension, example_type, remove=True):
        if example_type not in EXAMPLES:
            raise ValueError(f"Incorrect type {example_type} for get_test_file")
        example = EXAMPLES[example_type]

        source_path = os.path.join(EXAMPLES_DIR, f'{example}.{extension}')
        target_path = os.path.join(EXAMPLES_DIR, f'_{test_name}_{example}.{extension}')
        shutil.copyfile(source_path, target_path)

        self.path = target_path
        self.remove = remove

    def __enter__(self):
        return self.path

    def __exit__(self, type, value, tb):
        if tb:
            return None
        if self.remove:
            os.remove(self.path)

# Example values

prop_to_example_string = {
    'title': 'Example Title',
    'artist': 'Example Artist',
    'album': 'Example Album',
    'albumartist': 'Example Album Artist',
    'tracknumber': 1,
    'totaltracknumber': 99,
    'genre': 'Example Genre',
    'releasedate': '2022',
    'comment': 'Example Comment',

    'bpm': 160,
    'compilation': 'Example Compilation',
    'composer': 'Example Composer',
    'copyright': 'Example Copyright',
    'encodedby': 'Example Encoded by',
    'mood': 'Example Mood',
    'conductor': 'Example Conductor',
    'arranger': 'Example Arranger',
    'discnumber': 1,
    'publisher': 'Example Publisher',
    'isrc': 'Example-ISRC',
    'language': 'Example Language',
    'discsubtitle': 'Example Disc Subtitle',
    'url': 'https://example.com',

    'albumartistsort': 'Example Album Artist (sort)',
    'albumsort': 'Example Album (sort)',
    'composersort': 'Example Composer (sort)',
    'artistsort': 'Example Artist (sort)',
    'titlesort': 'Example Title (sort)'
}

# Actual test functions will follow

def run_backend_tests(file_class, extension, skip_channels=False):
    # Simple read test
    file_read = file_class(os.path.join(EXAMPLES_DIR, f'example.{extension}'))
    backend_read(file_read, skip_channels)

    # Simple write test
    with TestFile('test_write', extension, 'notags') as file_write:
        backend_write(file_class(file_write), skip_channels)

    # One-by-one write test
    with TestFile('test_write_individual', extension, 'notags') as file_write_individual:
        backend_write_individual(file_class(file_write_individual), skip_channels)

    # Tag deletion test
    with TestFile('test_delete', extension, 'alltags') as file_delete:
        backend_delete(file_class(file_delete))

    # Make sure tags are deleted when set to empty values
    with TestFile('test_write_empty', extension, 'alltags') as file_write_empty:
        backend_write_empty(file_class(file_write_empty), skip_channels)

    # File rename test; do this twice: once for no tags, once for all tags
    with TestFile('test_rename', extension, 'notags', remove=False) as file_rename:
        backend_rename(file_class(file_rename))
    with TestFile('test_rename', extension, 'alltags', remove=False) as file_rename:
        backend_rename(file_class(file_rename))

    # Test full-length release date and validation
    if file_class._supports_full_dates:
        with TestFile('test_full_releasedate', extension, 'alltags') as file_full_releasedate:
            backend_full_releasedate(file_class(file_full_releasedate))

def backend_read(file, skip_channels=False):
    """Tests common backend read functions."""
    for prop in file.handled_properties + file.supported_extra_tags:
        assert file.get_property(prop) == prop_to_example_string[prop], f'Invalid value for property {prop} (expected {type(prop_to_example_string[prop])} {prop_to_example_string[prop]}, got {type(file.get_property(prop))} {file.get_property(prop)})'

        assert file.has_tag(prop), f'tag {prop} not found in file'

    if file._supports_album_covers:
        try:
            assert file.get_property('front_cover_path'), 'cover art not found in file'
            assert filecmp.cmp(file.get_property('front_cover_path'), os.path.join(EXAMPLES_DIR, f'cover.png'), shallow=False), 'cover art not found in file'
        except TypeError:
            raise ValueError('cover art not found in file')

    assert file.get_property('is_modified') == False
    if not skip_channels: # mutagen-mp4, at least with the m4a file, has some trouble with this step
        assert file.get_property('channels') == 1
    assert file.get_property('length') == 1
    assert file.get_property('bitrate') != 0

def backend_read_empty(file, skip_cover=False):
    for prop in file.handled_properties + file.supported_extra_tags:
        try:
            assert not file.get_property(prop)
            assert not file.has_tag(prop)
        except AssertionError:
            raise ValueError(f'example-notags file has {prop} property set to {file.get_property(prop)}; this either means that something is broken in the file, or in the backend.')

    assert file.get_property('is_modified') == False
    if not skip_cover:
        if file.get_property('front_cover_path'):
            shutil.copyfile(file.get_property('front_cover_path'), file.path + '.png')
        assert not file.get_property('front_cover_path'), file.get_property('front_cover_path')

def backend_write(file, skip_channels=False):
    """Tests common backend write functions."""
    backend_read_empty(file)

    for prop in file.handled_properties + file.supported_extra_tags:
        file.set_property(prop, prop_to_example_string[prop])
        assert file.is_modified
        assert prop in file.modified_tags
        assert file.has_tag(prop), f'tag {prop} not found in file'

    if file._supports_album_covers:
        file.set_property('front_cover_path', os.path.join(EXAMPLES_DIR, f'cover.png'))
        assert file.get_property('front_cover_path')

    assert file.get_property('is_modified') == True
    props_set = set(tuple(file.handled_properties) + tuple(file.supported_extra_tags))
    if file._supports_album_covers:
        props_set.add('front_cover_path')
    assert set(file.modified_tags) == props_set

    file.save()

    assert file.get_property('is_modified') == False
    assert not file.modified_tags

    file_class = type(file)
    backend_read(file_class(file.path), skip_channels)

def backend_write_individual(empty_file, skip_channels=False):
    """Tests common backend write functions by writing each property separately."""
    backend_read_empty(empty_file)
    empty_file_path = empty_file.path
    file_class = type(empty_file)
    extension = os.path.splitext(empty_file_path)[1]

    for prop in empty_file.handled_properties:
        new_file_path = os.path.join(EXAMPLES_DIR, f'_example-notags-{prop}.{extension}')
        shutil.copyfile(
            empty_file_path,
            new_file_path
        )
        target_value = prop_to_example_string[prop]
        file = file_class(new_file_path)
        file.set_property(prop, target_value)

        assert file.has_tag(prop), f'tag {prop} not found in file'

        file.save()

        file_read = file_class(new_file_path)
        assert file_read.get_property(prop) == target_value
        for _prop in empty_file.handled_properties:
            if _prop != prop and prop != 'totaltracknumber':
                assert not file.has_tag(_prop), f"file erroneously has tag {prop}"

        os.remove(new_file_path)

def backend_write_empty(file, skip_channels=False):
    """Tests whether writing empty values removes the tag from the file."""
    for prop in file.handled_properties + file.supported_extra_tags:
        # tracknumber/totaltracknumber have separate handling as they're stored
        # as a single value in pretty much every file format. skip them for now
        if prop in ('tracknumber', 'totaltracknumber'):
            continue
        if prop in file.int_properties or prop in file.float_properties:
            file.set_property(prop, 0)
        else:
            file.set_property(prop, '')
        assert not file.has_tag(prop), f'cleared tag {prop} found in file'

    if 'totaltracknumber' in file.handled_properties:
        file.set_property('tracknumber', 0)
        file.set_property('totaltracknumber', 0)

        assert not file.has_tag('tracknumber'), 'cleared tag tracknumber found in file'

        file.set_property('tracknumber', 1)
        assert file.has_tag('tracknumber')
        file.set_property('totaltracknumber', 1)
        assert file.has_tag('tracknumber')
        file.set_property('tracknumber', 0)
        assert file.has_tag('tracknumber')
        file.set_property('totaltracknumber', 0)
        assert not file.has_tag('tracknumber')

        file.set_property('tracknumber', 1)
        file.set_property('totaltracknumber', 1)
        file.set_property('totaltracknumber', 0)
        assert file.has_tag('tracknumber')
        file.set_property('tracknumber', 0)
        assert not file.has_tag('tracknumber')

    else:
        file.set_property('tracknumber', 0)
        assert not file.has_tag('tracknumber'), 'cleared tag tracknumber found in file'

    assert file.get_property('is_modified') == True

    if file._supports_album_covers:
        file.set_property('front_cover_path', os.path.join(EXAMPLES_DIR, f'cover.png'))
        assert file.get_property('front_cover_path')

    file.save()

    assert file.get_property('is_modified') == False
    assert not file.modified_tags

    file_class = type(file)
    backend_read_empty(file_class(file.path), skip_cover=True)

def backend_delete(file):
    """Tests common backend delete functions."""
    for prop in file.handled_properties + file.supported_extra_tags:
        file.delete_tag(prop)
        assert not file.has_tag(prop), f'tag {prop} erroneously found in file'
        assert not file.get_property(prop), f'tag {prop} should have been deleted, but has value of {file.get_property(prop)}, {file.mg_file.tags}'

    assert file.get_property('is_modified') == True

    file.save()

    assert file.get_property('is_modified') == False

    if file._supports_album_covers:
        file.delete_cover()
        assert not file.has_tag('front-cover-path')
        assert not file.front_cover_path
        assert not file.front_cover.cover_path

        assert file.get_property('is_modified') == True
        file.save()
        assert file.get_property('is_modified') == False

    file_class = type(file)
    backend_read_empty(file_class(file.path))

def backend_rename(file):
    """Tests the ability of the file to be renamed."""
    original_path = file.props.path
    orig_copy_path = original_path + '-orig'
    shutil.copyfile(original_path, orig_copy_path)
    new_path = original_path + '-moved'

    file.set_property('title', 'Moved Title')

    file.set_property('path', new_path)

    assert not os.path.exists(original_path)
    assert os.path.exists(new_path)
    assert file.props.path == new_path
    assert file.props.title == 'Moved Title'
    assert filecmp.cmp(orig_copy_path, new_path, shallow=False)

    file.save()
    filecmp.clear_cache()
    assert not os.path.exists(original_path)
    assert os.path.exists(new_path)
    assert not filecmp.cmp(orig_copy_path, new_path, shallow=False)

    os.remove(orig_copy_path)
    os.remove(new_path)

def backend_full_releasedate(file):
    """Tests various values for the releasedate field"""
    path = file.props.path
    file_class = type(file)
    for value in ('0000', '2022', '2022-01', '2022-01-31'):
        file = file_class(path)
        file.set_property('releasedate', value)
        assert file.is_modified
        assert file._releasedate_cached == value
        file.save()
        file = file_class(path)
        assert file.get_property('releasedate') == value, f'Invalid date value (expected "{value}", got "{file.get_property("releasedate")}")'
