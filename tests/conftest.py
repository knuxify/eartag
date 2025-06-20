import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "networked_tests: enable MusicBrainz and AcoustID test")


def pytest_addoption(parser):
    parser.addoption(
        "--networked_tests",
        action="store_true",
        help="Enable MusicBrainz and AcoustID test; not recommended unless you're doing development on them",  # noqa: E501
    )


def pytest_runtest_setup(item):
    if "networked_tests" in item.keywords and not item.config.getoption("--networked_tests"):
        pytest.skip("need --networked_tests option to run this test")
