import re, os
f = "docs/agh-execution-record.raw.jsonl"
if not os.path.exists(f):
    print("no raw record at", f)
    raise SystemExit(0)
data = open(f, encoding="utf-8").read()
hits = [m.start() for m in re.finditer("B02_unit_slip", data)]
print("B02 mentions in raw record:", len(hits))
for h in hits:
    seg = data[h - 200:h + 400]
    mc = re.search(r'"model_check_verdict"\s*:\s*"(\w+)"', seg)
    mf = re.search(r'"model_check_findings"\s*:\s*(\[[^\]]*\])', seg)
    if mc:
        print("  B02 model_check_verdict:", mc.group(1), "| findings:", mf.group(1) if mf else "n/a")
