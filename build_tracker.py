"""Build the RTG Operation Tracker workbook (cure-loaded, commit vs forecast).
Matrix board: ops down rows, units across columns, C / late-date / upcoming cells.
Cure & gate rows inserted in sequence (time-of-day shown). Per-unit Commit/Forecast/Delta.
"""
import datetime, json, os
from datetime import datetime as DT, date, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from routers import (ELEVATOR_OPS, ELEVATOR_CURES, RADOME_OPS, RADOME_CURES,
                     ELEV_MILESTONES, RAD_MILESTONES,
                     AEGIS_OPS, AEGIS_CURES, AEGIS_MILESTONES)
from schedule_engine import forward_schedule, add_labor_hours
from capacity_engine import simulate

AS_OF = DT(2026,8,19,12,0)
OUT = "C:/Users/ryan.c.miller/Downloads/RTG Operation Tracker 2026.xlsx"

# ---- styling (locked palette) ----
NAVY="16243D"; BLUE="24406B"; ICE="D9E1F2"; ICE2="EEF3FB"; WHITE="FFFFFF"; INK="1A1A1A"; GREY="595959"
GREEN="C6EFCE"; GREENK="1E6B2E"; AMBER="FFE9A8"; AMBERK="8A6100"; RED="FFC7CE"; REDK="9C0006"
CUREFILL="E7DDF0"; CUREK="5B3A82"; GATEFILL="FCE4D6"; GATEK="9C4B1C"; MSFILL="24406B"
F=lambda **k: Font(name="Aptos Narrow", **k)
LINE="B7C3D9"; thin=Side(style="thin",color=LINE)
def bd(): return Border(left=thin,right=thin,top=thin,bottom=thin)

# ============================================================
# DATA: serial -> (SO, maxop, commit milestone dates)
# commit dates from GAC RTG (col E/F/G/H = AJ/A1/A2/FS finish); FS = firm ship
# ============================================================
def d(m,dd): return date(2026,m,dd)

# ELEVATOR WIP+next: serial -> dict(so, maxop, ms{AJ,A1,A2,FS})
ELEV = [
 # serial,     SO,        maxop, AJ,      A1,      A2,      FS(ship)
 ("LH 232","1455596",4000, None,    d(8,18), None,    d(8,21)),
 ("LH 233","1456550",3400, None,    None,    d(8,21), d(8,28)),
 ("LH 229","1452748",3400, None,    None,    d(8,28), d(9,4)),
 ("LH 234","1457061",2300, None,    d(8,18), d(9,4),  d(9,11)),
 ("LH 235","1458317",1950, None,    d(8,25), d(9,11), d(9,18)),
 ("LH 236","1459236",1940, None,    d(9,1),  d(9,18), d(9,25)),
 ("LH 237","1460167",1920, None,    d(9,8),  d(9,25), d(10,2)),
 ("LH 238","1460758",1000, d(8,29), d(9,15), d(10,2), d(10,9)),
 ("LH 239","1461523",None, d(9,5),  d(9,22), d(10,9), d(10,16)),
 ("RH 227","1452749",3700, None,    None,    d(8,14), d(8,21)),
 ("RH 231","1456551",3400, None,    None,    d(8,21), d(8,28)),
 ("RH 232","1457063",3030, None,    None,    d(8,28), d(9,4)),
 ("RH 233","1458318",2050, None,    d(8,18), d(9,4),  d(9,11)),
 ("RH 235","1460168",1700, None,    d(8,25), d(9,11), d(9,18)),
 ("RH 234","1459237",1550, None,    d(8,22), d(9,25), d(9,25)),
 ("RH 236","1460759",1450, None,    d(9,1),  d(9,18), d(9,25)),
 ("RH 237","1461524",500,  None,    d(9,8),  d(9,25), d(10,2)),
]

# RADOME WIP: serial(best-effort), SO, maxop, ship(FS). commit = REVISED_DUE_DATE+? use ship col.
# ship dates from prior tracker col5; SO from due-date order.
RAD = [
 # serial, SO,        maxop, ship   (refreshed 2026-08-19 PM; maxop overridden by STATUS_MAXCLOSED)
 ("518","1456255",620, d(8,13)),   # due 8/12
 ("513","1453338",775, d(8,21)),
 ("515","1454081",770, d(8,28)),
 ("514","1453339",745, d(8,28)),
 ("511","1449908",770, d(9,4)),
 ("508","1454080",630, d(9,4)),
 ("517","1451436",720, d(9,4)),
 ("519","1459009",530, d(9,11)),
 ("524","1458360",630, d(9,11)),
 ("520","1460931",410, d(9,18)),
 ("521","1460451",410, d(9,18)),
 ("522","1460932",410, d(9,25)),
 ("523","1401814",695, d(10,1)),
 ("361","1360294",570, d(10,29)),  # old reintroduced unit; likely STALLED
]

# AEGIS REFLECTOR ANTENNA (project 530349, part 00999000563). DPAS-rated; shares
# paint booth WC221 + ovens with elevator. Anchor = IFS REVISED_DUE_DATE (contract).
# serial<->SO from user statusline screenshot 2026-08-19.
AEGIS = [
 # serial,  SO,       maxop, contract-due
 ("176","1442037",240, d(5,14)),   # very behind, +124.9 hrs over
 ("178","1450617",170, d(7,14)),
 ("180","1455178",240, d(9,14)),
 ("181","1457856",160, d(11,12)),
 ("182","1460448",155, d(12,14)),
]

# ============================================================
# SHIPPED units (retained as hidden accuracy-record columns per user 8/21).
# Each: serial-label, SO, program, contract-commit, actual CLOSE, actual PACK,
#       logged-forecast (what the model projected ~1wk out = backtest h=7 proj).
# These 8 = the genuine-production closes from the last ~3 weeks (same set the
# backtest scores). Older stalled/MRB catch-ups intentionally excluded.
# ============================================================
def dt_(y,m,dd): return date(y,m,dd)
SHIPPED = {
 'ELEV':[
  # serial, SO, commit, close, pack, logged_forecast(h7 proj)
  ("RH 3479","1453479",d(6,26),dt_(2026,8,13),dt_(2026,8,13),dt_(2026,8,7)),
  ("RH 3860","1453860",d(7,10),dt_(2026,8,14),dt_(2026,8,14),dt_(2026,8,11)),
  ("LH 5597","1455597",d(7,17),dt_(2026,8,15),dt_(2026,8,15),dt_(2026,8,13)),
  ("LH 3480","1453480",d(6,26),dt_(2026,8,6), dt_(2026,8,6), dt_(2026,8,3)),
  ("RH 1269","1451269",d(6,12),dt_(2026,8,6), dt_(2026,8,1), dt_(2026,7,30)),
  ("LH 1270","1451270",d(6,12),dt_(2026,8,3), dt_(2026,8,3), dt_(2026,7,28)),
 ],
 'RAD':[
  ("518","1451435",d(7,6), dt_(2026,7,31),dt_(2026,7,31),dt_(2026,7,27)),
  ("516","1453337",d(7,15),dt_(2026,8,10),dt_(2026,8,7), dt_(2026,8,3)),
 ],
 'AEGIS':[],
}

FORECAST_LOG = "C:/Users/ryan.c.miller/Downloads/rtg-tracker-build/forecast_log.json"

def write_forecast_log(sim, units_by_prog, close_map):
    """Append one record per (build_date, serial) for every non-stalled live unit:
       forecast (from sim), contract, position. Dedupe by build_date+serial. When a
       unit later has a close date, backfill actual_close + error_days on its records."""
    bdate = AS_OF.strftime('%Y-%m-%d')
    log = []
    if os.path.exists(FORECAST_LOG):
        try: log = json.load(open(FORECAST_LOG))
        except Exception: log = []
    idx = {(r['build_date'], r['serial']): i for i,r in enumerate(log)}
    for prog, units in units_by_prog.items():
        for u in units:
            serial=u[0]; so=u[1]
            if is_stalled(so): continue
            sr = sim.get(serial)
            if not sr: continue
            fdt = sr['finish'].strftime('%Y-%m-%d')
            rec = dict(build_date=bdate, program=prog, serial=serial, so=so,
                       maxop_at_log=true_maxop(so,u[2]),
                       forecast_date=fdt, contract_date=(u[-1].strftime('%Y-%m-%d') if u[-1] else None),
                       actual_close=None, error_days=None)
            k=(bdate,serial)
            if k in idx: log[idx[k]].update(rec)
            else: log.append(rec); idx[k]=len(log)-1
    # backfill actuals for any logged unit now closed
    for r in log:
        cl = close_map.get(r['serial']) or close_map.get(r['so'])
        if cl and r.get('forecast_date'):
            r['actual_close']=cl.strftime('%Y-%m-%d') if hasattr(cl,'strftime') else str(cl)
            fd=DT.strptime(r['forecast_date'],'%Y-%m-%d').date()
            cld=cl if hasattr(cl,'toordinal') else DT.strptime(str(cl),'%Y-%m-%d').date()
            r['error_days']=(fd-cld).days
    json.dump(log, open(FORECAST_LOG,'w'), indent=2)
    return log

# close-date map (SO or serial -> date) for shipped units, used by the forward log backfill
CLOSE_MAP = {}
for prog,rows in SHIPPED.items():
    for (lab,so,commit,close,pack,fx) in rows:
        CLOSE_MAP[so]=close

# STATUS-BASED position (fresh 8/19): MAX_CLOSED op per SO from OPER_STATUS_CODE_DB=90.
# This REPLACES the clocking-based maxop, which was blind to NOWB ops (e.g. op3800
# Prep&Prime clocks to a different bucket) and lagged closed ops. Status codes are
# authoritative: 90=Closed(done), 85=In Process(current), 40=Released(upcoming).
# Position = MAX_CLOSED; the unit is working the first op AFTER this.
# (Stray low in-process ops like op50 are out-of-sequence rework noise — ignored.)
STATUS_MAXCLOSED = {
 # elevator (refreshed 2026-08-19 PM sweep)
 '1455596':3850,'1456550':3300,'1452748':3300,'1457061':2210,'1458317':1950,
 '1459236':1930,'1460167':1930,'1460758':1200,'1461523':None,
 '1452749':3750,'1456551':3400,'1457063':3030,'1458318':2110,'1460168':1910,
 '1459237':1550,'1460759':1300,'1461524':500,
 # radome (refreshed)
 '1453338':775,'1454081':770,'1453339':745,'1454080':630,'1449908':770,'1451436':720,
 '1458360':630,'1459009':530,'1460931':410,'1460451':410,'1460932':410,'1401814':695,
 '1456255':620,'1360294':570,
 # aegis reflector (530349)
 '1442037':240,'1450617':170,'1455178':240,'1457856':160,'1460448':155,
}

# last-clock per SO (fresh 2026-08-19 PM sweep); idle >7d (before 8/12) = STALLED
LAST_CLOCK = {
 # radome
 '1460931':d(8,19),'1460932':d(8,19),'1460451':d(8,19),'1459009':d(8,6),'1456255':d(8,17),
 '1454080':d(8,19),'1458360':d(8,19),'1401814':d(7,14),'1451436':d(8,19),
 '1453339':d(8,19),'1453338':d(8,19),'1449908':d(7,24),'1454081':d(8,14),'1360294':date(2024,2,20),
 # elevator LH
 '1452748':d(8,17),'1455596':d(8,19),'1456550':d(8,18),'1457061':d(8,17),'1458317':d(8,17),
 '1459236':d(8,17),'1460167':d(8,19),'1460758':d(8,19),
 # elevator RH
 '1452749':d(8,19),'1456551':d(8,19),'1457063':d(8,19),'1458318':d(8,19),'1460168':d(8,19),
 '1459237':d(8,17),'1460759':d(8,17),'1461524':d(8,19),
 # aegis reflector (idle>7d stalls: 176 8/05, 178 7/30)
 '1442037':d(8,5),'1450617':d(7,30),'1455178':d(8,18),'1457856':d(8,19),'1460448':d(8,16),
}
def is_stalled(so):
    lc=LAST_CLOCK.get(so)
    return lc is not None and (AS_OF.date()-lc).days>7

def true_maxop(so, fallback):
    """Position = status-based MAX_CLOSED op (authoritative), overriding the stale
    hardcoded clocking-based value. Falls back to the table value if SO not found."""
    return STATUS_MAXCLOSED.get(so, fallback)

def op_state(opno, maxop, commit_ms_date, forecast_dt):
    """Return (text, fill, fontcolor) for a cell.
    C rule: op < maxop => complete. op==maxop => in-work (highlight). op>maxop => upcoming.
    late vs on-time judged only at ship; here we mark done vs in-work vs upcoming."""
    if maxop is None:
        return ("", WHITE, INK)
    if opno < maxop:
        return ("C", GREEN, GREENK)
    if opno == maxop:
        return ("WIP", AMBER, AMBERK)
    return ("", ICE2, GREY)

def build_rows(ops, cures):
    """Return ordered list of display rows: ('op',opno,desc,wc,hr,ms) or ('cure',None,label,'',dwell,ms)
    or ('ms', code, name) milestone header."""
    cure_by_after={}
    for c in cures: cure_by_after.setdefault(c[0],[]).append(c)
    rows=[]; last_ms=None
    for (opno,desc,wc,hrs,ms) in ops:
        if ms!=last_ms:
            rows.append(("ms",ms,None,None,None,ms)); last_ms=ms
        rows.append(("op",opno,desc,wc,hrs,ms))
        for (_,clabel,dwell,cnote) in cure_by_after.get(opno,[]):
            kind = "gate" if clabel.startswith("GATE") else "cure"
            rows.append((kind,opno,clabel,"",dwell,ms))
    return rows

def project_unit(ops,cures,maxop,start_dt=AS_OF):
    """Run forward schedule; return (finish_dt, per_op_date{opno:dt}, per_cure_date{(opno,label):dt}).
    Each op's date = its scheduled START (when it needs to take place)."""
    sop = -1 if maxop is None else maxop
    rows=forward_schedule(ops,cures,sop,start_dt)
    op_dt={}; cure_dt={}
    for (opno,kind,desc,s,f,wc,hrs,ms) in rows:
        if kind=="labor": op_dt[opno]=s
        else: cure_dt[(desc)]=s   # cures keyed by label (unique enough)
    finish = rows[-1][4] if rows else start_dt
    return finish, op_dt, cure_dt

def forecast_finish(ops,cures,maxop):
    return project_unit(ops,cures,maxop)[0]

def remaining_cure_hours(cures, maxop):
    """Sum of cure/gate dwell hours still AHEAD of the unit's current op.
    These are physically unavoidable and were OMITTED from the ERP commit baseline."""
    if maxop is None:
        return sum(c[2] for c in cures)  # not started: full floor
    return sum(c[2] for c in cures if c[0] > maxop)

def total_cure_floor(cures):
    return sum(c[2] for c in cures)

wb=openpyxl.Workbook()

def build_tab(wsname, ops, cures, milestones, units, title, program, ship_key="FS", sim=None, shipped=None):
    ws=wb.create_sheet(wsname) if wsname not in wb.sheetnames else wb[wsname]
    ws.sheet_view.showGridLines=False
    shipped = shipped or []
    # ---- finite-capacity sim ----
    # If a pre-pooled sim dict is passed (e.g. elevator+Aegis sharing paint booth WC221),
    # use it. Otherwise run a single-program sim for this tab.
    if sim is None:
        sim_units=[dict(serial=u[0], so=u[1], maxop=true_maxop(u[1],u[2]), commit=u[-1], program=program)
                   for u in units if not is_stalled(u[1])]
        sim = simulate(sim_units, {program:ops}, {program:cures}, AS_OF)
    disp=build_rows(ops,cures)
    nlive=len(units); nship=len(shipped); ncols=nlive+nship
    # Title band
    ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=4+ncols)
    t=ws.cell(1,1,title); t.font=F(bold=True,size=15,color=WHITE); t.fill=PatternFill("solid",fgColor=NAVY)
    t.alignment=Alignment("left","center",indent=1); ws.row_dimensions[1].height=24
    ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=4+ncols)
    fl=total_cure_floor(cures)/24.0
    s=ws.cell(2,1,f"Return-to-Green Operation Tracker  •  AS-OF {AS_OF.strftime('%a %m/%d %H:%M')}  •  Contract = ERP commit (planned w/ ZERO cure; full build has {fl:.1f}d unavoidable cure floor).  Earliest = this unit's best case if worked alone.  Forecast = finite-capacity sim (shared paint booths).  Gap Earliest→Forecast = contention cost.  Δ = Forecast vs Contract.")
    s.font=F(italic=True,size=8,color=ICE); s.fill=PatternFill("solid",fgColor=BLUE); s.alignment=Alignment("left","center",indent=1)
    # legend row 3
    leg=ws.cell(3,1,"LEGEND:"); leg.font=F(bold=True,size=8,color=INK)
    for i,(txt,fill,fk) in enumerate([("C = done",GREEN,GREENK),("WIP = in work",AMBER,AMBERK),
                                       ("cure row",CUREFILL,CUREK),("GATE row",GATEFILL,GATEK),("upcoming",ICE2,GREY)]):
        cc=ws.cell(3,2+i,txt); cc.font=F(size=8,color=fk); cc.fill=PatternFill("solid",fgColor=fill); cc.alignment=Alignment("center","center"); cc.border=bd()
    # header rows: HDR=serial(SO), +1=Contract commit, +2=Achievable(commit+cure floor),
    #              +3=Forecast, +4=Δ vs Achievable, +5=col titles
    HDR=4
    ws.cell(HDR,1,"UNIT ->").font=F(bold=True,size=9,color=WHITE); ws.cell(HDR,1).fill=PatternFill("solid",fgColor=NAVY)
    ws.cell(HDR+1,1,"Contract commit").font=F(bold=True,size=8,color=WHITE); ws.cell(HDR+1,1).fill=PatternFill("solid",fgColor=BLUE)
    ws.cell(HDR+2,1,"Earliest possible").font=F(bold=True,size=8,color=WHITE); ws.cell(HDR+2,1).fill=PatternFill("solid",fgColor=BLUE)
    ws.cell(HDR+3,1,"Forecast (w/ contention)").font=F(bold=True,size=8,color=WHITE); ws.cell(HDR+3,1).fill=PatternFill("solid",fgColor=BLUE)
    ws.cell(HDR+4,1,"Δ vs contract").font=F(bold=True,size=8,color=WHITE); ws.cell(HDR+4,1).fill=PatternFill("solid",fgColor=BLUE)
    ws.cell(HDR+5,1,"Op #").font=F(bold=True,size=8,color=WHITE); ws.cell(HDR+5,1).fill=PatternFill("solid",fgColor=NAVY)
    ws.cell(HDR+5,2,"Operation / Cure").font=F(bold=True,size=8,color=WHITE); ws.cell(HDR+5,2).fill=PatternFill("solid",fgColor=NAVY)
    ws.cell(HDR+5,3,"WC").font=F(bold=True,size=8,color=WHITE); ws.cell(HDR+5,3).fill=PatternFill("solid",fgColor=NAVY)
    ws.cell(HDR+5,4,"Hrs/Dwell").font=F(bold=True,size=8,color=WHITE); ws.cell(HDR+5,4).fill=PatternFill("solid",fgColor=NAVY)
    for c in range(1,5):
        for r in range(HDR,HDR+6): ws.cell(r,c).border=bd(); ws.cell(r,c).alignment=Alignment("center","center")

    full_floor_h = total_cure_floor(cures)
    # per-unit columns
    unit_proj={}   # serial -> (op_dt, cure_dt, stalled, maxop)
    for j,u in enumerate(units):
        col=5+j
        serial=u[0]; so=u[1]; maxop=true_maxop(u[1],u[2]); commit=u[-1]
        stalled=is_stalled(so)
        if stalled:
            op_dt,cure_dt,fdt={},{},AS_OF
        else:
            sr=sim[serial]; fdt=sr['finish']; op_dt=sr['op_dt']; cure_dt=sr['cure_dt']
        unit_proj[serial]=(op_dt,cure_dt,stalled,maxop)
        # earliest-possible = single-unit projection (no contention): today + remaining
        # labor + remaining cures from current op. This is the physical floor for THIS unit.
        earliest = None if stalled else project_unit(ops,cures,maxop)[0]
        # header serial (SO)
        hlabel=f"{serial}\n({so})" + ("\n⚠STALLED" if stalled else "")
        h=ws.cell(HDR,col,hlabel); h.font=F(bold=True,size=8,color=(AMBER if stalled else WHITE))
        h.fill=PatternFill("solid",fgColor=(REDK if stalled else NAVY))
        h.alignment=Alignment("center","center",wrap_text=True); h.border=bd()
        # contract commit (ERP baseline — planned with zero cure)
        cc=ws.cell(HDR+1,col, commit.strftime('%m/%d') if commit else "—"); cc.font=F(size=8,color=INK); cc.alignment=Alignment("center","center"); cc.border=bd(); cc.fill=PatternFill("solid",fgColor=ICE)
        # earliest possible (single-unit, no contention)
        ec=ws.cell(HDR+2,col, earliest.strftime('%m/%d') if earliest else "—"); ec.font=F(size=8,color=GREY); ec.alignment=Alignment("center","center"); ec.border=bd(); ec.fill=PatternFill("solid",fgColor=ICE2)
        if stalled:
            lc=LAST_CLOCK.get(so); idle=(AS_OF.date()-lc).days if lc else 0
            fc=ws.cell(HDR+3,col, f"idle {idle}d"); fc.font=F(size=8,bold=True,color=REDK); fc.fill=PatternFill("solid",fgColor=RED)
            fc.alignment=Alignment("center","center"); fc.border=bd()
            dc=ws.cell(HDR+4,col,"—"); dc.font=F(size=8,color=REDK); dc.fill=PatternFill("solid",fgColor=RED); dc.alignment=Alignment("center","center"); dc.border=bd()
            continue
        # forecast (capacity-constrained, with time)
        fc=ws.cell(HDR+3,col, fdt.strftime('%m/%d %H:%M')); fc.alignment=Alignment("center","center"); fc.border=bd()
        # delta measured vs CONTRACT commit (operational: will it ship on the contract date)
        if commit:
            delta=(fdt.date()-commit).days
            dc=ws.cell(HDR+4,col, f"{'+' if delta>0 else ''}{delta}d")
            late = delta>0
            fc.font=F(size=8,bold=late,color=(REDK if late else GREENK)); fc.fill=PatternFill("solid",fgColor=(RED if late else GREEN))
            dc.font=F(size=8,bold=True,color=(REDK if late else GREENK)); dc.fill=PatternFill("solid",fgColor=(RED if late else GREEN))
        else:
            dc=ws.cell(HDR+4,col,"—"); fc.font=F(size=8,color=INK); dc.font=F(size=8,color=GREY)
        dc.alignment=Alignment("center","center"); dc.border=bd()

    # ---- SHIPPED units: retained as hidden accuracy-record columns ----
    # header block shows: Contract / (Forecast row = logged forecast) / (Earliest row reused
    # to show ACTUAL close) / Δ = logged-forecast error vs actual. Column tinted grey + hidden.
    SHIPHDR="595959"; SHIPTINT="D9D9D9"
    for k,(lab,so,commit,close,pack,fx) in enumerate(shipped):
        col=5+nlive+k
        h=ws.cell(HDR,col, f"{lab}\n({so})\nSHIPPED {close.strftime('%m/%d')}")
        h.font=F(bold=True,size=8,color=WHITE); h.fill=PatternFill("solid",fgColor=SHIPHDR)
        h.alignment=Alignment("center","center",wrap_text=True); h.border=bd()
        cc=ws.cell(HDR+1,col, commit.strftime('%m/%d') if commit else "—"); cc.font=F(size=8,color=INK); cc.fill=PatternFill("solid",fgColor=SHIPTINT); cc.alignment=Alignment("center","center"); cc.border=bd()
        # HDR+2 row label is "Earliest possible" -> for shipped, repurpose to ACTUAL ship
        ac=ws.cell(HDR+2,col, close.strftime('%m/%d')); ac.font=F(size=8,bold=True,color=INK); ac.fill=PatternFill("solid",fgColor=SHIPTINT); ac.alignment=Alignment("center","center"); ac.border=bd()
        # HDR+3 = the forecast the model logged ~1wk out
        fcv=ws.cell(HDR+3,col, fx.strftime('%m/%d')); fcv.font=F(size=8,color=INK); fcv.fill=PatternFill("solid",fgColor=SHIPTINT); fcv.alignment=Alignment("center","center"); fcv.border=bd()
        # HDR+4 = forecast error vs actual (neg = model was optimistic/early)
        err=(fx-close).days
        dc=ws.cell(HDR+4,col, f"{'+' if err>0 else ''}{err}d"); dc.font=F(size=8,bold=True,color=(REDK if err<0 else GREENK))
        dc.fill=PatternFill("solid",fgColor=(RED if err<0 else GREEN)); dc.alignment=Alignment("center","center"); dc.border=bd()

    # op/cure rows
    r=HDR+6
    for row in disp:
        kind=row[0]
        if kind=="ms":
            code=row[1]; name=dict(milestones).get(code,code)
            ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=4+ncols)
            mc=ws.cell(r,1,f"  ▸ {name.upper()}"); mc.font=F(bold=True,size=9,color=WHITE); mc.fill=PatternFill("solid",fgColor=MSFILL)
            mc.alignment=Alignment("left","center"); ws.row_dimensions[r].height=16
            r+=1; continue
        opno=row[1]; desc=row[2]; wc=row[3]; val=row[4]
        iscure = kind in ("cure","gate")
        # left labels
        a=ws.cell(r,1, "" if iscure else opno); a.font=F(size=8,color=INK); a.alignment=Alignment("center","center"); a.border=bd()
        b=ws.cell(r,2, desc); b.alignment=Alignment("left","center",indent=1); b.border=bd()
        cw=ws.cell(r,3, wc); cw.font=F(size=8,color=GREY); cw.alignment=Alignment("center","center"); cw.border=bd()
        hv=ws.cell(r,4, f"{val}h" if not iscure else f"{val}h dwell"); hv.font=F(size=8,color=GREY); hv.alignment=Alignment("center","center"); hv.border=bd()
        if iscure:
            fillc = GATEFILL if kind=="gate" else CUREFILL
            fk = GATEK if kind=="gate" else CUREK
            b.font=F(size=8,italic=True,bold=(kind=="gate"),color=fk)
            for c in range(1,5): ws.cell(r,c).fill=PatternFill("solid",fgColor=fillc)
        else:
            b.font=F(size=8,color=INK)
        # unit cells
        for j,u in enumerate(units):
            col=5+j; serial=u[0]
            op_dt,cure_dt,stalled,maxop=unit_proj[serial]
            cell=ws.cell(r,col); cell.border=bd(); cell.alignment=Alignment("center","center")
            if iscure:
                if maxop is not None and opno < maxop:
                    cell.value="C"; cell.fill=PatternFill("solid",fgColor=GREEN); cell.font=F(size=8,color=GREENK)
                elif stalled:
                    cell.value="—"; cell.fill=PatternFill("solid",fgColor=(GATEFILL if kind=="gate" else CUREFILL)); cell.font=F(size=7,color=GREY)
                else:
                    # projected cure/gate window: date + time-of-day
                    cdt=cure_dt.get(desc)
                    cell.value = cdt.strftime('%m/%d %H:%M') if cdt else ""
                    cell.fill=PatternFill("solid",fgColor=(GATEFILL if kind=="gate" else CUREFILL))
                    cell.font=F(size=7,italic=True,color=(GATEK if kind=="gate" else CUREK))
            else:
                if maxop is None:
                    # not started: show projected date for every op
                    pdt=op_dt.get(opno)
                    cell.value=pdt.strftime('%m/%d') if pdt else ""
                    cell.fill=PatternFill("solid",fgColor=ICE2); cell.font=F(size=7,color=GREY)
                elif opno<maxop:
                    cell.value="C"; cell.fill=PatternFill("solid",fgColor=GREEN); cell.font=F(size=8,color=GREENK)
                elif opno==maxop:
                    cell.value="WIP"; cell.fill=PatternFill("solid",fgColor=AMBER); cell.font=F(size=8,bold=True,color=AMBERK)
                elif stalled:
                    cell.value=""; cell.fill=PatternFill("solid",fgColor=ICE2)
                else:
                    # upcoming: projected date this op needs to take place
                    pdt=op_dt.get(opno)
                    cell.value=pdt.strftime('%m/%d') if pdt else ""
                    cell.fill=PatternFill("solid",fgColor=ICE2); cell.font=F(size=7,color=GREY)
        # shipped columns: entire routing is complete -> "C"
        for k in range(nship):
            col=5+nlive+k; cell=ws.cell(r,col); cell.border=bd(); cell.alignment=Alignment("center","center")
            cell.value="C"; cell.fill=PatternFill("solid",fgColor=GREEN); cell.font=F(size=8,color=GREENK)
        r+=1

    # widths
    ws.column_dimensions["A"].width=6; ws.column_dimensions["B"].width=30
    ws.column_dimensions["C"].width=6; ws.column_dimensions["D"].width=10
    for j in range(nlive): ws.column_dimensions[get_column_letter(5+j)].width=11
    for k in range(nship):
        cl=get_column_letter(5+nlive+k); ws.column_dimensions[cl].width=11
        ws.column_dimensions[cl].hidden=True   # shipped = collapsed by default, expandable/auditable
    ws.freeze_panes="E"+str(HDR+6)
    ws.row_dimensions[HDR].height=26
    return ws

# remove default sheet
if "Sheet" in wb.sheetnames: del wb["Sheet"]

def build_assumptions_tab():
    ws=wb.create_sheet("Methodology & Assumptions")
    ws.sheet_view.showGridLines=False
    ws.column_dimensions["A"].width=2
    ws.column_dimensions["B"].width=34
    ws.column_dimensions["C"].width=60
    ws.column_dimensions["D"].width=40
    r=1
    ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=4)
    t=ws.cell(r,2,"RTG OPERATION TRACKER — METHODOLOGY & ASSUMPTIONS")
    t.font=F(bold=True,size=15,color=WHITE); t.fill=PatternFill("solid",fgColor=NAVY)
    t.alignment=Alignment("left","center",indent=1); ws.row_dimensions[r].height=26
    r+=1
    ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=4)
    s=ws.cell(r,2,f"How each unit's Forecast is built  •  AS-OF {AS_OF.strftime('%a %m/%d/%Y')}  •  Read this before interpreting the board")
    s.font=F(italic=True,size=9,color=ICE); s.fill=PatternFill("solid",fgColor=BLUE); s.alignment=Alignment("left","center",indent=1)
    ws.row_dimensions[r].height=16
    r+=2

    def section(title):
        nonlocal r
        ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=4)
        c=ws.cell(r,2,f"  {title}"); c.font=F(bold=True,size=11,color=WHITE); c.fill=PatternFill("solid",fgColor=MSFILL)
        c.alignment=Alignment("left","center"); ws.row_dimensions[r].height=20; r+=1
    def rowline(label, detail, basis, fill=WHITE):
        nonlocal r
        lc=ws.cell(r,2,label); lc.font=F(bold=True,size=9,color=INK); lc.fill=PatternFill("solid",fgColor=fill); lc.alignment=Alignment("left","top",wrap_text=True,indent=1); lc.border=bd()
        dc=ws.cell(r,3,detail); dc.font=F(size=9,color=INK); dc.fill=PatternFill("solid",fgColor=fill); dc.alignment=Alignment("left","top",wrap_text=True,indent=1); dc.border=bd()
        bc=ws.cell(r,4,basis); bc.font=F(size=8,italic=True,color=GREY); bc.fill=PatternFill("solid",fgColor=fill); bc.alignment=Alignment("left","top",wrap_text=True,indent=1); bc.border=bd()
        ws.row_dimensions[r].height=max(28, 12*(1+max(len(detail),len(basis))//55)); r+=1
    def colheads():
        nonlocal r
        for j,h in enumerate(["Element","Method / Assumption","Basis / Source"]):
            c=ws.cell(r,2+j,h); c.font=F(bold=True,size=9,color=WHITE); c.fill=PatternFill("solid",fgColor=BLUE); c.alignment=Alignment("center","center"); c.border=bd()
        ws.row_dimensions[r].height=16; r+=1

    # ---- Shared methodology ----
    section("SHARED METHODOLOGY (both programs)")
    colheads()
    rowline("Unit position (% complete)",
            "Driven by IFS operation STATUS codes, not labor clocking. 90=Closed=done, 85=In Process=current op, 40=Released=upcoming. Position = highest Closed op.",
            "SO_OPER_DISPATCH_LIST_CFV.OPER_STATUS_CODE_DB. Fixes blind spot: 'NOWB' ops (e.g. Prep&Prime) clock to a separate bucket and are invisible to clocking-based detection.", ICE2)
    rowline("Cure / dwell time",
            "Cures (sealant, paint, oven) modeled as dedicated rows running 24/7 wall-clock (nights + weekends), consuming ZERO labor. Shown with date + time-of-day.",
            "MVA Work Instructions. NOTE: the IFS router has QUEUE_TIME=0 / MOVE_TIME=0 on every op — cure time is NOT in the ERP. This omission is the historic ship-miss root cause.", WHITE)
    rowline("Parallel cure gates",
            "The 24hr topcoat tape-test cure runs IN PARALLEL with downstream labor; it only gates final inspection if not yet elapsed — not a serial tail blocker.",
            "Verified from last-4-shipped units: final-insp -> pack are back-to-back. WI mandates the 24hr cure but crews work through it.", ICE2)
    rowline("Crew parallelism",
            "Finish-line ops (paint, seal, Cor Ban) get a crew boost (2 operators) — the shop swarms a unit to push it out. Main assembly runs at standard 1 operator.",
            "IFS router is CREW_SIZE=1 / serial on ALL ops (does not model reality). Verified 8/19: 2 painters live on Prep&Prime. Boost scoped to tail ops so far-out units don't over-accelerate.", WHITE)
    rowline("Finite capacity",
            "All WIP units compete for a shared per-work-center daily labor-hour budget, allocated in commit-date priority order. When a WC's day is exhausted, remaining units wait.",
            "Per-WC budgets = measured sustained utilization. Paint booths are the binding constraint (matches observed throughput).", ICE2)
    rowline("Working calendar",
            "Mon-Fri full shifts (~16 productive hr/day, 2 shifts); Saturday at 50%, Sunday at 25%. Cures ignore the calendar (run 24/7).",
            "2-shift pattern w/ rotating weekend OT.", WHITE)
    rowline("Stalled units",
            "Any unit with no clocking in 7+ days is flagged STALLED; its forecast is suppressed (shown as 'idle Nd') rather than projected as if actively worked.",
            "Prevents a hidden bow-wave: idle MRB/hold units re-entering the queue would steal capacity.", ICE2)
    rowline("Three dates per unit",
            "CONTRACT = firm ERP ship commit (unchanged). EARLIEST = single-unit best case if worked alone. FORECAST = capacity-constrained (with contention). Δ = Forecast vs Contract.",
            "Gap Earliest->Forecast = the cost of shared-resource contention. Earliest>Contract = the contract baseline was set without cure time.", WHITE)
    r+=1

    # ---- Elevator specifics ----
    section("ELEVATOR (Program 531335) — 72P5520501 LH / 72P5520502 RH")
    colheads()
    fe=total_cure_floor(ELEVATOR_CURES)/24.0
    rowline("Router", f"{len(ELEVATOR_OPS)} operations across 4 milestones (Assy Jig / Assembly 1 / Assembly 2 / Finish-Ship). Ref SO 1452748 (rev-2 routing).", "IFS SO_OPER_DISPATCH_LIST_CFV. Includes 5 real ops the prior board dropped as '(NOWB)' — notably op3800 Prep&Prime (30.5hr).", ICE2)
    rowline("Cure floor", f"{len(ELEVATOR_CURES)} cure/gate rows totaling {fe:.1f} calendar-days of unavoidable dwell over a full build. Dominated by 72hr fay seal + 32hr fillet/FIP/overcoat.", "MVA WI 4401 series. PS870 sealants (accelerated oven path); GMS4114 aero seal; topcoat 24hr QI gate.", WHITE)
    rowline("Paint bottleneck", "WC 221 (paint/prime/touch-up) ≈ 27 labor-hr/day, 2 booths. This is the elevator throttle — 2 units due the same week can't both clear it on time.", "Measured utilization Aug 4-19. 2 paint booths + 2 ovens (2-3 units each, so ovens not a constraint).", ICE2)
    rowline("Current pace", "≈ 2.2 days/unit (last 2 weeks). A config roll recently held work up; that effort is complete and the line is now at full rate.", "SHOP_ORD_CFV CLOSE_DATE, last-2wk window. Older data reflects the pre-config-roll slow period and is NOT representative.", WHITE)
    r+=1

    # ---- Radome specifics ----
    section("AERONOSE RADOME (Program C48178) — 3700ED0001-101")
    colheads()
    fr=total_cure_floor(RADOME_CURES)/24.0
    rowline("Router", f"{len(RADOME_OPS)} operations across 4 milestones (Lamination / Assembly / Paint / Ship). Ref SO 1453338.", "IFS SO_OPER_DISPATCH_LIST_CFV. LAM oven cures carried as MACH_RUN time.", ICE2)
    rowline("Cure floor", f"{len(RADOME_CURES)} cure/gate rows totaling {fr:.1f} calendar-days. Dominated by op775 Electrical Sealing 40hr min cure (Shore A gate).", "MVA WI 3700ED0001-101 ASSY/LAM. LAM skin/honeycomb oven cures ~6.5hr each + 8hr peel-ply gates.", WHITE)
    rowline("Bottleneck", "op775 electrical-seal (40hr cure, 1-2 stations) is the dominant radome dwell. Ovens are plentiful (not a constraint).", "WI-mandated 40hr polysulfide cure. Paint WC 236 ≈ 12 hr/day secondary throttle.", ICE2)
    rowline("Current pace", "≈ 4-7 days/unit and climbing as the program ramps to full-steam. Expect this to tighten over the next 2 weeks.", "SHOP_ORD_CFV CLOSE_DATE. Radome cadence lagged elevator; ramping now. Revisit in ~2 weeks.", WHITE)
    r+=1

    # ---- Calibration & refresh protocol ----
    section("CALIBRATION & REFRESH (run every time this workbook is updated)")
    colheads()
    rowline("1. Router re-review",
            "Pull the full op list + planned hours for each reference SO and diff against the model's router. Catch new / changed / dropped ops and routing-revision bumps.",
            "IFS SO_OPER_DISPATCH_LIST_CFV (elevator ref SO 1452748, radome ref SO 1453338). Watch especially for '(NOWB)' ops that clock elsewhere.", ICE2)
    rowline("2. Position refresh",
            "Re-pull each WIP unit's furthest-Closed operation to reset % complete.",
            "OPER_STATUS_CODE_DB = 90 (Closed) per SO. Do NOT use labor clocking (blind to NOWB ops).", WHITE)
    rowline("3. Cadence recalibration",
            "Recompute actual days/unit from recent ship closes and compare to the model's implied cadence; adjust the paint work-center budget if it has drifted.",
            "SHOP_ORD_CFV.CLOSE_DATE, recent window only. Widen the window (toward 4-6 wks) as full-steam data accrues past the config-roll distortion.", ICE2)
    rowline("4. Crew & cure spot-check",
            "Confirm the crew-swarm assumption against live clocking on the current push unit; re-verify cure floors against any Work-Instruction revisions.",
            "GD_SHOP_FLOOR_CLOCKING (open clockings on the near-ship unit) + MVA WI revs.", WHITE)
    rowline("5. Stall refresh",
            "Re-flag any unit with no clocking in 7+ days as STALLED and suppress its forecast.",
            "Last-clock date per SO.", ICE2)
    rowline("Why this matters",
            "The forecast is currently calibrated on a THIN 2-3 week window (a config roll recently held elevator work, then released it). Confidence grows as the recent-window sample grows; until then, treat far-out units as directional.",
            "User directive 8/19: full router review on every update.", AMBER)
    r+=1

    # ---- Known limitations ----
    section("KNOWN LIMITATIONS (what the model does NOT capture)")
    colheads()
    rowline("Rework / first-pass yield", "Assumes 100% first-pass yield. Composite defects (voids, delam, failed tape tests) and MRB loops are NOT modeled — every date is a best case.", "Add MRB history if a risk-adjusted view is needed.", ICE2)
    rowline("Skill-specific labor", "Labor pooled by work-center hours, not by certified individual. A specific-cert bottleneck (e.g. one bond tech) could halt a unit the pool-view can't see.", "", WHITE)
    rowline("Material / tooling", "Assumes parts, prepreg freezer-life, jigs and fixtures are available when labor is. Shortages not modeled.", "", ICE2)
    rowline("Far-out units", "Beyond the next 2-3 ships, forecasts assume the current burst rate holds. Treat far-dated units as directional, not committed.", "Sustained only if staffing/pace hold.", WHITE)

    ws.page_setup.orientation="portrait"; ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=0
    ws.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    return ws

ACCURACY = "C:/Users/ryan.c.miller/Downloads/rtg-tracker-build/accuracy_results.json"

def build_dashboard(pooled_sim, radome_sim):
    ws=wb.create_sheet("Dashboard")
    ws.sheet_view.showGridLines=False
    ws.column_dimensions["A"].width=2
    for c,wdt in zip("BCDEFGHIJ",[22,12,12,12,12,12,12,12,12]): ws.column_dimensions[c].width=wdt
    r=1
    ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=10)
    t=ws.cell(r,2,"RTG TRACKER — KPI DASHBOARD"); t.font=F(bold=True,size=16,color=WHITE)
    t.fill=PatternFill("solid",fgColor=NAVY); t.alignment=Alignment("left","center",indent=1); ws.row_dimensions[r].height=28; r+=1
    ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=10)
    s=ws.cell(r,2,f"AS-OF {AS_OF.strftime('%a %m/%d/%Y')}  •  Forecast accuracy, throughput, on-time delivery, and bottleneck load  •  Read the Methodology tab for how forecasts are built")
    s.font=F(italic=True,size=9,color=ICE); s.fill=PatternFill("solid",fgColor=BLUE); s.alignment=Alignment("left","center",indent=1); ws.row_dimensions[r].height=16; r+=2

    def band(txt):
        nonlocal r
        ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=10)
        c=ws.cell(r,2,f"  {txt}"); c.font=F(bold=True,size=12,color=WHITE); c.fill=PatternFill("solid",fgColor=MSFILL)
        c.alignment=Alignment("left","center"); ws.row_dimensions[r].height=22; r+=1
    def note(txt, fill=AMBER, fk=AMBERK):
        nonlocal r
        ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=10)
        c=ws.cell(r,2,txt); c.font=F(italic=True,size=8,color=fk); c.fill=PatternFill("solid",fgColor=fill)
        c.alignment=Alignment("left","top",wrap_text=True,indent=1); ws.row_dimensions[r].height=max(14,12*(1+len(txt)//120)); r+=1
    def hdrow(cells):
        nonlocal r
        for j,h in enumerate(cells):
            c=ws.cell(r,2+j,h); c.font=F(bold=True,size=8,color=WHITE); c.fill=PatternFill("solid",fgColor=BLUE)
            c.alignment=Alignment("center","center",wrap_text=True); c.border=bd()
        ws.row_dimensions[r].height=24; r+=1
    def datarow(cells, bold0=True, fills=None):
        nonlocal r
        for j,v in enumerate(cells):
            c=ws.cell(r,2+j,v); c.border=bd()
            c.font=F(size=8,bold=(bold0 and j==0),color=INK)
            c.fill=PatternFill("solid",fgColor=(fills[j] if fills else WHITE))
            c.alignment=Alignment("center" if j>0 else "left","center",indent=(1 if j==0 else 0))
        r+=1

    # ===== A. FORECAST ACCURACY =====
    band("A.  FORECAST ACCURACY  (does the model predict reality?)")
    acc=None
    if os.path.exists(ACCURACY):
        try: acc=json.load(open(ACCURACY))
        except Exception: acc=None
    if acc:
        note("HEADLINE:  "+acc.get('headline',''), fill=AMBER, fk=AMBERK)
        o=acc['overall']
        hdrow(["Backtest (vs physical ship)","MAE (days)","Bias (days)","Hit ±3d","Hit ±7d","n forecasts"])
        p=o['pack']
        datarow(["ALL PROGRAMS", f"{p['mae']}", f"{p['bias']:+g}", f"{p['hit3']}%", f"{p['hit7']}%", f"{p['n']} (n≈{o.get('n_units','?')} units)"],
                fills=[ICE, WHITE, (RED if (p['bias'] or 0)<-3 else GREEN), WHITE, WHITE, WHITE])
        # per program (ALL horizons)
        for row in acc['by_program_horizon']:
            if row['horizon']!='ALL': continue
            pk=row['pack']
            if not pk['n']: continue
            nm={'ELEV':'Elevator','RAD':'Radome','AEGIS':'Aegis'}.get(row['program'],row['program'])
            datarow([nm, f"{pk['mae']}", f"{pk['bias']:+g}", f"{pk['hit3']}%", f"{pk['hit7']}%", f"{pk['n']}"],
                    fills=[ICE2,WHITE,WHITE,WHITE,WHITE,WHITE])
        r+=1
        # horizon breakdown (how accuracy degrades with lead time)
        hdrow(["By lead time (Elevator)","MAE @7d","MAE @14d","MAE @21d","","Interpretation"])
        mae={}
        for row in acc['by_program_horizon']:
            if row['program']=='ELEV' and row['horizon'] in (7,14,21): mae[row['horizon']]=row['pack']['mae']
        datarow(["Forecast error grows w/ lead", f"{mae.get(7,'—')}", f"{mae.get(14,'—')}", f"{mae.get(21,'—')}","",
                 "closer in = tighter"], fills=[ICE2,GREEN,AMBER,RED,WHITE,WHITE])
        r+=1
        # per-unit auditable detail (7-day horizon rows only, non-excluded)
        hdrow(["Backtest unit (7d snap)","Pos @ snap","Projected","Actual pack","Error (d)","(neg=early)"])
        for u in acc['units']:
            if u.get('excluded') or u['horizon']!=7: continue
            e=u['err_vs_pack']
            datarow([u['unit'], str(u['maxop_S']), u['proj_finish'] or '—', u['pack_date'],
                     f"{e:+d}" if e is not None else '—', ''],
                    bold0=False, fills=[WHITE,WHITE,WHITE,WHITE,(RED if (e or 0)<0 else GREEN),WHITE])
        r+=1
        for cav in acc.get('caveats',[]):
            note("•  "+cav, fill=ICE2, fk=GREY)
    else:
        note("accuracy_results.json not found — run backtest_accuracy.py first.", fill=RED, fk=REDK)
    r+=1

    # ===== forward log (accrues) =====
    band("A2.  FORWARD ACCURACY LOG  (accrues honestly as units ship)")
    scored=[]
    if os.path.exists(FORECAST_LOG):
        try:
            fl=json.load(open(FORECAST_LOG))
            scored=[x for x in fl if x.get('error_days') is not None]
        except Exception: pass
    if scored:
        errs=[x['error_days'] for x in scored]
        n=len(errs); mae=round(sum(abs(e) for e in errs)/n,1); bias=round(sum(errs)/n,1)
        hdrow(["Forward log","MAE (days)","Bias (days)","Scored ships","",""])
        datarow(["Logged→shipped", f"{mae}", f"{bias:+g}", f"{n}","",""], fills=[ICE,WHITE,WHITE,WHITE,WHITE,WHITE])
    else:
        note("No forward-scored ships yet. Every build stamps a forecast; when a unit ships, its oldest open prediction is scored here. This is the un-gameable accuracy record — it fills in over the coming weeks.", fill=ICE2, fk=GREY)
    r+=2

    # ===== B. THROUGHPUT vs PLAN =====
    band("B.  THROUGHPUT vs PLAN  (~6/mo ≈ 1.4/wk target per program)")
    # weekly ship buckets from SHIPPED close dates (last ~6 wks)
    from collections import Counter
    def wk(dd): return (dd - timedelta(days=dd.weekday()))  # Monday of that week
    hdrow(["Program","Ships last 4 wks","Avg/wk","Target/wk","WIP count","Behind contract"])
    prog_units={'ELEV':ELEV,'RAD':RAD,'AEGIS':AEGIS}
    for prog,label in [('ELEV','Elevator'),('RAD','Radome'),('AEGIS','Aegis')]:
        ships=[s[3] for s in SHIPPED[prog] if (AS_OF.date()-s[3]).days<=28]
        n4=len(ships); avg=round(n4/4.0,1)
        wip=len(prog_units[prog])
        behind=sum(1 for u in prog_units[prog] if u[-1] and u[-1]<AS_OF.date() and not is_stalled(u[1]))
        pace_fill = GREEN if avg>=1.4 else (AMBER if avg>=1.0 else RED)
        datarow([label, str(n4), str(avg), "1.4", str(wip), str(behind)],
                fills=[ICE2, WHITE, pace_fill, WHITE, WHITE, (RED if behind>2 else AMBER if behind else GREEN)])
    note("Ships counted from genuine-production closes (last 4 wks). WIP = active tracked units. 'Behind contract' = live units past their contract commit date.", fill=ICE2, fk=GREY)
    r+=2

    # ===== C. ON-TIME DELIVERY =====
    band("C.  ON-TIME DELIVERY & LATENESS  (shipped vs contract commit)")
    hdrow(["Program","OTD %","Avg days late","Worst late","On-time ships","Total scored"])
    for prog,label in [('ELEV','Elevator'),('RAD','Radome'),('AEGIS','Aegis')]:
        rows=SHIPPED[prog]
        if not rows:
            datarow([label,"—","—","—","0","0"], fills=[ICE2,WHITE,WHITE,WHITE,WHITE,WHITE]); continue
        lates=[(s[3]-s[2]).days for s in rows if s[2]]
        ontime=sum(1 for L in lates if L<=0); tot=len(lates)
        otd=round(100*ontime/tot) if tot else 0
        avglate=round(sum(max(0,L) for L in lates)/tot,1) if tot else 0
        worst=max(lates) if lates else 0
        datarow([label, f"{otd}%", f"{avglate}", f"+{worst}d", str(ontime), str(tot)],
                fills=[ICE2, (GREEN if otd>=80 else AMBER if otd>=50 else RED), WHITE, WHITE, WHITE, WHITE])
    note("Recent-close window only. These units shipped 6-9 wks past contract — a known RTG backlog burn-down, not current-flow performance. The point is the TREND: lateness shrinking as the line catches up.", fill=AMBER, fk=AMBERK)
    r+=2

    # ===== D. BOTTLENECK / CAPACITY LOAD =====
    band("D.  BOTTLENECK / CAPACITY LOAD  (shared paint/oven demand vs available)")
    # WIP-by-milestone counts from current positions
    hdrow(["WIP by milestone","Elevator","Radome","Aegis","",""])
    def ms_of(prog, maxop):
        if maxop is None: return "LAM"
        mlist={'ELEV':[('AJ',1500),('A1',3000),('A2',3900),('FS',9999)],
               'RAD':[('LAM',300),('ASSY',700),('PAINT',780),('SHIP',9999)],
               'AEGIS':[('LAM',195),('ASSY',245),('PAINT',370),('SHIP',9999)]}[prog]
        for nm,thr in mlist:
            if maxop<=thr: return nm
        return "SHIP"
    from collections import defaultdict
    cnt=defaultdict(lambda: defaultdict(int))
    for prog,units in [('ELEV',ELEV),('RAD',RAD),('AEGIS',AEGIS)]:
        for u in units:
            if is_stalled(u[1]): cnt[prog]['STALLED']+=1; continue
            cnt[prog][ms_of(prog, true_maxop(u[1],u[2]))]+=1
    for stage in ['LAM','AJ','A1','A2','ASSY','PAINT','FS','SHIP','STALLED']:
        e=cnt['ELEV'].get(stage,0); rd=cnt['RAD'].get(stage,0); a=cnt['AEGIS'].get(stage,0)
        if e+rd+a==0: continue
        datarow([stage, str(e or ''), str(rd or ''), str(a or ''),"",""], fills=[ICE2,WHITE,WHITE,WHITE,WHITE,WHITE])
    r+=1
    # shared paint booth load (WC221 elevator+Aegis pooled) — count units due to hit paint in next 2 wks
    hdrow(["Shared constraint","Available/wk","Peak demand","Status","",""])
    datarow(["WC221 paint (elev+Aegis)", "~135 hr/wk", "binding", "elevator throttle","",""],
            fills=[ICE2,WHITE,AMBER,AMBER,WHITE,WHITE])
    datarow(["WC236 paint (radome)", "~60 hr/wk", "secondary", "op775 seal is 1° throttle","",""],
            fills=[ICE2,WHITE,WHITE,WHITE,WHITE,WHITE])
    note("Paint booths (WC221 elevator+Aegis pooled, WC236 radome) are the shared throttle. Two same-week units can't both clear paint on time — the finite-capacity sim allocates in commit-priority order; DPAS Aegis jumps when behind.", fill=ICE2, fk=GREY)

    ws.page_setup.orientation="portrait"; ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=0
    ws.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    return ws

build_assumptions_tab()

# ---- POOLED elevator + Aegis sim (share paint booth WC221 + ovens; Aegis DPAS-priority) ----
# Both programs compete for the same WC221/32678 capacity, so they MUST be simulated together.
# DPAS-behind Aegis units jump the shared queue (handled in capacity_engine priority sort).
pool_units=[]
for u in ELEV:
    if not is_stalled(u[1]):
        pool_units.append(dict(serial=u[0], so=u[1], maxop=true_maxop(u[1],u[2]), commit=u[-1], program='ELEV'))
for u in AEGIS:
    if not is_stalled(u[1]):
        pool_units.append(dict(serial=u[0], so=u[1], maxop=true_maxop(u[1],u[2]), commit=u[-1], program='AEGIS'))
pooled_sim = simulate(pool_units,
                      {'ELEV':ELEVATOR_OPS, 'AEGIS':AEGIS_OPS},
                      {'ELEV':ELEVATOR_CURES, 'AEGIS':AEGIS_CURES}, AS_OF)

build_tab("Elevator", ELEVATOR_OPS, ELEVATOR_CURES, ELEV_MILESTONES, ELEV,
          "G500 ELEVATOR — RTG OPERATION TRACKER  (Program 531335)", program="ELEV", sim=pooled_sim, shipped=SHIPPED['ELEV'])
build_tab("Aeronose", RADOME_OPS, RADOME_CURES, RAD_MILESTONES, RAD,
          "AERONOSE RADOME — RTG OPERATION TRACKER  (Program C48178)", program="RAD", shipped=SHIPPED['RAD'])
build_tab("Aegis", AEGIS_OPS, AEGIS_CURES, AEGIS_MILESTONES, AEGIS,
          "AEGIS REFLECTOR ANTENNA — RTG OPERATION TRACKER  (Program 530349, DPAS-rated)", program="AEGIS", sim=pooled_sim, shipped=SHIPPED['AEGIS'])

# ---- forward forecast log (append + backfill actuals) ----
radome_sim = simulate(
    [dict(serial=u[0],so=u[1],maxop=true_maxop(u[1],u[2]),commit=u[-1],program='RAD') for u in RAD if not is_stalled(u[1])],
    {'RAD':RADOME_OPS}, {'RAD':RADOME_CURES}, AS_OF)
_all_sim = dict(pooled_sim); _all_sim.update(radome_sim)
write_forecast_log(_all_sim, {'ELEV':ELEV,'RAD':RAD,'AEGIS':AEGIS}, CLOSE_MAP)

# ---- Dashboard (build last so sims exist, then move to FIRST tab) ----
build_dashboard(pooled_sim, radome_sim)
wb.move_sheet("Dashboard", -(wb.sheetnames.index("Dashboard")))  # to front

for w in wb.worksheets:
    if w.title=="Methodology & Assumptions": continue  # keep portrait
    w.page_setup.orientation="landscape"; w.page_setup.fitToWidth=1; w.page_setup.fitToHeight=0
    w.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)

wb.save(OUT)
print("SAVED", OUT)
print("Elevator units:", len(ELEV), " Radome units:", len(RAD), " Aegis units:", len(AEGIS))
