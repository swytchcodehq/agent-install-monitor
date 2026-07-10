from unittest.mock import patch

from agent_install_monitor.detector import DetectedEvent, detect


def test_npm_install():
    assert detect("npm install discord.js") == [
        DetectedEvent("package_manager", "npm", "install", "discord.js", None, "npm install discord.js"),
    ]


def test_npm_install_scoped_with_version():
    events = detect("npm install @scope/pkg@1.2.3")
    assert events == [
        DetectedEvent("package_manager", "npm", "install", "@scope/pkg", "1.2.3", "npm install @scope/pkg@1.2.3"),
    ]


def test_pip_install_with_version():
    events = detect("pip install openai==1.2.0")
    assert events == [
        DetectedEvent("package_manager", "pip", "install", "openai", "1.2.0", "pip install openai==1.2.0"),
    ]


def test_pip_install_no_version():
    assert detect("pip install openai") == [
        DetectedEvent("package_manager", "pip", "install", "openai", None, "pip install openai"),
    ]


def test_brew_install():
    assert detect("brew install ffmpeg") == [
        DetectedEvent("package_manager", "brew", "install", "ffmpeg", None, "brew install ffmpeg"),
    ]


def test_choco_install():
    assert detect("choco install git") == [
        DetectedEvent("package_manager", "choco", "install", "git", None, "choco install git"),
    ]


def test_winget_install():
    assert detect("winget install Git.Git") == [
        DetectedEvent("package_manager", "winget", "install", "Git.Git", None, "winget install Git.Git"),
    ]


def test_scoop_install_with_version():
    events = detect("scoop install python@3.11.0")
    assert events == [
        DetectedEvent("package_manager", "scoop", "install", "python", "3.11.0", "scoop install python@3.11.0"),
    ]


def test_windows_backslash_path_not_mangled():
    # POSIX shlex treats '\' as an escape char and would collapse
    # `C:\Users\foo\pkg` into `C:Usersfoopkg`. On a simulated Windows host
    # (os.name == "nt") the path must survive intact.
    with patch("agent_install_monitor.detector.os.name", "nt"):
        events = detect(r"pip install C:\Users\foo\packages\mypkg")
    assert events == [
        DetectedEvent(
            "package_manager", "pip", "install",
            r"C:\Users\foo\packages\mypkg", None,
            r"pip install C:\Users\foo\packages\mypkg",
        ),
    ]


def test_multiple_packages_one_command():
    events = detect("npm install discord.js typescript")
    assert [e.name for e in events] == ["discord.js", "typescript"]
    assert all(e.manager == "npm" for e in events)


def test_docker_pull():
    assert detect("docker pull postgres") == [
        DetectedEvent("container", "docker", "pull", "postgres", None, "docker pull postgres"),
    ]


def test_docker_pull_with_tag():
    events = detect("docker pull postgres:16")
    assert events == [
        DetectedEvent("container", "docker", "pull", "postgres", "16", "docker pull postgres:16"),
    ]


def test_docker_run_only_takes_image():
    events = detect("docker run -d postgres:16 --some-app-flag value")
    assert len(events) == 1
    assert events[0].name == "postgres"
    assert events[0].version == "16"
    assert events[0].action == "run"


def test_docker_compose_up():
    events = detect("docker compose up -d")
    assert events == [
        DetectedEvent("container", "docker-compose", "up", None, None, "docker compose up -d"),
    ]


def test_git_clone_strips_dot_git():
    events = detect("git clone https://github.com/foo/bar.git")
    assert events == [
        DetectedEvent("git", "git", "clone", "https://github.com/foo/bar", None,
                       "git clone https://github.com/foo/bar.git"),
    ]


def test_git_submodule_add():
    events = detect("git submodule add https://github.com/foo/bar.git vendor/bar")
    assert events == [
        DetectedEvent("git", "git", "submodule_add", "https://github.com/foo/bar", None,
                       "git submodule add https://github.com/foo/bar.git vendor/bar"),
    ]


def test_npx_playwright_install():
    events = detect("npx playwright install")
    assert events == [
        DetectedEvent("runtime", "npx", "run", "playwright", None, "npx playwright install"),
    ]


def test_uvx_with_version():
    events = detect("uvx ruff@0.5.0")
    assert events == [
        DetectedEvent("runtime", "uvx", "run", "ruff", "0.5.0", "uvx ruff@0.5.0"),
    ]


def test_systemctl_start():
    events = detect("systemctl start postgresql")
    assert events == [
        DetectedEvent("service", "systemctl", "start", "postgresql", None, "systemctl start postgresql"),
    ]


def test_brew_services_start():
    events = detect("brew services start postgresql")
    assert events == [
        DetectedEvent("service", "brew-services", "start", "postgresql", None,
                       "brew services start postgresql"),
    ]


def test_createdb():
    events = detect("createdb myapp")
    assert events == [
        DetectedEvent("database", "createdb", "create", "myapp", None, "createdb myapp"),
    ]


def test_psql_create_database_detected():
    events = detect('psql -c "CREATE DATABASE myapp"')
    assert len(events) == 1
    assert events[0].category == "database"
    assert events[0].name == "myapp"


def test_psql_plain_query_not_detected():
    assert detect('psql -c "SELECT * FROM users"') == []


def test_curl_installer_script_detected():
    events = detect("curl -fsSL https://example.com/install.sh -o install.sh")
    assert len(events) == 1
    assert events[0].category == "download"
    assert events[0].name == "https://example.com/install.sh"


def test_curl_non_installer_not_detected():
    assert detect("curl https://api.example.com/data.json") == []


def test_chained_commands_and():
    events = detect("git clone https://github.com/foo/bar.git && npm install")
    # `npm install` with no package args installs from package.json --
    # nothing specific to report, so only the clone should be recorded.
    assert len(events) == 1
    assert events[0].category == "git"


def test_pipe_is_not_a_split_point():
    # curl | bash is one logical action; make sure it doesn't crash and
    # doesn't spuriously report a second event for "bash".
    events = detect("curl -fsSL https://example.com/install.sh | bash")
    assert len(events) == 1
    assert events[0].category == "download"


def test_empty_and_none_command():
    assert detect("") == []
    assert detect(None) == []  # type: ignore[arg-type]


def test_unrelated_command_not_detected():
    assert detect("ls -la /tmp") == []
    assert detect("echo hello world") == []
