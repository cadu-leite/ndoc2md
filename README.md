# ndoc2md

Conversor de documentos para **Markdown** preservando a **hierarquia de títulos**.

- Formatos de escritório (`.docx`, `.odt`, `.html`, `.rtf`, `.epub`, `.tex`, `.org`, `.rst`, `.textile`) → via **pandoc**.
  Os níveis `#`/`##`/`###` saem dos estilos *Título 1/2/3* do Word.
- `.pdf` → via **pymupdf4llm** (extra opcional `pdf`; o pandoc não lê PDF).
  Figuras e diagramas do PDF são extraídos como PNG para `<nome>_media/`
  (com link relativo no `.md`), a menos que se use `--no-media`.

## Requisitos

- [`pandoc`](https://pandoc.org) no PATH (`brew install pandoc`)
- [`uv`](https://docs.astral.sh/uv/)

## Instalação

```bash
cd ndoc2md
uv sync                 # núcleo (só pandoc, sem dependências Python)
uv sync --extra pdf     # se for converter PDFs também
```

> **⚠️ Restrição de plataforma (extra `pdf`)**
>
> O extra `pdf` está fixado em `pymupdf4llm>=0.0.22,<0.1` para manter compatibilidade com
> **macOS em CPU Intel (`macosx_*_x86_64`)**, faixa em que a dependência é só `pymupdf`
> (que tem wheel para Mac Intel). A partir da `1.27.2.1`, o `pymupdf4llm` passa a exigir
> `pymupdf_layout` → **`onnxruntime`**, que **não publica wheel para macOS Intel em nenhuma
> versão do macOS** — `uv sync --extra pdf` falharia com *"can't be installed because it
> doesn't have a source distribution or wheel for the current platform"*.
>
> - **Apple Silicon (arm64), Linux ou Windows:** o teto pode subir — edite o `pyproject.toml`:
>   `pdf = ["pymupdf4llm"]` (layout/OCR melhores; testado em Linux x86_64).
> - O **núcleo (pandoc)** funciona em qualquer plataforma, sem essa restrição.

## Uso

```bash
# um arquivo (.md gerado ao lado do original)
uv run ndoc2md "../glossario/Definições - glossario.docx"

# uma pasta inteira, recursivo
uv run ndoc2md ../glossario ../projeto

# para uma pasta de saída específica
uv run ndoc2md ../projeto -o ./saida

# ver o que seria convertido, sem escrever
uv run ndoc2md .. --dry-run

# remover os sumários/TOC feios que o pandoc gera (opt-in)
uv run ndoc2md "../glossario/Definições - glossario.docx" --clean-toc --overwrite
```

### Opções

| Opção            | Efeito                                                        |
| ---------------- | ------------------------------------------------------------- |
| `-o, --output-dir` | pasta de saída (padrão: ao lado do original)                |
| `--no-recursive` | ao receber uma pasta, não percorrer subpastas                 |
| `--clean-toc`    | remove linhas de sumário/TOC do pandoc (desligado por padrão) |
| `--no-media`     | não extrair imagens                                           |
| `--overwrite`    | sobrescrever `.md` existente                                  |
| `--dry-run`      | só lista o que seria convertido                               |

O nome de saída preserva a extensão de origem: `relatorio.docx` gera `relatorio.docx.md`.
Assim o tipo do arquivo original fica legível no nome da saída, e dois arquivos de mesmo nome com
extensões diferentes (`rel.docx` e `rel.html`) deixam de disputar o mesmo `.md`.

Por padrão o `.md` é gerado na mesma pasta do documento de origem.

Em `converter.py`:

```python
dst_dir = Path(output_dir) if output_dir else src.parent   # ← mesma pasta do original
dst = dst_dir / f"{src.name}.md"                            # ← nome completo (com extensão), .md
```

Então:

| Comando | Saída |
|---------|-------|
| uv run ndoc2md "../glossario/Definições - glossario.docx" | ../glossario/Definições - glossario.docx.md |
| uv run ndoc2md ../projeto (pasta) | cada .md ao lado do seu original, em ../projeto/... |
| uv run ndoc2md ../projeto -o ./saida | ./saida/ **espelhando** a árvore de ../projeto/ |

Três observações:
- As imagens vão para `<nome>.<ext>_media/` na mesma pasta de saída (`Definições - glossario.docx_media/`).
- Com -o/--output-dir você muda o destino; sem ele, fica junto do original.
- Com -o e uma pasta de entrada, a estrutura de subpastas é **espelhada** no
  destino (não achatada) — dois arquivos de mesmo nome em subpastas
  diferentes não colidem.


## Como biblioteca

```python
from ndoc2md import convert_file, gather

# gather devolve pares (arquivo, raiz); a raiz permite espelhar a árvore com -o
for f, root in gather(["../glossario"]):
    res = convert_file(f, "./saida", input_root=root, clean_toc=True, overwrite=True)
    print(res.output, res.engine)
```

## Observação sobre hierarquia

A hierarquia só é reconstruída se o `.docx` usar os **estilos nativos de título** do
Word. Se o texto estiver apenas em **negrito grande**, o pandoc trata como parágrafo
comum e não há como inferir o nível automaticamente — corrija os estilos no Word antes.
