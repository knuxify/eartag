# Backend implementation notes

This document explains the most important parts of how backends work and what they should contain.

## Cover art support

Backends that support cover art must set `_supports_album_covers` to `True`.

### Cover API

There are two main variables to consider when working with covers:

* `{front,back}-cover-path` - GObject property containing the full path to the cover image. When loading a cover from a tagged file, this will usually be pre-filled to the location of the cover tempfile (explained in the "Cover tempfile" section). **These are created by the `EartagFile` class** and usually won't have to be modified by baclends.
* `{front-back}-cover` - GObject property containing an EartagFileCover option. **This is managed by the `EartagFile` class and MUST NOT be modified by backends.** It automatically applies changes from the respective `cover-path` property, and is primarily used to check if two covers are identical.

For most common functions, `cover_type` is represented by a member of the enum `CoverType`, which contains `FRONT` and `BACK` values. This class is not to be confused with `mutagen.id3.PictureType`, which represents the internal picture type of ID3, WMA and Vorbis/FLAC formats, and should be referred to as `pictype`.

## Loading cover from tagged file

Implementations **must** define a function named `load_cover(self)` that loads both the front and back covers, if available.

### Cover tempfile

As the cover art implementation reads cover data from a file, embedded cover data must be extracted into a file to be displayed. To make the process easier, the `EartagFile` class provides a helper, `create_cover_tempfile(self, cover_type: CoverType, data, extension)` which automatically takes the data and saves it into the correct temp file, then sets the relevant cover-path property to the path to the tempfile.

## Setting cover file

Implementations **must** define a setter function, `set_cover_path(cover_type: CoverType, value)` that sets the cover from the provided file. This setter:

* Must save the path to the `self._{front,back}_cover_path` variable;
* Must call the `delete_{front,back}_cover` method if the provided value is empty.

Implementations should call `self.delete_cover(cover_type, clear_only=True)` to make sure that all conflicting covers are removed first.

## Deleting cover

Implementations **must** define a function named `delete_cover(self, cover_type: CoverType, clear_only=False)` that deletes the cover with the provided type.

Implementations of these functions **must include the following snippet at the end**:

```python
	if not clear_only:
	    self._cleanup_cover(cover_type)
```

This function automatically closes the cover tempfile (if present) and clears the `_{front,back}_cover_path` variable, then marks it as modified.
