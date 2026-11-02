import pytest

from airfoileditor.model.xo2_driver import Worker, Xoptfoil2


@pytest.mark.parametrize("program_class", [Worker, Xoptfoil2])
@pytest.mark.parametrize("version, expected_ready", [("2.0.0", True), ("1.0.9", False)])
@pytest.mark.parametrize("colored", [False, True])
def test_program_version_detection(monkeypatch, tmp_path, program_class,
                                   version, expected_ready, colored):
    monkeypatch.setattr(program_class, "ready", False)
    monkeypatch.setattr(program_class, "version", "")
    monkeypatch.setattr(program_class, "ready_msg", "")
    monkeypatch.setattr(program_class, "exe_dir", str(tmp_path))
    program = program_class(workingDir=str(tmp_path))
    name = program_class.NAME
    header = (f"\x1b[94m {name}\x1b[0m                                 "
              f"\x1b[1;32m{version}\x1b[0m") if colored else f" {name} {version}"

    def execute(args, workingDir, capture_output):
        assert args == "-h"
        assert workingDir == str(tmp_path)
        assert capture_output
        program._pipe_out_lines = ["", header, "Usage information"]
        return 0

    monkeypatch.setattr(program, "_execute", execute)

    assert program.isReady(str(tmp_path), min_version="2.0.0") is expected_ready
    assert program.version == version
    if expected_ready:
        assert program.ready_msg == "Ready"
    else:
        assert program.ready_msg == f"wrong version {version} - need 2.0.0"
