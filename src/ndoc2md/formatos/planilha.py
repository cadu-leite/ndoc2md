"""Planilhas: `.ods` (Calc, OpenDocument) e `.sxc` (Calc do OpenOffice 1.x).

Cada aba vira uma seção `## nome da aba` com uma tabela GFM. A célula sai com o texto
exibido (o valor já formatado, e o resultado da fórmula, não a fórmula). As linhas e
colunas vazias das bordas saem; a primeira linha com conteúdo vira o cabeçalho.
"""

from __future__ import annotations

from pathlib import Path

from .base import Conversao
from .odf import Leitor, Pacote, montar


def converter_planilha(
    src: Path, ext: str, dst_dir: Path, media_base: str, *,
    extract_media: bool, sem_html: bool, silencioso: bool,
) -> Conversao:
    """Converte `.ods` ou `.sxc`; a saída não tem HTML, então `sem_html` não muda nada."""
    with Pacote(src) as pacote:
        leitor = Leitor(pacote, dst_dir, media_base, extract_media)
        abas = [el for el in pacote.corpo("spreadsheet") if el.tag == "table:table"]
        blocos: list[str] = []
        for n, aba in enumerate(abas, 1):
            nome = aba.get("table:name") or f"Aba {n}"
            leitor.local = f"a aba {nome}"
            oculta = pacote.propriedade(aba.get("table:style-name"), "table:display") == "false"
            blocos.append(f"## {nome} (oculta)" if oculta else f"## {nome}")
            tabela = leitor.tabela(aba)
            blocos.append(tabela or "*(aba vazia)*")
            # Imagens e gráficos soltos sobre a aba (não presos a uma célula).
            formas = aba.find("table:shapes")
            if formas is not None:
                blocos += leitor.blocos(formas)
    return Conversao(montar(blocos, leitor), "odf", leitor.media_dir, None, tuple(leitor.avisos()))


CONVERSORES = {".ods": converter_planilha, ".sxc": converter_planilha}
