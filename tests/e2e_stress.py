#!/usr/bin/env python
"""E2E stress 450k: mapa + recovery NUMA unica operacao + hash check completo."""
import hashlib, json, os, resource, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from recovermap.core import RecoverMapEngine

img, manifest_path, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
t0 = time.time()

print("carregando manifesto...", flush=True)
manifest = {m["path"]: m for m in json.load(open(manifest_path))}
print("manifesto: %d arquivos | %.1fs" % (len(manifest), time.time()-t0), flush=True)

eng = RecoverMapEngine(img)
tw = time.time()
walk_last = [0]
def wprog(n, ndirs):
    if n - walk_last[0] >= 100000:
        walk_last[0] = n
        print("  walk: %d entradas (t+%.0fs)" % (n, time.time()-t0), flush=True)
entries = eng.walk(on_progress=wprog)
tw = time.time() - tw
files = [e for e in entries if not e.is_dir]
orphans = [e for e in files if e.path.startswith("$OrphanFiles/")]
user = [e for e in files if not e.path.startswith("$OrphanFiles/")]
deleted_user = [e for e in user if e.deleted]
print("MAPA: %d entradas | %d arquivos | %d do usuario (%d deletados) | %d orfaos | %.1fs | ~%d/s"
      % (len(entries), len(files), len(user), len(deleted_user), len(orphans), tw,
         int(len(files)/max(tw, .001))), flush=True)
assert len(user) == len(manifest), "usuario: esperado %d, veio %d" % (len(manifest), len(user))

last = [0]
def prog(i, n, path):
    if i - last[0] >= 50000:
        last[0] = i
        print("  recovery: %d/%d (t+%.0fs)" % (i, n, time.time()-t0), flush=True)

tr = time.time()
res = eng.recover(outdir, entries, on_progress=prog,
                  report_path=os.path.join(outdir, "recovermap-report.csv"))
tr = time.time() - tr
print("RECOVERY 1 OPERACAO: %d alvos | %d OK | %d fail | %d bytes | %.1fs | ~%d arq/s"
      % (res["total"], res["ok"], res["fail"], res["bytes"], tr,
         int(res["ok"]/max(tr, .001))), flush=True)
assert res["fail"] == 0, "falhas: %d" % res["fail"]
assert res["total"] == len(files), "alvos != arquivos do mapa"

th = time.time()
ok_hash = mismatch = missing = 0
k = 0
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
    k += 1
    if k % 100000 == 0:
        print("  hash-check: %d/%d" % (k, len(manifest)), flush=True)
th = time.time() - th
summary = {
    "recuperados_numa_operacao": res["total"],
    "hash_ok": ok_hash, "hash_mismatch": mismatch, "missing": missing,
    "arquivo_deletado_F-250000": os.path.isfile(os.path.join(outdir, "F-250000.txt")),
    "tempo_walk_s": round(tw, 1), "tempo_recovery_s": round(tr, 1),
    "tempo_hash_check_s": round(th, 1),
    "rss_pico_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
}
print(json.dumps(summary, indent=1), flush=True)
assert missing == 0 and mismatch == 0 and ok_hash == len(manifest)
print("STRESS_OK: %d arquivos numa UNICA operacao | %d/%d hashes identicos | deletado recuperado"
      % (res["total"], ok_hash, len(manifest)), flush=True)
