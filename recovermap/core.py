"""Engine RecoverMap: caminha no filesystem via pytsk3 (The Sleuth Kit),
gera o mapa completo do volume e recupera arquivos SEM LIMITE.

A fonte (disco ou imagem) e aberta SEMPRE somente-leitura — o programa
nunca escreve na midia de origem.
"""
from __future__ import annotations

import hashlib
import html as _html
import csv
import json
import os
from dataclasses import dataclass, asdict
from typing import Callable, Optional

CHUNK = 4 * 1024 * 1024

_SANITIZE = {c: "_" for c in '<>:"\\/|?*'}
for _i in range(32):
    _SANITIZE[chr(_i)] = "_"


def sanitize_name(name: str) -> str:
    """Torna um nome seguro para gravar em disco (Windows/Linux)."""
    return "".join(_SANITIZE.get(ch, ch) for ch in name).strip() or "_"


@dataclass
class MapEntry:
    inum: int
    path: str          # caminho relativo dentro do volume, ex.: docs/rel.pdf
    name: str
    size: int
    is_dir: bool
    deleted: bool
    recoverable: bool  # arquivo (nao diretorio) com metadata legivel


class RecoverMapEngine:
    def __init__(self, source: str, offset: int = 0):
        import pytsk3  # import tardio: so quando abrir uma fonte
        self._t = pytsk3
        self.img = pytsk3.Img_Info(source)            # autodetecta tipo
        self.fs = pytsk3.FS_Info(self.img, offset=offset)  # autodetecta FS

    # ---------------------------------------------------------------- mapa
    def walk(self, include_deleted: bool = True,
             on_progress: Optional[Callable[[int, int], None]] = None
             ) -> list[MapEntry]:
        """Percorre toda a arvore e devolve um MapEntry por nome encontrado.

        Arquivos deletados aparecem quando o FS preserva o registro
        (ex.: MFT do NTFS). Diretorios deletados nao sao percorridos.
        """
        t = self._t
        entries: list[MapEntry] = []
        seen_dirs: set[int] = set()
        ndirs = 1
        stack: list[tuple[object, str]] = [(self.fs.open_dir("/"), "")]
        while stack:
            d, prefix = stack.pop()
            # iteracao LAZY: uma entrada viva por vez — materializar a lista
            # inteira com list(d) estoura RAM em diretorios com centenas de
            # milhares de entradas (~2-3 KB por proxy SWIG)
            iterator = iter(d)
            while True:
                try:
                    e = next(iterator)
                except StopIteration:
                    break
                except Exception:
                    break  # diretorio ilegivel a partir daqui: segue o resto
                name = self._entry_name(e)
                if not name or name in (".", ".."):
                    continue
                # metadados internos do NTFS ($MFT, $LogFile, $Extend, ...):
                # nao sao arquivos do usuario — ficam fora do mapa.
                # $OrphanFiles (virtual do TSK, arquivos perdidos) e mantido.
                if prefix == "" and name.startswith("$") \
                        and not name.startswith("$OrphanFiles"):
                    continue
                # $OrphanFiles e um DIRETORIO virtual do TSK (arquivos sem
                # entrada de diretorio): recursa, nunca vira "arquivo".
                if prefix == "" and name == "$OrphanFiles":
                    ino = e.info.meta.addr if e.info.meta is not None else -1
                    entries.append(MapEntry(ino, name, name, 0, True,
                                            False, False))
                    try:
                        stack.append((self._open_dir_orphan(ino), name + "/"))
                        ndirs += 1
                    except Exception:
                        pass
                    continue
                deleted = False
                if e.info.name is not None:
                    deleted = e.info.name.flags == t.TSK_FS_NAME_FLAG_UNALLOC
                meta = e.info.meta
                if meta is None and e.info.name is not None \
                        and getattr(e.info.name, "meta_addr", 0):
                    # entrada UNALLOC (deletada): a iteracao nao popula o
                    # meta — abre o inode apontado pela entrada do diretorio
                    try:
                        fh = self.fs.open_meta(e.info.name.meta_addr)
                        meta = fh.info.meta
                    except Exception:
                        meta = None
                path = prefix + name
                if meta is None:
                    entries.append(MapEntry(-1, path, name, 0, False,
                                            deleted, False))
                    continue
                if meta.type == t.TSK_FS_META_TYPE_DIR:
                    entries.append(MapEntry(meta.addr, path, name, meta.size,
                                            True, deleted, False))
                    if not deleted and meta.addr not in seen_dirs:
                        seen_dirs.add(meta.addr)
                        try:
                            stack.append((self._open_dir_inum(meta.addr),
                                          path + "/"))
                            ndirs += 1
                        except Exception:
                            pass
                else:
                    entries.append(MapEntry(meta.addr, path, name, meta.size,
                                            False, deleted, True))
                if on_progress:
                    on_progress(len(entries), ndirs)
        return entries

    # ------------------------------------------------------------ leitura
    def iter_chunks(self, entry: MapEntry, chunk: int = CHUNK):
        """Lê o conteudo do arquivo em blocos (seguro p/ arquivos grandes)."""
        fh = self.fs.open_meta(entry.inum)
        read_random = getattr(fh, "read_random", None)
        off, size = 0, entry.size
        while off < size:
            want = min(chunk, size - off)
            if read_random is not None:
                # pytsk3 20260715: read_random(offset, tamanho)
                data = read_random(off, want)
            else:
                data = fh.read(want)
            if not data:
                break
            yield data
            off += len(data)

    # ---------------------------------------------------------- recovery
    def recover(self, outdir: str, entries: list[MapEntry],
                only_deleted: bool = False,
                on_progress: Optional[Callable[[int, int, str], None]] = None,
                report_path: Optional[str] = None) -> dict:
        """Extrai TODOS os arquivos do mapa para outdir, sem limite de numero.

        Retorna resumo: {total, ok, fail, bytes, report}.
        """
        files = [e for e in entries
                 if e.recoverable and (not only_deleted or e.deleted)]
        os.makedirs(outdir, exist_ok=True)
        ok = fail = nbytes = 0
        rows = []
        for i, e in enumerate(files, 1):
            status, err, sha, dest = "OK", "", "", ""
            try:
                rel = "/".join(sanitize_name(p)
                               for p in e.path.split("/")
                               if p and p not in (".", ".."))
                dest = os.path.join(outdir, rel)
                os.makedirs(os.path.dirname(dest) or outdir, exist_ok=True)
                if os.path.lexists(dest):
                    base, ext = os.path.splitext(dest)
                    k = 2
                    while os.path.lexists(dest):
                        dest = f"{base} ({k}){ext}"
                        k += 1
                h = hashlib.sha256()
                n = 0
                with open(dest, "wb") as out:
                    for data in self.iter_chunks(e):
                        h.update(data)
                        n += len(data)
                        out.write(data)
                ok += 1
                nbytes += n
                sha = h.hexdigest()
            except Exception as exc:  # arquivo ruim nao derruba o lote
                status, fail, err = "FAIL", fail + 1, str(exc)
            rows.append({"status": status, "path": e.path, "size": e.size,
                         "deleted": e.deleted, "sha256": sha,
                         "saved_as": dest, "error": err})
            if on_progress:
                on_progress(i, len(files), e.path)
        if report_path:
            with open(report_path, "w", newline="", encoding="utf-8") as f:
                _csv_write(f, rows)
        return {"total": len(files), "ok": ok, "fail": fail,
                "bytes": nbytes, "report": report_path}

    # ------------------------------------------------------------ exports
    def export_map(self, entries: list[MapEntry], path: str) -> str:
        """Exporta o mapa em CSV, JSON ou HTML (pela extensao)."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            with open(path, "w", encoding="utf-8") as f:
                json.dump([asdict(e) for e in entries], f,
                          ensure_ascii=False, indent=1)
        elif ext == ".html":
            with open(path, "w", encoding="utf-8") as f:
                f.write(_html_page(entries))
        else:  # csv por padrao
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["path", "name", "size", "deleted",
                            "is_dir", "recoverable", "inum"])
                for e in entries:
                    w.writerow([e.path, e.name, e.size, int(e.deleted),
                                int(e.is_dir), int(e.recoverable), e.inum])
        return path

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _entry_name(e) -> str:
        raw = None
        if e.info.name is not None and e.info.name.name:
            raw = e.info.name.name
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "surrogateescape")
        return raw or ""

    def _open_dir_inum(self, inum: int):
        fs = self.fs
        for attempt in (lambda: fs.open_dir(inum=inum),
                        lambda: fs.open_dir(inode=inum),
                        lambda: fs.open_dir("/")):
            try:
                return attempt()
            except (TypeError, ValueError):
                continue
        raise RuntimeError(f"diretorio {inum} ilegivel")

    def _open_dir_orphan(self, inum: int):
        """Abre o $OrphanFiles (diretorio virtual do TSK)."""
        fs = self.fs
        for attempt in (lambda: fs.open_dir(inum=inum),
                        lambda: fs.open_dir("/$OrphanFiles"),
                        lambda: fs.open_dir("$OrphanFiles")):
            try:
                return attempt()
            except Exception:
                continue
        raise RuntimeError("$OrphanFiles ilegivel")


def _csv_write(f, rows):
    import csv
    w = csv.writer(f)
    w.writerow(["status", "path", "size", "deleted", "sha256",
                "saved_as", "error"])
    for r in rows:
        w.writerow([r["status"], r["path"], r["size"], int(r["deleted"]),
                    r["sha256"], r["saved_as"], r["error"]])


def _html_page(entries: list[MapEntry]) -> str:
    rows = []
    files = dirs = deleted = 0
    for e in entries:
        if e.is_dir:
            dirs += 1
        else:
            files += 1
        deleted += int(e.deleted and not e.is_dir)
        rows.append(
            "<tr class='{cls}'><td>{p}</td><td>{s}</td><td>{d}</td></tr>"
            .format(p=_html.escape(e.path),
                    s=f"{e.size:,}".replace(",", "."),
                    d="🗑" if e.deleted else "",
                    cls="del" if e.deleted else ""))
    return """<!doctype html><html lang=pt-br><meta charset=utf-8>
<title>RecoverMap — mapa do volume</title>
<style>
:root{color-scheme:light dark}
body{font:14px system-ui;margin:2rem;background:#f6f6f8;color:#1c1c22}
@media (prefers-color-scheme:dark){body{background:#14151c;color:#e8e8f0}
 tr:hover{background:#1f2130}}
h1{font-size:1.2rem} .meta{opacity:.7;margin:.3rem 0 1rem}
table{border-collapse:collapse;width:100%}
td{padding:.25rem .6rem;border-bottom:1px solid rgba(128,128,128,.25)}
tr.del{opacity:.75} tr:hover{background:rgba(128,128,128,.12)}
</style>
<h1>RecoverMap — mapa do volume</h1>
<div class=meta>{files:,} arquivos · {dirs:,} pastas · {deleted:,} deletados</div>
<table>{body}</table>""".replace("{files}", f"{files:,}").replace(
        "{dirs}", f"{dirs:,}").replace("{deleted}", f"{deleted:,}"
    ).replace("{body}", "\n".join(rows))
