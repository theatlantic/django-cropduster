#!/usr/bin/env python
import os
import warnings
import django_admin_testutils


def main():
    warnings.simplefilter("error", Warning)
    os.environ['DJANGO_SETTINGS_MODULE'] = 'cropduster.tests.settings'
    runtests = django_admin_testutils.RunTests(
        "cropduster.tests.settings", "cropduster")
    runtests()


if __name__ == '__main__':
    main()
