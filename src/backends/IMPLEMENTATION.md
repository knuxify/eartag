# Backend implementation notes

This document explains the most important parts of how backends work and what they should contain.

## Cover art support

Backends that support cover art must set:

* `_supports_album_covers` to `True`
* `_supported_album_cover_mimetypes` to a list containing mimetype strings

They must also implement the following three functions:

* `async load_cover(self)`, which loads both the front and back covers from the file, if available.
* `async set_cover_from_data(self, cover_type: CoverType, data: bytes, mime: str | None = None)`, which loads a cover from the given data and applies it to the file's tags.
* `delete_cover(self, cover_type: CoverType, clear_only: bool = False)`, which deletes the cover with the given type.

### Accessing cover data

The above three functions change the contents of the `front_cover` and `back_cover` properties. These both return a value of either None for no cover, or an instance of EartagFileCover.

Users can listen to cover changes by connecting to the `cover-updated` signal, which has an argument with the cover type (from the CoverType enum) as an integer.

### `set_cover_from_path`

For `set_cover_from_path`, start with the following template:

```python
    async def set_cover_from_path(self, cover_type: CoverType, path: str):
        if cover_type != CoverType.FRONT and cover_type != CoverType.BACK:
            raise ValueError
            
		if not mime:
			mime = get_mimetype_buffer(data)

        # Set cover in UI and check if it's valid
        ret = await self._set_cover_from_data(cover_type, data)
        if ret is False:
            return
            
		# Add the cover data to your tags here. The raw loaded data as a bytes
		# object is available in the "data" variable.
```

### `delete_cover`

Implementations **must** define a function named `delete_cover(self, cover_type: CoverType, clear_only: bool = False)` that deletes the cover with the provided type.

Implementations of these functions **must include the following snippet at the end**:

```python
	if not clear_only:
	    self._cleanup_cover(cover_type)
```

This function automatically closes the cover tempfile (if present) and clears the `_{front,back}_cover_path` variable, then marks it as modified.
