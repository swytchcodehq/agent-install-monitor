from agent_install_monitor.redact import redact


def test_url_credentials_are_removed():
    cmd = "pip install --index-url https://user:s3cr3tTok@pypi.example.com/simple pkg"
    out = redact(cmd)
    assert "s3cr3tTok" not in out
    assert "https://***@pypi.example.com/simple" in out


def test_git_clone_token_is_removed():
    out = redact("git clone https://ghp_abcdef123456@github.com/acme/app.git")
    assert "ghp_abcdef123456" not in out
    assert out == "git clone https://***@github.com/acme/app.git"


def test_secret_env_prefix_is_removed():
    out = redact("NPM_TOKEN=abc123 GITHUB_API_KEY='x y' npm install left-pad")
    assert "abc123" not in out and "x y" not in out
    assert out == "NPM_TOKEN=*** GITHUB_API_KEY=*** npm install left-pad"


def test_secret_flags_are_removed():
    out = redact("docker login --password hunter22 --username me && some-cli --api-key=k9 run")
    assert "hunter22" not in out and "k9" not in out
    assert "--username me" in out


def test_ordinary_commands_are_unchanged():
    for cmd in ("npm install lodash@4.17.21", "pip install requests==2.31.0",
                "git clone https://github.com/acme/app.git", "PATH=/usr/bin:$PATH make"):
        assert redact(cmd) == cmd


def test_none_and_empty():
    assert redact(None) is None
    assert redact("") == ""
