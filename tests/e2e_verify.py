#!/usr/bin/env python
"""Verificacao E2E: mapa + recuperacao unica contra manifesto SHA-256.

Prova: 5001 arquivos do usuario + orfaos do NTFS recuperados NUMA unica
operacao (acima do limite de 4000/operacao de edicoes Free), conteudo
identico (SHA-256) ao original.
"""
import hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from recovermap.core import RecoverMapEngine

img = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "tests/data/test-ntfs.img")
manifest_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "tests/data/manifest-ntfs.json")
outdir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, "tests/data/out")

manifest = {m["path"]: m for m in json.load(open(manifest_path))}
print("manifesto: %d arquivos esperados" % len(manifest))

eng = RecoverMapEngine(img)
entries = eng.walk()
files = [e for e in entries if not e.is_dir]
orphans = [e for e in files if e.path.startswith("$OrphanFiles/")]
user = [e for e in files if not e.path.startswith("$OrphanFiles/")]
deleted_user = [e for e in user if e.deleted]
print("MAPA: %d entradas | %d arquivos | %d do usuario (%d deletados) | %d orfaos ($OrphanFiles)"
      % (len(entries), len(files), len(user), len(deleted_user), len(orphans)))
for o in orphans[:5]:
    print("   orfao: %s (%d bytes, deletado=%s)" % (o.path, o.size, o.deleted))
assert len(user) == len(manifest), "usuario: esperado %d, veio %d" % (len(manifest), len(user))

res = eng.recover(outdir, entries,
                  report_path=os.path.join(outdir, "recovermap-report.csv"))
print("RECOVERY 1 OPERACAO:", res)
assert res["fail"] == 0, "houve %d falhas" % res["fail"]
assert res["total"] == len(files), "nem todos os arquivos do mapa foram alvo"

ok_hash = mismatch = missing = 0
for path, m in manifest.items():
    p = os.path.join(outdir, path)
    if not os.path.isfile(p):
        missing += 1
        continue
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    if h == m["sha256"]:
        ok_hash += 1
    else:
        mismatch += 1

orphan_dir = os.path.join(outdir, "$OrphanFiles")
n_orphan = sum(len(f) for _, _, f in os.walk(orphan_dir)) if os.path.isdir(orphan_dir) else 0

summary = {
    "recuperados_numa_operacao": res["total"],
    "hash_ok": ok_hash, "hash_mismatch": mismatch, "missing": missing,
    "orfaos_recuperados": n_orphan,
    "arquivo_deletado_F-00042": os.path.isfile(os.path.join(outdir, "F-00042.txt")),
}
print(json.dumps(summary, indent=1))
assert missing == 0 and mismatch == 0, "conteudo divergente"
assert ok_hash == len(manifest), "nem todos os arquivos do manifesto conferem"
assert res["total"] > 4000, "a operacao unica deveria exceder 4000 arquivos"
print("E2E_OK: %d arquivos recuperados numa UNICA operacao (>4000, sem limite), "
      "%d/%d hashes identicos, arquivo deletado recuperado, %d orfaos inclusos"
      % (res["total"], ok_hash, len(manifest), n_orphan))
