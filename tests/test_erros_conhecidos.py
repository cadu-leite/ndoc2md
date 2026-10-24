"""Regressão para os bugs abertos, um por item.

Cada teste é marcado `xfail(strict=True)`: enquanto o bug segue aberto, o teste
falha do jeito esperado (xfailed).
Se o bug for corrigido, o teste passa e o `strict=True` transforma isso num erro
de suíte (XPASS) — sinal para remover o marcador e mover o item para "resolvido".
"""

from __future__ import annotations

import pytest
from conftest import make_docx, make_docx_with_image, requer_pandoc, requer_pdf

from ndoc2md.converter import ConversionError, convert_file, gather, strip_toc
from ndoc2md.cli import main

pytestmark = requer_pandoc


# Erro 1 (-o com duas raízes sobrescreve homônimo) foi resolvido em 2026-09-11 —
# ver test_cli.py::test_colisao_entre_raizes_e_barrada_antes_de_converter.

# Erro 3 (caminho inexistente sai da lista sem aviso) foi resolvido em 2026-09-12 —
# ver test_cli.py::test_caminho_inexistente_barra_a_conversao_do_lote.


@pytest.mark.xfail(strict=True, reason="erro 4: pasta legítima terminada em _media fica invisível")
def test_erro_4_pasta_social_media_nao_e_ignorada(tmp_path):
    pasta = tmp_path / "social_media"
    make_docx(pasta, "c.docx", "# C\n\ntexto\n")
    achados = gather([str(pasta)])
    assert len(achados) == 1


@pytest.mark.xfail(strict=True, reason="erro 5: mídia relatada pela existência da pasta, não pelo conteúdo")
def test_erro_5_pasta_de_midia_vazia_nao_e_relatada(tmp_path):
    docx = make_docx(tmp_path, "doc.docx", "# T\n\ntexto sem imagem\n")
    orfa = tmp_path / "doc.docx_media"
    orfa.mkdir()
    (orfa / "orfao.png").write_text("x")

    res = convert_file(docx, overwrite=True)
    assert res.media_dir is None


@pytest.mark.xfail(strict=True, reason="erro 6: mídia obsoleta sobrevive ao --overwrite")
def test_erro_6_midia_obsoleta_e_removida_no_overwrite(tmp_path):
    docx = make_docx(tmp_path, "doc.docx", "# T\n\ntexto sem imagem\n")
    media = tmp_path / "doc.docx_media"
    media.mkdir()
    orfao = media / "orfao.png"
    orfao.write_text("x")

    convert_file(docx, overwrite=True)
    assert not orfao.exists()


@pytest.mark.xfail(strict=True, reason="erro 7: --clean-toc colapsa linha em branco dentro de bloco de código")
def test_erro_7_strip_toc_preserva_blocos_de_codigo():
    cerca = "`" * 3
    md = f"# T\n\n{cerca}python\na = 1\n\n\n\nb = 2\n{cerca}\n"
    limpo, _ = strip_toc(md)
    assert "a = 1\n\n\n\nb = 2" in limpo


@pytest.mark.xfail(strict=True, reason="erro 9: exit 1 serve tanto para 'nada encontrado' quanto para 'falha'")
def test_erro_9_codigos_de_saida_distintos_para_vazio_e_falha(tmp_path):
    pasta_vazia = tmp_path / "pasta_vazia"
    pasta_vazia.mkdir()  # existe, mas não tem nenhum arquivo suportado — não confundir com o erro 3
    vazio = main([str(pasta_vazia)])

    ruim = tmp_path / "ruim.docx"
    ruim.write_bytes(b"nao e um docx de verdade")
    falha = main([str(ruim), "--overwrite"])

    assert vazio != falha


@pytest.mark.xfail(strict=True, reason="erro 10: relative_to lança ValueError cru em vez de ConversionError")
def test_erro_10_input_root_fora_da_arvore_vira_conversion_error(tmp_path):
    docx = make_docx(tmp_path, "a.docx", "# A\n\ntexto\n")
    with pytest.raises(ConversionError):
        convert_file(docx, tmp_path / "saida", input_root="/etc", overwrite=True)


# Erro 11 (--no-media no .docx deixa o link de imagem quebrado) foi resolvido em 2026-09-12 —
# ver test_converter.py::test_no_media_nao_deixa_link_de_imagem_quebrado.


@pytest.mark.xfail(strict=True, reason="erro 17: .docx sai com <img> HTML em vez de ![]()")
def test_erro_17_docx_usa_sintaxe_markdown_para_imagem(tmp_path):
    docx = make_docx_with_image(tmp_path, "doc.docx")
    res = convert_file(docx, overwrite=True)
    conteudo = res.output.read_text(encoding="utf-8")
    assert "<img" not in conteudo


@pytest.mark.xfail(strict=True, reason="erro 20: título do sumário sobrevive ao --clean-toc quando a seção fica vazia")
def test_erro_20_titulo_do_sumario_e_removido_quando_fica_vazio():
    md = "# Sumario\n\n[Termos [2](#termos)](#termos)\n\n# Termos\n\ncorpo.\n"
    limpo, _ = strip_toc(md)
    assert "# Sumario" not in limpo


@pytest.mark.xfail(strict=True, reason="erro 21: SUPPORTED_EXTENSIONS é set mutável e exportado")
def test_erro_21_supported_extensions_e_imutavel():
    import ndoc2md
    from ndoc2md.converter import SUPPORTED_EXTENSIONS as interno

    try:
        with pytest.raises((AttributeError, TypeError)):
            ndoc2md.SUPPORTED_EXTENSIONS.add(".exe")
        assert ".exe" not in interno
    finally:
        ndoc2md.SUPPORTED_EXTENSIONS.discard(".exe")


# Erro 12, parte "sem aviso", foi resolvido em 2026-09-12 — ver
# test_pdf.py::test_desenho_vetorial_isolado_gera_aviso. A parte "é descartado" continua
# em aberto (o pymupdf4llm não extrai forma vetorial isolada, e não dá pra contornar sem
# reimplementar a heurística dele) — por isso o teste abaixo, que cobra a extração em si,
# segue xfail.


