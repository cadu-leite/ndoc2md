"""Conversores por tipo de documento.

Cada módulo trata um tipo e expõe `CONVERSORES`, um dicionário extensão -> função
com a assinatura `(src, ext, dst_dir, media_base, *, extract_media, sem_html, silencioso)`
que devolve uma `Conversao`.

- `texto`: formatos de escritório e de marcação, pelo pandoc; `.sxw` pelo XML.
- `pdf`: PDF, pelo pymupdf4llm.
- `apresentacao`: `.odp` e `.sxi`, pelo XML.
- `planilha`: `.ods` e `.sxc`, pelo XML.

`odf` é o leitor de XML comum aos formatos do OpenDocument e do OpenOffice 1.x.
"""

from __future__ import annotations

from . import apresentacao, pdf, planilha, texto

CONVERSORES = {
    **texto.CONVERSORES,
    **pdf.CONVERSORES,
    **apresentacao.CONVERSORES,
    **planilha.CONVERSORES,
}
