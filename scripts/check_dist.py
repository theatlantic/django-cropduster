#!/usr/bin/env python
"""
Validate an existing wheel and source distribution.

Run after building both artifacts::

    python -m build
    python scripts/check_dist.py

The script requires one wheel and one sdist in ``dist/``; it does not build
them. It checks that:

* both artifacts contain the templates and static assets required at runtime;
* files removed in 5.0 are absent;
* the bundled source map remains below its size limit;
* package metadata declares the supported Python and django-generic-plus
  versions; and
* the long description passes ``twine check``.

The wheel and sdist are checked separately because setuptools populates them
from different configuration.
"""

import argparse
import os
import re
import subprocess
import sys
import tarfile
import zipfile


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATIC = "cropduster/static/cropduster"
STANDALONE_STATIC = "cropduster/standalone/static/ckeditor/ckeditor"

#: Non-Python files that have to be in the wheel and in the sdist.
REQUIRED_FILES = [
    # The built frontend. Fixed names: ManifestStaticFilesStorage hashes them
    # downstream, and Django's Media class names them.
    "%s/dist/cropduster.js" % STATIC,
    "%s/dist/cropduster.css" % STATIC,
    "%s/dist/LICENSES.txt" % STATIC,
    "%s/dist/cropduster.js.map" % STATIC,
    # Templates. `inline.html` is rendered by the widget for the bound
    # duplicate formset that displays errors; the other two are the widget and
    # the full-page dialog.
    "cropduster/templates/cropduster/custom_field.html",
    "cropduster/templates/cropduster/inline.html",
    "cropduster/templates/cropduster/upload.html",
    # The in-repo CKEditor 4 plugin, which opens the standalone dialog.
    "%s/plugins/cropduster/plugin.js" % STANDALONE_STATIC,
    "%s/plugins/cropduster/dialogs/cropduster.js" % STANDALONE_STATIC,
    "%s/plugins/cropduster/lang/en.js" % STANDALONE_STATIC,
    # Served by the upload view as the empty-image placeholder.
    "%s/img/blank.gif" % STATIC,
    # The two 6.0-removal shims: a console.warn and a zero-byte file, both
    # present so that a pipeline still naming them keeps resolving.
    "%s/js/cropduster.js" % STATIC,
    "%s/js/jsrender.js" % STATIC,
]

#: Deleted in 5.0 along with the jQuery dialog. Matched on the path tail so a
#: file that reappears under any directory is caught.
FORBIDDEN_NAMES = [
    "upload.js",
    "jquery.jcrop.js",
    "jquery.jcrop.min.js",
    "jquery.jcrop.css",
    "jquery.form.js",
    "jquery.class.js",
    "json2.js",
    "upload.css",
    "jcrop.gif",
    "LICENSE.Jcrop.txt",
    "cropduster_icon_upload_hover.png",
    "cropduster_icon_upload_select.png",
    "progressbar.gif",
    "arrows.png",
    "README.rst",
]

#: The generated source map is included by the static package-data glob. The
#: current map is about 1.2 MB; use a 2 MB limit so an unexpected increase
#: fails the artifact check.
MAP_PATH = "%s/dist/cropduster.js.map" % STATIC
MAP_BUDGET = 2 * 1024 * 1024

REQUIRES_PYTHON = ">=3.10"

#: ``Requires-Dist`` may reorder and normalize version clauses. Check for a
#: 4.x lower bound and a ``<5`` upper bound independently.
GENERIC_PLUS_LOWER = re.compile(r"^>=4(\.|$)")
GENERIC_PLUS_UPPER = re.compile(r"^<5(\.0)*$")
REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$", re.S)


class Artifact(object):
    """A wheel or an sdist, presented as a flat list of package-relative paths."""

    def __init__(self, path, members, metadata):
        self.path = path
        self.name = os.path.basename(path)
        #: Paths relative to the artifact's package root (the sdist's version
        #: directory is stripped, so both kinds compare against one list).
        self.members = members
        self.metadata = metadata

    def has(self, path):
        return path in self.members


def read_wheel(path):
    with zipfile.ZipFile(path) as zf:
        members = [name for name in zf.namelist() if not name.endswith("/")]
        metadata_names = [
            name for name in members
            if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise SystemExit(
                "%s: expected exactly one .dist-info/METADATA, found %d"
                % (path, len(metadata_names)))
        metadata = zf.read(metadata_names[0]).decode("utf-8")
    return Artifact(path, members, metadata)


def read_sdist(path):
    members = []
    metadata = None
    with tarfile.open(path, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            # Everything in an sdist is under `<name>-<version>/`.
            parts = member.name.split("/", 1)
            relative = parts[1] if len(parts) == 2 else parts[0]
            members.append(relative)
            if relative == "PKG-INFO":
                metadata = tf.extractfile(member).read().decode("utf-8")
    if metadata is None:
        raise SystemExit("%s: no PKG-INFO" % path)
    return Artifact(path, members, metadata)


def metadata_fields(metadata, field):
    """Values of one repeatable metadata header, from the headers only."""
    values = []
    for line in metadata.splitlines():
        if not line.strip():
            # The long description follows the blank line; a README that quotes
            # a header would otherwise be read as one.
            break
        if line.lower().startswith(field.lower() + ":"):
            values.append(line.split(":", 1)[1].strip())
    return values


def requirement_name(value):
    match = REQUIREMENT_NAME.match(value)
    return match.group(1).lower().replace("_", "-") if match else ""


def requirement_clauses(value):
    """The version clauses of one ``Requires-Dist``, markers and extras dropped."""
    match = REQUIREMENT_NAME.match(value)
    rest = match.group(2) if match else ""
    rest = rest.split(";")[0].strip().strip("()")
    return [re.sub(r"\s+", "", clause) for clause in rest.split(",") if clause.strip()]


def declared_version():
    """``cropduster.__version__``, read rather than imported."""
    init_py = os.path.join(REPO_ROOT, "cropduster", "__init__.py")
    with open(init_py) as f:
        match = re.search(r"""__version__\s*=\s*['"]([^'"]+)['"]""", f.read())
    if not match:
        raise SystemExit("could not find __version__ in %s" % init_py)
    return match.group(1)


def check_contents(artifact, failures, notes):
    for required in REQUIRED_FILES:
        if not artifact.has(required):
            failures.append("%s: missing %s" % (artifact.name, required))

    for member in artifact.members:
        tail = member.split("/")[-1]
        if tail in FORBIDDEN_NAMES:
            failures.append(
                "%s: %s was deleted in 5.0 but is in the artifact"
                % (artifact.name, member))

    if artifact.has(MAP_PATH):
        size = member_size(artifact, MAP_PATH)
        if size > MAP_BUDGET:
            failures.append(
                "%s: %s is %s, over the %s budget"
                % (artifact.name, MAP_PATH, human(size), human(MAP_BUDGET)))
        else:
            notes.append(
                "%s: source map ships, %s of a %s budget"
                % (artifact.name, human(size), human(MAP_BUDGET)))
    else:
        notes.append("%s: no source map" % artifact.name)


def member_size(artifact, path):
    if artifact.path.endswith(".whl"):
        with zipfile.ZipFile(artifact.path) as zf:
            return zf.getinfo(path).file_size
    with tarfile.open(artifact.path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.isfile() and member.name.split("/", 1)[-1] == path:
                return member.size
    raise SystemExit("%s: %s vanished between reads" % (artifact.name, path))


def check_metadata(artifact, failures, version):
    description_type = metadata_fields(
        artifact.metadata, "Description-Content-Type")
    if description_type != ["text/markdown"]:
        failures.append(
            "%s: Description-Content-Type is %r, expected ['text/markdown']"
            % (artifact.name, description_type))

    requires_python = metadata_fields(artifact.metadata, "Requires-Python")
    if requires_python != [REQUIRES_PYTHON]:
        failures.append(
            "%s: Requires-Python is %r, expected [%r]"
            % (artifact.name, requires_python, REQUIRES_PYTHON))

    generic_plus = [
        value for value in metadata_fields(artifact.metadata, "Requires-Dist")
        if requirement_name(value) == "django-generic-plus"]
    if not generic_plus:
        failures.append(
            "%s: no django-generic-plus in Requires-Dist" % artifact.name)
    for value in generic_plus:
        clauses = requirement_clauses(value)
        if not (any(GENERIC_PLUS_LOWER.match(c) for c in clauses)
                and any(GENERIC_PLUS_UPPER.match(c) for c in clauses)):
            failures.append(
                "%s: django-generic-plus pin is %r, expected >=4.x and <5"
                % (artifact.name, value))

    declared = metadata_fields(artifact.metadata, "Version")
    if declared != [version]:
        failures.append(
            "%s: metadata Version is %r, but cropduster.__version__ is %r"
            % (artifact.name, declared, version))


def run_twine(dist_dir, failures):
    files = sorted(
        os.path.join(dist_dir, name) for name in os.listdir(dist_dir)
        if name.endswith((".whl", ".tar.gz")))
    try:
        result = subprocess.run(
            [sys.executable, "-m", "twine", "check"] + files,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as e:
        failures.append("twine check could not run: %s" % e)
        return
    output = result.stdout.decode("utf-8", "replace").strip()
    if "No module named twine" in output:
        output += "\n(pip install twine, or pass --no-twine to skip this check)"
    if result.returncode != 0:
        failures.append("twine check failed:\n%s" % indent(output))
    else:
        print(indent(output))


def indent(text):
    return "\n".join("    " + line for line in text.splitlines())


def human(size):
    if size >= 1024 * 1024:
        return "%.2f MB" % (size / (1024.0 * 1024.0))
    return "%.1f kB" % (size / 1024.0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--dist", default=os.path.join(REPO_ROOT, "dist"),
        help="directory holding the built wheel and sdist (default: dist/)")
    parser.add_argument(
        "--no-twine", action="store_true",
        help="skip the twine check (it needs twine on the path)")
    args = parser.parse_args(argv)

    dist_dir = os.path.abspath(args.dist)
    if not os.path.isdir(dist_dir):
        raise SystemExit("no such directory: %s" % dist_dir)

    version = declared_version()
    names = sorted(os.listdir(dist_dir))
    wheels = [n for n in names if n.endswith(".whl")]
    sdists = [n for n in names if n.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(
            "%s: expected exactly one wheel and one sdist, found %r"
            % (dist_dir, wheels + sdists))

    artifacts = [
        read_wheel(os.path.join(dist_dir, wheels[0])),
        read_sdist(os.path.join(dist_dir, sdists[0])),
    ]

    failures = []
    notes = []
    for artifact in artifacts:
        print("checking %s" % artifact.name)
        check_contents(artifact, failures, notes)
        check_metadata(artifact, failures, version)

    if not args.no_twine:
        run_twine(dist_dir, failures)

    for note in notes:
        print("  note: %s" % note)

    if failures:
        print("\n%d problem(s):" % len(failures))
        for failure in failures:
            print("  - %s" % failure)
        return 1

    print("\nOK: %s and %s carry every required asset, no deleted asset, and "
          "the expected metadata." % (artifacts[0].name, artifacts[1].name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
