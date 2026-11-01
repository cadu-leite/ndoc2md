"""Núcleo de conversão: roteia cada extensão para o conversor do seu tipo e gera Markdown.

Os conversores ficam em `ndoc2md.formatos`, um módulo por tipo de documento. Aqui fica
o que é comum a todos: nome e pasta de saída, colisões, avisos, `--clean-toc`,
cabeçalho, gravação do `.md` e `--apagar-original`.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .erros import ConversionError, PdfSemTexto
from .formatos import CONVERSORES, pdf
from .formatos.pdf import EXT as PDF_EXT
from .formatos.texto import PANDOC_FORMATS, have_pandoc

__all__ = [
    "PANDOC_FORMATS",
    "PDF_EXT",
    "SUPPORTED_EXTENSIONS",
    "ConversionError",
    "PdfSemTexto",
    "Result",
    "check_path",
    "convert_file",
    "find_collisions",
    "gather",
    "have_pandoc",
    "resolve_dst",
    "strip_toc",
]

SUPPORTED_EXTENSIONS = set(CONVERSORES)

# Item de sumário gerado pelo pandoc, ex.: [Termos [2](#termos)](#termos)
# Assinatura segura: a linha inteira é um link e contém um link de número de
# página `[123](#...)`. Esse `[\d+](#` é exclusivo de sumário — links de corpo
# têm texto com palavras, não um número puro. (A âncora pode conter parênteses,
# como `#_Registro_(de_Imóveis)`, então não restringimos o miolo.)
_TOC_LINE = re.compile(r"^\s*\[.*\[\d+\]\(#.*\)\s*$")


@dataclass
class Result:
    source: Path
    output: Path
    engine: str
    toc_lines_removed: int = 0
    media_dir: Path | None = None
    sha256: str | None = None
    paginas: int | None = None
    avisos: tuple[str, ...] = ()
    original_apagado: bool = False


def strip_toc(md: str) -> tuple[str, int]:
    """Remove linhas de sumário/TOC e colapsa linhas em branco extras.

    Retorna (markdown_limpo, qtd_linhas_removidas) para que a remoção seja
    visível em vez de silenciosa.
    """
    lines = md.splitlines()
    kept = [ln for ln in lines if not _TOC_LINE.match(ln)]
    removed = len(lines) - len(kept)
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return (out + "\n") if out else "", removed


def _primeiro_ancestral_ausente(dir_: Path) -> Path | None:
    """Acha o ancestral mais alto de `dir_` que ainda não existe (o que `mkdir(parents=True)`
    criaria primeiro), ou `None` se `dir_` já existe. Serve para desfazer só a árvore nova
    criada por um `mkdir(parents=True)`, sem tocar em nada que já existia antes dele."""
    if dir_.exists():
        return None
    atual = dir_
    while atual.parent != atual and not atual.parent.exists():
        atual = atual.parent
    return atual


def resolve_dst(
    src: str | Path,
    output_dir: str | Path | None = None,
    input_root: str | Path | None = None,
    *,
    nome: str | None = None,
    prefixo_data: bool = False,
) -> Path:
    """Calcula o caminho de saída `.md` de `src`, sem tocar o sistema de arquivos.

    Mesma regra de `convert_file`: nome completo (com extensão) + `.md`, sob
    `output_dir` espelhando o caminho relativo a `input_root` quando os dois
    são dados. Serve para detectar colisão de destino antes de converter.

    `nome` troca o nome-base (a extensão de origem continua: `nome.pdf.md`), e
    `prefixo_data` põe a data de hoje na frente (`AAAA-MM-DD_`).
    """
    src = Path(src)
    if output_dir:
        dst_dir = Path(output_dir)
        if input_root is not None:
            dst_dir = dst_dir / src.parent.resolve().relative_to(Path(input_root).resolve())
    else:
        dst_dir = src.parent
    base = f"{nome}{src.suffix.lower()}" if nome else src.name
    prefixo = f"{date.today().isoformat()}_" if prefixo_data else ""
    return dst_dir / f"{prefixo}{base}.md"


def find_collisions(
    files: list[tuple[Path, Path]],
    output_dir: str | Path | None = None,
    *,
    prefixo_data: bool = False,
) -> dict[Path, list[Path]]:
    """Agrupa `files` (pares `(arquivo, raiz)` de `gather`) pelo destino `.md` que gerariam.

    Devolve só os destinos com mais de uma origem — por exemplo, duas raízes de
    entrada diferentes com um `a.docx` cada uma, sob o mesmo `output_dir`.
    """
    por_destino: dict[Path, list[Path]] = {}
    for src, root in files:
        dst = resolve_dst(src, output_dir, root, prefixo_data=prefixo_data)
        por_destino.setdefault(dst, []).append(src)
    return {dst: srcs for dst, srcs in por_destino.items() if len(srcs) > 1}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _cabecalho(titulo: str, src: Path, engine: str, sha: str, paginas: int | None) -> str:
    from . import __version__

    pags = f", {paginas} página(s)" if paginas is not None else ""
    return (
        f"# {titulo}\n\n"
        f"{date.today().isoformat()}, convertido de `{src.name}` por ndoc2md {__version__} "
        f"({engine}), sha256 `{sha[:12]}`{pags}.\n\n"
    )


def convert_file(
    src: str | Path,
    output_dir: str | Path | None = None,
    *,
    input_root: str | Path | None = None,
    clean_toc: bool = False,
    extract_media: bool = True,
    overwrite: bool = False,
    nome: str | None = None,
    prefixo_data: bool = False,
    cabecalho: bool = False,
    titulo: str | None = None,
    sem_html: bool = False,
    exigir_texto: bool = False,
    apagar_original: bool = False,
    silencioso: bool = False,
) -> Result:
    """Converte um único arquivo para `.md`. Lança ConversionError em falha.

    O nome de saída preserva a extensão de origem: `relatorio.docx` gera
    `relatorio.docx.md`, e a mídia vai para `relatorio.docx_media/`. Assim
    o tipo do arquivo original fica legível no nome da saída, e dois arquivos
    de mesmo nome com extensões diferentes deixam de disputar o mesmo `.md`.

    Com `output_dir` e `input_root`, o `.md` é gravado sob `output_dir`
    preservando o caminho relativo de `src` a `input_root` (espelha a árvore
    de origem em vez de achatar tudo num diretório só). Um lote com mais de
    um arquivo pode colidir no mesmo destino nesse caso — use `find_collisions`
    antes de converter para detectar isso.

    Opções novas (todas desligadas por padrão; desligadas, o resultado é o de antes):

    - `nome`, `prefixo_data`: nome do `.md` (ver `resolve_dst`).
    - `cabecalho`, `titulo`: o `.md` começa com `# título` e uma linha com data,
      arquivo de origem, versão do ndoc2md, motor, sha256 e páginas.
    - `sem_html`: pandoc com `gfm-raw_html`; no PDF, tira comentário HTML e troca `<br>`
      por quebra de linha.
    - `exigir_texto`: PDF sem texto em nenhuma página lança `PdfSemTexto` sem gravar
      nada; página escaneada no meio do PDF gera aviso.
    - `apagar_original`: apaga `src` depois da tentativa, com sucesso ou com falha
      (inclusive destino já existente). Arquivo ausente ou de extensão não suportada
      não é apagado.
    - `silencioso`: descarta os recados do pymupdf4llm no stdout e no stderr.
    """
    src = Path(src)
    if not src.is_file():
        raise ConversionError("arquivo não encontrado")
    ext = src.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ConversionError(f"extensão não suportada: {ext or '(sem extensão)'}")

    try:
        res = _convert(
            src, ext, output_dir, input_root, clean_toc, extract_media, overwrite, nome,
            prefixo_data, cabecalho, titulo, sem_html, exigir_texto, silencioso,
        )
    except ConversionError as exc:
        if apagar_original:
            src.unlink(missing_ok=True)
            exc.original_apagado = True
        raise
    if apagar_original:
        src.unlink(missing_ok=True)
        res.original_apagado = True
    return res


def _convert(
    src, ext, output_dir, input_root, clean_toc, extract_media, overwrite, nome,
    prefixo_data, cabecalho, titulo, sem_html, exigir_texto, silencioso,
) -> Result:
    dst = resolve_dst(src, output_dir, input_root, nome=nome, prefixo_data=prefixo_data)
    dst_dir = dst.parent
    if dst.exists() and not overwrite:
        raise ConversionError(f"já existe (use --overwrite): {dst}")

    avisos: list[str] = []
    if ext == PDF_EXT and exigir_texto:
        avisos = pdf.verificar_texto(src)

    # dst_dir precisa existir antes do engine rodar (pandoc usa cwd=dst_dir; o
    # pymupdf4llm cria a própria media_dir mas exige que o pai já exista). Guarda
    # o topo da árvore nova para desfazer se a conversão falhar depois, em vez de
    # deixar pasta vazia (ou parcialmente escrita) pra trás.
    topo_novo = _primeiro_ancestral_ausente(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    media_base = dst.name[: -len(".md")] if (nome or prefixo_data) else src.name
    try:
        conv = CONVERSORES[ext](
            src, ext, dst_dir, media_base,
            extract_media=extract_media, sem_html=sem_html, silencioso=silencioso,
        )
    except Exception:
        if topo_novo is not None:
            shutil.rmtree(topo_novo, ignore_errors=True)
        raise
    md, engine, media_dir, paginas = conv.md, conv.motor, conv.media_dir, conv.paginas
    avisos += conv.avisos

    for aviso in avisos:
        md += f"\n\n> **Aviso do ndoc2md:** {aviso}.\n"

    removed = 0
    if clean_toc:
        md, removed = strip_toc(md)

    sha = None
    if cabecalho:
        sha = _sha256(src)
        md = _cabecalho(titulo or src.stem, src, engine, sha, paginas) + md.strip() + "\n"

    dst.write_text(md, encoding="utf-8")
    return Result(src, dst, engine, removed, media_dir, sha, paginas, tuple(avisos))


def check_path(paths: list[str | Path]) -> None:
    """Garante que todo caminho em `paths` existe.

    Lança `ConversionError`, listando todos os que não existem, se algum faltar —
    para que um erro de digitação pare o lote inteiro em vez de ser silenciosamente
    ignorado (erro 3). Chamar antes de `gather`, que
    por si só descarta caminho inexistente sem avisar.
    """
    ausentes = [str(p) for p in paths if not Path(p).exists()]
    if ausentes:
        lista = ", ".join(ausentes)
        raise ConversionError(f"caminho não encontrado: {lista}")


def gather(paths, recursive: bool = True) -> list[tuple[Path, Path]]:
    """Expande arquivos e pastas em pares `(arquivo, raiz)`.

    A `raiz` é a pasta de entrada à qual o arquivo pertence (para pastas) ou
    o próprio diretório do arquivo (para arquivos soltos); serve para
    espelhar a árvore de origem sob `-o`. Ignora locks do Word (`~$...`) e
    qualquer coisa dentro de pastas `*_media`.
    """
    found: list[tuple[Path, Path]] = []
    seen: set[Path] = set()

    def add(f: Path, root: Path) -> None:
        key = f.resolve()
        if key not in seen:
            seen.add(key)
            found.append((f, root))

    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            for f in sorted(it):
                if (
                    f.is_file()
                    and f.suffix.lower() in SUPPORTED_EXTENSIONS
                    and not f.name.startswith("~$")
                    and not any(part.endswith("_media") for part in f.parts)
                ):
                    add(f, p)
        elif p.is_file():
            add(p, p.parent)
        # caminhos inexistentes são ignorados aqui; a CLI reporta lista vazia
    return found
