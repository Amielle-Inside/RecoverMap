"""CLI do RecoverMap.

  recovermap map <fonte> [-o mapa.csv|json|html] [--offset N] [--allocated-only]
  recovermap recover <fonte> -o <dir> [--deleted-only|--allocated-only] [--report r.csv] [--offset N]
  recovermap gui

Fonte pode ser uma imagem (.img/.raw/.dd/.E01) ou um dispositivo.
No Windows: \\\\.\\PhysicalDrive2 (disco inteiro) ou \\\\.\\C: (volume) — execute como admin.
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .core import RecoverMapEngine


def _engine(args) -> RecoverMapEngine:
    try:
        return RecoverMapEngine(args.source, offset=args.offset)
    except Exception as exc:
        sys.exit(f"[erro] nao consegui abrir '{args.source}': {exc}\n"
                 f"Dica: verifique o caminho/permissao (admin no Windows "
                 f"para discos fisicos) ou use --offset com o inicio da particao.")


def _filter(entries, only_deleted=False, allocated_only=False):
    out = []
    for e in entries:
        if e.is_dir:
            continue
        if only_deleted and not e.deleted:
            continue
        if allocated_only and e.deleted:
            continue
        out.append(e)
    return out


def cmd_map(args):
    eng = _engine(args)
    entries = eng.walk(include_deleted=not args.allocated_only)
    files = [e for e in entries if not e.is_dir]
    deleted = [e for e in files if e.deleted]
    print(f"{len(files):,} arquivos no mapa · "
          f"{len(deleted):,} deletados · "
          f"{len([e for e in entries if e.is_dir]):,} pastas".replace(",", "."))
    if args.out:
        eng.export_map(entries, args.out)
        print(f"mapa salvo em: {args.out}")
    else:
        for e in files[:40]:
            tag = "[DEL]" if e.deleted else "     "
            print(f"{tag} {e.size:>12}  {e.path}")
        if len(files) > 40:
            print(f"... e mais {len(files) - 40:,} arquivos "
                  f"(use -o mapa.csv para o inventario completo)".replace(",", "."))


def cmd_recover(args):
    eng = _engine(args)
    entries = eng.walk(include_deleted=not args.allocated_only)
    sel = _filter(entries, args.deleted_only, args.allocated_only)
    if not sel:
        sys.exit("[erro] nenhum arquivo no mapa com esse filtro.")
    report = args.report or "recovermap-report.csv"
    print(f"recuperando {len(sel):,} arquivos para {args.out} "
          f"(sem limite de quantidade)...".replace(",", "."))
    res = eng.recover(args.out, entries,
                      only_deleted=args.deleted_only,
                      report_path=report)
    print(f"concluido: {res['ok']:,} OK · {res['fail']:,} falhas · "
          f"{res['bytes']:,} bytes".replace(",", "."))
    print(f"relatorio: {res['report']}")
    if res["fail"]:
        sys.exit(1)


def cmd_gui(_args):
    from .gui import run
    run()


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="recovermap",
        description="Mapa completo do disco + recuperacao ILIMITADA de arquivos "
                    "(NTFS/FAT/exFAT/ext2-4/HFS+). Fonte aberta somente-leitura.")
    ap.add_argument("--version", action="version",
                    version=f"RecoverMap {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("map", help="gera o mapa (inventario) da fonte")
    p.add_argument("source", help="imagem ou dispositivo")
    p.add_argument("-o", "--out", help="saida: mapa.csv / mapa.json / mapa.html")
    p.add_argument("--offset", type=int, default=0,
                   help="offset em bytes do inicio da particao (default 0)")
    p.add_argument("--allocated-only", action="store_true",
                   help="omitir arquivos deletados do mapa")
    p.set_defaults(fn=cmd_map)

    p = sub.add_parser("recover", help="recupera os arquivos SEM LIMITE")
    p.add_argument("source")
    p.add_argument("-o", "--out", required=True, help="pasta de destino")
    p.add_argument("--deleted-only", action="store_true",
                   help="recuperar somente arquivos deletados")
    p.add_argument("--allocated-only", action="store_true",
                   help="pular arquivos deletados")
    p.add_argument("--report", help="caminho do CSV de relatorio")
    p.add_argument("--offset", type=int, default=0)
    p.set_defaults(fn=cmd_recover)

    p = sub.add_parser("gui", help="abre a interface grafica")
    p.set_defaults(fn=cmd_gui)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
