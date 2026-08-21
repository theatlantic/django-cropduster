"""Django admin image uploads with multiple named crops."""

import importlib

__version__ = '5.0.0.dev0'


_LAZY_IMPORTS = {
    'get_renderer': 'cropduster.renderers',
}


def __getattr__(name):
    try:
        module_name = _LAZY_IMPORTS[name]
    except KeyError:
        raise AttributeError("module %s has no attribute %r" % (__name__, name))
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_IMPORTS))
