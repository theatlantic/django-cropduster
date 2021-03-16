#!/usr/bin/env python

try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
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
        'six',
        'Pillow',
        'python-xmp-toolkit',
        'django-generic-plus>=2.0.3',
    ],
    include_package_data=True,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Framework :: Django',
        'Framework :: Django :: 1.11',
        'Framework :: Django :: 2.2',
        'Framework :: Django :: 3.0',
        'Framework :: Django :: 3.1',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ])
