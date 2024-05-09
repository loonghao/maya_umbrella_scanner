# -*- coding: UTF-8 -*-
import shutil

import nox
import argparse
import os
from pathlib import Path
from typing import Iterator, Tuple
import zipfile

PACKAGE_NAME = "maya_umbrella_scanner"
ROOT = os.path.dirname(__file__)


@nox.session
def lint(session: nox.Session) -> None:
    session.install("wemake-python-styleguide")
    session.run("flake8", PACKAGE_NAME)


@nox.session
def isort_check(session: nox.Session) -> None:
    session.install("isort")
    session.run("isort", "--check-only", PACKAGE_NAME)


@nox.session
def isort(session: nox.Session) -> None:
    session.install("isort")
    session.run("isort", PACKAGE_NAME)


@nox.session
def preflight(session: nox.Session) -> None:
    session.install("pre-commit")
    session.run("pre-commit", "run", "--all-files")


@nox.session
def ruff_format(session: nox.Session) -> None:
    session.install("ruff")
    session.run("ruff", "check", "--fix")


@nox.session
def ruff_check(session: nox.Session) -> None:
    session.install("ruff")
    session.run("ruff", "check")


@nox.session
def pytest(session: nox.Session) -> None:
    session.install("pytest", "pytest_cov")
    test_root = os.path.join(ROOT, "tests")
    session.run("pytest", f"--cov={PACKAGE_NAME}",
                "--cov-report=xml:coverage.xml",
                f"--rootdir={test_root}",
                env={"PYTHONPATH": ROOT}, )
