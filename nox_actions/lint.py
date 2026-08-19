# Import third-party modules
import nox
from nox_actions.utils import PACKAGE_NAME


ISORT_TARGETS = (
    PACKAGE_NAME,
    "nox_actions",
    "tests",
    "noxfile.py",
)


def lint(session: nox.Session) -> None:
    session.install("isort", "ruff")
    session.run("isort", "--check-only", *ISORT_TARGETS)
    session.run("ruff", "check")


def lint_fix(session: nox.Session) -> None:
    session.install("isort", "ruff", "pre-commit", "autoflake")
    session.run("ruff", "check", "--fix")
    session.run("isort", ".")
    session.run("pre-commit", "run", "--all-files")
    session.run("autoflake", "--in-place", "--remove-all-unused-imports", "--remove-unused-variables")
