"""Interface de linha de comando do doc2md."""

from __future__ import annotations

import argparse
import sys

from .converter import (
    ConversionError,
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
    p.set_defaults(recursive=True, extract_media=True, clean_toc=False)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if not have_pandoc():
        print(
            "ERRO: pandoc não encontrado no PATH. Instale com: brew install pandoc",
            file=sys.stderr,
        )
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

    colisoes = find_collisions(files, args.output_dir)
    if colisoes:
        for dst, srcs in colisoes.items():
            origens = " e ".join(str(s) for s in srcs)
            print(
                f"ERRO: {origens} gerariam o mesmo destino ({dst}) — renomeie um dos arquivos.",
                file=sys.stderr,
            )
        return 2

    ok = fail = 0
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
            )
        except ConversionError as exc:
            print(f"✗ {f.name}: {exc}", file=sys.stderr)
            fail += 1
            continue

        extra = []
        if res.toc_lines_removed:
            extra.append(f"{res.toc_lines_removed} linha(s) de TOC removida(s)")
        if res.media_dir:
            extra.append(f"mídia → {res.media_dir.name}/")
        suffix = f"  ({'; '.join(extra)})" if extra else ""
        print(f"✓ {res.source.name}  →  {res.output.name}  [{res.engine}]{suffix}")
        ok += 1

    if not args.dry_run:
        print(f"\nConcluído: {ok} convertido(s), {fail} falha(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
