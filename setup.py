#!/usr/bin/env python

try:
    from setuptools import setup, find_packages
    from setuptools.command.test import test
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages
    from setuptools.command.test import test


class mytest(test):
    def run(self, *args, **kwargs):
        from runtests import runtests
        runtests()
        # Upgrade().run(dist=True)
        # test.run(self, *args, **kwargs)

setup(
    name="django-cropduster",
    version="1",
    author="Llewellyn Hinkes",
    author_email="ortsed@gmail.com",
    url="http://github.com/ortsed/cropduster",
    description = "Image uploader and cropping tool",
    packages=find_packages(),
    zip_safe=False,
    install_requires=[
        "PIL",
    ],
    include_package_data=True,
    cmdclass={"test": mytest},
    classifiers=[
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Operating System :: OS Independent",
        "Topic :: Software Development"
    ],
)