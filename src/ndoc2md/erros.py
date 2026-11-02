"""Exceções do ndoc2md, num módulo sem dependências para que todo formato possa importá-las."""

from __future__ import annotations


class ConversionError(RuntimeError):
    """Falha ao converter um arquivo."""

    original_apagado = False


class PdfSemTexto(ConversionError):
    """PDF sem camada de texto (escaneado), com `exigir_texto=True`."""
