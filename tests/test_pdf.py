"""Testes do caminho de PDF (pymupdf4llm): aviso de página sem conteúdo reconhecido."""

from __future__ import annotations

from conftest import make_pdf, requer_pdf

from ndoc2md.converter import convert_file

pytestmark = requer_pdf


def test_desenho_vetorial_isolado_gera_aviso(tmp_path):
    """Erro 12 do docs/erros-conhecidos.md: o conteúdo continua perdido, mas agora com aviso."""
    import fitz

    pdf = make_pdf(
        tmp_path,
        "vetorial.pdf",
        lambda page: page.draw_rect(
            fitz.Rect(50, 50, 200, 150), color=(0, 0, 0), fill=(0.8, 0.1, 0.1)
        ),
    )
    res = convert_file(pdf, overwrite=True)
    conteudo = res.output.read_text(encoding="utf-8")

    assert "Aviso do ndoc2md" in conteudo
    assert "página 1" in conteudo


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
