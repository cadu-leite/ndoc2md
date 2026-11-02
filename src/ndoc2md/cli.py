"""Interface de linha de comando do doc2md."""

from __future__ import annotations

import argparse
import json
import sys

from .converter import (
    ConversionError,
    PANDOC_FORMATS,
    PdfSemTexto,
    Result,
    SUPPORTED_EXTENSIONS,
    check_path,
    convert_file,
    find_collisions,
    gather,
    have_pandoc,
)


def build_parser() -> argparse.ArgumentParser:
    exts = " ".join(sorted(SUPPORTED_EXTENSIONS))
    p = argparse.ArgumentParser(
        prog="ndoc2md",
        description="Converte documentos para Markdown preservando a hierarquia de títulos.",
        epilog=f"Extensões suportadas: {exts}",
    )
    p.add_argument("inputs", nargs="+", help="arquivos e/ou pastas a converter")
    p.add_argument(
        "-o", "--output-dir",
        help="pasta de saída (padrão: gera o .md ao lado de cada original)",
    )
    p.add_argument(
        "--no-recursive", dest="recursive", action="store_false",
        help="ao receber uma pasta, não percorrer subpastas",
    )
    p.add_argument(
        "--clean-toc", dest="clean_toc", action="store_true",
        help="remover linhas de sumário/TOC geradas pelo pandoc (desligado por padrão)",
    )
    p.add_argument(
        "--no-media", dest="extract_media", action="store_false",
        help="não extrair imagens para uma pasta <nome>_media",
    )
    p.add_argument(
        "--overwrite", action="store_true",
        help="sobrescrever .md já existente",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="apenas listar o que seria convertido",
    )
    novas = p.add_argument_group("opções novas (desligadas por padrão)")
    novas.add_argument(
        "--json", action="store_true",
        help="uma linha JSON por arquivo no stdout, sem os recados do pymupdf4llm",
    )
    novas.add_argument("--nome", help="nome-base do .md, sem extensão (só com um arquivo)")
    novas.add_argument(
        "--prefixo-data", dest="prefixo_data", action="store_true",
        help="começa o nome do .md com a data de hoje (AAAA-MM-DD_)",
    )
    novas.add_argument(
        "--cabecalho", action="store_true",
        help="começa o .md com o título e uma linha de origem (data, arquivo, sha256, páginas)",
    )
    novas.add_argument("--titulo", help="título do cabeçalho (padrão: nome do original)")
    novas.add_argument(
        "--sem-html", dest="sem_html", action="store_true",
        help="saída sem HTML: pandoc gfm-raw_html; no PDF, tira comentários e troca <br>",
    )
    novas.add_argument(
        "--exigir-texto", dest="exigir_texto", action="store_true",
        help="PDF sem texto (escaneado) não gera .md e sai com código 3",
    )
    novas.add_argument(
        "--apagar-original", dest="apagar_original", action="store_true",
        help="apaga o original depois da tentativa de conversão, com sucesso ou com falha",
    )
    p.set_defaults(recursive=True, extract_media=True, clean_toc=False)
    return p


def _registro(arquivo, res: Result | None, erro: ConversionError | None) -> dict:
    """Linha do --json: o resultado de um arquivo."""
    if res is not None:
        return {
            "ok": True,
            "origem": str(res.source),
            "saida": str(res.output),
            "motor": res.engine,
            "paginas": res.paginas,
            "sha256": res.sha256,
            "avisos": list(res.avisos),
            "midia": str(res.media_dir) if res.media_dir else None,
            "original_apagado": res.original_apagado,
        }
    return {
        "ok": False,
        "origem": str(arquivo),
        "erro": str(erro),
        "sem_texto": isinstance(erro, PdfSemTexto),
        "original_apagado": erro.original_apagado,
    }


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.nome and len(args.inputs) > 1:
        print("ERRO: --nome só vale com um arquivo", file=sys.stderr)
        return 2

    try:
        check_path(args.inputs)
    except ConversionError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    files = gather(args.inputs, recursive=args.recursive)
    if not files:
        print("Nenhum arquivo suportado encontrado.", file=sys.stderr)
        return 1

    # O pandoc só é exigido quando o lote tem um formato que passa por ele.
    if not have_pandoc() and any(f.suffix.lower() in PANDOC_FORMATS for f, _ in files):
        print(
            "ERRO: pandoc não encontrado no PATH. Instale com: brew install pandoc",
            file=sys.stderr,
        )
        return 2

    colisoes = find_collisions(files, args.output_dir, prefixo_data=args.prefixo_data)
    if colisoes:
        for dst, srcs in colisoes.items():
            origens = " e ".join(str(s) for s in srcs)
            print(
                f"ERRO: {origens} gerariam o mesmo destino ({dst}) — renomeie um dos arquivos.",
                file=sys.stderr,
            )
        return 2

    ok = fail = sem_texto = 0
    for f, root in files:
        if args.dry_run:
            print(f"[dry-run] {f}")
            continue
        try:
            res: Result = convert_file(
                f,
                args.output_dir,
                input_root=root,
                clean_toc=args.clean_toc,
                extract_media=args.extract_media,
                overwrite=args.overwrite,
                nome=args.nome,
                prefixo_data=args.prefixo_data,
                cabecalho=args.cabecalho,
                titulo=args.titulo,
                sem_html=args.sem_html,
                exigir_texto=args.exigir_texto,
                apagar_original=args.apagar_original,
                silencioso=args.json,
            )
        except ConversionError as exc:
            if isinstance(exc, PdfSemTexto):
                sem_texto += 1
            else:
                fail += 1
            if args.json:
                print(json.dumps(_registro(f, None, exc), ensure_ascii=False))
            else:
                print(f"✗ {f.name}: {exc}", file=sys.stderr)
            continue

        if args.json:
            print(json.dumps(_registro(f, res, None), ensure_ascii=False))
            ok += 1
            continue

        extra = []
        if res.toc_lines_removed:
            extra.append(f"{res.toc_lines_removed} linha(s) de TOC removida(s)")
        if res.media_dir:
            extra.append(f"mídia → {res.media_dir.name}/")
        suffix = f"  ({'; '.join(extra)})" if extra else ""
        print(f"✓ {res.source.name}  →  {res.output.name}  [{res.engine}]{suffix}")
        ok += 1

    if not args.dry_run and not args.json:
        print(f"\nConcluído: {ok} convertido(s), {fail + sem_texto} falha(s).")
    if fail:
        return 1
    return 3 if sem_texto else 0


if __name__ == "__main__":
    raise SystemExit(main())
