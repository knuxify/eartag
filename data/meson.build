data_conf = configuration_data()
data_conf.set('APP_ID', app_id)
data_conf.set('APP_BIN_NAME', bin_name)
data_conf.set('APP_GSCHEMA_PATH', '/' + app_id.replace('.', '/') + '/')
data_conf.set('APP_NAME', 'Ear Tag' + name_suffix)

desktop_file = i18n.merge_file(
  input: configure_file(
    input: files('app.drey.EarTag.desktop.in'),
    output: 'app.drey.EarTag.desktop.in',
    configuration: data_conf
  ),
  output: app_id + '.desktop',
  type: 'desktop',
  po_dir: '../po',
  install: true,
  install_dir: join_paths(get_option('datadir'), 'applications')
)

desktop_utils = find_program('desktop-file-validate', required: false)
if desktop_utils.found()
  test('Validate desktop file', desktop_utils,
    args: [desktop_file]
  )
endif

appstream_file = i18n.merge_file(
  input: configure_file(
    input: files('app.drey.EarTag.metainfo.xml.in'),
    output: 'app.drey.EarTag.metainfo.xml.in',
    configuration: data_conf
  ),
  output: app_id + '.metainfo.xml',
  po_dir: '../po',
  install: true,
  install_dir: join_paths(get_option('datadir'), 'metainfo')
)

appstreamcli = find_program('appstreamcli', required: false)
if appstreamcli.found()
  test('Validate appstream file', appstreamcli,
    args: ['validate', '--no-net', appstream_file]
  )
endif

install_data(
    configure_file(
    input: files('app.drey.EarTag.gschema.xml.in'),
    output: app_id + '.gschema.xml',
    configuration: data_conf
  ),
  install_dir: join_paths(get_option('datadir'), 'glib-2.0/schemas')
)

compile_schemas = find_program('glib-compile-schemas', required: false)
if compile_schemas.found()
  test('Validate schema file', compile_schemas,
    args: ['--strict', '--dry-run', meson.current_source_dir()]
  )
endif

subdir('icons')
