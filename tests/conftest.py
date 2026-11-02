"""Fixtures compartilhadas: geram .docx (via pandoc), pacotes OpenDocument e OpenOffice 1.x
(zip montado aqui) e imagens PNG, sem depender do Word, do LibreOffice ou do Pillow."""

from __future__ import annotations

import shutil
import struct
import subprocess
import zipfile
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


_NS_ODF = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "presentation": "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
}
_NS_OOO1 = {
    "office": "http://openoffice.org/2000/office",
    "style": "http://openoffice.org/2000/style",
    "text": "http://openoffice.org/2000/text",
    "table": "http://openoffice.org/2000/table",
    "draw": "http://openoffice.org/2000/drawing",
    "presentation": "http://openoffice.org/2000/presentation",
    "svg": "http://www.w3.org/2000/svg",
    "fo": "http://www.w3.org/1999/XSL/Format",
    "xlink": "http://www.w3.org/1999/xlink",
}
# extensão -> (mimetype, elemento que embrulha o corpo no ODF; o 1.x não embrulha)
_TIPOS_ODF = {
    ".odp": ("application/vnd.oasis.opendocument.presentation", "presentation"),
    ".ods": ("application/vnd.oasis.opendocument.spreadsheet", "spreadsheet"),
    ".odt": ("application/vnd.oasis.opendocument.text", "text"),
    ".sxi": ("application/vnd.sun.xml.impress", None),
    ".sxc": ("application/vnd.sun.xml.calc", None),
    ".sxw": ("application/vnd.sun.xml.writer", None),
}


def make_odf(
    pasta: Path, nome: str, corpo: str, *, estilos: str = "", arquivos: dict[str, bytes] | None = None
) -> Path:
    """Pacote ODF, ou OpenOffice 1.x, conforme a extensão de `nome`.

    `corpo` vai dentro de `office:body` (no ODF, dentro de `office:presentation`,
    `office:spreadsheet` ou `office:text`); `estilos` vai em `office:automatic-styles`;
    `arquivos` entra no zip como está (ex.: `{"Pictures/a.png": ...}`). O `mimetype` é o
    primeiro item do zip, sem compressão, como o LibreOffice grava.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    mimetype, embrulho = _TIPOS_ODF[Path(nome).suffix]
    legado = embrulho is None
    ns = _NS_OOO1 if legado else _NS_ODF
    xmlns = " ".join(f'xmlns:{p}="{u}"' for p, u in ns.items())
    if embrulho:
        corpo = f"<office:{embrulho}>{corpo}</office:{embrulho}>"
    versao = "" if legado else ' office:version="1.3"'
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<office:document-content {xmlns}{versao}>"
        f"<office:automatic-styles>{estilos}</office:automatic-styles>"
        f"<office:body>{corpo}</office:body></office:document-content>"
    )
    arquivos = arquivos or {}
    ns_manifest = (
        "http://openoffice.org/2001/manifest" if legado
        else "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
    )
    entradas = "".join(
        f'<manifest:file-entry manifest:media-type="{tipo}" manifest:full-path="{caminho}"/>'
        for caminho, tipo in [("/", mimetype), ("content.xml", "text/xml")]
        + [(c, "image/png") for c in arquivos]
    )
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<manifest:manifest xmlns:manifest="{ns_manifest}">{entradas}</manifest:manifest>'
    )
    destino = pasta / nome
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), mimetype, compress_type=zipfile.ZIP_STORED)
        z.writestr("content.xml", content)
        z.writestr("META-INF/manifest.xml", manifest)
        for caminho, dados in arquivos.items():
            z.writestr(caminho, dados)
    return destino


def png_bytes(color: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    """Bytes de um PNG válido (o mesmo de `make_png`, sem gravar arquivo)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        return make_png(Path(tmp) / "x.png", color).read_bytes()
