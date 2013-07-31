#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup


extra_kwargs = {}


try:
    from setuptools.command.test import test
except ImportError:
    pass
else:
    class mytest(test):
        def run(self, *args, **kwargs):
            from runtests import runtests
            runtests()
    extra_kwargs['cmdclass'] = {"test": mytest}


setup(
    name='cropduster3',
    version='3.0.6.4',
    author='The Atlantic',
    author_email='programmers@theatlantic.com',
    url='https://github.com/theatlantic/cropduster',
    description='Image uploader and cropping tool',
    packages=['cropduster3'],
    zip_safe=False,
    install_requires=['setuptools', 'PIL'],
    include_package_data=True,
    classifiers=[
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Operating System :: OS Independent',
        'Topic :: Software Development'
    ],
    **extra_kwargs
)
