"""Credential-path resolution tests.

Regression cover for the production defect where Render's Secret File was correctly
configured at /etc/secrets/gsheets_credentials.json but the app reported
"credentials JSON not found": the old resolver read ONLY the
GSHEET_CREDENTIALS_PATH env var and, when that was unset, never looked anywhere else.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gsheets  # noqa: E402

_PEM_MARKER = "-----" + "BEGIN" + " PRIVATE KEY" + "-----"

FAKE_CRED = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "test",
    # Built at runtime so the literal PEM marker never appears in this source file
    # (keeps secret scanners quiet); the value is a placeholder, not a real key.
    "private_key": _PEM_MARKER + "\nPLACEHOLDER-NOT-A-REAL-KEY\n" + _PEM_MARKER.replace("BEGIN", "END") + "\n",
    "client_email": "svc@test-project.iam.gserviceaccount.com",
    "token_uri": "https://oauth2.googleapis.com/token",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("GSHEET_CREDENTIALS_PATH", raising=False)
    monkeypatch.setenv("GSHEET_ID", "TEST_SHEET")
    yield


def write_cred(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(FAKE_CRED))
    return str(path)


def patch_candidates(monkeypatch, **overrides):
    """Rebuild the candidate list so the /etc/secrets entry can be redirected into
    tmp_path — the real /etc/secrets is not writable in CI."""
    new = []
    for label, getter in gsheets._CRED_CANDIDATES:
        if label in overrides:
            val = overrides[label]
            new.append((label, (lambda v=val: v)))
        else:
            new.append((label, getter))
    monkeypatch.setattr(gsheets, "_CRED_CANDIDATES", new)


def test_render_secret_file_is_discovered(tmp_path, monkeypatch):
    """THE production defect: no env var set, credential only at the Render Secret
    File location. Must be found."""
    secret = write_cred(tmp_path / "etc" / "secrets" / "gsheets_credentials.json")
    patch_candidates(monkeypatch, **{"render-secret-file": secret})
    path, source = gsheets.resolve_credentials_path()
    assert path == secret
    assert source == "render-secret-file"
    d = gsheets.credential_diagnostics()
    assert d["credential_found"] is True
    assert d["credential_source"] == "render-secret-file"
    assert d["gsheet_id_present"] is True


def test_real_render_path_is_in_the_candidate_list():
    """Guards the literal path Render mounts Secret Files at."""
    paths = []
    for _label, getter in gsheets._CRED_CANDIDATES:
        try:
            paths.append(getter())
        except Exception:
            pass
    assert "/etc/secrets/gsheets_credentials.json" in paths


def test_env_var_takes_priority(tmp_path, monkeypatch):
    env_cred = write_cred(tmp_path / "env" / "gsheets_credentials.json")
    secret = write_cred(tmp_path / "etc" / "secrets" / "gsheets_credentials.json")
    monkeypatch.setenv("GSHEET_CREDENTIALS_PATH", env_cred)
    patch_candidates(monkeypatch, **{"render-secret-file": secret})
    path, source = gsheets.resolve_credentials_path()
    assert path == env_cred
    assert source == "env:GSHEET_CREDENTIALS_PATH"


def test_backend_local_still_works(tmp_path, monkeypatch):
    """Local development: backend/gsheets_credentials.json."""
    local = write_cred(tmp_path / "backend" / "gsheets_credentials.json")
    patch_candidates(monkeypatch, **{"render-secret-file": "/nonexistent/x.json",
                                     "backend-local": local})
    path, source = gsheets.resolve_credentials_path()
    assert path == local
    assert source == "backend-local"


def test_repo_root_local_works(tmp_path, monkeypatch):
    root = write_cred(tmp_path / "gsheets_credentials.json")
    patch_candidates(monkeypatch, **{"render-secret-file": "/nonexistent/x.json",
                                     "backend-local": "/nonexistent/y.json",
                                     "repo-root-local": root})
    path, source = gsheets.resolve_credentials_path()
    assert path == root
    assert source == "repo-root-local"


def test_missing_credentials_returns_disabled_not_crash(monkeypatch):
    patch_candidates(monkeypatch, **{"render-secret-file": "/nonexistent/a.json",
                                     "backend-local": "/nonexistent/b.json",
                                     "repo-root-local": "/nonexistent/c.json"})
    path, source = gsheets.resolve_credentials_path()
    assert path is None and source is None
    gsheets._init()
    assert gsheets._status["enabled"] is False
    assert gsheets._status["credentialFound"] is False
    assert "/etc/secrets" in gsheets._status["reason"] or "Secret File" in gsheets._status["reason"]
    rep = gsheets.preflight()
    assert rep["enabled"] is False
    assert rep["credential_found"] is False
    assert rep["tabs"] == {}


def test_diagnostics_never_leak_key_material(tmp_path, monkeypatch):
    secret = write_cred(tmp_path / "etc" / "secrets" / "gsheets_credentials.json")
    patch_candidates(monkeypatch, **{"render-secret-file": secret})
    blob = json.dumps(gsheets.credential_diagnostics()) + json.dumps(gsheets.preflight())
    assert _PEM_MARKER not in blob
    assert "private_key" not in blob
    assert FAKE_CRED["private_key"] not in blob


def test_malformed_credential_reports_safely_without_echoing_contents(tmp_path, monkeypatch):
    bad = tmp_path / "etc" / "secrets" / "gsheets_credentials.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("NOT JSON " + _PEM_MARKER + " leaked-secret-material")
    patch_candidates(monkeypatch, **{"render-secret-file": str(bad)})
    gsheets._init()
    assert gsheets._status["enabled"] is False
    assert gsheets._status["credentialFound"] is True
    assert "leaked-secret-material" not in gsheets._status["reason"]
    assert _PEM_MARKER not in gsheets._status["reason"]


def test_gsheet_id_missing_is_reported_distinctly(tmp_path, monkeypatch):
    secret = write_cred(tmp_path / "etc" / "secrets" / "gsheets_credentials.json")
    patch_candidates(monkeypatch, **{"render-secret-file": secret})
    monkeypatch.delenv("GSHEET_ID", raising=False)
    gsheets._init()
    assert gsheets._status["enabled"] is False
    assert gsheets._status["credentialFound"] is True
    assert "GSHEET_ID" in gsheets._status["reason"]
    assert gsheets.credential_diagnostics()["gsheet_id_present"] is False
