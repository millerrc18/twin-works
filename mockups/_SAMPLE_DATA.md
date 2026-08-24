# Shared sample data for all 3 mockup concepts (use these EXACT values so concepts compare apples-to-apples)

## Landing page — 3 program cards
- **G500 Elevator** (531335): 17 WIP, 6 behind, 0 stalled, model EMPIRICAL, runs ~7d optimistic. Ships ~1.5/wk (target 1.4).
- **Aeronose Radome** (C48178): 11 active WIP, 1 behind, 7 parked/stalled, model EMPIRICAL, ~7.8d optimistic. Ships ~0.5/wk.
- **Aegis Reflector** (530349): 5 WIP, 0 behind, 2 stalled, model EMPIRICAL, ~7.1d optimistic, DPAS-rated, NO RTG plan.

Global KPIs for a header strip: Overall forecast accuracy MAE 7.1d (PRELIMINARY, n=8), OTD trending up, WC221 paint = binding constraint at 118% util.

## Forecast matrix (use Elevator) — columns are RTG delivery SLOTS, grouped LH then RH
Header block per column: serial (SO) / Contract / RTG target / Earliest / Forecast(P50) / Δ-vs-target
LH group (sorted by RTG target):
| serial | SO | RTG target | Forecast P50 | Δ |
|--------|-----|-----------|--------------|---|
| LH 232 | 1455596 | 08/21 | 08/28 | +7 |
| LH 233 | 1456550 | 08/28 | 09/01 | +4 |
| LH 229 | 1452748 | 09/04 | 09/02 | -2 |
| LH 234 | 1457061 | 09/11 | 09/11 | 0 |
| LH 235 | 1458317 | 09/18 | 09/15 | -3 |
| LH 236 | 1459236 | 09/25 | 09/16 | -9 |

RH group:
| RH 227 | 1452749 | 08/21 | 08/22 | +1 |
| RH 231 | 1456551 | 08/28 | 08/27 | -1 |
| RH 232 | 1457063 | 09/04 | 09/04 | 0 |
| RH 233 | 1458318 | 09/11 | 09/08 | -3 |
| RH 235 | 1460168 | 09/18 | 09/15 | -3 |

Unassigned/bumped group: (LH 238 - MRB hold, idle 9d)

## Operation rows (down the left), milestone bands, cure/gate rows
Milestone bands: ASSY JIG (AJ) / ASSEMBLY 1 (A1) / ASSEMBLY 2 (A2) / FINISH-SHIP (FS)
Sample op rows (op# · desc · WC · hrs):
- 100 Mark Data Plate · 248 · 0.8h   [AJ]
- 600 Locate & Shim Parts · 32684 · 17h  [AJ]
- 800 Liquid Shim Spar · 32684 · 6.5h  [AJ]
  - cure: Liquid shim RT cure · 8h dwell
- 2300 Install & Fillet Seal · 32684 · 18h  [A1]
- 3030 Fay Seal · 32684 · 12h  [A2]
- 3800 Prep & Prime · 221 · 30.5h  [FS]
  - cure: Topcoat 24hr tape-test · 24h dwell (GATE)
- 4100 Final Inspection · 32687 · 4h  [FS]
- 4200 Pack & Ship · P2PCK · 3h  [FS]

Cell states: C = done (green), WIP = in-work (amber), projected date = upcoming (grey/ice), cure row (purple), gate row (orange).
Example: LH 232 is at op 3850 (past 3800, in FS) so early ops = C, current = WIP, later = dates.

## Palette reference (current app, Excel-derived) — concepts can reinterpret
navy #16243D, blue #24406B, green #C6EFCE/#1E6B2E, amber #FFE9A8/#8A6100, red #FFC7CE/#9C0006,
cure purple #E7DDF0/#5B3A82, gate orange #FCE4D6/#9C4B1C, ice #EEF3FB.

## Honesty elements to include (part of the product's identity)
- Model status badge: "EMPIRICAL · n=8" (not yet TRAINED)
- Caveat line: "PRELIMINARY — forecast = best-case floor + measured slip, not guaranteed delivery"
- Δ measured vs RTG target (the date the team works to), contract shown as secondary.
