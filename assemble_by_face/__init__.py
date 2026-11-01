"""Assemble by Face: assemble mesh parts by their faces."""

# Development: F3 > "Reload Scripts" re-runs this file with its old globals
# still present, so reload every submodule (dependencies first) to pick up edits.
if "operators" in locals():
    import importlib
    for _mod in (merge, properties, operators, ui):  # noqa: F821
        importlib.reload(_mod)

from . import merge, operators, properties, ui  # noqa: E402

_modules = (properties, operators, ui)


def register():
    for mod in _modules:
        mod.register()


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
