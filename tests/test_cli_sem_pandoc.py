"""Testes de ndoc2md.cli.main sem pandoc no PATH: o pandoc só é exigido por formato que passa por ele."""

from __future__ import annotations

import pytest
from conftest import make_odf

from ndoc2md import cli


@pytest.fixture
def sem_pandoc(monkeypatch):
    monkeypatch.setattr(cli, "have_pandoc", lambda: False)


def test_planilha_converte_sem_pandoc(tmp_path, sem_pandoc):
    make_odf(tmp_path, "p.ods", '<table:table table:name="A"><table:table-row>'
             "<table:table-cell><text:p>1</text:p></table:table-cell></table:table-row></table:table>")
    assert cli.main([str(tmp_path)]) == 0
    assert (tmp_path / "p.ods.md").exists()


def test_lote_com_docx_exige_pandoc(tmp_path, sem_pandoc, capsys):
    make_odf(tmp_path, "p.ods", '<table:table table:name="A"/>')
    (tmp_path / "a.docx").write_bytes(b"")
    assert cli.main([str(tmp_path)]) == 2
    assert "pandoc não encontrado" in capsys.readouterr().err
    assert not (tmp_path / "p.ods.md").exists()
