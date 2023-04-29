# Ear Tag backends

Backends provide a single shared interface that works with all file types supported by Ear Tag. Currently, all backends use Mutagen internally.

## Available backends

* `mutagen_asf` - WMA files
* `mutagen_id3` - MP3 and WAV files
* `mutagen_mp4` - MP4, M4A and ALAC files
* `mutagen_vorbis` - OGG and FLAC files

## Available tags

Every file object has GObject properties that represent its information.

### File info

These tags are present in every file type (although some information may be inaccurate).

* `path` - path to the file.
* `filetype` - extension of the file, taken from the filename.
* `length` - length of the audio, in seconds.
* `bitrate` - bitrate of the audio, in kbps.
* `channels` - amount of audio channels in the file (1 - mono, 2 - stereo...)

### Basic tags

These tags are present in every file type.

* `title` - title of the track.
* `artist` - name of the artist.
* `tracknumber` - number of the track in the album.
* `totaltracknumber` - number of total tracks in the album.
* `album` - name of the album.
* `albumartist` - name of the album artist.
* `releaseyear` - year of the track's release.
* `genre` - the track's genre.
* `comment` - a short comment.

### Cover art

* `cover` - EartagFileCover object containing information about the cover image.
* `cover_path` - path to the extracted cover image. For newly loaded files, this will be a location in a temporary directory; when the cover art is updated, this points to the location of the loaded image.

### Extra tags

These tags are only present in specific filetypes; see the `supported_extra_tags` in the backend classes to get a list of tags supported by that backend.

* `bpm`
* `compilation`
* `composer`
* `copyright`
* `encodedby`
* `mood`
* `conductor`
* `arranger`
* `discnumber`
* `publisher`
* `isrc`
* `language`
* `discsubtitle`
* `url`

#### Sort tags

* `albumsort`
* `albumartistsort`
* `artistsort`
* `composersort`
* `titlesort`
