"""Fixtures compartilhadas: geram .docx (via pandoc) e imagens PNG sem depender do Word ou do Pillow."""

from __future__ import annotations

import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

pandoc_disponivel = shutil.which("pandoc") is not None

try:
    import pymupdf4llm  # noqa: F401

    pdf_disponivel = True
except ImportError:
    pdf_disponivel = False

requer_pandoc = pytest.mark.skipif(not pandoc_disponivel, reason="pandoc não está no PATH")
requer_pdf = pytest.mark.skipif(
    not pdf_disponivel, reason="extra `pdf` não instalado (uv sync --extra pdf)"
)


def _run_pandoc(args: list[str]) -> None:
    proc = subprocess.run(["pandoc", *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def make_png(path: Path, color: tuple[int, int, int] = (200, 30, 30), size: int = 4) -> Path:
    """Grava um PNG RGB válido, sem depender do Pillow."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(
            ">I", zlib.crc32(tag + data) & 0xFFFFFFFF
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(color) * size for _ in range(size))
    idat = zlib.compress(raw)
    path.write_bytes(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))
    return path


def make_docx(pasta: Path, nome: str, markdown: str) -> Path:
    """Converte `markdown` para `<pasta>/<nome>` (.docx) via pandoc."""
    pasta.mkdir(parents=True, exist_ok=True)
    md_file = pasta / f"_fonte_{nome}.md"
    md_file.write_text(markdown, encoding="utf-8")
    docx = pasta / nome
    _run_pandoc(["-f", "markdown", "-t", "docx", str(md_file), "-o", str(docx)])
    return docx


def make_docx_with_image(pasta: Path, nome: str) -> Path:
    """`.docx` com uma imagem embutida, para os casos de mídia."""
    png = make_png(pasta / "_fonte_imagem.png")
    return make_docx(pasta, nome, f"# Titulo\n\n![alt]({png.resolve()})\n")


@pytest.fixture
def basic_docx(tmp_path):
    return make_docx(tmp_path, "doc.docx", "# Titulo 1\n\ntexto\n\n## Titulo 2\n\nmais texto\n")


def make_pdf(pasta: Path, nome: str, desenhar) -> Path:
    """PDF de uma página só, com o conteúdo que `desenhar(page)` desenhar (via `fitz`)."""
    import fitz

    pasta.mkdir(parents=True, exist_ok=True)
    pdf = pasta / nome
    doc = fitz.open()
    page = doc.new_page()
    desenhar(page)
    doc.save(pdf)
    doc.close()
    return pdf
