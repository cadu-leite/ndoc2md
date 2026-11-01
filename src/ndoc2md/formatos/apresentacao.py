"""Apresentações: `.odp` (Impress, OpenDocument) e `.sxi` (Impress do OpenOffice 1.x).

Cada slide vira uma seção `## Slide N: título`. O título sai do quadro marcado com
`presentation:class="title"`; o resto do slide segue a ordem do arquivo (a ordem de
empilhamento, não a posição na tela); as notas do apresentador vêm no fim do slide.
"""

from __future__ import annotations

from pathlib import Path

from .base import Conversao
from .odf import Leitor, Pacote, montar

# Quadros que repetem o modelo do slide (rodapé, data, número) ou mostram a miniatura.
_CLASSES_IGNORADAS = {"page", "page-number", "date-time", "footer", "header", "handout"}


def _oculto(pacote: Pacote, slide) -> bool:
    return pacote.propriedade(slide.get("draw:style-name"), "presentation:visibility") == "hidden"


def _formas(slide):
    """Formas do slide que entram no corpo: sem notas, sem placeholder vazio."""
    for forma in slide:
        if forma.tag == "presentation:notes":
            continue
        if forma.get("presentation:placeholder") == "true":
            continue
        if forma.get("presentation:class") in _CLASSES_IGNORADAS:
            continue
        yield forma


def _notas(leitor: Leitor, slide) -> list[str]:
    notas = slide.find("presentation:notes")
    if notas is None:
        return []
    blocos: list[str] = []
    for forma in notas:
        if forma.get("presentation:class") == "notes":
            blocos += leitor.bloco(forma)
    return blocos


def converter_apresentacao(
    src: Path, ext: str, dst_dir: Path, media_base: str, *,
    extract_media: bool, sem_html: bool, silencioso: bool,
) -> Conversao:
    """Converte `.odp` ou `.sxi`; a saída não tem HTML, então `sem_html` não muda nada."""
    with Pacote(src) as pacote:
        leitor = Leitor(pacote, dst_dir, media_base, extract_media)
        slides = [el for el in pacote.corpo("presentation") if el.tag == "draw:page"]
        blocos: list[str] = []
        for n, slide in enumerate(slides, 1):
            leitor.local = f"o slide {n}"
            titulo = None
            corpo: list[str] = []
            for forma in _formas(slide):
                if titulo is None and forma.get("presentation:class") == "title":
                    titulo = leitor.texto_plano(forma)
                    continue
                corpo += leitor.bloco(forma)
            rotulo = f"Slide {n} (oculto)" if _oculto(pacote, slide) else f"Slide {n}"
            blocos.append(f"## {rotulo}: {titulo}" if titulo else f"## {rotulo}")
            blocos += corpo
            notas = _notas(leitor, slide)
            if notas:
                blocos.append("**Notas do apresentador:**")
                blocos += notas
    return Conversao(
        montar(blocos, leitor), "odf", leitor.media_dir, len(slides), tuple(leitor.avisos())
    )


CONVERSORES = {".odp": converter_apresentacao, ".sxi": converter_apresentacao}
