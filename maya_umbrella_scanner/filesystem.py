# Import built-in modules
import logging
import os
import subprocess
import sys
from tempfile import mkdtemp

# Import third-party modules
from maya_umbrella.signatures import FILE_VIRUS_SIGNATURES
from maya_umbrella.signatures import JOB_SCRIPTS_VIRUS_SIGNATURES


def this_root():
    """Returns the root directory of the current Maya installation."""
    path = sys.executable
    if "maya_umbrella.exe" in path:
        return os.path.dirname(path)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def assemble_env_paths(*paths):
    """Assembles a list of paths to be used in the environment PATH variable."""
    return ";".join(paths)


def get_rg_exe():
    """Assembles the path to the rg executable."""
    root = this_root()
    return os.path.join(root, "bin", "rg.exe")


def assemble_rg_varius_check_commands(path):
    """Assembles the commands to run rg to check for varius."""
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
