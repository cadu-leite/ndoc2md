"""Testes de ndoc2md.converter.strip_toc: comportamento hoje correto (regex _TOC_LINE)."""

from __future__ import annotations

from ndoc2md.converter import strip_toc


def test_remove_linhas_de_sumario_e_mantem_links_de_corpo():
    md = (
        "# Sumario\n\n"
        "[Termos [2](#termos)](#termos)\n"
        "[Definições [3](#definicoes)](#definicoes)\n\n"
        "# Termos\n\n"
        "Ver também [3](#definicoes) no meio do texto.\n"
    )
    limpo, removidas = strip_toc(md)
    assert removidas == 2
    assert "[Termos [2]" not in limpo
    assert "Ver também [3](#definicoes) no meio do texto." in limpo


def test_ancora_com_parenteses_e_reconhecida_como_toc():
    md = "[Registro [4](#_Registro_(de_Imoveis))](#_Registro_(de_Imoveis))\n"
    limpo, removidas = strip_toc(md)
    assert removidas == 1
    assert limpo == ""


def test_sem_sumario_devolve_markdown_praticamente_intacto():
    md = "# Titulo\n\ntexto comum\n"
    limpo, removidas = strip_toc(md)
    assert removidas == 0
    assert limpo == md
