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

    shutil.copyfile(
        os.path.join(EXAMPLES_DIR, f'example-notags.{extension}'),
        os.path.join(EXAMPLES_DIR, f'_example-notags-fortest.{extension}')
    )
    file_write_items = file_class(os.path.join(EXAMPLES_DIR, f'_example-notags-fortest.{extension}'))
    backend_write_items(file_write_items, skip_channels)
    os.remove(os.path.join(EXAMPLES_DIR, f'_example-notags-fortest.{extension}'))

    shutil.copyfile(
        os.path.join(EXAMPLES_DIR, f'example.{extension}'),
        os.path.join(EXAMPLES_DIR, f'_example-fortest.{extension}')
    )
    file_delete = file_class(os.path.join(EXAMPLES_DIR, f'_example-fortest.{extension}'))
    backend_delete(file_delete)
    os.remove(os.path.join(EXAMPLES_DIR, f'_example-fortest.{extension}'))

    shutil.copyfile(
        os.path.join(EXAMPLES_DIR, f'example-notags.{extension}'),
        os.path.join(EXAMPLES_DIR, f'_example-notags-fortest.{extension}')
    )
    file_rename = file_class(os.path.join(EXAMPLES_DIR, f'_example-notags-fortest.{extension}'))
    backend_rename(file_rename)
    # No need to remove; test function does this itself

    shutil.copyfile(
        os.path.join(EXAMPLES_DIR, f'example.{extension}'),
        os.path.join(EXAMPLES_DIR, f'_example-fortest.{extension}')
    )
    file_rename = file_class(os.path.join(EXAMPLES_DIR, f'_example-fortest.{extension}'))
    backend_rename(file_rename)
    # No need to remove; test function does this itself

    if file_class._supports_full_dates:
        shutil.copyfile(
            os.path.join(EXAMPLES_DIR, f'example.{extension}'),
            os.path.join(EXAMPLES_DIR, f'_example-fortest.{extension}')
        )
        file_rename_path = os.path.join(EXAMPLES_DIR, f'_example-fortest.{extension}')
        backend_full_releasedate(file_class, file_rename_path)
        os.remove(os.path.join(EXAMPLES_DIR, f'_example-fortest.{extension}'))

def backend_read(file, skip_channels=False):
    """Tests common backend read functions."""
    for prop in file.handled_properties:
        try:
            assert file.get_property(prop) == prop_to_example_string[prop]
        except AssertionError:
            raise ValueError(f'Invalid value for property {prop} (expected {type(prop_to_example_string[prop])} {prop_to_example_string[prop]}, got {type(file.get_property(prop))} {file.get_property(prop)})')

        try:
            assert file.has_tag(prop)
        except AssertionError:
            raise ValueError(f'tag {prop} not found in file')

    for prop in file.supported_extra_tags:
        try:
            assert file.get_property(prop) == prop_to_example_string[prop]
        except AssertionError:
            raise ValueError(f'Invalid value for property {prop} (expected {type(prop_to_example_string[prop])} {prop_to_example_string[prop]}, got {type(file.get_property(prop))} {file.get_property(prop)})')

        try:
            assert file.has_tag(prop)
        except AssertionError:
            raise ValueError(f'tag {prop} not found in file')

    if file._supports_album_covers:
        try:
            assert filecmp.cmp(file.get_property('cover_path'), os.path.join(EXAMPLES_DIR, f'cover.png'), shallow=False)
        except TypeError:
            raise ValueError('Cover art was not found in the provided file')

    assert file.get_property('is_modified') == False
    if not skip_channels: # mutagen-mp4, at least with the m4a file, has some trouble with this step
        assert file.get_property('channels') == 1
    assert file.get_property('length') == 1
    assert file.get_property('bitrate') != 0

def backend_read_empty(file, skip_cover=False):
    for prop in file.handled_properties:
        try:
            assert not file.get_property(prop) or (isinstance(file.get_property(prop), int) and file.get_property(prop) == -1)
            assert not file.has_tag(prop)
        except AssertionError:
            raise ValueError(f'example-notags file has {prop} property set to {file.get_property(prop)}; this either means that something is broken in the file, or in the backend.')

    for prop in file.supported_extra_tags:
        try:
            assert not file.get_property(prop) or (isinstance(file.get_property(prop), int) and file.get_property(prop) == -1)
            assert not file.has_tag(prop)
        except AssertionError:
            raise ValueError(f'example-notags file has {prop} property set to {file.get_property(prop)}; this either means that something is broken in the file, or in the backend.')

    assert file.get_property('is_modified') == False
    if not skip_cover:
        assert not file.get_property('cover_path')

def backend_write(file, skip_channels=False):
    """Tests common backend write functions."""
    backend_read_empty(file)

    for prop in file.handled_properties:
        file.set_property(prop, prop_to_example_string[prop])
        try:
            assert file.has_tag(prop)
        except AssertionError:
            raise ValueError(f'tag {prop} not found in file')

    for prop in file.supported_extra_tags:
        file.set_property(prop, prop_to_example_string[prop])
        try:
            assert file.has_tag(prop)
        except AssertionError:
            raise ValueError(f'tag {prop} not found in file')

    if file._supports_album_covers:
        file.set_property('cover_path', os.path.join(EXAMPLES_DIR, f'cover.png'))
        assert file.get_property('cover_path')

    assert file.get_property('is_modified') == True
    props_set = set(tuple(file.handled_properties) + tuple(file.supported_extra_tags))
    if file._supports_album_covers:
        props_set.add('cover_path')
    assert set(file.modified_tags) == props_set

    file.save()

    assert file.get_property('is_modified') == False
    assert not file.modified_tags

    file_class = type(file)
    backend_read(file_class(file.path), skip_channels)

def backend_write_items(empty_file, skip_channels=False):
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
        try:
            assert file.has_tag(prop)
        except AssertionError:
            raise ValueError(f'tag {prop} not found in file')
        file.save()

        file_read = file_class(new_file_path)
        assert file_read.get_property(prop) == target_value
        for _prop in empty_file.handled_properties:
            if _prop != prop and prop != 'totaltracknumber':
                try:
                    assert not file.has_tag(_prop)
                except:
                    raise ValueError(f"file erroneously has tag {prop}")

        os.remove(new_file_path)

def backend_delete(file):
    """Tests common backend delete functions."""
    for prop in file.handled_properties:
        file.delete_tag(prop)
        try:
            assert not file.has_tag(prop)
        except AssertionError:
            raise ValueError(f'tag {prop} erroneously found in file')

    for prop in file.supported_extra_tags:
        file.delete_tag(prop)
        try:
            assert not file.has_tag(prop)
        except AssertionError:
            raise ValueError(f'tag {prop} erroneously found in file')

    assert file.get_property('is_modified') == True

    file.save()

    file_class = type(file)
    backend_read_empty(file_class(file.path), skip_cover=True)

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

def backend_full_releasedate(file_class, path):
    """Tests various values for the releasedate field"""
    for value in ('', '0000', '2022', '2022-01', '2022-01-31'):
        file = file_class(path)
        file.set_property('releasedate', value)
        assert file.is_modified
        assert file._releasedate_cached == value
        file.save()
        file = file_class(path)
        assert file.get_property('releasedate') == value, f'Invalid date value (expected "{value}", got "{file.get_property("releasedate")}")'
