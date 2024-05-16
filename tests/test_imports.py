"""Import Test."""

# Import built-in modules
import importlib
import pkgutil

# Import local modules
import maya_umbrella_scanner


def test_imports():
    """Test import modules."""
    prefix = "{maya_umbrella_scanner}.".format(maya_umbrella_scanner=maya_umbrella_scanner.__name__)
    iter_packages = pkgutil.walk_packages(
        maya_umbrella_scanner.__path__,
        prefix,
    )
    for _, name, _ in iter_packages:
        module_name = name if name.startswith(prefix) else prefix + name
        importlib.import_module(module_name)
