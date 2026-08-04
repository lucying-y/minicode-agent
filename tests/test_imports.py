import subprocess
import sys


def test_persistence_package_can_be_imported_first() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from minicode_agent.persistence import SqliteRunStore"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
