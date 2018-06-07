#!/usr/bin/env python
import warnings
import selenosis


class RunTests(selenosis.RunTests):

    def __call__(self, *args, **kwargs):
        warnings.simplefilter("error", Warning)
        super(RunTests, self).__call__(*args, **kwargs)


def main():
    runtests = RunTests("cropduster.tests.settings", "cropduster")
    runtests()


if __name__ == '__main__':
    main()
