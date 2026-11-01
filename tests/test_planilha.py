"""Testes de ndoc2md.formatos.planilha: `.ods` e `.sxc`, lidos direto do XML."""

from __future__ import annotations

from conftest import make_odf, png_bytes

from ndoc2md.converter import convert_file


def celula(texto: str = "", repete: int = 1, **attrs: str) -> str:
    extra = "".join(f' table:{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    if repete > 1:
        extra += f' table:number-columns-repeated="{repete}"'
    conteudo = f"<text:p>{texto}</text:p>" if texto else ""
    return f"<table:table-cell{extra}>{conteudo}</table:table-cell>"


def linha(*celulas: str, repete: int = 1) -> str:
    attr = f' table:number-rows-repeated="{repete}"' if repete > 1 else ""
    return f"<table:table-row{attr}>{''.join(celulas)}</table:table-row>"


# Aba como o Calc grava: coluna vazia à esquerda, o resto da linha como célula vazia
# repetida 1020 vezes, o resto da folha como linha vazia repetida 1 milhão de vezes.
ABA_VENDAS = (
    '<table:table table:name="Vendas"><table:table-column table:number-columns-repeated="1024"/>'
    "<table:table-header-rows>"
    + linha(celula(), celula("Produto"), celula("Total"), celula(repete=1021))
    + "</table:table-header-rows>"
    + linha(celula(), celula("Café"), celula("1.234,50"), celula(repete=1021))
    + linha(celula(repete=1024), repete=2)
    + linha(celula(), celula("Chá | mate"), celula("3"), celula(repete=1021))
    + linha(celula(repete=1024), repete=1048570)
    + "</table:table>"
)
ABA_MESCLADA = (
    '<table:table table:name="Mescla">'
    + linha(celula("A", number_columns_spanned="2"), "<table:covered-table-cell/>", celula("C"))
    + linha(celula("x", repete=3))
    + "</table:table>"
)
ABA_VAZIA = '<table:table table:name="Vazia">' + linha(celula(repete=1024), repete=1048576) + "</table:table>"


def test_abas_viram_secoes_com_tabela(tmp_path):
    ods = make_odf(tmp_path, "p.ods", ABA_VENDAS + ABA_MESCLADA + ABA_VAZIA)
    res = convert_file(ods)
    md = res.output.read_text(encoding="utf-8")

    assert res.engine == "odf"
    assert res.paginas is None
    assert md == (
        "## Vendas\n\n"
        "| Produto | Total |\n"
        "|---------|-------|\n"
        "| Café | 1.234,50 |\n"
        "|  |  |\n"
        "|  |  |\n"
        "| Chá \\| mate | 3 |\n\n"
        "## Mescla\n\n"
        "| A |  | C |\n"
        "|---|---|---|\n"
        "| x | x | x |\n\n"
        "## Vazia\n\n"
        "*(aba vazia)*\n"
    )


def test_aba_oculta_e_marcada(tmp_path):
    estilos = (
        '<style:style style:name="ta2" style:family="table">'
        '<style:table-properties table:display="false"/></style:style>'
    )
    corpo = '<table:table table:name="Secreta" table:style-name="ta2">' + linha(celula("1")) + "</table:table>"
    ods = make_odf(tmp_path, "o.ods", corpo, estilos=estilos)
    md = convert_file(ods).output.read_text(encoding="utf-8")
    assert md.startswith("## Secreta (oculta)\n")


def test_grafico_sobre_a_aba_gera_aviso_e_imagem_e_copiada(tmp_path):
    corpo = (
        '<table:table table:name="Painel"><table:shapes>'
        '<draw:frame><draw:object xlink:href="./Object 1"/></draw:frame>'
        '<draw:frame><draw:image xlink:href="Pictures/logo.png"/></draw:frame>'
        "</table:shapes>" + linha(celula("v")) + "</table:table>"
    )
    ods = make_odf(tmp_path, "g.ods", corpo, arquivos={"Pictures/logo.png": png_bytes()})
    res = convert_file(ods)
    md = res.output.read_text(encoding="utf-8")

    assert "![](g.ods_media/logo.png)" in md
    assert [a for a in res.avisos if a.startswith("a aba Painel tem 1 objeto(s)")]


def test_celula_so_com_valor_usa_o_valor(tmp_path):
    corpo = (
        '<table:table table:name="Dados">'
        + linha(celula("Data"), celula("Qtd"))
        + linha(
            '<table:table-cell office:value-type="date" office:date-value="2026-11-01"/>',
            '<table:table-cell office:value-type="float" office:value="42"/>',
        )
        + "</table:table>"
    )
    ods = make_odf(tmp_path, "v.ods", corpo)
    md = convert_file(ods).output.read_text(encoding="utf-8")
    assert "| 2026-11-01 | 42 |" in md


def test_sxc_do_openoffice_1(tmp_path):
    corpo = (
        '<table:table table:name="Planilha1">'
        + linha(celula("Nome"), celula("Idade"), celula(repete=254))
        + linha(celula("Ana"), celula("30"), celula(repete=254))
        + linha(celula(repete=256), repete=31998)
        + "</table:table>"
    )
    sxc = make_odf(tmp_path, "antiga.sxc", corpo)
    md = convert_file(sxc).output.read_text(encoding="utf-8")
    assert md == "## Planilha1\n\n| Nome | Idade |\n|------|-------|\n| Ana | 30 |\n"
