# Import built-in modules
import logging
import os
import subprocess
import sys
from tempfile import mkdtemp

# Import third-party modules
from maya_umbrella.signatures import FILE_VIRUS_SIGNATURES
from maya_umbrella.signatures import JOB_SCRIPTS_VIRUS_SIGNATURES

# Import local modules
from maya_umbrella_scanner.template import BAT_TEMPLATE


def this_root():
    """Returns the root directory of the current Maya installation.

    Returns:
        str: The root directory of the current Maya installation.
    """
    path = sys.executable
    if "maya_umbrella.exe" in path:
        return os.path.dirname(path)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def assemble_env_paths(*paths):
    """Assemble environment paths separated by a semicolon.

    Args:
        *paths: Paths to be assembled.

    Returns:
        str: Assembled paths separated by a semicolon.
    """
    return ";".join(paths)


def get_rg_exe():
    """Assembles the path to the rg (ripgrep) executable.

    Returns:
        str: The path to the rg executable.
    """
    root = this_root()
    return os.path.join(root, "bin", "rg.exe")


def assemble_rg_varius_check_commands(path):
    """Assemble the command to check for viruses in the given path.

    Args:
        path (str): The path to check for viruses.

    Returns:
        str: The command to check for viruses in the given path.
    """
    rg = get_rg_exe()
    signatures = JOB_SCRIPTS_VIRUS_SIGNATURES + FILE_VIRUS_SIGNATURES
    signatures = list(set(signatures))
    infected_file = os.path.join(mkdtemp("maya-umbrella"), "infected_file.txt")
    backup_folder_name = os.getenv("MAYA_UMBRELLA_BACKUP_FOLDER_NAME", "_virus")
    logger = logging.getLogger(__name__)
    with open(infected_file, "wb") as f:
        cmd = [
            rg,
            "-l",
            "|".join(signatures),
            path,
            "--binary",
            "--sort-files",
            "-g",
            "*.m[ab]",
            "-g",
            # Ignore _virus backup files.
            f"!{backup_folder_name}"
        ]
        try:
            files = subprocess.check_output(cmd)
            f.write(files)
        except subprocess.CalledProcessError as e:
            logger.error(e)
            print(e)
    return infected_file


def create_bat_file(maya_python, run_maya_py, infected_file, temp_dir):
    """Create a batch file to call Maya's Python interpreter with the necessary arguments for virus scanning.

    Args:
        maya_python (str): Path to the Maya's Python interpreter.
        run_maya_py (str): Path to the Python script to run within Maya's Python interpreter.
        infected_file (str): Path to the file to be scanned for viruses.
        temp_dir (str): Path to the temporary directory to create the batch file in.
    """
    if not os.path.exists(maya_python):
        raise FileExistsError(f"Maya Python not found: {maya_python}")
    site_packages = os.path.join(this_root(), "lib", "site-packages")
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
