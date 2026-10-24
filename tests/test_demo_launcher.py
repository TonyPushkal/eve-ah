import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("preset,port", [("amaze-on", "8000"), ("hammered", "8001")])
def test_launcher_selects_isolated_preset(tmp_path, preset, port):
    executable = tmp_path / "eve-ah"
    output = tmp_path / "calls"
    executable.write_text(
        "#!/bin/sh\n"
        'printf "%s|%s|%s|%s\\n" "$*" "$EVE_DATA_DIR" "$EVE_STORAGE_DIR" '
        '"$EVE_BOT_CONFIG" >> "$CALLS"\n'
    )
    executable.chmod(0o755)
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/run-demo.sh"), preset],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:" + os.environ["PATH"], "CALLS": str(output)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = output.read_text().splitlines()
    assert len(calls) == 3
    for line, command in zip(calls, ["check", "ingest", f"serve --host 0.0.0.0 --port {port}"]):
        assert line == (
            f"--root {ROOT} {command}|{ROOT}/examples/{preset}/data|"
            f"{ROOT}/storage/{preset}|{ROOT}/examples/{preset}/bot.yaml"
        )


def test_launcher_rejects_unknown_preset():
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/run-demo.sh"), "../private"], capture_output=True
    )
    assert result.returncode == 2
    assert b"Usage:" in result.stderr


def test_launcher_stops_when_configuration_fails(tmp_path):
    executable = tmp_path / "eve-ah"
    executable.write_text('#!/bin/sh\necho "$*"\nexit 1\n')
    executable.chmod(0o755)
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/run-demo.sh"), "amaze-on"],
        env={**os.environ, "PATH": f"{tmp_path}:" + os.environ["PATH"]},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stdout.strip().endswith(" check")
    assert "ingest" not in result.stdout
