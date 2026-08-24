"""Parse the persisted IFS clocking-timeline tool-result into a clean JSON:
   { SO(str): { OPNO(int): "YYYY-MM-DD" (last-clock date) } }
The tool result is JSON with an outer 'result' string that itself contains JSON.
"""
import json, re, sys

SRC = r"C:\Users\ryan.c.miller\.claude\projects\C--Users-ryan-c-miller\7cc9493c-9e1f-4f7c-80d6-c6e8c2fcfbc7\tool-results\toolu_vrtx_01FMUejH2pnwBDHRFRgGqSG5.txt"
OUT = r"C:\Users\ryan.c.miller\Downloads\rtg-tracker-build\backtest_timeline.json"

raw = open(SRC, "r", encoding="utf-8").read()
# outer wrapper: {"result":"<escaped json>"}
outer = json.loads(raw)
inner = json.loads(outer["result"])
rows = inner["data"]
print("rows:", len(rows), "has_more:", inner.get("has_more"))

tl = {}
for r in rows:
    so = str(r["SO"]); op = int(r["OPNO"]); clk = r["LAST_CLK"]
    tl.setdefault(so, {})[op] = clk

json.dump(tl, open(OUT, "w"), indent=0)
print("wrote", OUT, "SOs:", len(tl))
# quick sanity: show a couple
for so in list(tl)[:3]:
    ops = sorted(tl[so].items())
    print(so, "ops:", len(ops), "range", ops[0][0], "->", ops[-1][0], "last", ops[-1][1])
