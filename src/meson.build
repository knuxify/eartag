pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
moduledir = join_paths(pkgdatadir, 'eartag')
gnome = import('gnome')
python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('VERSION', meson.project_version())
conf.set('APP_ID', app_id)
conf.set('APP_GRESOURCE_PATH', '/' + app_id.replace('.', '/'))
conf.set('DEVEL', get_option('devel'))
conf.set('ACOUSTID_API_KEY', get_option('acoustid_api_key'))
conf.set('localedir', join_paths(get_option('prefix'), get_option('localedir')))
conf.set('pkgdatadir', pkgdatadir)

blueprints = custom_target('blueprints',
  input: files(
    'ui/dialogs/closewarning.blp',
    'ui/dialogs/discardwarning.blp',
    'ui/dialogs/error.blp',
    'ui/dialogs/removaldiscardwarning.blp',
    'ui/dialogs/tagdeletewarning.blp',
    'ui/identify/altreleaserow.blp',
    'ui/identify/coverimage.blp',
    'ui/identify/filerow.blp',
    'ui/identify/identify.blp',
    'ui/identify/recordingrow.blp',
    'ui/albumcoverbutton.blp',
    'ui/albumcoverimage.blp',
    'ui/extract.blp',
    'ui/filelistitem.blp',
    'ui/filenamerow.blp',
    'ui/fileview.blp',
    'ui/moretagsgroup.blp',
    'ui/nofile.blp',
    'ui/previewselectorbutton.blp',
    'ui/previewselectoritem.blp',
    'ui/rename.blp',
    'ui/settings.blp',
    'ui/shortcuts.blp',
    'ui/tagselectorbutton.blp',
    'ui/window.blp'
  ),
  output: '.',
  command: [find_program('blueprint-compiler'), 'batch-compile', '@OUTPUT@', '@CURRENT_SOURCE_DIR@', '@INPUT@'],
)

gnome.compile_resources('eartag',
  configure_file(
    input: files('eartag.gresource.xml.in'),
    output: 'eartag.gresource.xml',
    configuration: conf
  ),
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  dependencies: blueprints,
)

configure_file(
  input: 'eartag.in',
  output: bin_name,
  configuration: conf,
  install: true,
  install_dir: get_option('bindir')
)

eartag_sources = [
  '__init__.py',
  '_async.py',
  'config.py',
  'dialogs.py',
  'extract.py',
  'identify.py',
  'logger.py',
  'main.py',
  'musicbrainz.py',
  'filemanager.py',
  'filelist.py',
  'fileview.py',
  'rename.py',
  'tagentry.py',
  'window.py',
]

subdir('backends')
subdir('utils')

install_data(eartag_sources, install_dir: moduledir)
