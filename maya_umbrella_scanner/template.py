RUNNER_TEMPLATE = """
import sys

if __name__ == '__main__':
    from maya_umbrella.maya_funs import maya_standalone_context
    from maya_umbrella import MayaVirusScanner

    print(sys.argv[-1])
    infected_file = sys.argv[-1]
    with open(infected_file, "rb") as f:
        files = f.readlines()
    with maya_standalone_context() as cmds:
        api = MayaVirusScanner()
        api.scan_files_from_list(files)

"""

BAT_TEMPLATE = """
@echo off
set PYTHONPATH=%PYTHONPATH%;{PYTHONPATH}
call "{MAYA_PYTHON}" {SCRIPT_PATH} {SCRIPT_ARGS}
"""
