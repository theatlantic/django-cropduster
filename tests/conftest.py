import warnings

import pytest
from django.test import TestCase


TestCase.pytestmark = pytest.mark.django_db(transaction=True, reset_sequences=True)

SELENIUM_RETRIES = 2


def pytest_addoption(parser):
    parser.addoption(
        "--write-fixtures", action="store_true", default=False,
        help=(
            "Rewrite the committed HTML fixtures under frontend/tests/fixtures/ "
            "from what the tests render, instead of comparing against them."))


def pytest_collection_modifyitems(config, items):
    """
    Apply pytest-retry only to browser tests.

    pytest-django converts django-selenosis's ``@tag("selenium")`` into the
    ``selenium`` marker. Tests carrying that marker receive pytest-retry's
    ``flaky`` marker; the rest of the suite is not retried.
    """
    if not config.pluginmanager.hasplugin("pytest-retry"):
        return
    for item in items:
        if item.get_closest_marker("selenium") and not item.get_closest_marker("flaky"):
            item.add_marker(pytest.mark.flaky(retries=SELENIUM_RETRIES))


attempts_key = pytest.StashKey[int]()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    item.stash[attempts_key] = 0
    yield


@pytest.hookimpl(trylast=True)
def pytest_runtest_call(item):
    """
    Expose failures from retried ``unittest.TestCase`` tests to pytest-retry.

    ``unittest.TestCase`` records a failure in
    ``TestCaseFunction._excinfo`` instead of raising it. On the initial
    attempt, ``pytest_runtest_makereport`` consumes that queue. pytest-retry
    runs later attempts by calling ``pytest_runtest_call`` and builds their
    reports directly from ``CallInfo``, so a failed retry can be reported as
    "passed on attempt 2" and then reappear as ``ERROR at teardown of ...``.

    For retry attempts only, raise the queued exception so that pytest-retry
    records the failure. Leave the initial attempt and tests without the
    ``flaky`` marker on pytest's normal path.

    See ``tests/test_retry_teardown.py``. This can be removed when
    pytest-retry handles unittest items itself; version 1.7.0 does not under
    pytest 8 or 9.
    """
    if not item.get_closest_marker("flaky"):
        return
    attempt = item.stash.get(attempts_key, 0) + 1
    item.stash[attempts_key] = attempt

    queued = getattr(item, "_excinfo", None)
    if not queued:
        return
    failure = queued[0].value
    if attempt > 1:
        queued.clear()
    raise failure


@pytest.fixture(autouse=True)
def suppress_warnings():
    warnings.simplefilter("error", Warning)
    warnings.filterwarnings('ignore', message='.*?ckeditor')
    warnings.filterwarnings('ignore', message='.*?collections')
    warnings.filterwarnings('ignore', message='.*?Resampling')
    warnings.filterwarnings('ignore', message='.*?distutils')
    # warning from grappelli 3.0 templates
    warnings.filterwarnings('ignore', message='.*?length_is')
