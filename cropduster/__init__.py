# this is a namespace package
try:
    import pkg_resources
except ImportError:
    import pkgutil
    __path__ = pkgutil.extend_path(__path__, __name__)
else:
    pkg_resources.declare_namespace(__name__)
