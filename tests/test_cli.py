"""Testes de ndoc2md.cli.main: código de saída e --dry-run."""

from __future__ import annotations

from conftest import make_docx, requer_pandoc

from ndoc2md.cli import main

pytestmark = requer_pandoc


def test_dry_run_lista_sem_escrever_md(tmp_path, capsys):
    docx = make_docx(tmp_path, "a.docx", "# A\n\ntexto\n")
    codigo = main([str(tmp_path), "--dry-run"])
    saida = capsys.readouterr().out
    assert codigo == 0
    assert docx.name in saida
    assert not (tmp_path / "a.docx.md").exists()


def test_conversao_bem_sucedida_retorna_zero(tmp_path):
    make_docx(tmp_path, "a.docx", "# A\n\ntexto\n")
    codigo = main([str(tmp_path), "--overwrite"])
    assert codigo == 0
    assert (tmp_path / "a.docx.md").exists()


def test_nenhum_arquivo_suportado_retorna_diferente_de_zero(tmp_path):
    codigo = main([str(tmp_path)])
    assert codigo != 0


def test_colisao_entre_raizes_e_barrada_antes_de_converter(tmp_path, capsys):
    """Erro 1 do docs/erros-conhecidos.md, resolvido: alerta e não converte nada do lote."""
    make_docx(tmp_path / "r1", "a.docx", "# UM\n\nconteudo um\n")
    make_docx(tmp_path / "r2", "a.docx", "# DOIS\n\nconteudo dois\n")
    saida = tmp_path / "saida"

    codigo = main([str(tmp_path / "r1"), str(tmp_path / "r2"), "-o", str(saida), "--overwrite"])
    erro = capsys.readouterr().err

    assert codigo != 0
    assert "renomeie" in erro.lower()
    assert not saida.exists()


def test_caminho_inexistente_barra_a_conversao_do_lote(tmp_path, capsys):
    """Erro 3 do docs/erros-conhecidos.md, resolvido: nenhum caminho pode faltar, nem os que existem convertem."""
    docx = make_docx(tmp_path, "a.docx", "# A\n\ntexto\n")
    inexistente = tmp_path / "NAO_EXISTE.docx"

    codigo = main([str(docx), str(inexistente), "--overwrite"])
    erro = capsys.readouterr().err

    assert codigo != 0
    assert str(inexistente) in erro
    assert not (tmp_path / "a.docx.md").exists()
