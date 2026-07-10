import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from bump_version import bump  # noqa: E402


def _write_pyproject(tmp_path, version):
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "x"\nversion = "{version}"\ndependencies = []\n')
    return path


def test_bump_patch(tmp_path):
    path = _write_pyproject(tmp_path, "1.2.3")
    assert bump("patch", path) == "1.2.4"
    assert 'version = "1.2.4"' in path.read_text()


def test_bump_minor_resets_patch(tmp_path):
    path = _write_pyproject(tmp_path, "1.2.3")
    assert bump("minor", path) == "1.3.0"


def test_bump_major_resets_minor_and_patch(tmp_path):
    path = _write_pyproject(tmp_path, "1.2.3")
    assert bump("major", path) == "2.0.0"


def test_unknown_part_raises(tmp_path):
    path = _write_pyproject(tmp_path, "1.2.3")
    try:
        bump("bogus", path)
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "bogus" in str(e)


def test_missing_version_line_raises(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "x"\n')
    try:
        bump("patch", path)
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "version" in str(e)


def test_only_touches_version_line(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\ndescription = "has version in it too"\n'
    )
    bump("patch", path)
    text = path.read_text()
    assert 'version = "1.2.4"' in text
    assert 'description = "has version in it too"' in text
