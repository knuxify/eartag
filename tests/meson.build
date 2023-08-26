python3 = find_program('python3')

networked = ''
if get_option('enable_networked_tests')
  networked = '--networked_tests'
endif

test('Run tests', python3,
  args: [
    '-m', 'pytest', networked,
  ],
  workdir: meson.project_source_root()
)
