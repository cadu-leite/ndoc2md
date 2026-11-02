"""Testes do `.sxw` (Writer do OpenOffice 1.x), lido direto do XML em ndoc2md.formatos.texto."""

from __future__ import annotations

from conftest import make_odf, png_bytes

from ndoc2md.converter import convert_file

CORPO_SXW = (
    "<text:sequence-decls><text:sequence-decl text:name=\"Table\"/></text:sequence-decls>"
    "<text:table-of-content><text:index-body><text:p>Sumário 1</text:p></text:index-body>"
    "</text:table-of-content>"
    '<text:h text:level="1">Contrato</text:h>'
    "<text:p>Entre as partes<text:footnote><text:footnote-citation>1</text:footnote-citation>"
    "<text:footnote-body><text:p>Ver anexo.</text:p></text:footnote-body></text:footnote>"
    " fica acordado.<office:annotation><text:p>comentário</text:p></office:annotation></text:p>"
    '<text:h text:level="2">Cláusulas</text:h>'
    "<text:ordered-list><text:list-item><text:p>Prazo</text:p>"
    "<text:unordered-list><text:list-item><text:p>12 meses</text:p></text:list-item>"
    "</text:unordered-list></text:list-item>"
    "<text:list-item><text:p>Valor</text:p></text:list-item></text:ordered-list>"
    '<text:p>Veja <text:a xlink:href="https://exemplo.com">o site</text:a>.</text:p>'
    "<table:table><table:table-column/><table:table-column/>"
    "<table:table-header-rows><table:table-row>"
    "<table:table-cell><text:p>Item</text:p></table:table-cell>"
    "<table:table-cell><text:p>Preço</text:p></table:table-cell>"
    "</table:table-row></table:table-header-rows>"
    "<table:table-row><table:table-cell><text:p>A</text:p></table:table-cell>"
    "<table:table-cell><text:p>10</text:p></table:table-cell></table:table-row>"
    "</table:table>"
    '<text:p><draw:image xlink:href="#Pictures/foto.png"/></text:p>'
)


def test_sxw_preserva_titulos_listas_tabela_e_notas(tmp_path):
    sxw = make_odf(tmp_path, "contrato.sxw", CORPO_SXW, arquivos={"Pictures/foto.png": png_bytes()})
    res = convert_file(sxw)
    md = res.output.read_text(encoding="utf-8")

    assert res.engine == "odf"
    assert md == (
        "# Contrato\n\n"
        "Entre as partes[^1] fica acordado.\n\n"
        "## Cláusulas\n\n"
        "1. Prazo\n    - 12 meses\n2. Valor\n\n"
        "Veja [o site](https://exemplo.com).\n\n"
        "| Item | Preço |\n|------|-------|\n| A | 10 |\n\n"
        "![](contrato.sxw_media/foto.png)\n\n"
        "[^1]: Ver anexo.\n"
    )
