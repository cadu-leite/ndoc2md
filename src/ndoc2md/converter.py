"""Núcleo de conversão: roteia cada extensão para o motor certo e gera Markdown.

- Formatos de escritório (docx, odt, html, rtf, epub, ...) -> pandoc (preserva a
  hierarquia de títulos a partir dos estilos "Título 1/2/3" do Word).
- PDF -> pymupdf4llm (extra opcional `pdf`), já que o pandoc não lê PDF.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# extensão -> formato de entrada do pandoc
PANDOC_FORMATS = {
    ".docx": "docx",
    ".odt": "odt",
    ".html": "html",
    ".htm": "html",
    ".rtf": "rtf",
    ".epub": "epub",
    ".tex": "latex",
    ".org": "org",
    ".rst": "rst",
    ".textile": "textile",
}
PDF_EXT = ".pdf"
SUPPORTED_EXTENSIONS = set(PANDOC_FORMATS) | {PDF_EXT}

# Item de sumário gerado pelo pandoc, ex.: [Termos [2](#termos)](#termos)
# Assinatura segura: a linha inteira é um link e contém um link de número de
# página `[123](#...)`. Esse `[\d+](#` é exclusivo de sumário — links de corpo
# têm texto com palavras, não um número puro. (A âncora pode conter parênteses,
# como `#_Registro_(de_Imóveis)`, então não restringimos o miolo.)
_TOC_LINE = re.compile(r"^\s*\[.*\[\d+\]\(#.*\)\s*$")


class ConversionError(RuntimeError):
    """Falha ao converter um arquivo."""


@dataclass
class Result:
    source: Path
    output: Path
    engine: str
    toc_lines_removed: int = 0
    media_dir: Path | None = None


def have_pandoc() -> bool:
    """True se o binário `pandoc` está no PATH."""
    return shutil.which("pandoc") is not None


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


_IMG_TAG = re.compile(r"<img\b[^>]*/?>")


def _drop_img_tags(md: str) -> str:
    """Remove tags `<img>` que o pandoc emite mesmo sem `--extract-media`.

    O writer GFM do pandoc referencia a imagem embutida do `.docx` (ex.:
    `<img src="media/rId20.png" .../>`) independente de `--extract-media` ter
    sido passado — sem essa flag, a imagem nunca é escrita em disco, e o link
    fica quebrado (erro 11). Chamar só quando
    `extract_media=False`, para que a imagem "saia" do `.md` sem deixar link
    órfão, do mesmo jeito que o caminho de PDF já se comporta.
    """
    md = re.sub(_IMG_TAG.pattern + r"\n\n", "", md)
    return _IMG_TAG.sub("", md)


def _run_pandoc(src: Path, fmt: str, cwd: Path, media_dir_name: str | None) -> str:
    """Roda pandoc com cwd na pasta de saída para que os links de mídia fiquem
    relativos ao .md gerado."""
    cmd = ["pandoc", "-f", fmt, "-t", "gfm", "--wrap=none"]
    if media_dir_name:
        cmd.append(f"--extract-media={media_dir_name}")
    cmd.append(str(src.resolve()))
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        encoding="utf-8",  # garante UTF-8 (acentuação PT-BR) em vez do locale
    )
    if proc.returncode != 0:
        raise ConversionError((proc.stderr or "").strip() or "falha no pandoc")
    return proc.stdout


def _warn_empty_pages(src: Path, chunks: list[dict]) -> str:
    """Reconstrói o Markdown a partir de `chunks` (`page_chunks=True`), avisando
    página que não gerou texto nem imagem apesar de ter desenho vetorial.

    O `pymupdf4llm` descarta traço/preenchimento vetorial isolado (uma forma
    sozinha, sem se agrupar com outras) por achar que é "açúcar" decorativo —
    e não avisa quando isso deixa a página inteira sem nada reconhecível
    (erro 12). Aqui a gente cruza cada página vazia
    do resultado com `page.get_drawings()` na própria fonte: se a página tem
    desenho vetorial e ainda assim não sobrou texto, imagem nem tabela, isso
    quase certo é conteúdo perdido — não uma página em branco de verdade.
    """
    import pymupdf

    doc = pymupdf.open(str(src.resolve()))
    try:
        partes = []
        for i, chunk in enumerate(chunks):
            texto = chunk["text"]
            vazia = not texto.strip() and not chunk["images"] and not chunk["tables"]
            if vazia and i < doc.page_count and doc[i].get_drawings():
                texto = (
                    f"\n\n> **Aviso do ndoc2md:** a página {i + 1} tem desenho vetorial "
                    "que não virou texto nem imagem no Markdown — confira o PDF original.\n\n"
                )
            partes.append(texto)
    finally:
        doc.close()
    return "".join(partes)


def _run_pdf(src: Path, media_dir: Path | None) -> tuple[str, Path | None]:
    """Converte PDF via pymupdf4llm.

    Se `media_dir` for dado, extrai figuras/diagramas como PNG para lá e
    reescreve os links no Markdown para ficarem relativos ao `.md` gerado
    (mesma semântica do caminho pandoc). Sem `media_dir`, extrai só texto.
    """
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise ConversionError(
            "suporte a PDF não instalado — rode: uv sync --extra pdf"
        ) from exc
    if media_dir is None:
        chunks = pymupdf4llm.to_markdown(str(src.resolve()), page_chunks=True)
        return _warn_empty_pages(src, chunks), None
    chunks = pymupdf4llm.to_markdown(
        str(src.resolve()),
        page_chunks=True,
        write_images=True,
        image_path=str(media_dir),
        image_format="png",
        dpi=150,
    )
    md = _warn_empty_pages(src, chunks)
    # pymupdf4llm insere o próprio image_path como prefixo do link, sempre como
    # `![](<prefixo>/arquivo.png)` (única sintaxe de imagem que ele emite); torná-lo
    # relativo à pasta do .md (o .md e a pasta de mídia são irmãos) mirando só essa
    # sintaxe, para não reescrever o caminho se ele aparecer no texto do documento.
    prefix = str(media_dir)
    # `![]( ... )` sempre sozinho na linha (pymupdf4llm emite exatamente
    # "\n![](%s)\n") — casar a linha inteira, com `.*` guloso até o `)` final,
    # em vez de `[^)]*`, porque o nome do arquivo de origem pode ter parênteses.
    img_tag = re.compile(r"^!\[\]\(" + re.escape(prefix) + r"/?(.*)\)$", re.MULTILINE)
    md = img_tag.sub(lambda m: f"![]({media_dir.name}/{m.group(1)})", md)
    return md, (media_dir if media_dir.is_dir() else None)


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
) -> Path:
    """Calcula o caminho de saída `.md` de `src`, sem tocar o sistema de arquivos.

    Mesma regra de `convert_file`: nome completo (com extensão) + `.md`, sob
    `output_dir` espelhando o caminho relativo a `input_root` quando os dois
    são dados. Serve para detectar colisão de destino antes de converter.
    """
    src = Path(src)
    if output_dir:
        dst_dir = Path(output_dir)
        if input_root is not None:
            dst_dir = dst_dir / src.parent.resolve().relative_to(Path(input_root).resolve())
    else:
        dst_dir = src.parent
    return dst_dir / f"{src.name}.md"


def find_collisions(
    files: list[tuple[Path, Path]], output_dir: str | Path | None = None
) -> dict[Path, list[Path]]:
    """Agrupa `files` (pares `(arquivo, raiz)` de `gather`) pelo destino `.md` que gerariam.

    Devolve só os destinos com mais de uma origem — por exemplo, duas raízes de
    entrada diferentes com um `a.docx` cada uma, sob o mesmo `output_dir`.
    """
    por_destino: dict[Path, list[Path]] = {}
    for src, root in files:
        dst = resolve_dst(src, output_dir, root)
        por_destino.setdefault(dst, []).append(src)
    return {dst: srcs for dst, srcs in por_destino.items() if len(srcs) > 1}


def convert_file(
    src: str | Path,
    output_dir: str | Path | None = None,
    *,
    input_root: str | Path | None = None,
    clean_toc: bool = False,
    extract_media: bool = True,
    overwrite: bool = False,
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
    """
    src = Path(src)
    if not src.is_file():
        raise ConversionError("arquivo não encontrado")
    ext = src.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ConversionError(f"extensão não suportada: {ext or '(sem extensão)'}")

    dst = resolve_dst(src, output_dir, input_root)
    dst_dir = dst.parent
    if dst.exists() and not overwrite:
        raise ConversionError(f"já existe (use --overwrite): {dst}")

    # dst_dir precisa existir antes do engine rodar (pandoc usa cwd=dst_dir; o
    # pymupdf4llm cria a própria media_dir mas exige que o pai já exista). Guarda
    # o topo da árvore nova para desfazer se a conversão falhar depois, em vez de
    # deixar pasta vazia (ou parcialmente escrita) pra trás.
    topo_novo = _primeiro_ancestral_ausente(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    media_dir: Path | None = None
    try:
        if ext == PDF_EXT:
            pdf_media = dst_dir / f"{src.name}_media" if extract_media else None
            md, media_dir = _run_pdf(src, pdf_media)
            engine = "pymupdf4llm"
        else:
            media_name = f"{src.name}_media" if extract_media else None
            md = _run_pandoc(src, PANDOC_FORMATS[ext], cwd=dst_dir, media_dir_name=media_name)
            engine = "pandoc"
            if media_name and (dst_dir / media_name).is_dir():
                media_dir = dst_dir / media_name
            if not extract_media:
                md = _drop_img_tags(md)
    except Exception:
        if topo_novo is not None:
            shutil.rmtree(topo_novo, ignore_errors=True)
        raise

    removed = 0
    if clean_toc:
        md, removed = strip_toc(md)

    dst.write_text(md, encoding="utf-8")
    return Result(src, dst, engine, removed, media_dir)


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
