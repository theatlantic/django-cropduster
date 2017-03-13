#!/usr/bin/env python
import warnings
import django_admin_testutils


def main():
    warnings.simplefilter("error", Warning)
    runtests = django_admin_testutils.RunTests(
        "cropduster.tests.settings", "cropduster")
    runtests()


if __name__ == '__main__':
    main()
