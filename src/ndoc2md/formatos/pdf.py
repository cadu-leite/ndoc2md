"""PDF: lido pelo pymupdf4llm (extra opcional `pdf`, que vem dentro do pymupdf 2.x),
já que o pandoc não lê PDF."""

from __future__ import annotations

import contextlib
import io
import platform
import re
import shutil
import sys
import tempfile
from pathlib import Path

from ..erros import ConversionError, PdfSemTexto
from .base import Conversao

EXT = ".pdf"

# `--sem-html`: o pymupdf4llm 2.x marca texto dentro de figura com comentário HTML
# e quebra linha com `<br>`.
_HTML_COMENTARIO = re.compile(r"<!--.*?-->[ \t]*\n?", re.DOTALL)
_HTML_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _limpar_html(md: str) -> str:
    """`sem_html=True` no PDF: comentário HTML sai, `<br>` vira quebra de linha."""
    return _HTML_BR.sub("\n", _HTML_COMENTARIO.sub("", md))


def _mensagem_sem_pdf() -> str:
    """Mensagem para quando o pymupdf não está instalado.

    O extra `pdf` não instala nada em macOS Intel nem em Python 3.10 (o pymupdf 2.x
    não tem versão para eles); nesses casos o caminho é o Docker.
    """
    if sys.platform == "darwin" and platform.machine() == "x86_64":
        return (
            "PDF não é suportado em macOS com CPU Intel (o pymupdf 2.x não tem versão para "
            "essa plataforma) — rode o ndoc2md pelo Docker; veja o README, seção \"macOS Intel\""
        )
    if sys.version_info < (3, 11):
        return (
            "PDF exige Python 3.11 ou mais novo (pymupdf 2.x) — use Python 3.11+ ou rode "
            "o ndoc2md pelo Docker; veja o README, seção \"macOS Intel\""
        )
    return "suporte a PDF não instalado — rode: uv sync --extra pdf"


def _warn_empty_pages(src: Path, chunks: list[dict]) -> str:
    """Reconstrói o Markdown a partir de `chunks` (`page_chunks=True`), avisando
    página que não gerou nada apesar de ter desenho vetorial.

    O pymupdf4llm 0.0.x descartava traço/preenchimento vetorial isolado sem avisar
    (erro 12); o 2.x transforma esse desenho em imagem quando a mídia é extraída.
    Sem mídia, ou se o motor ainda descartar o desenho, a página fica vazia: aqui a
    gente cruza cada página vazia do resultado com `page.get_drawings()` na própria
    fonte — página com desenho vetorial e sem nada no Markdown é conteúdo perdido,
    não uma página em branco de verdade. (No 2.x, imagem e tabela já vêm dentro do
    `text` do chunk.)
    """
    import pymupdf

    doc = pymupdf.open(str(src.resolve()))
    try:
        partes = []
        for i, chunk in enumerate(chunks):
            texto = chunk["text"]
            vazia = not texto.strip()
            if vazia and i < doc.page_count and doc[i].get_drawings():
                texto = (
                    f"\n\n> **Aviso do ndoc2md:** a página {i + 1} tem desenho vetorial "
                    "que não virou texto nem imagem no Markdown — confira o PDF original.\n\n"
                )
            partes.append(texto)
    finally:
        doc.close()
    return "".join(partes)


def _paginas_pdf(src: Path) -> list[tuple[bool, bool]]:
    """Para cada página: (tem texto, tem imagem), lido na fonte."""
    import pymupdf

    with pymupdf.open(str(src.resolve())) as doc:
        return [(bool(p.get_text().strip()), bool(p.get_images())) for p in doc]


def _avisos_escaneadas(paginas: list[tuple[bool, bool]]) -> list[str]:
    return [
        f"a página {i + 1} é imagem sem texto (escaneada); o conteúdo dela não está neste Markdown"
        for i, (tem_texto, tem_imagem) in enumerate(paginas)
        if not tem_texto and tem_imagem
    ]


def verificar_texto(src: Path) -> list[str]:
    """`exigir_texto=True`: lança `PdfSemTexto` se nenhuma página tem texto; senão,
    devolve um aviso por página escaneada no meio do PDF."""
    try:
        paginas_fonte = _paginas_pdf(src)
    except ImportError as exc:
        raise ConversionError(_mensagem_sem_pdf()) from exc
    if not any(tem_texto for tem_texto, _ in paginas_fonte):
        raise PdfSemTexto(
            f"o PDF não tem texto em nenhuma das {len(paginas_fonte)} página(s); "
            "parece escaneado — peça a versão digital do documento"
        )
    return _avisos_escaneadas(paginas_fonte)


def _run_pdf(
    src: Path, media_dir: Path | None, silencioso: bool = False
) -> tuple[str, Path | None, int]:
    """Converte PDF via pymupdf4llm, sem OCR. Devolve (markdown, pasta de mídia, páginas).

    Se `media_dir` for dado, extrai figuras/diagramas como PNG para lá e
    reescreve os links no Markdown para ficarem relativos ao `.md` gerado
    (mesma semântica do caminho pandoc). Sem `media_dir`, extrai só texto.
    """
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise ConversionError(_mensagem_sem_pdf()) from exc

    # O pymupdf4llm escreve recados no stdout e no stderr; `silencioso` os descarta
    # (a CLI usa com --json, que precisa de stdout limpo).
    abafar = contextlib.ExitStack()
    if silencioso:
        abafar.enter_context(contextlib.redirect_stdout(io.StringIO()))
        abafar.enter_context(contextlib.redirect_stderr(io.StringIO()))

    if media_dir is None:
        with abafar:
            chunks = pymupdf4llm.to_markdown(str(src.resolve()), page_chunks=True, use_ocr=False)
        return _warn_empty_pages(src, chunks), None, len(chunks)

    # O pymupdf4llm 2.x troca espaço, acento e parênteses do image_path e não cria a
    # pasta: as imagens vão para uma pasta temporária do sistema (caminho só com letras,
    # números e `_`) e depois são movidas para `media_dir`, que mantém o nome de sempre
    # (`<arquivo>_media`).
    with tempfile.TemporaryDirectory(prefix="ndoc2md_") as tmp:
        with abafar:
            chunks = pymupdf4llm.to_markdown(
                str(src.resolve()),
                page_chunks=True,
                use_ocr=False,
                write_images=True,
                image_path=tmp,
                image_format="png",
                dpi=150,
            )
        md = _warn_empty_pages(src, chunks)
        imagens = sorted(Path(tmp).iterdir())
        if imagens:
            media_dir.mkdir(exist_ok=True)
            for img in imagens:
                shutil.move(str(img), str(media_dir / img.name))
    # pymupdf4llm insere o próprio image_path como prefixo do link, sempre como
    # `![](<prefixo>/arquivo.png)` (única sintaxe de imagem que ele emite); torná-lo
    # relativo à pasta do .md (o .md e a pasta de mídia são irmãos) mirando só essa
    # sintaxe, para não reescrever o caminho se ele aparecer no texto do documento.
    # `![]( ... )` sempre sozinho na linha — casar a linha inteira, com `.*` guloso
    # até o `)` final, em vez de `[^)]*`, porque o nome do arquivo pode ter parênteses.
    img_tag = re.compile(r"^!\[\]\(" + re.escape(tmp) + r"/?(.*)\)$", re.MULTILINE)
    md = img_tag.sub(lambda m: f"![]({media_dir.name}/{m.group(1)})", md)
    return md, (media_dir if media_dir.is_dir() else None), len(chunks)


def converter_pdf(
    src: Path, ext: str, dst_dir: Path, media_base: str, *,
    extract_media: bool, sem_html: bool, silencioso: bool,
) -> Conversao:
    """Converte um PDF; `sem_html` tira comentário HTML e troca `<br>`."""
    pdf_media = dst_dir / f"{media_base}_media" if extract_media else None
    md, media_dir, paginas = _run_pdf(src, pdf_media, silencioso)
    if sem_html:
        md = _limpar_html(md)
    return Conversao(md, "pymupdf4llm", media_dir, paginas)


CONVERSORES = {EXT: converter_pdf}
