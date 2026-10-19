# Contributing

The plugin is a single Python script, `bin/herdr-jj-sidebar.py`, using only the
standard library. It supports Python 3.9 so that it runs on the Python macOS
ships, with nothing extra to install.

To try your changes in Herdr, link your checkout in place of the installed
plugin:

```sh
herdr plugin link .
```

## Tests

```sh
python3 -m unittest discover -s test
```

The tests build real jj repos and run the plugin against `test/fake_herdr.py`,
which records what the plugin reports. They need jj and git.

## Lint

```sh
uvx ruff check .
uvx ruff format .
```

CI runs both, plus the tests on Python 3.9 and the latest Python.
