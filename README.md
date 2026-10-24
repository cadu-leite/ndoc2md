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
> Desde a 0.2.0, o extra `pdf` instala o **`pymupdf` 2.x**, que já traz o `pymupdf4llm`
> (layout melhor: no cartão CNPJ de teste, a série 0.0.x deixou 82 de 151 palavras fora do `.md`;
> o 2.x, nenhuma). Ele puxa `pymupdf_layout` → **`onnxruntime`** e exige **Python 3.11+**.
>
> - **macOS em CPU Intel (`macosx_*_x86_64`):** nem o `pymupdf` 2.x nem o `onnxruntime` publicam
>   wheel para essa plataforma. Lá o `uv sync --extra pdf` termina sem instalar o `pymupdf`, e o
>   ndoc2md avisa que PDF exige Docker — veja [macOS Intel](#macos-intel-docker).
> - **Python 3.10:** mesmo comportamento: o extra não instala nada, e o aviso indica Python 3.11+ ou Docker.
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

Opções novas da 0.2.0, todas desligadas por padrão (desligadas, a saída é a mesma da 0.1.0):

| Opção               | Efeito                                                                                   |
| ------------------- | ---------------------------------------------------------------------------------------- |
| `--json`            | uma linha JSON por arquivo no stdout, sem os recados do `pymupdf4llm`                    |
| `--nome NOME`       | nome-base do `.md`, sem extensão: `--nome contrato` gera `contrato.pdf.md` (só com um arquivo) |
| `--prefixo-data`    | começa o nome do `.md` com a data de hoje (`2026-10-24_contrato.pdf.md`)                 |
| `--cabecalho`       | começa o `.md` com `# título` e uma linha com data, arquivo de origem, versão, motor, sha256 e páginas |
| `--titulo TEXTO`    | título do cabeçalho (padrão: nome do original sem extensão)                             |
| `--sem-html`        | saída sem HTML: pandoc com `gfm-raw_html`; no PDF, tira comentários e troca `<br>` por quebra de linha |
| `--exigir-texto`    | PDF sem texto (escaneado) não gera `.md` e sai com código 3; página escaneada no meio gera aviso |
| `--apagar-original` | apaga o original depois da tentativa de conversão, **com sucesso ou com falha** (inclusive `.md` já existente); arquivo ausente ou de extensão não suportada não é apagado |

Códigos de saída: `0` tudo convertido; `1` alguma falha ou nada encontrado; `2` erro de uso
(pandoc ausente, caminho inexistente, colisão de destino); `3` só com `--exigir-texto`, algum PDF sem texto.

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

## macOS Intel (Docker)

No macOS com CPU Intel o `pymupdf` 2.x não instala, então PDF só converte pelo container.
O `Dockerfile` na raiz do repositório traz Python 3.13, pandoc e `ndoc2md[pdf]`.

```bash
docker build -t ndoc2md .

# converte a pasta atual; o .md sai ao lado de cada original
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/dados" ndoc2md . --no-media
```

O container monta a pasta atual em `/dados`; os caminhos passados ao `ndoc2md` são relativos a ela.
Funciona igual em Linux, Windows e Apple Silicon, para quem preferir não instalar nada localmente.

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
