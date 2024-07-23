# Import built-in modules
import argparse
import os
import sys
from tempfile import TemporaryDirectory

# Import third-party modules
import click
from maya_umbrella.filesystem import get_maya_install_root

# Import local modules
from maya_umbrella_scanner.filesystem import assemble_rg_varius_check_commands
from maya_umbrella_scanner.filesystem import create_bat_file
from maya_umbrella_scanner.template import RUNNER_TEMPLATE


def main():
    """Main entry point for the script. Parses command line arguments and runs the appropriate functions."""
    args = argparse.ArgumentParser()
    args.add_argument("--maya-version", type=str)
    args.add_argument("--path", type=str, required=True)
    options = args.parse_args(sys.argv[1:])
    if not os.path.exists(options.path):
        raise click.ClickException(f"Path does not exist: {options.path}")
    infected_file = assemble_rg_varius_check_commands(options.path)
    if not infected_file:
        click.echo("No infected files found.")
        sys.exit(0)
    if options.maya_version:
        maya_root = get_maya_install_root(options.maya_version)
        maya_python = os.path.join(maya_root, "bin", "mayapy.exe")
        click.echo(f"Loading maya... {maya_python}")
        with TemporaryDirectory() as temp_dir:
            run_maya_py = os.path.join(temp_dir, "run_maya.py")
            with open(run_maya_py, "w") as f:
                f.write(RUNNER_TEMPLATE)
            create_bat_file(maya_python, run_maya_py, infected_file, temp_dir)
    else:
        click.echo(f"Export infected files to: {infected_file}")
