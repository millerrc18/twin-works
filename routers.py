# Router definitions from IFS research (SO_OPER_DISPATCH_LIST_CFV planned hours)
# Elevator: 72P5520501 (LH) / 72P5520502 (RH), ref SO 1452748
# Radome:   3700ED0001-101, ref SO 1453338
#
# planned_hr = LABOR_SETUP_TIME + LABOR_RUN_FACTOR * qty(1)
# milestone boundaries:
#   Elevator: AJ<=1300, A1<=2800, A2<=3600, FS<=4200
#   Radome:   LAM<=570, ASSY<=710, PAINT<=755, SHIP<=790
#
# We DROP ONLY per-unit MRB-clocking placeholder ops (e.g. "MRB 69825 Ops Clockings"
# at 2052/2054/2810/2820/2830) — those are variance buckets, not standard router steps.
# NOTE: "(NOWB)" = No Work Booked to a sub-order (in-line work); these ARE real
# value-add ops and are KEPT (e.g. op 3800 Prep & Prime, 30.5 hr).

import datetime as _dt

# ---- ELEVATOR ----  (op_no, description, work_center, planned_hr, milestone)
# milestone in {AJ, A1, A2, FS}
ELEVATOR_OPS = [
    (100,  "Mark Data Plate",                   "248",   0.8,  "AJ"),
    (200,  "Install Data Plate & Plug Parts",   "32684", 4.0,  "AJ"),
    (300,  "Record Serial Numbers Make Parts",  "32684", 2.0,  "AJ"),
    (400,  "Locate Box & Closeout Ribs",        "32684", 10.0, "AJ"),
    (500,  "Drill & Install Shear Clips",       "32684", 10.0, "AJ"),
    (600,  "Locate & Shim Parts",               "32684", 17.0, "AJ"),
    (700,  "Prep & Prime Aluminum Shims",       "32684", 2.5,  "AJ"),
    (800,  "Liquid Shim Spar & Details",        "32684", 6.5,  "AJ"),
    (1000, "Assembly",                          "32684", 26.5, "AJ"),
    (1100, "Drill Seal Holes",                  "32684", 2.8,  "AJ"),
    (1200, "Inspection",                        "32687", 2.5,  "AJ"),
    (1300, "Remove Elev from AJ, Install in HF","32684", 1.0,  "AJ"),
    (1450, "Remove Excess Liquid Shim",         "32684", 2.5,  "A1"),
    (1500, "Touch Up LE Ribs & Hinges",         "221",   2.0,  "A1"),
    (1510, "Touch Up Primer",                   "221",   2.0,  "A1"),
    (1520, "Touch Up Topcoat",                  "221",   2.5,  "A1"),
    (1550, "Drill LE Skins & Attach Shims",     "32684", 4.0,  "A1"),
    (1600, "Locate & Drill Outbd Closeout Clip","32684", 2.0,  "A1"),
    (1610, "Install Close Out Clip",            "32684", 1.5,  "A1"),
    (1700, "Prepare Drill Panels Spar Web",     "32684", 1.5,  "A1"),
    (1710, "Drill Spar Web Holes",             "32684", 3.5,  "A1"),
    (1800, "Install Hinges & LE Ribs to Spar",  "32684", 3.0,  "A1"),
    (1810, "Install Spar / Clip Fasteners",     "32684", 1.5,  "A1"),
    (1900, "Temporary Load LE Panels",          "32684", 2.5,  "A1"),
    (1910, "Locate LE Skins",                   "32684", 2.0,  "A1"),
    (1920, "Drill LE Skins",                    "32684", 3.5,  "A1"),
    (1930, "Drill OB Seal Holes",              "32684", 2.2,  "A1"),
    (1940, "Prepare Test Panel, LE Skins",      "32684", 2.7,  "A1"),
    (1950, "Countersink LE Skins",              "32684", 3.7,  "A1"),
    (2010, "Install Static Wick Bases",         "32684", 2.8,  "A1"),
    (2050, "Locate & Drill TE Splices",         "32684", 8.5,  "A1"),
    (2100, "Prepare Drill Panels, Spar Flange", "32684", 1.8,  "A1"),
    (2110, "Drill Upper Surface",               "32684", 4.0,  "A1"),
    (2120, "Drill Lower Surface",               "32684", 3.0,  "A1"),
    (2200, "Prepare Panels Box Flange - CSK",   "32684", 3.0,  "A1"),
    (2210, "Countersink Box Flange Holes",      "32684", 4.0,  "A1"),
    (2300, "Install & Fillet Seal Details",     "32684", 18.0, "A1"),
    (2400, "Install Dimple Washers",            "32684", 2.0,  "A1"),
    (2500, "Shim Bumpers",                      "32684", 0.9,  "A1"),
    (2510, "Install Bumpers",                   "32684", 1.0,  "A1"),
    (2700, "Electrical Grounding Bracket Assys","32684", 1.7,  "A1"),
    (2710, "Install Electrical Ground Brackets","32684", 0.9,  "A1"),
    (2720, "Install Jumper Ground Cables",      "32684", 1.5,  "A1"),
    (2725, "Inspect Bumper Location",           "32687", 0.5,  "A1"),
    (2750, "Fastener Check MAF 663",            "32684", 1.0,  "A1"),
    (2800, "Inspection Operation",              "32687", 2.1,  "A1"),
    (2900, "Remove FOD from Box Assembly",      "32684", 2.2,  "A2"),
    (2950, "Install Plugs",                     "32684", 1.0,  "A2"),
    (3000, "Seal Electrical Hardware",          "32684", 2.5,  "A2"),
    (3010, "Epon Coat",                         "32684", 1.0,  "A2"),
    (3030, "Overcoat Fastener Tails",           "32684", 12.7, "A2"),
    (3200, "Fay Seal LE Skins",                 "32684", 3.5,  "A2"),
    (3210, "Install LE Skin & Spar Fasteners",  "32684", 4.3,  "A2"),
    (3215, "Inspect LE Skin Installation",      "32687", 3.0,  "A2"),
    (3220, "Aero Seal Gaps",                    "32684", 2.7,  "A2"),
    (3250, "Inspect Sealant Application - Spar","32687", 3.0,  "A2"),
    (3300, "Touch Up Spar & Spar Fasteners",    "221",   24.5, "A2"),
    (3400, "Create FIP Seal",                   "32684", 9.0,  "A2"),
    (3500, "Final LE Panel Installation",       "32684", 17.0, "A2"),
    (3600, "Inspect Fastener Install, Step/Gap","32687", 1.0,  "A2"),
    (3700, "Aero Seal Gaps",                    "32684", 2.0,  "FS"),
    (3725, "Inspect Aero Seal",                 "32687", 1.0,  "FS"),
    (3750, "Inspect Contour QCF 4401-005",      "32687", 0.6,  "FS"),
    (3800, "Prep & Prime (paint)",              "221",   30.5, "FS"),
    (3850, "Inspect Touch Up",                  "32687", 0.1,  "FS"),
    (3900, "Install Seal Assemblies",           "32684", 4.2,  "FS"),
    (4000, "Remove LE Panel Fasteners for Ship","32684", 2.7,  "FS"),
    (4005, "Inspect Hinge Hole Diameters",      "32687", 0.5,  "FS"),
    (4010, "Apply Cor Ban",                     "32684", 16.0, "FS"),
    (4020, "Inspection of Cor Ban",             "32687", 0.5,  "FS"),
    (4030, "Install Leading Edge Panels",       "32687", 4.0,  "FS"),
    (4100, "Final Inspection QCF 4401-008",     "32687", 1.5,  "FS"),
    (4200, "Pack & Ship WI 4401-PACK",          "P2PCK", 1.5,  "FS"),
]

# ============================================================
# CREW FACTOR (floor reality, NOT in ERP router which is all CREW_SIZE=1/serial).
# The shop SWARMS a unit's finish line (paint/seal/Cor-Ban) to push it out the door,
# but MAIN ASSEMBLY runs at standard single/low crew (finite labor pool governs the
# back of the line). So crew boost applies ONLY to tail/finishing ops, by op number.
# Verified 2026-08-19: 2 painters live on op3800 Prep&Prime.
# Main assembly kept at 1x so far-out units don't over-accelerate (steady-state honest).
# ------------------------------------------------------------
# Tail/finishing ops that get swarmed (elevator op>=3800 paint+ship push; the big
# seal ops 2300/3030/3300 also run crews). value = concurrent operators.
CREW_BY_OP = {
    # elevator finish line (paint & ship push)
    3800:2.0, 3900:2.0, 4010:2.0, 4030:2.0,
    # elevator big seal/touch-up ops that swarm
    2300:2.0, 3030:2.0, 3300:2.0,
    # radome finish line
    775:1.5, 780:1.5, 730:1.5, 740:1.5, 750:1.5,
}
def crew(wc, opno=None):
    """Crew factor: >1 only on swarmed tail/finishing ops (by op#). Main assembly = 1x."""
    if opno is not None and opno in CREW_BY_OP:
        return CREW_BY_OP[opno]
    return 1.0

# PARALLEL cures: run 24/7 alongside DOWNSTREAM labor rather than serially blocking.
# The WI 24hr topcoat tape-test must ELAPSE before final inspection (op4100), but the
# 3850->4030 labor happens WHILE it cures. Model as: cure starts after its op, and
# gates the named GATE_OP only if not yet elapsed (usually the tail labor covers it).
# label-substring -> gate_op (the op that cannot start until this cure has elapsed)
PARALLEL_CURE_GATES = {
    "Topcoat 24hr tape-test": 4100,   # elevator: gates final inspection, not a serial tail
}

# ============================================================
# CURE / DWELL MAP (from MVA Work Instructions, 2026-08-18)
# Pure calendar dwell, ZERO labor, elapses 24/7 wall-clock.
# Inserted as its own row AFTER the named op. dwell_hr = wall-clock hours.
# path: accelerated (oven) chosen per user. gate=True means it blocks next op.
# (after_op, label, dwell_hr, note)
# ------------------------------------------------------------
ELEVATOR_CURES = [
    (800,  "CURE — Liquid Shim (spar & details)",      8,   "GMS4003 liquid shim; ambient set before assembly"),
    (2300, "CURE — Fillet Seal Details (PS870 B-2)",   32,  "24hr flash + 8hr @125F oven (accelerated)"),
    (3000, "CURE — Seal Elec Hardware / CHO-BOND",     24,  "CHO-BOND 1038 24hr resistance-check gate (168hr full cure runs parallel)"),
    (3030, "CURE — Overcoat Fastener Tails (PS870)",   32,  "24hr flash + 8hr @125F oven (accelerated); 3-day RT fallback"),
    (3200, "CURE — Fay Seal LE Skins (PS870 C-12)",    72,  "24hr flash + 48hr @125F oven (accelerated); 14-day RT fallback"),
    (3220, "CURE — Aero Seal tack-free",               2,   "GMS4114 2hr tack-free; topcoat within 7 days"),
    (3400, "CURE — FIP Seal (PS870 B-2)",              32,  "24hr flash + 8hr @125F oven (accelerated)"),
    (3700, "CURE — Aero Seal Gaps tack-free",          2,   "GMS4114 2hr tack-free (Op 3700 — the Friday-miss driver)"),
    (3800, "CURE — Prime/Topcoat dry-to-handle",       4,   "op3800 Prep&Prime (30.5hr labor, WC221): primer flash + topcoat dry-to-handle before 3900 install"),
    (3800, "GATE — Topcoat 24hr tape-test (QI, parallel)", 24, "WI: topcoat must cure 24hr @75F. Runs IN PARALLEL with op3850-4030 labor; only gates final insp (op4100) if not yet elapsed. Applied at op3800 topcoat."),
    (4010, "CURE — Cor Ban tack-free",                 4,   "GAC115AD1 CIC dry to tack-free (visual, no timed spec; est 4hr)"),
]

# ---- RADOME ----  milestone in {LAM, ASSY, PAINT, SHIP}
RADOME_OPS = [
    (130, "Outer Skin Bagging",             "AEROL", 1.46,  "LAM"),
    (170, "Outer Skin Cure",                "ATUP",  1.095, "LAM"),
    (210, "Honeycomb Application",          "AEROL", 5.84,  "LAM"),
    (250, "Bagging of Honeycomb",           "AEROL", 1.46,  "LAM"),
    (290, "Cure of Honeycomb",              "238",   1.095, "LAM"),
    (330, "Diverter Anchor Installation",   "AEROL", 2.92,  "LAM"),
    (370, "Diverter Anchor Bagging",        "AEROL", 0.73,  "LAM"),
    (410, "Diverter Anchor Cure",           "238",   1.095, "LAM"),
    (450, "Inner Skin Lamination",          "AEROL", 7.3,   "LAM"),
    (490, "Inner Skin Bagging",             "AEROL", 1.46,  "LAM"),
    (530, "Inner Skin Cure",                "ATUP",  1.095, "LAM"),
    (570, "Demold & Deflash",               "AEROL", 1.46,  "LAM"),
    (575, "Inspection Station",             "P3 QA", 0.73,  "ASSY"),
    (580, "Trim Radome & Drill Drain Hole", "AEROA", 4.0,   "ASSY"),
    (590, "Seal Edge, Chamfer & Drain Hole","AEROA", 1.9,   "ASSY"),
    (620, "Dry Fit Details for Liquid Shim","AEROA", 2.4,   "ASSY"),
    (621, "Shim Gap Inspection",            "P3 QA", 0.219, "ASSY"),
    (625, "Liquid Shim Details",            "AEROA", 9.5,   "ASSY"),
    (630, "Drill Radome & Countersink Holes","AEROA",7.6,   "ASSY"),
    (635, "Measure Fastener Grip Length",   "AEROA", 1.0,   "ASSY"),
    (640, "Install Fasteners",              "AEROA", 3.9,   "ASSY"),
    (650, "Fastener & Shore D Inspection",  "P3 QA", 0.292, "ASSY"),
    (660, "Drill & Install Hinge Fasteners","AEROA", 1.9,   "ASSY"),
    (670, "Install Ground Straps",          "AEROA", 1.9,   "ASSY"),
    (680, "Drill & Countersink Shell LDS",  "AEROA", 4.1,   "ASSY"),
    (690, "Diverter Installation",          "AEROA", 3.0,   "ASSY"),
    (695, "LDS & Electrical Bond Inspection","P3 QA",0.511, "ASSY"),
    (700, "Fillet Seal Lightning Diverters","AEROA", 0.001, "ASSY"),
    (705, "Inspection of LDS Fillet Seal",  "P3 QA", 0.001, "ASSY"),
    (710, "Install Environmental Seal",     "AEROA", 4.5,   "ASSY"),
    (720, "Paint Prep, Plug Holes",         "AEROA", 2.8,   "PAINT"),
    (730, "Fill Surface Imperfections",     "236",   12.4,  "PAINT"),
    (740, "Anti-Static Paint",              "236",   5.7,   "PAINT"),
    (745, "Inspection",                     "P3 QA", 0.511, "PAINT"),
    (750, "Environmental Primer",           "236",   7.6,   "PAINT"),
    (755, "Inspection",                     "P3 QA", 0.511, "PAINT"),
    (760, "Bag Loose Parts & Weigh",        "236",   0.6,   "SHIP"),
    (770, "RF Test",                        "298",   0.001, "SHIP"),
    (775, "Electrical Sealing",             "AEROA", 9.5,   "SHIP"),
    (780, "ID & Touch Up",                  "236",   2.3,   "SHIP"),
    (785, "Final Inspection",               "3FINL", 1.241, "SHIP"),
    (790, "Pack & Ship",                    "235",   3.3,   "SHIP"),
]

# ============================================================
# RADOME CURE / DWELL MAP (from MVA WI 3700ED0001-101 + IFS MACH_RUN oven times)
# Radome cures come from TWO sources not modeled as dwell in the RTG tracker:
#  (1) LAM oven cures (op 170/290/410/530): MACH_RUN=6.5hr each = autoclave/oven
#      dwell that elapses wall-clock while no operator is hands-on.
#  (2) WI-mandated post-bond gates beyond MACH_RUN: 8hr peel-ply-to-next-bond
#      gate after skin cures; op775 electrical sealing 40hr polysulfide cure
#      (IFS shows only 11.6 mach hr — the WI 40hr min governs).
# (after_op, label, dwell_hr, note)
# ------------------------------------------------------------
RADOME_CURES = [
    (170, "CURE — Outer Skin oven (BT250E-1)",       6.5, "IFS MACH_RUN 6.5hr autoclave/oven cure"),
    (170, "GATE — Peel-ply to next bond",            8,   "WI 8hr peel-ply-to-bond gate before honeycomb (170->210)"),
    (290, "CURE — Honeycomb oven",                   6.5, "IFS MACH_RUN 6.5hr oven cure"),
    (410, "CURE — Diverter Anchor oven",             6.5, "IFS MACH_RUN 6.5hr oven cure"),
    (410, "GATE — Peel-ply to inner-skin bond",      8,   "WI 8hr peel-ply-to-bond gate before inner skin (410->450)"),
    (530, "CURE — Inner Skin oven (BT250E-1)",       6.5, "IFS MACH_RUN 6.5hr autoclave/oven cure"),
    (590, "CURE — Edge/Chamfer seal",                6,   "GAA100BD08-class edge seal set before dry-fit (est 6hr RT)"),
    (620, "GATE — Pre-drill shim set",               8,   "WI min 8hr RT before drilling radome (op620->630)"),
    (625, "CURE — Liquid Shim Details",              6,   "GAA100BD10 6hr RT (or 2hr@150F accel); Shore D gate"),
    (700, "CURE — LDS Fillet Seal (RTV)",            2,   "diverter fillet RTV cure gate before env seal"),
    (710, "CURE — Environmental Seal set",           6,   "env seal set before paint prep (est 6hr)"),
    (730, "CURE — Fill Surface Imperfections",       2,   "glazing putty 60-90min@140F or ambient set"),
    (740, "CURE — Anti-Static Paint flash",          2,   "anti-static topcoat flash + dry before inspection"),
    (750, "CURE — Environmental Primer",             4,   "primer flash + dry-to-recoat before final"),
    (775, "GATE — Electrical Sealing 40hr (Shore A)", 40, "op775 polysulfide 00200054000: WI MIN 40hr cure, Shore A>=35 gate (IFS mach 11.6hr understates) — dominant radome dwell"),
]

# ============================================================
# AEGIS REFLECTOR ANTENNA  (project 530349, part 00999000563 / dwg 6778045-50)
# 3rd program. DPAS-RATED -> takes priority for shared capacity when behind contract.
# Shares ovens (32678) + PAINT BOOTH (WC 221) with ELEVATOR. Ref SO 1442037.
# Milestones: LAM<=195, ASSY<=245, PAINT<=370, SHIP<=400.
# DROP admin ops 1,6,7,8,9 + MRB 196/197 (variance buckets).
# (op_no, description, work_center, planned_hr, milestone)
# ------------------------------------------------------------
AEGIS_OPS = [
    (90,  "Inprocess Inspection",          "32687", 10.0, "LAM"),
    (100, "General Instructions",          "244",   0.5,  "LAM"),
    (105, "Core Bond",                     "244",   10.0, "LAM"),
    (108, "Core Bond - Cont.",             "244",   10.0, "LAM"),
    (110, "Autoclave Cure 1X70AR002",      "32678", 5.0,  "LAM"),
    (115, "Debag",                         "244",   4.0,  "LAM"),
    (120, "Rear Machining",                "234",   8.0,  "LAM"),
    (132, "Fill Strut Holes & Cut Tube",   "42676", 12.0, "LAM"),
    (133, "Inspection",                    "32687", 0.5,  "LAM"),
    (134, "Tube Installation",             "42676", 5.0,  "LAM"),
    (135, "Rear Skin Lamination",          "244",   15.0, "LAM"),
    (140, "Rear Skin Autoclave Cure",      "32678", 1.0,  "LAM"),
    (145, "Debag",                         "244",   5.0,  "LAM"),
    (150, "Inspection",                    "32687", 1.0,  "LAM"),
    (155, "CNC Inserts/Bosses",            "234",   4.0,  "LAM"),
    (157, "Inspection",                    "32687", 1.0,  "LAM"),
    (160, "Ring Bond",                     "42676", 36.0, "LAM"),
    (170, "CNC Trim/Open Holes",           "234",   2.0,  "LAM"),
    (175, "Inspection",                    "32687", 5.0,  "LAM"),
    (180, "Perimeter Edge Fill",           "42676", 24.0, "LAM"),
    (185, "Edge Lamination",               "244",   14.0, "LAM"),
    (190, "Edge Cure",                     "313",   1.0,  "LAM"),
    (192, "Debag After Cure",              "244",   2.0,  "LAM"),
    (194, "Inspection",                    "32687", 0.25, "LAM"),
    (195, "Edge Clean Up",                 "42676", 16.0, "LAM"),
    (200, "Mount Reflector",               "42676", 2.0,  "ASSY"),
    (230, "Move Reflector & Detail Bond",  "42676", 16.0, "ASSY"),
    (235, "Inspection",                    "32687", 2.0,  "ASSY"),
    (240, "NDI Inspection",                "2 NDI", 6.0,  "ASSY"),
    (245, "Surface Preparation",           "42676", 28.0, "ASSY"),
    (250, "Test Panel Prep",               "42676", 4.0,  "PAINT"),
    (255, "Inspection",                    "32687", 1.2,  "PAINT"),
    (260, "Reflector Prep",                "42676", 6.0,  "PAINT"),
    (270, "Sealer Application",            "42676", 10.0, "PAINT"),
    (275, "Inspection",                    "32687", 0.5,  "PAINT"),
    (280, "Primer Prep",                   "221",   8.0,  "PAINT"),
    (290, "Primer Coat",                   "221",   8.0,  "PAINT"),
    (295, "Inspection",                    "32687", 1.0,  "PAINT"),
    (300, "Top Coat",                      "221",   24.0, "PAINT"),
    (310, "Finish Inspection",             "32687", 2.0,  "PAINT"),
    (320, "Clean Up / Stencil",            "221",   4.0,  "PAINT"),
    (340, "Inspection",                    "32687", 2.2,  "PAINT"),
    (370, "Paint Sealer (Rejex)",          "221",   4.2,  "PAINT"),
    (375, "Gloss Inspection & Peel Test",  "32687", 1.0,  "PAINT"),
    (380, "Pack & Ship",                   "221",   6.0,  "SHIP"),
    (390, "In Crate Inspection",           "32687", 2.0,  "SHIP"),
    (400, "Seal Crate",                    "221",   1.5,  "SHIP"),
]

# AEGIS cures: autoclave/edge from router MACH_RUN + WI-mandated dwell (WI 00999000563)
# (after_op, label, dwell_hr, note)
AEGIS_CURES = [
    (110, "CURE — Autoclave Cure (1X70AR002)",   5,   "IFS MACH_RUN autoclave cure, front core bond"),
    (140, "CURE — Rear Skin Autoclave Cure",     7,   "IFS MACH_RUN autoclave cure, rear skin"),
    (160, "CURE — Ring Bond Epocast 1636 RT",    12,  "WI 00999000563: Epocast 1636 min 12hr RT cure"),
    (190, "CURE — Edge Cure",                    16.5,"IFS MACH_RUN edge cure (op190, WC313)"),
    (270, "CURE — Sealer bake/dry",              6,   "epoxy MIL-C-22750 sealer; primer within 6hr of bake"),
    (290, "CURE — Primer dry-to-recoat",         4,   "primer flash + dry before topcoat"),
    (300, "GATE — Topcoat 24hr cure (QI)",       24,  "topcoat cure before finish insp/paint-adhesion (est per elevator topcoat gate)"),
]

# Discrete cure-station capacity. Ovens remain unconstrained: the floor-confirmed
# bottlenecks are two Plant 2 paint booths and one conservative Plant 3 electrical-seal station.
# The topcoat tape-test is deliberately absent because it runs in parallel after the unit leaves
# the booth; it gates final inspection but does not reserve a booth for 24 hours.
CURE_STATION_CAPACITIES = {
    "P2_PAINT_BOOTH": 2,
    "P3_ELECTRICAL_SEAL": 1,
}
CURE_STATION_RULES = {
    ("ELEV", 3800, next(label for after_op, label, *_ in ELEVATOR_CURES
                         if after_op == 3800 and "dry-to-handle" in label)): "P2_PAINT_BOOTH",
    ("ELEV", 4010, next(label for after_op, label, *_ in ELEVATOR_CURES
                         if after_op == 4010 and "Cor Ban" in label)): "P2_PAINT_BOOTH",
    ("RAD", 775, next(label for after_op, label, *_ in RADOME_CURES
                       if after_op == 775 and "Electrical Sealing" in label)): "P3_ELECTRICAL_SEAL",
}
# DPAS-rated programs take shared-capacity priority when behind contract.
DPAS_PROGRAMS = {"AEGIS"}
# Work centers SHARED across programs (must be pooled, not private budgets):
SHARED_WC = {"221", "32678"}  # 221=paint booth (elev+aegis), 32678=autoclave/ovens

# ============================================================
# PER-SHIFT CAPACITY (measured hrs/shift/weekday, 3wk clocking 7/29-8/19, TOP-ASM ops only)
# Shift windows inferred from clocking start-time clusters (Marion):
#   1st = 0600-1400, 2nd = 1400-2200, 3rd = 2200-0600.
# WC221 paint = top-asm draw only (~39/day); sub-component paint (op5900/8010 skins/
# panels) consumes the rest of the booth and is treated as already-reserved (implicit).
# key: (program, wc) -> {1:hrs, 2:hrs, 3:hrs} per weekday. Missing shift = 0.
# NOTE: 221 + 32678 are SHARED (elev+aegis) — pooled sim sums both programs' draw
#       against a combined booth cap (see SHIFT_CAP_SHARED below).
# ------------------------------------------------------------
WC_SHIFT = {
 # ELEVATOR (531335)
 ("ELEV","32684"): {1:118, 2:37, 3:28},   # main assembly — day-heavy
 ("ELEV","221"):   {1:17,  2:9,  3:13},   # top-asm paint (prep&prime/spar touchup)
 ("ELEV","32687"): {1:19,  2:0,  3:7},    # QA — DAY-SHIFT ONLY gate (swing ~0)
 ("ELEV","INSP"):  {1:0,   2:11, 3:3},
 ("ELEV","248"):   {1:9,   2:0,  3:0},
 ("ELEV","P2PCK"): {1:8,   2:8,  3:8},    # pack (floored)
 # RADOME (C48178)
 ("RAD","AEROL"):  {1:21,  2:25, 3:2},    # layup — day+swing
 ("RAD","AEROA"):  {1:14,  2:0,  3:14},   # assembly — day+night, swing gap
 ("RAD","236"):    {1:14,  2:9,  3:12},   # radome paint — thin all shifts
 ("RAD","238"):    {1:14,  2:15, 3:18},   # oven (24/7-ish)
 ("RAD","ATUP"):   {1:8,   2:11, 3:8},    # autoclave
 ("RAD","P3 QA"):  {1:5,   2:8,  3:5},
 ("RAD","INSP"):   {1:6,   2:17, 3:11},
 ("RAD","3FINL"):  {1:4,   2:4,  3:4},
 ("RAD","235"):    {1:8,   2:8,  3:8},
 ("RAD","298"):    {1:4,   2:4,  3:4},
 # AEGIS (530349) — shares 221 paint + 32678 ovens with elevator
 ("AEGIS","244"):  {1:13,  2:2,  3:16},   # core bond / skin lam
 ("AEGIS","42676"):{1:17,  2:0,  3:0},    # ring bond / edge / surface prep
 ("AEGIS","234"):  {1:20,  2:12, 3:0},    # CNC machining
 ("AEGIS","32678"):{1:26,  2:0,  3:15},   # autoclave (shared w/ elev)
 ("AEGIS","221"):  {1:6,   2:3,  3:4},    # paint (shared w/ elev; small aegis draw)
 ("AEGIS","32687"):{1:8,   2:2,  3:2},
 ("AEGIS","313"):  {1:8,   2:8,  3:8},    # edge cure oven
 ("AEGIS","2 NDI"):{1:6,   2:2,  3:2},
}
DEFAULT_SHIFT = {1:8, 2:6, 3:4}  # any (program,wc) not listed
def wc_shift_budget(program, wc, shift):
    return WC_SHIFT.get((program,wc), DEFAULT_SHIFT).get(shift, 0)

# ELEVATOR-ONLY weekend OT rotation: 2 weekends ON, 1 OFF.
# Anchor: weekend of 8/16-17 was OFF; 8/23-24 + 8/30-31 ON (mandatory OT); 9/6-7 OFF; repeat.
# Returns weekend work factor for a date (elevator only). Weekdays always 1.0.
def elevator_weekend_factor(dd):
    if dd.weekday() < 5:
        return 1.0                             # weekday
    # OT-ON weekends (Sat/Sun) — mandatory, treat as ~full day
    on_weekends = {
        _dt.date(2026,8,23), _dt.date(2026,8,24),
        _dt.date(2026,8,30), _dt.date(2026,8,31),
        # cycle continues: 9/6-7 OFF, 9/13-14 ON, 9/20-21 ON, 9/27-28 OFF ...
        _dt.date(2026,9,13), _dt.date(2026,9,14),
        _dt.date(2026,9,20), _dt.date(2026,9,21),
        _dt.date(2026,10,4), _dt.date(2026,10,5),
        _dt.date(2026,10,11), _dt.date(2026,10,12),
    }
    if dd in on_weekends:
        return 0.85                            # mandatory OT weekend ~85% of weekday
    return 0.0                                  # OFF weekend — no elevator work

ELEV_MILESTONES = [("AJ","Assy Jig"),("A1","Assembly 1"),("A2","Assembly 2"),("FS","Finish / Ship")]
RAD_MILESTONES  = [("LAM","Lamination"),("ASSY","Assembly"),("PAINT","Paint"),("SHIP","Ship")]
AEGIS_MILESTONES = [("LAM","Lamination"),("ASSY","Assembly"),("PAINT","Paint"),("SHIP","Ship")]
