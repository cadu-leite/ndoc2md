"""Leitura direta do XML de pacotes OpenDocument (ODF) e OpenOffice.org 1.x.

O pandoc só lê `.odt`. Apresentação (`.odp`, `.sxi`), planilha (`.ods`, `.sxc`) e o texto
do OpenOffice 1.x (`.sxw`) são lidos aqui: o pacote é um zip, e o conteúdo fica em
`content.xml`. Só a biblioteca padrão é usada (`zipfile` e `xml.etree`).

O OpenOffice 1.x usa os mesmos nomes de elemento do ODF, com outros namespaces
(`http://openoffice.org/2000/...`). Ao abrir o pacote, cada tag e cada atributo vira
`prefixo:nome` (ex.: `text:p`), igual nos dois formatos; o resto do código só compara
com esses nomes.

Diferenças do 1.x que o código trata: lista numerada é `text:ordered-list` e lista com
marcador é `text:unordered-list`; título usa `text:level` (no ODF, `text:outline-level`);
quadro de texto de slide é `draw:text-box` direto na página; nota de rodapé é
`text:footnote`; link de imagem começa com `#` (`#Pictures/...`); e `office:body` traz
o conteúdo direto, sem `office:text`/`office:presentation`/`office:spreadsheet`.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from ..erros import ConversionError

if TYPE_CHECKING:
    from typing_extensions import Self

_PREFIXOS = {
    # ODF (OASIS)
    "urn:oasis:names:tc:opendocument:xmlns:office:1.0": "office",
    "urn:oasis:names:tc:opendocument:xmlns:style:1.0": "style",
    "urn:oasis:names:tc:opendocument:xmlns:text:1.0": "text",
    "urn:oasis:names:tc:opendocument:xmlns:table:1.0": "table",
    "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0": "draw",
    "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0": "presentation",
    "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0": "svg",
    # OpenOffice.org 1.x
    "http://openoffice.org/2000/office": "office",
    "http://openoffice.org/2000/style": "style",
    "http://openoffice.org/2000/text": "text",
    "http://openoffice.org/2000/table": "table",
    "http://openoffice.org/2000/drawing": "draw",
    "http://openoffice.org/2000/presentation": "presentation",
    "http://www.w3.org/2000/svg": "svg",
    # comum aos dois
    "http://www.w3.org/1999/xlink": "xlink",
}

_LISTAS = {"text:list", "text:ordered-list", "text:unordered-list"}
_ITENS_DE_LISTA = {"text:list-item", "text:list-header"}
_NOTAS = {"text:note", "text:footnote", "text:endnote"}
_CORPO_DA_NOTA = {"text:note-body", "text:footnote-body", "text:endnote-body"}
# Agrupam linhas de tabela sem serem linhas.
_GRUPOS_DE_LINHAS = {"table:table-header-rows", "table:table-rows", "table:table-row-group"}
# Conteúdo gerado ou fora do texto corrido: sumário e índices, comentários, controle de
# alterações, declarações e formulários.
_IGNORADOS = {
    "text:table-of-content", "text:illustration-index", "text:table-index",
    "text:object-index", "text:user-index", "text:alphabetical-index",
    "text:bibliography", "text:tracked-changes", "office:annotation",
    "office:annotation-end", "text:sequence-decls", "text:variable-decls",
    "text:user-field-decls", "text:dde-connection-decls", "office:forms",
    "table:table-column", "table:table-columns", "table:table-header-columns",
    "table:table-column-group", "table:named-expressions", "table:database-ranges",
    "table:data-pilot-tables", "table:content-validations", "table:calculation-settings",
    "table:label-ranges", "draw:enhanced-geometry", "svg:title", "svg:desc",
    "presentation:animations", "presentation:settings", "office:event-listeners",
    "draw:glue-point",
}
# Alternativas de conteúdo dentro de `draw:frame`; vale a primeira que aparecer (as
# seguintes são substitutas, como a prévia `.svm` de uma tabela do Impress).
_CONTEUDO_DE_QUADRO = {
    "draw:text-box", "table:table", "draw:image", "draw:object", "draw:object-ole",
    "draw:plugin", "draw:applet",
}
_OBJETOS = {"draw:object", "draw:object-ole", "draw:plugin", "draw:applet"}
# Valor da célula sem `text:p` (o LibreOffice sempre grava o texto exibido; outros
# geradores podem gravar só o valor). ODF usa `office:`, o 1.x usa `table:`.
_VALORES_DE_CELULA = tuple(
    f"{prefixo}:{nome}"
    for nome in ("string-value", "value", "date-value", "time-value", "boolean-value")
    for prefixo in ("office", "table")
)
_URL_EXTERNA = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def _nome(chave: str) -> str:
    """`{uri}local` -> `prefixo:local` quando o namespace é conhecido."""
    if chave.startswith("{"):
        uri, _, local = chave[1:].partition("}")
        prefixo = _PREFIXOS.get(uri)
        if prefixo:
            return f"{prefixo}:{local}"
    return chave


def _inteiro(valor: str | None, padrao: int = 1) -> int:
    try:
        return max(int(valor), 0) if valor is not None else padrao
    except ValueError:
        return padrao


def _uma_linha(texto: str) -> str:
    return " ".join(texto.split())


class Pacote:
    """Um pacote ODF ou OpenOffice 1.x aberto, com o `content.xml` já normalizado.

    Use com `with`, que fecha o zip no fim.
    """

    def __init__(self, src: Path):
        self._zip: zipfile.ZipFile | None = None
        try:
            self._zip = zipfile.ZipFile(src)
            self.raiz = self._ler_xml("content.xml")
            estilos = (
                self._ler_xml("styles.xml") if "styles.xml" in self._zip.namelist() else None
            )
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            self.close()
            raise ConversionError(f"não é um pacote OpenDocument válido: {exc}") from exc
        # Índice nome -> estilo; o `content.xml` vem antes do `styles.xml`.
        self._estilos: dict[str, ET.Element] = {}
        for raiz in (self.raiz, estilos):
            if raiz is None:
                continue
            for el in raiz.iter():
                if el.tag in ("style:style", "text:list-style") and el.get("style:name"):
                    self._estilos.setdefault(el.get("style:name"), el)

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _ler_xml(self, nome: str) -> ET.Element:
        raiz = ET.fromstring(self._zip.read(nome))
        for el in raiz.iter():
            if isinstance(el.tag, str):
                el.tag = _nome(el.tag)
            if el.attrib:
                el.attrib = {_nome(k): v for k, v in el.attrib.items()}
        return raiz

    def corpo(self, tipo: str) -> ET.Element:
        """Elemento que contém o documento: `office:<tipo>` no ODF, `office:body` no 1.x."""
        body = self.raiz.find("office:body")
        if body is None:
            raise ConversionError("não é um pacote OpenDocument válido: sem office:body")
        interno = body.find(f"office:{tipo}")
        return interno if interno is not None else body

    def ler(self, caminho: str) -> bytes | None:
        try:
            return self._zip.read(caminho)
        except KeyError:
            return None

    def estilo(self, nome: str | None) -> ET.Element | None:
        """`style:style` ou `text:list-style` com esse nome (automático ou comum)."""
        return self._estilos.get(nome) if nome else None

    def propriedade(self, nome_estilo: str | None, atributo: str) -> str | None:
        """Valor de `atributo` em qualquer `*-properties` do estilo (ODF) ou no próprio
        elemento `style:properties` (1.x)."""
        estilo = self.estilo(nome_estilo)
        if estilo is None:
            return None
        for el in estilo.iter():
            if atributo in el.attrib:
                return el.get(atributo)
        return None

    def lista_numerada(self, nome_estilo: str | None, nivel: int) -> bool:
        """True se o estilo de lista numera esse nível (1 = primeiro)."""
        estilo = self.estilo(nome_estilo)
        if estilo is None:
            return False
        for el in estilo:
            if el.get("text:level") == str(nivel):
                return el.tag == "text:list-level-style-number"
        return False


class Leitor:
    """Transforma elementos ODF em blocos de Markdown.

    Guarda o estado de uma conversão: pasta de mídia, imagens já copiadas, notas de
    rodapé e a contagem de objetos incorporados (gráfico, fórmula, OLE) que ficam de
    fora, para o aviso no fim do `.md`.
    """

    def __init__(self, pacote: Pacote, dst_dir: Path, media_base: str, extract_media: bool):
        self.pacote = pacote
        self._dst_dir = dst_dir
        self._media_name = f"{media_base}_media" if extract_media else None
        self._copiadas: dict[str, str] = {}
        self._notas: list[str] = []
        self.local = "o documento"
        self._objetos: dict[str, int] = {}
        self._externas: dict[str, int] = {}

    # --- resultado ---------------------------------------------------------------

    @property
    def media_dir(self) -> Path | None:
        if self._media_name and self._copiadas:
            return self._dst_dir / self._media_name
        return None

    def notas_de_rodape(self) -> str:
        return "\n".join(f"[^{i}]: {t}" for i, t in enumerate(self._notas, 1))

    def avisos(self) -> list[str]:
        avisos = [
            f"{local} tem {n} objeto(s) incorporado(s) (gráfico, fórmula ou OLE) "
            "que não está(ão) neste Markdown"
            for local, n in self._objetos.items()
        ]
        avisos += [
            f"{local} tem {n} imagem(ns) vinculada(s) a arquivo externo, "
            "fora deste Markdown"
            for local, n in self._externas.items()
        ]
        return avisos

    # --- texto corrido -------------------------------------------------------------

    def inline(self, el: ET.Element) -> str:
        """Texto de um parágrafo, com espaços (`text:s`), links, imagens e notas."""
        partes = [el.text or ""]
        for filho in el:
            tag = filho.tag
            if tag == "text:s":
                partes.append(" " * _inteiro(filho.get("text:c")))
            elif tag == "text:tab":
                partes.append(" ")
            elif tag == "text:line-break":
                partes.append("\n")
            elif tag in _NOTAS:
                partes.append(self._nota(filho))
            elif tag == "text:a":
                texto = self.inline(filho)
                href = filho.get("xlink:href", "")
                usar_link = href and not href.startswith("#") and texto.strip()
                partes.append(f"[{texto}]({href})" if usar_link else texto)
            elif tag in ("draw:frame", "draw:image", "draw:a", "draw:g"):
                partes.append(" ".join(self.bloco(filho)))
            elif tag not in _IGNORADOS and isinstance(tag, str):
                partes.append(self.inline(filho))
            partes.append(filho.tail or "")
        return "".join(partes)

    def _nota(self, el: ET.Element) -> str:
        corpo = next((f for f in el if f.tag in _CORPO_DA_NOTA), None)
        if corpo is None:
            return ""
        self._notas.append(_uma_linha(" ".join(self.blocos(corpo))))
        return f"[^{len(self._notas)}]"

    def texto_plano(self, el: ET.Element) -> str:
        """Todo o texto de um elemento numa linha só (título de slide, célula)."""
        return _uma_linha(" ".join(self.bloco(el)))

    # --- blocos ------------------------------------------------------------------

    def blocos(self, el: ET.Element) -> list[str]:
        """Blocos de Markdown dos filhos de `el`, na ordem do documento.

        Listas vizinhas viram um bloco só: o Impress grava cada item de primeiro nível
        numa `text:list` própria, e a linha em branco entre elas separaria os itens.
        """
        saida: list[str] = []
        lista_antes = False
        for filho in el:
            novos = self.bloco(filho)
            if not novos:
                continue
            e_lista = filho.tag in _LISTAS
            if e_lista and lista_antes:
                saida[-1] += "\n" + novos[0]
                novos = novos[1:]
            saida += novos
            lista_antes = e_lista
        return saida

    def bloco(self, el: ET.Element) -> list[str]:
        tag = el.tag
        if tag in _IGNORADOS or not isinstance(tag, str):
            return []
        if tag == "text:h":
            nivel = _inteiro(el.get("text:outline-level") or el.get("text:level"))
            texto = _uma_linha(self.inline(el))
            return [f"{'#' * min(max(nivel, 1), 6)} {texto}"] if texto else []
        if tag == "text:p":
            texto = self.inline(el).strip()
            return [texto] if texto else []
        if tag in _LISTAS:
            linhas = self.lista(el, 0, el.get("text:style-name"))
            return ["\n".join(linhas)] if linhas else []
        if tag == "table:table":
            tabela = self.tabela(el)
            return [tabela] if tabela else []
        if tag == "draw:frame":
            return self._quadro(el)
        if tag == "draw:image":
            imagem = self.imagem(el.get("xlink:href", ""), "")
            return [imagem] if imagem else []
        if tag in _OBJETOS:
            self._objetos[self.local] = self._objetos.get(self.local, 0) + 1
            return []
        return self.blocos(el)

    def _quadro(self, quadro: ET.Element) -> list[str]:
        conteudo = next((f for f in quadro if f.tag in _CONTEUDO_DE_QUADRO), None)
        if conteudo is None:
            return []
        if conteudo.tag == "draw:image":
            alt = next(
                (_uma_linha(f.text or "") for f in quadro if f.tag in ("svg:title", "svg:desc")),
                "",
            )
            imagem = self.imagem(conteudo.get("xlink:href", ""), alt)
            return [imagem] if imagem else []
        return self.bloco(conteudo)

    def lista(self, el: ET.Element, nivel: int, estilo: str | None) -> list[str]:
        """Linhas de uma lista; cada nível de aninhamento recua 4 espaços.

        No ODF, o aninhamento é `text:list` dentro de `text:list-item`, e o item de fora
        pode não ter parágrafo (só serve de degrau). O estilo da lista de fora vale para
        as de dentro quando elas não declaram o próprio.
        """
        estilo = el.get("text:style-name") or estilo
        if el.tag == "text:ordered-list":
            numerada = True
        elif el.tag == "text:unordered-list":
            numerada = False
        else:
            numerada = self.pacote.lista_numerada(estilo, nivel + 1)
        recuo = "    " * nivel
        linhas: list[str] = []
        n = 0
        for item in el:
            if item.tag not in _ITENS_DE_LISTA:
                continue
            for parte in item:
                if parte.tag in _LISTAS:
                    linhas += self.lista(parte, nivel + 1, estilo)
                    continue
                for bloco in self.bloco(parte):
                    if parte.tag in ("text:p", "text:h"):
                        n += 1
                        marcador = f"{n}." if numerada else "-"
                        linhas.append(f"{recuo}{marcador} {_uma_linha(bloco)}")
                    else:
                        linhas += [f"{recuo}    {ln}" for ln in bloco.splitlines()]
        return linhas

    # --- tabelas -------------------------------------------------------------------

    def linhas_da_tabela(self, tabela: ET.Element) -> list[list[str]]:
        """Células da tabela como texto, sem as linhas e colunas vazias das bordas.

        Planilha marca repetição com `table:number-rows-repeated` e
        `table:number-columns-repeated` (é comum o resto da folha vir como uma linha
        vazia repetida 1 milhão de vezes). Linha ou célula vazia só é expandida quando
        há conteúdo depois dela; a sobra vazia no fim é descartada.
        """
        linhas: list[list[str]] = []
        vazias_pendentes = 0
        for linha, repeticoes in self._linhas(tabela):
            celulas = self._celulas(linha)
            if not celulas:
                if linhas:
                    vazias_pendentes += repeticoes
                continue
            linhas.extend([] for _ in range(vazias_pendentes))
            vazias_pendentes = 0
            linhas.extend(list(celulas) for _ in range(repeticoes))
        if not linhas:
            return []
        primeira = min(
            next(i for i, c in enumerate(lin) if c) for lin in linhas if any(lin)
        )
        largura = max(len(lin) for lin in linhas) - primeira
        return [(lin[primeira:] + [""] * largura)[:largura] for lin in linhas]

    def _linhas(self, el: ET.Element):
        for filho in el:
            if filho.tag == "table:table-row":
                yield filho, _inteiro(filho.get("table:number-rows-repeated"))
            elif filho.tag in _GRUPOS_DE_LINHAS:
                yield from self._linhas(filho)

    def _celulas(self, linha: ET.Element) -> list[str]:
        celulas: list[str] = []
        vazias_pendentes = 0
        for cel in linha:
            if cel.tag not in ("table:table-cell", "table:covered-table-cell"):
                continue
            repeticoes = _inteiro(cel.get("table:number-columns-repeated"))
            texto = ""
            if cel.tag == "table:table-cell":
                texto = _uma_linha(" ".join(self.blocos(cel)))
                if not texto:
                    texto = next((cel.get(a) for a in _VALORES_DE_CELULA if cel.get(a)), "")
            if not texto:
                vazias_pendentes += repeticoes
                continue
            celulas.extend([""] * vazias_pendentes)
            vazias_pendentes = 0
            celulas.extend([texto] * repeticoes)
        return celulas

    def tabela(self, el: ET.Element) -> str:
        """Tabela GFM; a primeira linha com conteúdo vira o cabeçalho."""
        return tabela_gfm(self.linhas_da_tabela(el))

    # --- imagens -------------------------------------------------------------------

    def imagem(self, href: str, alt: str) -> str:
        """Copia a imagem do pacote para a pasta de mídia e devolve o link `![alt](...)`.

        Só copia o que está dentro do pacote; o nome do arquivo de destino é só o nome
        final do caminho (nada de `..`). URL `http(s)://` vira link direto; outro arquivo
        externo conta para o aviso. Com `extract_media=False`, a imagem sai do Markdown.
        """
        href = href.removeprefix("#").removeprefix("./")
        if not href or self._media_name is None:
            return ""
        alt = alt.replace("[", "(").replace("]", ")")
        if _URL_EXTERNA.match(href) and href.lower().startswith(("http://", "https://")):
            return f"![{alt}]({_destino_md(href)})"
        dados = None if _URL_EXTERNA.match(href) or href.startswith("/") else self.pacote.ler(href)
        if dados is None:
            self._externas[self.local] = self._externas.get(self.local, 0) + 1
            return ""
        if href not in self._copiadas:
            nome = PurePosixPath(href).name
            pasta = self._dst_dir / self._media_name
            pasta.mkdir(exist_ok=True)
            (pasta / nome).write_bytes(dados)
            self._copiadas[href] = f"{self._media_name}/{nome}"
        return f"![{alt}]({_destino_md(self._copiadas[href])})"


def _destino_md(destino: str) -> str:
    """Destino de link Markdown; entre `<>` quando tem espaço ou parêntese."""
    return f"<{destino}>" if re.search(r"[\s()<>]", destino) else destino


def _celula_gfm(texto: str) -> str:
    return texto.replace("|", "\\|")


def tabela_gfm(linhas: list[list[str]]) -> str:
    if not linhas:
        return ""
    cab, *corpo = linhas
    saida = [
        "| " + " | ".join(_celula_gfm(c) for c in cab) + " |",
        "|" + "|".join("-" * max(3, len(_celula_gfm(c)) + 2) for c in cab) + "|",
    ]
    saida += ["| " + " | ".join(_celula_gfm(c) for c in lin) + " |" for lin in corpo]
    return "\n".join(saida)


def montar(blocos: list[str], leitor: Leitor) -> str:
    """Junta os blocos com linha em branco e põe as notas de rodapé no fim."""
    md = "\n\n".join(b for b in blocos if b)
    notas = leitor.notas_de_rodape()
    if notas:
        md = f"{md}\n\n{notas}" if md else notas
    return md + "\n" if md else ""
