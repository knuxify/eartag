# Eartag

Small and simple music tag editor that doesn't try to manage your entire library

## Why?

A lot of music tag editors are made to apply changes to entire music libraries. They require you to set up a music folder, etc. This is convenient when you want to keep your entire library in check, but sometimes you just need to edit one file's data without any of the additional hassle.

Thus, Eartag was made to be a simple tag editor that can edit one file at a time, as needed.

## Dependencies

Eartag is written in Python, and uses GTK4 and libadwaita for the UI. The following dependencies are required:

- Python >= 3.6
- GTK4
- libadwaita
- pygobject
- pytaglib (used for the main tagging functionality)
- eyed3 (used for MP3 file album art tagging)
- python-magic (used for MIME type detection in some cases)
