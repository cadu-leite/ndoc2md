"""Testes do caminho de PDF (pymupdf4llm): aviso de página sem conteúdo reconhecido."""

from __future__ import annotations

from conftest import make_pdf, requer_pdf

from ndoc2md.converter import convert_file

pytestmark = requer_pdf


def test_desenho_vetorial_isolado_gera_aviso(tmp_path):
    """Sem mídia, a página só com desenho vetorial fica vazia no Markdown: tem que avisar."""
    import fitz

    pdf = make_pdf(
        tmp_path,
        "vetorial.pdf",
        lambda page: page.draw_rect(
            fitz.Rect(50, 50, 200, 150), color=(0, 0, 0), fill=(0.8, 0.1, 0.1)
        ),
    )
    res = convert_file(pdf, overwrite=True, extract_media=False)
    conteudo = res.output.read_text(encoding="utf-8")

    assert "Aviso do ndoc2md" in conteudo
    assert "página 1" in conteudo


def test_desenho_vetorial_isolado_vira_imagem(tmp_path):
    """Erro 12, resolvido com o pymupdf 2.x: o desenho vetorial isolado vira imagem."""
    import fitz

    pdf = make_pdf(
        tmp_path,
        "diagrama.pdf",
        lambda page: page.draw_rect(
            fitz.Rect(50, 50, 200, 150), color=(0, 0, 0), fill=(0.8, 0.1, 0.1)
        ),
    )
    res = convert_file(pdf, overwrite=True)

    assert res.media_dir is not None and any(res.media_dir.iterdir())
    assert "Aviso do ndoc2md" not in res.output.read_text(encoding="utf-8")


def test_pdf_so_texto_nao_gera_aviso(tmp_path):
    pdf = make_pdf(
        tmp_path,
        "texto.pdf",
        lambda page: page.insert_text((50, 50), "Texto normal, sem desenho nenhum.", fontsize=12),
    )
    res = convert_file(pdf, overwrite=True)
    conteudo = res.output.read_text(encoding="utf-8")

    assert "Aviso do ndoc2md" not in conteudo
    assert "Texto normal" in conteudo


def test_texto_com_caminho_da_media_dir_nao_e_corrompido(tmp_path):
    """A relativização do link de imagem não deve tocar em texto comum do PDF
    que coincida com o caminho absoluto da pasta de mídia."""
    import fitz

    pdf = tmp_path / "relatorio.pdf"
    media_dir = tmp_path / f"{pdf.name}_media"
    caminho_no_texto = f"{media_dir}/algo.png"

    def desenhar(page):
        rect = fitz.Rect(20, 20, page.rect.width - 20, page.rect.height - 20)
        page.insert_textbox(
            rect, f"Este arquivo foi salvo em {caminho_no_texto}, conforme o protocolo.", fontsize=8
        )

    make_pdf(tmp_path, "relatorio.pdf", desenhar)
    res = convert_file(pdf, overwrite=True)
    conteudo = res.output.read_text(encoding="utf-8")

    assert caminho_no_texto in conteudo


def test_nome_de_arquivo_com_parenteses_nao_corrompe_link_de_imagem(tmp_path):
    """O nome de arquivo pode ter parênteses (ex.: 'Relatório (rascunho).pdf'); o link de
    imagem gerado por pymupdf4llm carrega esse nome, e a relativização não pode truncar
    no primeiro ')' que aparecer nele."""
    import fitz

    def desenhar(page):
        page.draw_rect(fitz.Rect(50, 50, 250, 100), color=(0, 0, 0), fill=(0.8, 0.1, 0.1))
        page.draw_line(fitz.Point(150, 100), fitz.Point(150, 150), color=(0, 0, 0), width=2)
        page.draw_rect(fitz.Rect(80, 150, 220, 190), color=(0, 0, 0), fill=(0.1, 0.4, 0.8))

    pdf = make_pdf(tmp_path, "Relatório (rascunho).pdf", desenhar)
    res = convert_file(pdf, overwrite=True)
    conteudo = res.output.read_text(encoding="utf-8")

    assert res.media_dir is not None
    [imagem] = list(res.media_dir.iterdir())
    assert f"![]({res.media_dir.name}/{imagem.name})" in conteudo


def test_desenho_conectado_vira_imagem_sem_aviso(tmp_path):
    """Formas vetoriais que se tocam (um "fluxograma" de verdade) passam pelo filtro do
    pymupdf4llm e viram imagem — só a forma isolada (erro 12) é descartada."""
    import fitz

    def desenhar(page):
        page.draw_rect(fitz.Rect(50, 50, 250, 100), color=(0, 0, 0), fill=(0.8, 0.1, 0.1))
        page.draw_line(fitz.Point(150, 100), fitz.Point(150, 150), color=(0, 0, 0), width=2)
        page.draw_rect(fitz.Rect(80, 150, 220, 190), color=(0, 0, 0), fill=(0.1, 0.4, 0.8))

    pdf = make_pdf(tmp_path, "fluxograma.pdf", desenhar)
    res = convert_file(pdf, overwrite=True)
    conteudo = res.output.read_text(encoding="utf-8")

    assert "Aviso do ndoc2md" not in conteudo
    assert res.media_dir is not None and any(res.media_dir.iterdir())
