project('eartag',
          version: '0.6.0',
    meson_version: '>= 0.58.0',
  default_options: [ 'warning_level=2',
                   ],
)

if get_option('devel')
  app_id = 'app.drey.EarTag.Devel'
  bin_name = 'eartag-devel'
  name_suffix = ' (Development)'
else
  app_id = 'app.drey.EarTag'
  bin_name = 'eartag'
  name_suffix = ''
endif

i18n = import('i18n')

subdir('data')
subdir('src')
subdir('po')
subdir('tests')

meson.add_install_script('build-aux/meson/postinstall.py')
