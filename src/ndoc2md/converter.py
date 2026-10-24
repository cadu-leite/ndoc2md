"""Núcleo de conversão: roteia cada extensão para o motor certo e gera Markdown.

- Formatos de escritório (docx, odt, html, rtf, epub, ...) -> pandoc (preserva a
  hierarquia de títulos a partir dos estilos "Título 1/2/3" do Word).
- PDF -> pymupdf4llm (extra opcional `pdf`, que vem dentro do pymupdf 2.x), já que
  o pandoc não lê PDF.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
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

# `--sem-html`: o pymupdf4llm 2.x marca texto dentro de figura com comentário HTML
# e quebra linha com `<br>`.
_HTML_COMENTARIO = re.compile(r"<!--.*?-->[ \t]*\n?", re.DOTALL)
_HTML_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
# `![alt](destino)`; o destino pode ter parênteses no nome do arquivo.
_IMAGEM_MD = re.compile(r"!\[([^\]]*)\]\(([^()\s]*(?:\([^()\s]*\)[^()\s]*)*)\)")


class ConversionError(RuntimeError):
    """Falha ao converter um arquivo."""

    original_apagado = False


class PdfSemTexto(ConversionError):
    """PDF sem camada de texto (escaneado), com `exigir_texto=True`."""


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


def _drop_md_images(md: str) -> str:
    """Troca `![alt](destino)` pelo texto alternativo, ou remove quando não há texto.

    Com `sem_html=True` o pandoc emite imagem como `![]()` em vez de `<img>`; sem a
    mídia extraída, o link apontaria para um arquivo que não existe.
    """
    def troca(m: re.Match) -> str:
        alt = m.group(1).strip()
        return f"[imagem: {alt}]" if alt else ""

    return re.sub(r"\n{3,}", "\n\n", _IMAGEM_MD.sub(troca, md))


def _limpar_html(md: str) -> str:
    """`sem_html=True` no PDF: comentário HTML sai, `<br>` vira quebra de linha."""
    return _HTML_BR.sub("\n", _HTML_COMENTARIO.sub("", md))


def _run_pandoc(
    src: Path, fmt: str, cwd: Path, media_dir_name: str | None, sem_html: bool = False
) -> str:
    """Roda pandoc com cwd na pasta de saída para que os links de mídia fiquem
    relativos ao .md gerado."""
    cmd = ["pandoc", "-f", fmt, "-t", "gfm-raw_html" if sem_html else "gfm", "--wrap=none"]
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


def _mensagem_sem_pdf() -> str:
    """Mensagem para quando o pymupdf não está instalado.

    O extra `pdf` não instala nada em macOS Intel nem em Python 3.10 (o pymupdf 2.x
    não tem versão para eles); nesses casos o caminho é o Docker.
    """
    if sys.platform == "darwin" and platform.machine() == "x86_64":
        return (
            "PDF não é suportado em macOS com CPU Intel (o pymupdf 2.x não tem versão para "
            "essa plataforma) — rode o ndoc2md pelo Docker; veja o README, seção \"macOS Intel\""
        )
    if sys.version_info < (3, 11):
        return (
            "PDF exige Python 3.11 ou mais novo (pymupdf 2.x) — use Python 3.11+ ou rode "
            "o ndoc2md pelo Docker; veja o README, seção \"macOS Intel\""
        )
    return "suporte a PDF não instalado — rode: uv sync --extra pdf"


def _warn_empty_pages(src: Path, chunks: list[dict]) -> str:
    """Reconstrói o Markdown a partir de `chunks` (`page_chunks=True`), avisando
    página que não gerou nada apesar de ter desenho vetorial.

    O pymupdf4llm 0.0.x descartava traço/preenchimento vetorial isolado sem avisar
    (erro 12); o 2.x transforma esse desenho em imagem quando a mídia é extraída.
    Sem mídia, ou se o motor ainda descartar o desenho, a página fica vazia: aqui a
    gente cruza cada página vazia do resultado com `page.get_drawings()` na própria
    fonte — página com desenho vetorial e sem nada no Markdown é conteúdo perdido,
    não uma página em branco de verdade. (No 2.x, imagem e tabela já vêm dentro do
    `text` do chunk.)
    """
    import pymupdf

    doc = pymupdf.open(str(src.resolve()))
    try:
        partes = []
        for i, chunk in enumerate(chunks):
            texto = chunk["text"]
            vazia = not texto.strip()
            if vazia and i < doc.page_count and doc[i].get_drawings():
                texto = (
                    f"\n\n> **Aviso do ndoc2md:** a página {i + 1} tem desenho vetorial "
                    "que não virou texto nem imagem no Markdown — confira o PDF original.\n\n"
                )
            partes.append(texto)
    finally:
        doc.close()
    return "".join(partes)


def _paginas_pdf(src: Path) -> list[tuple[bool, bool]]:
    """Para cada página: (tem texto, tem imagem), lido na fonte."""
    import pymupdf

    with pymupdf.open(str(src.resolve())) as doc:
        return [(bool(p.get_text().strip()), bool(p.get_images())) for p in doc]


def _avisos_escaneadas(paginas: list[tuple[bool, bool]]) -> list[str]:
    return [
        f"a página {i + 1} é imagem sem texto (escaneada); o conteúdo dela não está neste Markdown"
        for i, (tem_texto, tem_imagem) in enumerate(paginas)
        if not tem_texto and tem_imagem
    ]


def _run_pdf(
    src: Path, media_dir: Path | None, silencioso: bool = False
) -> tuple[str, Path | None, int]:
    """Converte PDF via pymupdf4llm, sem OCR. Devolve (markdown, pasta de mídia, páginas).

    Se `media_dir` for dado, extrai figuras/diagramas como PNG para lá e
    reescreve os links no Markdown para ficarem relativos ao `.md` gerado
    (mesma semântica do caminho pandoc). Sem `media_dir`, extrai só texto.
    """
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise ConversionError(_mensagem_sem_pdf()) from exc

    # O pymupdf4llm escreve recados no stdout e no stderr; `silencioso` os descarta
    # (a CLI usa com --json, que precisa de stdout limpo).
    abafar = contextlib.ExitStack()
    if silencioso:
        abafar.enter_context(contextlib.redirect_stdout(io.StringIO()))
        abafar.enter_context(contextlib.redirect_stderr(io.StringIO()))

    if media_dir is None:
        with abafar:
            chunks = pymupdf4llm.to_markdown(str(src.resolve()), page_chunks=True, use_ocr=False)
        return _warn_empty_pages(src, chunks), None, len(chunks)

    # O pymupdf4llm 2.x troca espaço, acento e parênteses do image_path e não cria a
    # pasta: as imagens vão para uma pasta temporária do sistema (caminho só com letras,
    # números e `_`) e depois são movidas para `media_dir`, que mantém o nome de sempre
    # (`<arquivo>_media`).
    with tempfile.TemporaryDirectory(prefix="ndoc2md_") as tmp:
        with abafar:
            chunks = pymupdf4llm.to_markdown(
                str(src.resolve()),
                page_chunks=True,
                use_ocr=False,
                write_images=True,
                image_path=tmp,
                image_format="png",
                dpi=150,
            )
        md = _warn_empty_pages(src, chunks)
        imagens = sorted(Path(tmp).iterdir())
        if imagens:
            media_dir.mkdir(exist_ok=True)
            for img in imagens:
                shutil.move(str(img), str(media_dir / img.name))
    # pymupdf4llm insere o próprio image_path como prefixo do link, sempre como
    # `![](<prefixo>/arquivo.png)` (única sintaxe de imagem que ele emite); torná-lo
    # relativo à pasta do .md (o .md e a pasta de mídia são irmãos) mirando só essa
    # sintaxe, para não reescrever o caminho se ele aparecer no texto do documento.
    # `![]( ... )` sempre sozinho na linha — casar a linha inteira, com `.*` guloso
    # até o `)` final, em vez de `[^)]*`, porque o nome do arquivo pode ter parênteses.
    img_tag = re.compile(r"^!\[\]\(" + re.escape(tmp) + r"/?(.*)\)$", re.MULTILINE)
    md = img_tag.sub(lambda m: f"![]({media_dir.name}/{m.group(1)})", md)
    return md, (media_dir if media_dir.is_dir() else None), len(chunks)


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
        try:
            paginas_fonte = _paginas_pdf(src)
        except ImportError as exc:
            raise ConversionError(_mensagem_sem_pdf()) from exc
        if not any(tem_texto for tem_texto, _ in paginas_fonte):
            raise PdfSemTexto(
                f"o PDF não tem texto em nenhuma das {len(paginas_fonte)} página(s); "
                "parece escaneado — peça a versão digital do documento"
            )
        avisos = _avisos_escaneadas(paginas_fonte)

    # dst_dir precisa existir antes do engine rodar (pandoc usa cwd=dst_dir; o
    # pymupdf4llm cria a própria media_dir mas exige que o pai já exista). Guarda
    # o topo da árvore nova para desfazer se a conversão falhar depois, em vez de
    # deixar pasta vazia (ou parcialmente escrita) pra trás.
    topo_novo = _primeiro_ancestral_ausente(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    media_base = dst.name[: -len(".md")] if (nome or prefixo_data) else src.name
    media_dir: Path | None = None
    paginas: int | None = None
    try:
        if ext == PDF_EXT:
            pdf_media = dst_dir / f"{media_base}_media" if extract_media else None
            md, media_dir, paginas = _run_pdf(src, pdf_media, silencioso)
            engine = "pymupdf4llm"
            if sem_html:
                md = _limpar_html(md)
        else:
            media_name = f"{media_base}_media" if extract_media else None
            md = _run_pandoc(src, PANDOC_FORMATS[ext], cwd=dst_dir, media_dir_name=media_name,
                             sem_html=sem_html)
            engine = "pandoc"
            if media_name and (dst_dir / media_name).is_dir():
                media_dir = dst_dir / media_name
            if not extract_media:
                md = _drop_img_tags(md)
                if sem_html:
                    md = _drop_md_images(md)
    except Exception:
        if topo_novo is not None:
            shutil.rmtree(topo_novo, ignore_errors=True)
        raise

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
