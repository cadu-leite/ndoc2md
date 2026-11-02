# ndoc2md

Conversor de documentos para **Markdown** preservando a **hierarquia de títulos**.

- Formatos de escritório (`.docx`, `.odt`, `.html`, `.rtf`, `.epub`, `.tex`, `.org`, `.rst`, `.textile`) → via **pandoc**.
  Os níveis `#`/`##`/`###` saem dos estilos *Título 1/2/3* do Word.
- `.pdf` → via **pymupdf4llm** (extra opcional `pdf`; o pandoc não lê PDF).
  Figuras e diagramas do PDF são extraídos como PNG para `<nome>_media/`
  (com link relativo no `.md`), a menos que se use `--no-media`.
- Apresentações (`.odp`, `.sxi`), planilhas (`.ods`, `.sxc`) e texto do OpenOffice 1.x (`.sxw`) → leitura direta do XML, sem dependência extra.
  Ver [Apresentações, planilhas e OpenOffice 1.x](#apresentações-planilhas-e-openoffice-1x).

## Requisitos

- [`pandoc`](https://pandoc.org) no PATH (`brew install pandoc`), para os formatos lidos pelo pandoc
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

## Apresentações, planilhas e OpenOffice 1.x

O pandoc só lê o `.odt`.
Os formatos abaixo são lidos direto do `content.xml` do pacote, com a biblioteca padrão do Python (`zipfile` e `xml.etree`).
O motor aparece como `odf` na saída do CLI e no `--json`.

| Extensão | Programa                               | Estrutura do `.md`                                               |
|----------|----------------------------------------|------------------------------------------------------------------|
| `.odp`   | Impress (OpenDocument)                 | `## Slide N: título`, corpo do slide, notas do apresentador      |
| `.sxi`   | Impress do OpenOffice 1.x              | igual ao `.odp`                                                  |
| `.ods`   | Calc (OpenDocument)                    | `## nome da aba` e uma tabela GFM por aba                        |
| `.sxc`   | Calc do OpenOffice 1.x                 | igual ao `.ods`                                                  |
| `.sxw`   | Writer do OpenOffice 1.x               | títulos `#` pelo nível de tópico, listas, tabelas, notas de rodapé |

Apresentação:

- O título vem do quadro de título do layout (`presentation:class="title"`); slide sem esse quadro sai como `## Slide N`.
- O corpo segue a ordem de empilhamento do arquivo, não a posição na tela.
- Número de página, data, rodapé e placeholder vazio ficam de fora.
- Texto do slide mestre (o fundo comum a todos os slides) fica de fora.
- Slide oculto sai como `## Slide N (oculto): título`.
- `paginas` (no `--json` e no `--cabecalho`) recebe o número de slides.

Planilha:

- A célula sai com o texto exibido: o número já formatado e o resultado da fórmula, gravados no arquivo na hora em que ele foi salvo.
- As linhas e colunas vazias das bordas saem; a primeira linha com conteúdo vira o cabeçalho da tabela.
- Célula mesclada ocupa a primeira coluna; as colunas cobertas ficam vazias.
- Aba oculta sai como `## nome (oculta)`; aba vazia sai com `*(aba vazia)*`.

Para todos esses formatos:

- Imagem do pacote vai para `<nome>.<ext>_media/`, com link relativo; `--no-media` tira a imagem do `.md`.
- Gráfico, fórmula ou objeto OLE incorporado não vira texto; o `.md` termina com um aviso que conta esses objetos por slide ou por aba.
- `--sem-html` não muda nada, porque a saída já não tem HTML.
- Esses formatos convertem sem o pandoc no PATH; o CLI só exige o pandoc quando o lote tem um formato lido por ele.

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
