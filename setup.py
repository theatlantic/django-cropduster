#!/usr/bin/env python

from setuptools import setup, find_packages


setup(
    name='django-cropduster',
    version=__import__('cropduster').__version__,
    author='The Atlantic',
    author_email='programmers@theatlantic.com',
    url='https://github.com/theatlantic/django-cropduster',
    description='Django image uploader and cropping tool',
    packages=find_packages(exclude=["tests"]),
    zip_safe=False,
    long_description=open('README.rst').read(),
    license='BSD',
    platforms='any',
    install_requires=[
        'Pillow',
        'python-xmp-toolkit',
        'django-generic-plus>=2.0.3',
    ],
    include_package_data=True,
    python_requires='>=3',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Framework :: Django",
        "Framework :: Django :: 2.2",
        "Framework :: Django :: 3.2",
        "Framework :: Django :: 4.0",
        "Framework :: Django :: 4.1",
        "Framework :: Django :: 4.2",
    ])
