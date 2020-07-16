#!/usr/bin/env python
import warnings
import selenosis


class RunTests(selenosis.RunTests):

    def __call__(self, *args, **kwargs):
        warnings.simplefilter("error", Warning)
        warnings.filterwarnings('ignore', message='.*?ckeditor')

        # Introduced in Python 3.7
        warnings.filterwarnings(
            'ignore',
            category=DeprecationWarning,
            message="Using or importing the ABCs from 'collections' instead of from 'collections.abc'",
        )
        super(RunTests, self).__call__(*args, **kwargs)


def main():
    runtests = RunTests("cropduster.tests.settings", "cropduster")
    runtests()


if __name__ == '__main__':
    main()
