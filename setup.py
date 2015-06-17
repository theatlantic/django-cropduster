#!/usr/bin/env python

try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages


setup_kwargs = {}

try:
    setup_kwargs['long_description'] = open('README.rst').read()
except IOError:
    pass

setup(
    name='django-cropduster',
    version='4.8.24',
    author='The Atlantic',
    author_email='programmers@theatlantic.com',
    url='https://github.com/theatlantic/django-cropduster',
    description='Django image uploader and cropping tool',
    packages=find_packages(exclude=['cropduster3', 'cropduster3.*']),
    zip_safe=False,
    install_requires=[
        'Pillow',
        'Django>=1.2',
        'python-xmp-toolkit',
        'django-generic-plus>=1.1.0',
        'six>=1.7.0',
    ],
    include_package_data=True,
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Operating System :: OS Independent',
        'Topic :: Software Development'
    ],
    **setup_kwargs)
