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
    author_email='atmoprogrammers@theatlantic.com',
    url='http://github.com/theatlantic/django-cropduster',
    description='Image uploader and cropping tool',
    packages=find_packages(),
    zip_safe=False,
    install_requires=[
        'Pillow',
        'jsonutil',
        'Django>=1.2',
        'python-xmp-toolkit',
    ],
    include_package_data=True,
    classifiers=[
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Operating System :: OS Independent',
        'Topic :: Software Development'
    ],
)
