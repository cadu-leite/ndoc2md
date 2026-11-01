"""Conversores por tipo de documento.

Cada módulo trata um tipo e expõe `CONVERSORES`, um dicionário extensão -> função
com a assinatura `(src, ext, dst_dir, media_base, *, extract_media, sem_html, silencioso)`
que devolve uma `Conversao`.

- `texto`: formatos de escritório e de marcação, pelo pandoc.
- `pdf`: PDF, pelo pymupdf4llm.
"""

from __future__ import annotations

from . import pdf, texto

CONVERSORES = {**texto.CONVERSORES, **pdf.CONVERSORES}
