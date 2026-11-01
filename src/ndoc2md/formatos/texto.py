"""Documentos de texto.

- Formatos de escritório e de marcação lidos pelo pandoc, que preserva a hierarquia de
  títulos a partir dos estilos "Título 1/2/3" do Word.
- `.sxw` (Writer do OpenOffice 1.x), que o pandoc não lê: o XML é lido direto, como nas
  apresentações e planilhas (ver `odf.py`). O título sai do nível de estrutura de
  tópicos (`text:h`).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ..erros import ConversionError
from .base import Conversao
from .odf import Leitor, Pacote, montar

# extensão -> formato de entrada do pandoc
PANDOC_FORMATS = {
    ".docx": "docx",
    ".odt": "odt",
    ".html": "html",
    ".htm": "html",
    ".rtf": "rtf",
    ".epub": "epub",
    ".tex": "latex",
    ".org": "org",
    ".rst": "rst",
    ".textile": "textile",
}

# `![alt](destino)`; o destino pode ter parênteses no nome do arquivo.
_IMAGEM_MD = re.compile(r"!\[([^\]]*)\]\(([^()\s]*(?:\([^()\s]*\)[^()\s]*)*)\)")


def have_pandoc() -> bool:
    """True se o binário `pandoc` está no PATH."""
    return shutil.which("pandoc") is not None


_IMG_TAG = re.compile(r"<img\b[^>]*/?>")


def _drop_img_tags(md: str) -> str:
    """Remove tags `<img>` que o pandoc emite mesmo sem `--extract-media`.

    O writer GFM do pandoc referencia a imagem embutida do `.docx` (ex.:
    `<img src="media/rId20.png" .../>`) independente de `--extract-media` ter
    sido passado — sem essa flag, a imagem nunca é escrita em disco, e o link
    fica quebrado (erro 11). Chamar só quando
    `extract_media=False`, para que a imagem "saia" do `.md` sem deixar link
    órfão, do mesmo jeito que o caminho de PDF já se comporta.
    """
    md = re.sub(_IMG_TAG.pattern + r"\n\n", "", md)
    return _IMG_TAG.sub("", md)


def _drop_md_images(md: str) -> str:
    """Troca `![alt](destino)` pelo texto alternativo, ou remove quando não há texto.

    Com `sem_html=True` o pandoc emite imagem como `![]()` em vez de `<img>`; sem a
    mídia extraída, o link apontaria para um arquivo que não existe.
    """
    def troca(m: re.Match) -> str:
        alt = m.group(1).strip()
        return f"[imagem: {alt}]" if alt else ""

    return re.sub(r"\n{3,}", "\n\n", _IMAGEM_MD.sub(troca, md))


def _run_pandoc(
    src: Path, fmt: str, cwd: Path, media_dir_name: str | None, sem_html: bool = False
) -> str:
    """Roda pandoc com cwd na pasta de saída para que os links de mídia fiquem
    relativos ao .md gerado."""
    cmd = ["pandoc", "-f", fmt, "-t", "gfm-raw_html" if sem_html else "gfm", "--wrap=none"]
    if media_dir_name:
        cmd.append(f"--extract-media={media_dir_name}")
    cmd.append(str(src.resolve()))
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        encoding="utf-8",  # garante UTF-8 (acentuação PT-BR) em vez do locale
    )
    if proc.returncode != 0:
        raise ConversionError((proc.stderr or "").strip() or "falha no pandoc")
    return proc.stdout


def converter_pandoc(
    src: Path, ext: str, dst_dir: Path, media_base: str, *,
    extract_media: bool, sem_html: bool, silencioso: bool,
) -> Conversao:
    """Converte um formato da tabela `PANDOC_FORMATS`."""
    media_name = f"{media_base}_media" if extract_media else None
    md = _run_pandoc(src, PANDOC_FORMATS[ext], cwd=dst_dir, media_dir_name=media_name,
                     sem_html=sem_html)
    media_dir = None
    if media_name and (dst_dir / media_name).is_dir():
        media_dir = dst_dir / media_name
    if not extract_media:
        md = _drop_img_tags(md)
        if sem_html:
            md = _drop_md_images(md)
    return Conversao(md, "pandoc", media_dir)


def converter_sxw(
    src: Path, ext: str, dst_dir: Path, media_base: str, *,
    extract_media: bool, sem_html: bool, silencioso: bool,
) -> Conversao:
    """Converte `.sxw`; a saída não tem HTML, então `sem_html` não muda nada."""
    with Pacote(src) as pacote:
        leitor = Leitor(pacote, dst_dir, media_base, extract_media)
        blocos = leitor.blocos(pacote.corpo("text"))
    return Conversao(montar(blocos, leitor), "odf", leitor.media_dir, None, tuple(leitor.avisos()))


CONVERSORES = {ext: converter_pandoc for ext in PANDOC_FORMATS}
CONVERSORES[".sxw"] = converter_sxw
