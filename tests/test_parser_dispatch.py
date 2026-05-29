"""Verify parser dispatch by extension."""
from pathlib import Path

import pytest

from ingestion import parser_dispatch


def test_pdf_routes_to_parse_pdf(monkeypatch):
    called = {}

    def fake_pdf(path: Path):
        called["fn"] = "pdf"
        return path

    monkeypatch.setattr(parser_dispatch, "parse_pdf", fake_pdf)
    parser_dispatch.parse(Path("foo.pdf"))
    assert called["fn"] == "pdf"


def test_html_routes_to_parse_html(monkeypatch):
    called = {}
    monkeypatch.setattr(
        parser_dispatch, "parse_html", lambda p: called.update(fn="html") or p
    )
    parser_dispatch.parse(Path("a.html"))
    assert called["fn"] == "html"


def test_htm_routes_to_parse_html(monkeypatch):
    called = {}
    monkeypatch.setattr(
        parser_dispatch, "parse_html", lambda p: called.update(fn="html") or p
    )
    parser_dispatch.parse(Path("a.htm"))
    assert called["fn"] == "html"


def test_docx_routes_to_parse_docx(monkeypatch):
    called = {}
    monkeypatch.setattr(
        parser_dispatch, "parse_docx", lambda p: called.update(fn="docx") or p
    )
    parser_dispatch.parse(Path("a.docx"))
    assert called["fn"] == "docx"


def test_uppercase_extension_routes_correctly(monkeypatch):
    called = {}
    monkeypatch.setattr(
        parser_dispatch, "parse_pdf", lambda p: called.update(fn="pdf") or p
    )
    parser_dispatch.parse(Path("UPPER.PDF"))
    assert called["fn"] == "pdf"


def test_unsupported_extension_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        parser_dispatch.parse(Path("foo.txt"))


def test_no_extension_raises():
    with pytest.raises(ValueError):
        parser_dispatch.parse(Path("foo"))
