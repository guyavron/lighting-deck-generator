"""B-08 (QA 21-22.10): כשהוספת תמונה מכתובת נכשלת, ההודעה בעברית ואומרת
מה לעשות — לא `<urlopen error [Errno 11001] getaddrinfo failed>`.
"""
import socket
import urllib.error

import pytest
from fastapi import HTTPException

import server as SRV

DRAG = "גרור"


def _fail_with(monkeypatch, exc):
    import urllib.request

    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(HTTPException) as e:
        SRV.photos_fetch(SRV.FetchSpec(url="https://example.com/a.jpg"))
    assert e.value.status_code == 400
    return e.value.detail


def _clean(detail):
    # שום טקסט טכני של פייתון לא מגיע לעובד
    for bad in ("getaddrinfo", "Errno", "urlopen", "Traceback", "timed out"):
        assert bad not in detail, detail


def test_no_internet_for_the_server_says_so_and_points_to_drag(monkeypatch):
    d = _fail_with(monkeypatch, urllib.error.URLError(
        socket.gaierror(11001, "getaddrinfo failed")))
    _clean(d)
    assert "אינטרנט" in d and DRAG in d


def test_a_timeout_says_the_site_did_not_answer(monkeypatch):
    d = _fail_with(monkeypatch, TimeoutError("timed out"))
    _clean(d)
    assert "לא ענה" in d and DRAG in d


def test_a_refusing_site_says_which_code_and_points_to_drag(monkeypatch):
    d = _fail_with(monkeypatch, urllib.error.HTTPError(
        "https://example.com/a.jpg", 403, "Forbidden", {}, None))
    _clean(d)
    assert "403" in d and DRAG in d


def test_a_missing_picture_says_it_was_not_found(monkeypatch):
    d = _fail_with(monkeypatch, urllib.error.HTTPError(
        "https://example.com/a.jpg", 404, "Not Found", {}, None))
    assert "לא נמצאה" in d and "404" in d


def test_any_other_failure_still_has_no_python_text(monkeypatch):
    d = _fail_with(monkeypatch, RuntimeError("weird internal thing"))
    assert "weird" not in d and DRAG in d
