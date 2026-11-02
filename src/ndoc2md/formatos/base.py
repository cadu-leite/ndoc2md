"""Contrato comum dos formatos: o que cada conversor devolve para o orquestrador."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Conversao:
    """Saída de um conversor de formato, antes do pós-processamento comum.

    O orquestrador (`converter.convert_file`) acrescenta avisos, aplica `--clean-toc`
    e o cabeçalho, e grava o `.md`.
    """

    md: str
    motor: str
    media_dir: Path | None = None
    paginas: int | None = None
    avisos: tuple[str, ...] = ()
