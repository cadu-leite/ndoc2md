"""Testes de ndoc2md.converter.gather: quais arquivos entram na lista e com qual raiz."""

from __future__ import annotations

from conftest import make_docx, requer_pandoc

from ndoc2md.converter import gather

pytestmark = requer_pandoc


def test_recursivo_encontra_arquivo_em_subpasta(tmp_path):
    make_docx(tmp_path / "sub", "b.docx", "# B\n\ntexto\n")
    achados = gather([str(tmp_path)])
    assert [f.name for f, _ in achados] == ["b.docx"]


def test_no_recursive_ignora_subpasta(tmp_path):
    make_docx(tmp_path, "a.docx", "# A\n\ntexto\n")
    make_docx(tmp_path / "sub", "b.docx", "# B\n\ntexto\n")
    achados = gather([str(tmp_path)], recursive=False)
    assert [f.name for f, _ in achados] == ["a.docx"]


def test_ignora_lock_file_do_word(tmp_path):
    docx = make_docx(tmp_path, "a.docx", "# A\n\ntexto\n")
    (tmp_path / "~$a.docx").write_text("lock")
    achados = gather([str(tmp_path)])
    assert [f for f, _ in achados] == [docx]


def test_raiz_de_arquivo_solto_e_a_propria_pasta(tmp_path):
    docx = make_docx(tmp_path, "a.docx", "# A\n\ntexto\n")
    [(f, raiz)] = gather([str(docx)])
    assert f == docx
    assert raiz == tmp_path


def test_raiz_de_pasta_e_a_pasta_de_entrada_mesmo_para_arquivo_aninhado(tmp_path):
    make_docx(tmp_path / "sub", "b.docx", "# B\n\ntexto\n")
    [(_, raiz)] = gather([str(tmp_path)])
    assert raiz == tmp_path


def test_mesmo_arquivo_com_grafias_de_caminho_diferentes_nao_duplica(tmp_path):
    docx = make_docx(tmp_path / "sub", "b.docx", "# B\n\ntexto\n")
    caminho_com_volta = tmp_path / "sub" / ".." / "sub" / "b.docx"
    achados = gather([str(docx), str(caminho_com_volta)])
    assert [f for f, _ in achados] == [docx]
