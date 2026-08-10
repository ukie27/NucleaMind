"""
Entry point for running the legacy CLI as a module: python -m nucleamind.legacy
"""

from nucleamind.legacy.cli.commands import app

if __name__ == "__main__":
    app()
