# Import built-in modules
import argparse
import os
import subprocess
import sys
from tempfile import TemporaryDirectory

# Import third-party modules
import click
from maya_umbrella.filesystem import get_maya_install_root

# Import local modules
from maya_umbrella_scanner.filesystem import assemble_env_paths
from maya_umbrella_scanner.filesystem import assemble_rg_varius_check_commands
from maya_umbrella_scanner.template import BAT_TEMPLATE
from maya_umbrella_scanner.template import RUNNER_TEMPLATE


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--maya-version", type=str)
    args.add_argument("--path", type=str, required=True)
    options = args.parse_args(sys.argv[1:])
    if not os.path.exists(options.path):
        raise click.ClickException(f"Path does not exist: {options.path}")
    infected_file = assemble_rg_varius_check_commands(options.path)
    if options.maya_version:
        maya_root = get_maya_install_root(options.maya_version)
        maya_python = os.path.join(maya_root, "bin", "mayapy.exe")
        click.echo(f"Loading maya... {maya_python}")
        site_packages = os.path.join(os.path.dirname(sys.executable), "lib", "site-packages")
        with TemporaryDirectory() as temp_dir:
            run_maya_py = os.path.join(temp_dir, "run_maya.py")
            with open(run_maya_py, "w") as f:
                f.write(RUNNER_TEMPLATE)
            bat_template = BAT_TEMPLATE.format(
                PYTHONPATH=assemble_env_paths(site_packages),
                MAYA_PYTHON=maya_python,
                SCRIPT_PATH=run_maya_py,
                SCRIPT_ARGS=infected_file,
            )
            bat_file = os.path.join(temp_dir, "call_maya.bat")
            with open(bat_file, "w") as f:
                f.write(bat_template)
            subprocess.call(bat_file, shell=True)
    else:
        click.echo(f"Export infected files to: {infected_file}")
