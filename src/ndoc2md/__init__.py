"""ndoc2md — conversão de documentos para Markdown preservando a hierarquia."""

from .converter import (
    ConversionError,
    Result,
    SUPPORTED_EXTENSIONS,
    convert_file,
    gather,
    have_pandoc,
)

__all__ = [
    "ConversionError",
    "Result",
    "SUPPORTED_EXTENSIONS",
    "convert_file",
    "gather",
    "have_pandoc",
]
__version__ = "0.2.0"
