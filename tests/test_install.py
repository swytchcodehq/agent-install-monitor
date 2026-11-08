import importlib.util
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "install.py"


@pytest.fixture
def install(monkeypatch):
    spec = importlib.util.spec_from_file_location("install_under_test", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.calls = []
    return mod


def _fake_pip(mod, fail_on=()):
    def pip(venv, spec):
        mod.calls.append(spec)
        if any(spec.startswith(f) for f in fail_on):
            raise subprocess.CalledProcessError(1, ["pip", "install", spec])
    return pip


def test_auto_uses_pypi_first(install):
    install._pip = _fake_pip(install)
    assert install.pip_install(Path("/venv"), "auto") == "PyPI"
    assert install.calls == [f"agent-install-monitor=={install.VERSION}"]


def test_auto_falls_back_to_github(install):
    install._pip = _fake_pip(install, fail_on=("agent-install-monitor==",))
    assert install.pip_install(Path("/venv"), "auto") == "GitHub"
    assert install.calls[-1] == (
        f"https://github.com/swytchcodehq/agent-install-monitor/archive/refs/tags/v{install.VERSION}.tar.gz"
    )


def test_github_only_skips_pypi(install):
    install._pip = _fake_pip(install)
    assert install.pip_install(Path("/venv"), "github") == "GitHub"
    assert len(install.calls) == 1 and install.calls[0].startswith("https://github.com/")


def test_pypi_only_stops_when_pypi_fails(install):
    install._pip = _fake_pip(install, fail_on=("agent-install-monitor==",))
    with pytest.raises(SystemExit):
        install.pip_install(Path("/venv"), "pypi")
    assert len(install.calls) == 1


def test_versions_match():
    root = _PATH.parent
    import re
    versions = {
        "pyproject.toml": re.search(r'(?m)^version = "([^"]+)"', (root / "pyproject.toml").read_text()).group(1),
        "__init__.py": re.search(r'(?m)^__version__ = "([^"]+)"',
                                 (root / "src" / "agent_install_monitor" / "__init__.py").read_text()).group(1),
        "install.py": re.search(r'(?m)^VERSION = "([^"]+)"', _PATH.read_text()).group(1),
    }
    assert len(set(versions.values())) == 1, versions
