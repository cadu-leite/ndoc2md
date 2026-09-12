"""Testes de ndoc2md.converter.convert_file e have_pandoc: comportamento hoje correto."""

from __future__ import annotations

import pytest
from conftest import make_docx, make_docx_with_image, requer_pandoc

from ndoc2md.converter import (
    ConversionError,
    check_path,
    convert_file,
    find_collisions,
    gather,
    have_pandoc,
)

pytestmark = requer_pandoc


def test_have_pandoc_true_no_ambiente_de_teste():
    assert have_pandoc() is True


def test_convert_file_gera_md_ao_lado_do_original(basic_docx):
    res = convert_file(basic_docx, overwrite=True)
    assert res.output == basic_docx.parent / "doc.docx.md"
    assert res.engine == "pandoc"
    conteudo = res.output.read_text(encoding="utf-8")
    assert "# Titulo 1" in conteudo
    assert "## Titulo 2" in conteudo


def test_extensao_nao_suportada_leva_a_conversion_error(tmp_path):
    alheio = tmp_path / "arquivo.xyz"
    alheio.write_text("qualquer coisa")
    with pytest.raises(ConversionError):
        convert_file(alheio)


def test_arquivo_inexistente_leva_a_conversion_error(tmp_path):
    with pytest.raises(ConversionError):
        convert_file(tmp_path / "nao_existe.docx")


def test_sem_overwrite_nao_sobrescreve_md_existente(basic_docx):
    convert_file(basic_docx, overwrite=True)
    with pytest.raises(ConversionError):
        convert_file(basic_docx, overwrite=False)


def test_overwrite_sobrescreve_md_existente(basic_docx):
    convert_file(basic_docx, overwrite=True)
    res = convert_file(basic_docx, overwrite=True)
    assert res.output.exists()


def test_extensoes_diferentes_mesmo_nome_nao_colidem(tmp_path):
    """Erro 2 do docs/erros-conhecidos.md, resolvido: a extensão de origem entra no nome do .md."""
    make_docx(tmp_path, "rel.docx", "# UM\n\nconteudo docx\n")
    html = tmp_path / "rel.html"
    html.write_text("<h1>DOIS</h1><p>conteudo html</p>", encoding="utf-8")

    for f, raiz in gather([str(tmp_path)]):
        convert_file(f, input_root=raiz, overwrite=True)

    docx_md = (tmp_path / "rel.docx.md").read_text(encoding="utf-8")
    html_md = (tmp_path / "rel.html.md").read_text(encoding="utf-8")
    assert "UM" in docx_md
    assert "DOIS" in html_md


def test_espelha_arvore_com_uma_raiz_sob_output_dir(tmp_path):
    entrada = tmp_path / "entrada"
    make_docx(entrada, "a.docx", "# A\n\ntexto\n")
    make_docx(entrada / "sub", "b.docx", "# B\n\ntexto\n")
    saida = tmp_path / "saida"

    for f, raiz in gather([str(entrada)]):
        convert_file(f, saida, input_root=raiz, overwrite=True)

    assert (saida / "a.docx.md").exists()
    assert (saida / "sub" / "b.docx.md").exists()


def test_find_collisions_detecta_duas_raizes_com_mesmo_nome(tmp_path):
    """Erro 1 do docs/erros-conhecidos.md, resolvido: duas raízes com `a.docx` colidem sob -o."""
    make_docx(tmp_path / "r1", "a.docx", "# UM\n\nconteudo um\n")
    make_docx(tmp_path / "r2", "a.docx", "# DOIS\n\nconteudo dois\n")
    saida = tmp_path / "saida"

    achados = gather([str(tmp_path / "r1"), str(tmp_path / "r2")])
    colisoes = find_collisions(achados, saida)

    assert list(colisoes.keys()) == [saida / "a.docx.md"]
    [origens] = colisoes.values()
    assert {p.parent.name for p in origens} == {"r1", "r2"}


def test_find_collisions_vazio_quando_destinos_sao_distintos(tmp_path):
    entrada = tmp_path / "entrada"
    make_docx(entrada, "a.docx", "# A\n\ntexto\n")
    make_docx(entrada / "sub", "b.docx", "# B\n\ntexto\n")

    achados = gather([str(entrada)])
    assert find_collisions(achados, tmp_path / "saida") == {}


def test_check_path_nao_reclama_quando_tudo_existe(basic_docx):
    check_path([str(basic_docx), str(basic_docx.parent)])


def test_check_path_lanca_conversion_error_listando_os_ausentes(tmp_path):
    """Erro 3 do docs/erros-conhecidos.md, resolvido: caminho inexistente para a execução."""
    docx = make_docx(tmp_path, "a.docx", "# A\n\ntexto\n")
    inexistente = tmp_path / "NAO_EXISTE.docx"

    with pytest.raises(ConversionError, match=str(inexistente)):
        check_path([str(docx), str(inexistente)])


def test_no_media_nao_deixa_link_de_imagem_quebrado(tmp_path):
    """Erro 11 do docs/erros-conhecidos.md, resolvido: a imagem some, sem link órfão."""
    docx = make_docx_with_image(tmp_path, "doc.docx")
    res = convert_file(docx, extract_media=False, overwrite=True)
    conteudo = res.output.read_text(encoding="utf-8")

    assert "media/" not in conteudo
    assert "<img" not in conteudo
    assert res.media_dir is None
