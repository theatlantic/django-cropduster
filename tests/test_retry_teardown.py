"""
Regression tests for pytest-retry with ``unittest.TestCase``.

Without the hook in ``tests.conftest``, a failed retry can be reported as
"passed on attempt 2" and later appear as ``ERROR at teardown of ...``. The
same bug stops the test before the configured number of attempts has run.

These subprocess tests verify the hook without starting Django, Selenium, or
the live server. They also verify that a test which fails every attempt still
fails the pytest process.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


pytest.importorskip("pytest_retry")

REPO_ROOT = Path(__file__).resolve().parent.parent

# Three attempts, of which the first `failures` fail.
CASE = '''
    import unittest

    import pytest

    ATTEMPTS = {{}}


    @pytest.mark.flaky(retries=2)
    class Flaky(unittest.TestCase):
        def test_it(self):
            ATTEMPTS["n"] = ATTEMPTS.get("n", 0) + 1
            if ATTEMPTS["n"] <= {failures}:
                raise AssertionError("attempt %d" % ATTEMPTS["n"])
'''


def run_case(tmp_path, failures, with_hook=True):
    # Give the nested run its own root directory so it cannot inherit an
    # unrelated pytest configuration.
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "conftest.py").write_text(
        'pytest_plugins = ["tests.conftest"]' if with_hook else "")
    (tmp_path / "test_case.py").write_text(
        textwrap.dedent(CASE.format(failures=failures)))

    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    # The generated test needs no database, and the conftest does not read
    # settings at import, so Django does not need to be configured.
    env.pop("DJANGO_SETTINGS_MODULE", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "test_case.py"],
        cwd=tmp_path, env=env, capture_output=True, text=True)


@pytest.mark.parametrize("failures,attempt", [(1, 2), (2, 3)])
def test_a_recovered_retry_exits_zero(tmp_path, failures, attempt):
    result = run_case(tmp_path, failures=failures)

    assert result.returncode == 0, result.stdout
    assert "1 passed" in result.stdout
    assert "ERROR" not in result.stdout
    # Confirm that pytest-retry used every attempt needed for this case.
    assert f"passed on attempt {attempt}!" in result.stdout


def test_a_test_that_never_passes_still_fails_the_run(tmp_path):
    result = run_case(tmp_path, failures=3)

    assert result.returncode == 1, result.stdout
    assert "1 failed" in result.stdout
    assert "failed after 3 attempts!" in result.stdout


def test_without_the_hook_a_recovered_retry_exits_one(tmp_path):
    """Record the pytest-retry behavior that requires the hook."""
    result = run_case(tmp_path, failures=2, with_hook=False)

    assert result.returncode == 1, result.stdout
    # The retry is reported as passed, but its failure later appears during
    # teardown and makes the process exit with an error.
    assert "1 passed" in result.stdout
    assert "passed on attempt 2!" in result.stdout
    assert "ERROR at teardown" in result.stdout
