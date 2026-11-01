"""Testes de ndoc2md.formatos.apresentacao: `.odp` e `.sxi`, lidos direto do XML.

O XML dos slides segue o que o Impress grava (conferido num `.odp` salvo pelo
LibreOffice 24.2): título em `presentation:class="title"`, cada item de primeiro
nível numa `text:list` própria, prévia `.svm` depois da tabela, notas em
`presentation:notes`.
"""

from __future__ import annotations

import pytest
from conftest import make_odf, png_bytes

from ndoc2md.converter import ConversionError, convert_file

TITULO = (
    '<draw:frame presentation:class="title"><draw:text-box>'
    "<text:p><text:span>{}</text:span></text:p></draw:text-box></draw:frame>"
)

SLIDES_ODP = (
    '<draw:page draw:name="capa">'
    + TITULO.format("Relatório trimestral")
    + '<draw:frame presentation:class="subtitle"><draw:text-box>'
    "<text:p>Ação<text:s text:c=\"3\"/>e coração</text:p></draw:text-box></draw:frame>"
    '<draw:frame presentation:class="page-number"><draw:text-box>'
    "<text:p><text:page-number>1</text:page-number></text:p></draw:text-box></draw:frame>"
    '<draw:frame presentation:class="outline" presentation:placeholder="true">'
    "<draw:text-box/></draw:frame>"
    "</draw:page>"
    '<draw:page draw:name="resultados">'
    + TITULO.format("Resultados")
    + '<draw:frame presentation:class="outline"><draw:text-box>'
    "<text:list><text:list-item><text:p>Receita subiu</text:p></text:list-item></text:list>"
    "<text:list><text:list-item><text:list><text:list-item>"
    "<text:p>Mercado interno</text:p></text:list-item></text:list></text:list-item></text:list>"
    "<text:list><text:list-item><text:p>Custos estáveis</text:p></text:list-item></text:list>"
    "</draw:text-box></draw:frame>"
    '<draw:frame><draw:image xlink:href="Pictures/grafico.png"><text:p/></draw:image>'
    "<svg:title>Gráfico de receita</svg:title></draw:frame>"
    "<draw:custom-shape><text:p>Caixa livre<text:line-break/>segunda linha</text:p>"
    "<draw:enhanced-geometry/></draw:custom-shape>"
    "<draw:frame><table:table><table:table-column/><table:table-column/>"
    "<table:table-row><table:table-cell><text:p>Mês</text:p></table:table-cell>"
    "<table:table-cell><text:p>Valor</text:p></table:table-cell></table:table-row>"
    "<table:table-row><table:table-cell><text:p>Jan</text:p></table:table-cell>"
    "<table:table-cell><text:p>10 | 20</text:p></table:table-cell></table:table-row>"
    '</table:table><draw:image xlink:href="Pictures/TablePreview1.svm"/></draw:frame>'
    "<presentation:notes>"
    '<draw:page-thumbnail presentation:class="page"/>'
    '<draw:frame presentation:class="notes"><draw:text-box>'
    "<text:p>Citar a fonte.</text:p></draw:text-box></draw:frame>"
    "</presentation:notes>"
    "</draw:page>"
)
ARQUIVOS_ODP = {"Pictures/grafico.png": png_bytes(), "Pictures/TablePreview1.svm": b"svm"}


@pytest.fixture
def odp(tmp_path):
    return make_odf(tmp_path, "apres.odp", SLIDES_ODP, arquivos=ARQUIVOS_ODP)


def test_slide_vira_secao_com_titulo(odp):
    res = convert_file(odp)
    md = res.output.read_text(encoding="utf-8")

    assert res.output == odp.parent / "apres.odp.md"
    assert res.engine == "odf"
    assert res.paginas == 2
    assert md.startswith("## Slide 1: Relatório trimestral\n\nAção   e coração\n\n## Slide 2: Resultados\n")


def test_placeholder_vazio_e_numero_de_pagina_ficam_fora(odp):
    md = convert_file(odp).output.read_text(encoding="utf-8")
    secao_1 = md.split("## Slide 2")[0]
    assert secao_1 == "## Slide 1: Relatório trimestral\n\nAção   e coração\n\n"


def test_listas_vizinhas_viram_uma_lista_aninhada(odp):
    md = convert_file(odp).output.read_text(encoding="utf-8")
    assert "- Receita subiu\n    - Mercado interno\n- Custos estáveis\n" in md


def test_imagem_copiada_com_texto_alternativo(odp):
    res = convert_file(odp)
    md = res.output.read_text(encoding="utf-8")

    assert "![Gráfico de receita](apres.odp_media/grafico.png)" in md
    assert res.media_dir == odp.parent / "apres.odp_media"
    assert sorted(p.name for p in res.media_dir.iterdir()) == ["grafico.png"]


def test_tabela_vira_gfm_sem_a_previa_svm(odp):
    md = convert_file(odp).output.read_text(encoding="utf-8")
    assert "| Mês | Valor |\n|-----|-------|\n| Jan | 10 \\| 20 |" in md
    assert "svm" not in md


def test_forma_com_texto_e_quebra_de_linha(odp):
    md = convert_file(odp).output.read_text(encoding="utf-8")
    assert "Caixa livre\nsegunda linha" in md


def test_notas_do_apresentador_no_fim_do_slide(odp):
    md = convert_file(odp).output.read_text(encoding="utf-8")
    assert md.endswith("**Notas do apresentador:**\n\nCitar a fonte.\n")


def test_no_media_tira_a_imagem_sem_criar_pasta(odp):
    res = convert_file(odp, extract_media=False)
    md = res.output.read_text(encoding="utf-8")

    assert "![" not in md
    assert res.media_dir is None
    assert not (odp.parent / "apres.odp_media").exists()


def test_placeholder_com_texto_entra(tmp_path):
    """Nos modelos do Impress (ex.: Grey_Elegant.otp), o título é placeholder e tem texto."""
    corpo = (
        '<draw:page><draw:frame presentation:class="title" presentation:placeholder="true">'
        "<draw:text-box><text:p>Grey Elegant</text:p></draw:text-box></draw:frame>"
        '<draw:frame presentation:class="subtitle" presentation:placeholder="true">'
        "<draw:text-box><text:p>Lorem Ipsum</text:p></draw:text-box></draw:frame></draw:page>"
    )
    odp = make_odf(tmp_path, "m.odp", corpo)
    md = convert_file(odp).output.read_text(encoding="utf-8")
    assert md == "## Slide 1: Grey Elegant\n\nLorem Ipsum\n"


def test_slide_oculto_e_marcado(tmp_path):
    estilos = (
        '<style:style style:name="dp1" style:family="drawing-page">'
        '<style:drawing-page-properties presentation:visibility="hidden"/></style:style>'
    )
    odp = make_odf(
        tmp_path, "o.odp",
        '<draw:page draw:style-name="dp1">' + TITULO.format("Rascunho") + "</draw:page>",
        estilos=estilos,
    )
    md = convert_file(odp).output.read_text(encoding="utf-8")
    assert md == "## Slide 1 (oculto): Rascunho\n"


def test_slide_sem_titulo(tmp_path):
    odp = make_odf(tmp_path, "s.odp", "<draw:page><draw:custom-shape><text:p>só texto</text:p></draw:custom-shape></draw:page>")
    md = convert_file(odp).output.read_text(encoding="utf-8")
    assert md == "## Slide 1\n\nsó texto\n"


def test_lista_numerada_pelo_estilo(tmp_path):
    estilos = (
        '<text:list-style style:name="L1">'
        '<text:list-level-style-number text:level="1"/>'
        '<text:list-level-style-bullet text:level="2"/></text:list-style>'
    )
    corpo = (
        '<draw:page><draw:frame presentation:class="outline"><draw:text-box>'
        '<text:list text:style-name="L1">'
        "<text:list-item><text:p>um</text:p></text:list-item>"
        "<text:list-item><text:p>dois</text:p><text:list><text:list-item>"
        "<text:p>marcador</text:p></text:list-item></text:list></text:list-item>"
        "</text:list></draw:text-box></draw:frame></draw:page>"
    )
    odp = make_odf(tmp_path, "n.odp", corpo, estilos=estilos)
    md = convert_file(odp).output.read_text(encoding="utf-8")
    assert "1. um\n2. dois\n    - marcador" in md


def test_objeto_incorporado_gera_aviso(tmp_path):
    corpo = (
        "<draw:page>" + TITULO.format("Vendas")
        + '<draw:frame><draw:object xlink:href="./Object 1"/>'
        '<draw:image xlink:href="./ObjectReplacements/Object 1"/></draw:frame></draw:page>'
    )
    odp = make_odf(tmp_path, "g.odp", corpo)
    res = convert_file(odp)
    md = res.output.read_text(encoding="utf-8")

    aviso = "o slide 1 tem 1 objeto(s) incorporado(s) (gráfico, fórmula ou OLE)"
    assert [a for a in res.avisos if aviso in a]
    assert f"> **Aviso do ndoc2md:** {aviso}" in md


def test_imagem_fora_do_pacote_nao_e_copiada(tmp_path):
    """O link da imagem não pode levar a escrita para fora da pasta de mídia."""
    corpo = (
        '<draw:page><draw:frame><draw:image xlink:href="../../fora.png"/></draw:frame>'
        '<draw:frame><draw:image xlink:href="Pictures/../../escapa.png"/></draw:frame></draw:page>'
    )
    odp = make_odf(tmp_path / "in", "x.odp", corpo, arquivos={"Pictures/../../escapa.png": png_bytes()})
    res = convert_file(odp)

    assert not (tmp_path / "fora.png").exists()
    assert not (tmp_path / "escapa.png").exists()
    assert sorted(p.name for p in res.media_dir.iterdir()) == ["escapa.png"]
    assert [a for a in res.avisos if "1 imagem(ns) vinculada(s) a arquivo externo" in a]


def test_arquivo_que_nao_e_zip_leva_a_conversion_error(tmp_path):
    falso = tmp_path / "falso.odp"
    falso.write_text("não é zip")
    saida = tmp_path / "nova" / "saida"

    with pytest.raises(ConversionError, match="OpenDocument"):
        convert_file(falso, saida)
    assert not (tmp_path / "nova").exists()


# --- OpenOffice 1.x ------------------------------------------------------------

SLIDES_SXI = (
    "<draw:page draw:name=\"page1\">"
    '<draw:text-box presentation:class="title"><text:p>Plano antigo</text:p></draw:text-box>'
    '<draw:text-box presentation:class="outline"><text:unordered-list>'
    "<text:list-item><text:p>Primeiro</text:p>"
    "<text:unordered-list><text:list-item><text:p>Detalhe</text:p></text:list-item>"
    "</text:unordered-list></text:list-item>"
    "<text:list-item><text:p>Segundo</text:p></text:list-item>"
    "</text:unordered-list></draw:text-box>"
    '<draw:image xlink:href="#Pictures/logo.png"/>'
    "<presentation:notes>"
    '<draw:page-thumbnail presentation:class="page"/>'
    '<draw:text-box presentation:class="notes"><text:p>Nota 1.x</text:p></draw:text-box>'
    "</presentation:notes>"
    "</draw:page>"
)


def test_sxi_do_openoffice_1(tmp_path):
    sxi = make_odf(tmp_path, "antigo.sxi", SLIDES_SXI, arquivos={"Pictures/logo.png": png_bytes()})
    res = convert_file(sxi)
    md = res.output.read_text(encoding="utf-8")

    assert res.engine == "odf"
    assert md == (
        "## Slide 1: Plano antigo\n\n"
        "- Primeiro\n    - Detalhe\n- Segundo\n\n"
        "![](antigo.sxi_media/logo.png)\n\n"
        "**Notas do apresentador:**\n\n"
        "Nota 1.x\n"
    )
