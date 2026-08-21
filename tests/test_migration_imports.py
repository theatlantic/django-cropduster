"""Check the dotted paths stored in Cropduster migrations.

Cropduster's ``0001_initial`` and ``0002_alt_text`` migrations refer to
``cropduster.fields.*``, ``cropduster.models.generate_filename``, and
``cropduster.settings.*``. Roughly forty migrations in one downstream
project store such paths in their operations. If one of these objects is
moved, downstream projects can no longer load their migration histories; no
other test in this suite loads those paths.
"""

import ast
import importlib
import os

from django import test

import cropduster.migrations


MIGRATION_FILES = ('0001_initial.py', '0002_alt_text.py')

# These paths occur in Cropduster's two migrations.
# test_the_expected_paths_are_found fails if all_paths() stops finding them;
# without this set, the resolution checks would pass vacuously if the AST
# walk broke.
REQUIRED_PATHS = {
    'cropduster.fields.CropDusterImageField',
    'cropduster.fields.CropDusterSimpleImageField',
    'cropduster.fields.ReverseForeignRelation',
    'cropduster.models.generate_filename',
    'cropduster.settings.CROPDUSTER_DB_PREFIX',
}

# Downstream migrations also store these paths in deconstructed fields or
# ``RunPython`` functions, even though Cropduster's own migrations do not.
DOWNSTREAM_PATHS = {
    'cropduster.fields.CropDusterField',
    'cropduster.fields.CropDusterImageField',
    'cropduster.fields.ReverseForeignRelation',
    'cropduster.models.Image',
    'cropduster.models.Thumb',
    'cropduster.resizing.Crop',
    'cropduster.resizing.Size',
    'cropduster.exceptions.CropDusterException',
}


def dotted_paths(source):
    """Return dotted expressions in ``source`` that begin with an import.

    ``import cropduster.fields`` binds ``cropduster``, ``from django.db import
    models`` binds ``models`` to ``django.db.models``; attribute chains built
    on either binding name the paths that a migration resolves when it is
    imported.
    """
    tree = ast.parse(source)

    roots = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    roots[alias.asname] = alias.name
                else:
                    root = alias.name.split('.')[0]
                    roots[root] = root
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                roots[alias.asname or alias.name] = '%s.%s' % (node.module, alias.name)

    def flatten(node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name) or node.id not in roots:
            return None
        parts.append(roots[node.id])
        return '.'.join(reversed(parts))

    paths = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            path = flatten(node)
            if path:
                paths.add(path)
    return paths


def resolve(path):
    """Import ``path``, whether it names a module or an attribute of one."""
    parts = path.split('.')
    obj = importlib.import_module(parts[0])
    for i, part in enumerate(parts[1:], start=1):
        try:
            obj = getattr(obj, part)
        except AttributeError:
            obj = importlib.import_module('.'.join(parts[:i + 1]))
    return obj


class TestMigrationImports(test.SimpleTestCase):

    def all_paths(self):
        directory = os.path.dirname(cropduster.migrations.__file__)
        paths = set()
        for name in MIGRATION_FILES:
            with open(os.path.join(directory, name)) as f:
                paths |= dotted_paths(f.read())
        return paths

    def test_every_referenced_path_resolves(self):
        for path in sorted(self.all_paths()):
            with self.subTest(path=path):
                resolve(path)

    def test_the_expected_paths_are_found(self):
        self.assertLessEqual(REQUIRED_PATHS, self.all_paths())

    def test_paths_frozen_in_downstream_migrations_resolve(self):
        for path in sorted(DOWNSTREAM_PATHS):
            with self.subTest(path=path):
                resolve(path)

    def test_migrations_load(self):
        for name in MIGRATION_FILES:
            module = importlib.import_module(
                'cropduster.migrations.%s' % os.path.splitext(name)[0])
            self.assertTrue(module.Migration.operations)
