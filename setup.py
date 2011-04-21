from distutils.core import setup
from distutils.command.install import INSTALL_SCHEMES

# Tell distutils to put the data_files in platform-specific installation
# locations. See here for an explanation:
# http://groups.google.com/group/comp.lang.python/browse_thread/thread/35ec7b2fed36eaec/2105ee4d9e8042cb
for scheme in INSTALL_SCHEMES.values():
    scheme['data'] = scheme['purelib']

# Dynamically calculate the version based on tagging.VERSION.
version_tuple = __import__('cropduster').VERSION
if version_tuple[2] is not None:
    version = "%d.%d_%s" % version_tuple
else:
    version = "%d.%d" % version_tuple[:2]

setup(
    name = 'cropduster',
    version = version,
    description = 'Image management app',
    author = 'ATL Programmers',
    author_email = 'ATMOprogrammers@theatlantic.com',
    url = 'git.amc:/var/git/atl-django-apps/cropduster',
    packages = ['cropduster'],
    classifiers = ['Development Status :: 1 - Beta',
                   'Environment :: Web Environment',
                   'Framework :: Django',
                   'Intended Audience :: Developers',
                   'License :: OSI Approved :: BSD License',
                   'Operating System :: OS Independent',
                   'Programming Language :: Python',
                   'Topic :: Utilities'],
)