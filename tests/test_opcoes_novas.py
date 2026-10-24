"""Opções novas da 0.2.0, todas desligadas por padrão.

Desligadas, o resultado é o da 0.1.0 (comparação byte a byte registrada no changelog);
estes testes cobrem só o comportamento com cada opção ligada.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from conftest import make_docx_with_image, make_pdf, requer_pandoc, requer_pdf

from ndoc2md import converter
from ndoc2md.cli import main
from ndoc2md.converter import ConversionError, PdfSemTexto, convert_file, resolve_dst

TEXTO = "Contrato de prestação de serviços entre as partes."


def _texto(page):
    page.insert_text((72, 72), TEXTO, fontsize=12)


def _imagem(page):
    import fitz

    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 60), 0)
    pix.set_rect(pix.irect, (200, 30, 30))
    page.insert_image(fitz.Rect(72, 200, 372, 500), pixmap=pix)


def _pdf(pasta, nome, paginas):
    """PDF com uma página por item de `paginas` (funções que desenham na página)."""
    import fitz

    pasta.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for desenhar in paginas:
        desenhar(doc.new_page())
    caminho = pasta / nome
    doc.save(caminho)
    doc.close()
    return caminho


# --- nome e cabeçalho ---------------------------------------------------------


def test_nome_e_prefixo_de_data(tmp_path):
    src = tmp_path / "doc_123_Cartão CNPJ.pdf"
    hoje = date.today().isoformat()
    assert resolve_dst(src, nome="cartao-cnpj").name == "cartao-cnpj.pdf.md"
    assert resolve_dst(src, prefixo_data=True).name == f"{hoje}_doc_123_Cartão CNPJ.pdf.md"
    assert resolve_dst(src, nome="c", prefixo_data=True).name == f"{hoje}_c.pdf.md"


@requer_pdf
def test_cabecalho_com_titulo_origem_e_sha(tmp_path):
    pdf = make_pdf(tmp_path, "contrato.pdf", _texto)
    res = convert_file(pdf, cabecalho=True, titulo="Contrato X")
    linhas = res.output.read_text(encoding="utf-8").splitlines()
    assert linhas[0] == "# Contrato X"
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}, convertido de `contrato\.pdf` por ndoc2md \S+ \(pymupdf4llm\), "
        rf"sha256 `{res.sha256[:12]}`, 1 página\(s\)\.",
        linhas[2],
    )


# --- sem HTML -----------------------------------------------------------------


def test_limpar_html_do_pdf():
    md = "a\n<!-- Start of picture text -->\nX<br>Y<br/>\n<!-- End of picture text -->\nb"
    assert converter._limpar_html(md) == "a\nX\nY\n\nb"


@requer_pandoc
def test_sem_html_no_pandoc(tmp_path):
    html = tmp_path / "p.html"
    html.write_text(f"<html><body><div class='x'><p>{TEXTO}</p></div></body></html>", encoding="utf-8")
    md = convert_file(html, sem_html=True).output.read_text(encoding="utf-8")
    assert TEXTO in md and "<div" not in md


@requer_pandoc
def test_sem_html_sem_midia_nao_deixa_link_quebrado(tmp_path):
    docx = make_docx_with_image(tmp_path, "img.docx")
    md = convert_file(docx, extract_media=False, sem_html=True).output.read_text(encoding="utf-8")
    assert "![" not in md and "<img" not in md and "[imagem: alt]" in md


# --- exigir texto -------------------------------------------------------------


@requer_pdf
def test_exigir_texto_barra_pdf_escaneado_sem_gravar(tmp_path):
    pdf = _pdf(tmp_path, "escaneado.pdf", [_imagem, _imagem])
    saida = tmp_path / "saida"
    with pytest.raises(PdfSemTexto, match="2 página"):
        convert_file(pdf, saida, exigir_texto=True)
    assert not saida.exists()


@requer_pdf
def test_exigir_texto_avisa_pagina_escaneada_no_meio(tmp_path):
    pdf = _pdf(tmp_path, "misto.pdf", [_texto, _imagem])
    res = convert_file(pdf, exigir_texto=True)
    assert len(res.avisos) == 1 and "página 2" in res.avisos[0]
    assert "a página 2 é imagem sem texto" in res.output.read_text(encoding="utf-8")


@requer_pdf
def test_sem_exigir_texto_escaneado_continua_gerando_md(tmp_path):
    pdf = _pdf(tmp_path, "escaneado.pdf", [_imagem])
    assert convert_file(pdf, extract_media=False).output.exists()


# --- apagar original ----------------------------------------------------------


@requer_pdf
def test_apagar_original_no_sucesso(tmp_path):
    pdf = make_pdf(tmp_path, "a.pdf", _texto)
    res = convert_file(pdf, apagar_original=True)
    assert res.original_apagado and not pdf.exists() and res.output.exists()


@requer_pdf
def test_apagar_original_na_falha(tmp_path):
    pdf = _pdf(tmp_path, "escaneado.pdf", [_imagem])
    with pytest.raises(PdfSemTexto) as exc:
        convert_file(pdf, exigir_texto=True, apagar_original=True)
    assert exc.value.original_apagado and not pdf.exists()


@requer_pdf
def test_apagar_original_com_destino_existente(tmp_path):
    pdf = make_pdf(tmp_path, "a.pdf", _texto)
    convert_file(pdf)
    with pytest.raises(ConversionError, match="já existe"):
        convert_file(pdf, apagar_original=True)
    assert not pdf.exists()


def test_apagar_original_nao_apaga_extensao_nao_suportada(tmp_path):
    txt = tmp_path / "nota.txt"
    txt.write_text("x")
    with pytest.raises(ConversionError, match="extensão não suportada"):
        convert_file(txt, apagar_original=True)
    assert txt.exists()


# --- mensagem sem pymupdf -----------------------------------------------------


def test_mensagem_sem_pdf_no_macos_intel(monkeypatch):
    monkeypatch.setattr(converter.sys, "platform", "darwin")
    monkeypatch.setattr(converter.platform, "machine", lambda: "x86_64")
    assert "Docker" in converter._mensagem_sem_pdf()


def test_mensagem_sem_pdf_no_linux_continua_a_mesma(monkeypatch):
    monkeypatch.setattr(converter.sys, "platform", "linux")
    assert converter._mensagem_sem_pdf() == "suporte a PDF não instalado — rode: uv sync --extra pdf"


# --- CLI ----------------------------------------------------------------------


@requer_pandoc
@requer_pdf
def test_cli_json_uma_linha_por_arquivo(tmp_path, capsys):
    pdf = make_pdf(tmp_path, "a.pdf", _texto)
    assert main([str(pdf), "--json", "--nome", "contrato", "--cabecalho"]) == 0
    linhas = capsys.readouterr().out.strip().splitlines()
    assert len(linhas) == 1
    reg = json.loads(linhas[0])
    assert reg["ok"] and reg["saida"].endswith("contrato.pdf.md") and reg["paginas"] == 1
    assert len(reg["sha256"]) == 64 and reg["original_apagado"] is False


@requer_pandoc
@requer_pdf
def test_cli_exigir_texto_sai_com_3(tmp_path, capsys):
    pdf = _pdf(tmp_path, "escaneado.pdf", [_imagem])
    assert main([str(pdf), "--json", "--exigir-texto", "--apagar-original"]) == 3
    reg = json.loads(capsys.readouterr().out.strip())
    assert not reg["ok"] and reg["sem_texto"] and reg["original_apagado"] and not pdf.exists()


@requer_pandoc
@requer_pdf
def test_cli_sem_exigir_texto_escaneado_sai_com_0(tmp_path):
    pdf = _pdf(tmp_path, "escaneado.pdf", [_imagem])
    assert main([str(pdf), "--no-media"]) == 0


@requer_pandoc
def test_cli_nome_com_dois_arquivos_sai_com_2(tmp_path, basic_docx):
    outro = tmp_path / "b.html"
    outro.write_text("<p>x</p>", encoding="utf-8")
    assert main([str(basic_docx), str(outro), "--nome", "x"]) == 2
