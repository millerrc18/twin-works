import json, datetime
from datetime import date, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import FormulaRule
from routers import ELEVATOR_OPS, RADOME_OPS, ELEV_MILESTONES, RAD_MILESTONES
from completion import ELEV_COMPLETION, RAD_COMPLETION
from actuals import ELEV_ACTUALS, RAD_ACTUALS

# completion marker values: "C" = complete on-time (green), "CL" = complete late (amber)
def block_verdict(block_code, unit_label, firm, actuals):
    """Return 'CL' if this milestone block finished after its firm date, else 'C'.
    firm: {code:date}; actuals: {label:{code:'YYYY-MM-DD'}}"""
    amap=actuals.get(unit_label,{})
    astr=amap.get(block_code)
    fdate=firm.get(block_code)
    if astr and fdate:
        adate=datetime.datetime.strptime(astr,"%Y-%m-%d").date()
        return "CL" if adate>fdate else "C"
    return "C"  # no data or milestone was pre-complete -> treat on-time

def apply_completion(op_dates, ops, label, compmap, firm, actuals):
    rule=compmap.get(label)
    if not rule: return op_dates
    # precompute verdict per block
    verds={}
    def mark(opno, block):
        op_dates[opno]=verds.setdefault(block, block_verdict(block,label,firm,actuals))
    if rule[0]=="ALL":
        for o in ops: mark(o[0],o[4])
        return op_dates
    _,cutoff,closed=rule
    for o in ops:
        opno=o[0]
        if opno<cutoff: mark(opno,o[4])
        elif opno==cutoff and closed: mark(opno,o[4])
    return op_dates

data = json.load(open(r"C:/Users/ryan.c.miller/Downloads/rtg-tracker-build/rtg_data.json"))
TODAY = date(2026,8,16)  # as-of anchor written into a cell; conditional format reads it

def pd(s): return datetime.datetime.strptime(s,"%Y-%m-%d").date() if s else None
def add_workdays(start,n):
    d=start; step=1 if n>=0 else -1; left=abs(int(round(n)))
    while left>0:
        d+=timedelta(days=step)
        if d.weekday()<5: left-=1
    return d
def workdays_between(a,b):
    if a>b: a,b=b,a
    n=0; d=a
    while d<b:
        d+=timedelta(days=1)
        if d.weekday()<5: n+=1
    return n

def compute_op_dates(ops, mcodes, firm):
    codes=[c for c,_ in mcodes]
    block_ops={c:[o for o in ops if o[4]==c] for c in codes}
    block_hrs={c:sum(o[3] for o in block_ops[c]) for c in codes}
    ends={c:firm.get(c) for c in codes}
    result={}; prev_end=None
    for i,c in enumerate(codes):
        end=ends[c]; ops_c=block_ops[c]
        if end is None:
            for o in ops_c: result[o[0]]="C"
            continue
        if prev_end is not None: start=prev_end
        else:
            nxt=None
            for j in range(i+1,len(codes)):
                if ends[codes[j]]: nxt=ends[codes[j]]; break
            span=max(1,workdays_between(end,nxt)) if nxt else 5
            start=add_workdays(end,-span)
        total=block_hrs[c] or 1.0; wd=max(1,workdays_between(start,end)); cum=0.0
        for o in ops_c:
            cum+=o[3]; dt=add_workdays(start,(cum/total)*wd)
            if dt>end: dt=end
            result[o[0]]=dt
        if ops_c: result[ops_c[-1][0]]=end
        prev_end=end
    return result

# ---- palette ----
NAVY="16243D"; BLUE="24406B"; STEEL="2E5496"; ICE="EAF0FA"; ROW1="FFFFFF"; ROW2="F4F7FC"
CTXT="1F1F1F"; SUBT="C9D6EC"; SHIPTXT="FFE08A"
GREEN="C6EFCE"; GREENTXT="1E6B2E"; RED="FFC7CE"; REDTXT="9C0006"; AMBER="FFE9A8"; AMBERTXT="8A6100"
MS_FILL={"AJ":"2E5496","A1":"33608F","A2":"3C6FA3","FS":"4B82BC",
         "LAM":"2E5496","ASSY":"33608F","PAINT":"3C6FA3","SHIP":"4B82BC"}
thin=Side(style="thin",color="C6CFDD"); medium=Side(style="medium",color="1F3A63")
def bd(l=thin,r=thin,t=thin,b=thin): return Border(left=l,right=r,top=t,bottom=b)
F=lambda **k: Font(name="Aptos", **k)

ASOF_CELL="B3"  # holds the as-of date used by conditional formatting

def build_tab(ws, title, subtitle, ops, milestones, groups, compmap=None, actuals=None):
    """groups: list of (group_label_or_None, [units]) ; units={label,firm}. group_label None = no divider."""
    NL=4                      # left cols: Op#, Operation, WC, Hrs
    fdc=NL+1                  # first data col
    # flatten units + insert divider columns between groups
    layout=[]                 # list of ("unit",unitdict) or ("div",label)
    for gi,(glabel,units) in enumerate(groups):
        if gi>0: layout.append(("div",glabel))
        for u in units: layout.append(("unit",u))
    ncols=len(layout)
    total_cols=NL+ncols

    # ---------- title ----------
    ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=total_cols)
    t=ws.cell(1,1,title); t.font=F(bold=True,size=18,color="FFFFFF")
    t.fill=PatternFill("solid",fgColor=NAVY); t.alignment=Alignment("left","center",indent=1)
    ws.row_dimensions[1].height=30

    # ---------- subtitle + as-of + legend ----------
    ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=total_cols)
    s=ws.cell(2,1,subtitle); s.font=F(italic=True,size=10,color=SUBT)
    s.fill=PatternFill("solid",fgColor=BLUE); s.alignment=Alignment("left","center",indent=1)
    ws.row_dimensions[2].height=17

    # row 3: as-of + legend strip
    ws.cell(3,1,"AS-OF:").font=F(bold=True,size=9,color="FFFFFF")
    ws.cell(3,1).fill=PatternFill("solid",fgColor=NAVY); ws.cell(3,1).alignment=Alignment("right","center")
    a=ws.cell(3,2,TODAY); a.number_format="m/d/yy"; a.font=F(bold=True,size=9,color="FFF2CC")
    a.fill=PatternFill("solid",fgColor=NAVY); a.alignment=Alignment("center","center")
    # legend chips in cols 3..NL and beyond
    leg=[("C = Done on-time",GREEN,GREENTXT),("Done LATE",AMBER,AMBERTXT),("Upcoming",ROW1,CTXT),("PAST DUE",RED,REDTXT)]
    for i,(txt,fill,tc) in enumerate(leg):
        col=3+i
        lc=ws.cell(3,col,txt); lc.font=F(bold=True,size=8,color=tc)
        lc.fill=PatternFill("solid",fgColor=fill); lc.alignment=Alignment("center","center")
        lc.border=bd()
    # fill remainder of row3 navy
    for col in range(3+len(leg), total_cols+1):
        ws.cell(3,col).fill=PatternFill("solid",fgColor=NAVY)
    ws.row_dimensions[3].height=16

    # ---------- header block rows 4(unit) 5(ship) 6(titles) ----------
    r_unit,r_ship,r_title=4,5,6
    ws.merge_cells(start_row=r_unit,start_column=1,end_row=r_unit,end_column=NL)
    c=ws.cell(r_unit,1,"OPERATION   /   UNIT  →"); c.font=F(bold=True,size=10,color="FFFFFF")
    c.fill=PatternFill("solid",fgColor=NAVY); c.alignment=Alignment("center","center")
    ws.merge_cells(start_row=r_ship,start_column=1,end_row=r_ship,end_column=NL)
    csl=ws.cell(r_ship,1,"FIRM SHIP DATE  →"); csl.font=F(bold=True,size=9,color=SHIPTXT)
    csl.fill=PatternFill("solid",fgColor=BLUE); csl.alignment=Alignment("right","center",indent=1)
    for idx,(kind,obj) in enumerate(layout):
        col=fdc+idx
        if kind=="div":
            for rr in (r_unit,r_ship):
                dcell=ws.cell(rr,col); dcell.fill=PatternFill("solid",fgColor=NAVY)
            lab=ws.cell(r_unit,col, obj or "")
            lab.font=F(bold=True,size=9,color="FFF2CC"); lab.alignment=Alignment("center","center",text_rotation=90)
            ws.merge_cells(start_row=r_unit,start_column=col,end_row=r_ship,end_column=col)
            continue
        u=obj
        cu=ws.cell(r_unit,col,u["label"]); cu.font=F(bold=True,size=9,color="FFFFFF")
        cu.fill=PatternFill("solid",fgColor=STEEL); cu.alignment=Alignment("center","center",text_rotation=0)
        cu.border=bd(t=medium)
        sd=u["firm"].get(milestones[-1][0])
        cs=ws.cell(r_ship,col, sd if sd else None); cs.number_format="m/d"
        cs.font=F(bold=True,size=9,color=SHIPTXT); cs.fill=PatternFill("solid",fgColor=BLUE)
        cs.alignment=Alignment("center","center"); cs.border=bd(b=medium)
    for i,h in enumerate(["Op #","Operation","WC","Hrs"]):
        cc=ws.cell(r_title,1+i,h); cc.font=F(bold=True,size=9,color="FFFFFF")
        cc.fill=PatternFill("solid",fgColor=NAVY); cc.alignment=Alignment("center","center"); cc.border=bd()
    for idx,(kind,obj) in enumerate(layout):
        col=fdc+idx
        hc=ws.cell(r_title,col,"" if kind=="div" else "req'd")
        hc.font=F(size=7,italic=True,color="B7C4DB"); hc.fill=PatternFill("solid",fgColor=NAVY)
        hc.alignment=Alignment("center","center"); hc.border=bd()
    ws.row_dimensions[r_unit].height=16; ws.row_dimensions[r_ship].height=15; ws.row_dimensions[r_title].height=13

    # precompute unit dates
    ud=[]
    for kind,obj in layout:
        if kind!="unit": ud.append(None); continue
        od=compute_op_dates(ops,milestones,obj["firm"])
        if compmap is not None: od=apply_completion(od,ops,obj["label"],compmap,obj["firm"],actuals or {})
        ud.append(od)

    row=r_title+1
    data_first_row=row
    for code,name in milestones:
        ws.merge_cells(start_row=row,start_column=1,end_row=row,end_column=total_cols)
        hc=ws.cell(row,1,f"   {name.upper()}"); hc.font=F(bold=True,size=11,color="FFFFFF")
        hc.fill=PatternFill("solid",fgColor=MS_FILL[code]); hc.alignment=Alignment("left","center",indent=1)
        ws.row_dimensions[row].height=19; row+=1
        block=[o for o in ops if o[4]==code]
        for k,o in enumerate(block):
            opno,desc,wc,hrs,_=o
            zeb=ROW2 if (k%2==1) else ROW1
            a=ws.cell(row,1,opno); a.alignment=Alignment("center","center"); a.font=F(size=8,color="4A4A4A")
            b=ws.cell(row,2,desc); b.alignment=Alignment("left","center",indent=1); b.font=F(size=9,color=CTXT)
            cc=ws.cell(row,3,wc); cc.alignment=Alignment("center","center"); cc.font=F(size=8,color="7A7A7A")
            dd=ws.cell(row,4,hrs); dd.number_format="0.0"; dd.alignment=Alignment("center","center"); dd.font=F(size=8,color="7A7A7A")
            for cx in range(1,NL+1):
                ws.cell(row,cx).fill=PatternFill("solid",fgColor=zeb); ws.cell(row,cx).border=bd()
            for idx,(kind,obj) in enumerate(layout):
                col=fdc+idx; cell=ws.cell(row,col)
                if kind=="div":
                    cell.fill=PatternFill("solid",fgColor="DCE3F0"); cell.border=bd(); continue
                v=ud[idx].get(opno)
                if v=="C":
                    cell.value="C"; cell.font=F(bold=True,size=9,color=GREENTXT)
                    cell.fill=PatternFill("solid",fgColor=GREEN)
                elif v=="CL":
                    cell.value="C"; cell.font=F(bold=True,size=9,color=AMBERTXT)
                    cell.fill=PatternFill("solid",fgColor=AMBER)
                elif isinstance(v,date):
                    cell.value=v; cell.number_format="m/d"; cell.font=F(size=9,color=CTXT)
                    cell.fill=PatternFill("solid",fgColor=zeb)
                else:
                    cell.fill=PatternFill("solid",fgColor=zeb)
                cell.alignment=Alignment("center","center"); cell.border=bd()
            ws.row_dimensions[row].height=14.5; row+=1
    data_last_row=row-1

    # ---------- conditional formatting ----------
    # data range (dates only). "C" cells already green (static). For date cells:
    #   PAST DUE (red)  : date < as-of  (op should've finished, not marked done)
    #   AMBER           : as-of <= date <= as-of+3
    #   (else stays plain = on/ahead)
    first_col_letter=get_column_letter(fdc); last_col_letter=get_column_letter(total_cols)
    rng=f"{first_col_letter}{data_first_row}:{last_col_letter}{data_last_row}"
    tl=f"{first_col_letter}{data_first_row}"  # top-left for relative formula
    asof="$B$3"
    # 1) typed "C" -> green on-time  [highest priority]
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=[f'EXACT({tl},"C")'],
        fill=PatternFill("solid",fgColor=GREEN), font=Font(name="Aptos",color=GREENTXT,bold=True),
        stopIfTrue=True))
    # 2) typed "L" -> amber done-late
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=[f'EXACT({tl},"L")'],
        fill=PatternFill("solid",fgColor=AMBER), font=Font(name="Aptos",color=AMBERTXT,bold=True),
        stopIfTrue=True))
    # 3) past due: a date < as-of (not yet done)
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=[f'AND(ISNUMBER({tl}),{tl}<{asof})'],
        fill=PatternFill("solid",fgColor=RED), font=Font(name="Aptos",color=REDTXT,bold=True)))
    # 4) upcoming within 3 days -> light amber warn
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=[f'AND(ISNUMBER({tl}),{tl}>={asof},{tl}<={asof}+3)'],
        fill=PatternFill("solid",fgColor="FFF3C4"), font=Font(name="Aptos",color=AMBERTXT)))

    # ---------- widths / freeze / print ----------
    ws.column_dimensions["A"].width=5.5; ws.column_dimensions["B"].width=33
    ws.column_dimensions["C"].width=6.5; ws.column_dimensions["D"].width=6
    for idx,(kind,_) in enumerate(layout):
        w=2.6 if kind=="div" else 6.6
        ws.column_dimensions[get_column_letter(fdc+idx)].width=w
    ws.freeze_panes=f"{first_col_letter}{data_first_row}"
    ws.sheet_view.showGridLines=False
    ws.print_title_rows=f"1:{r_title}"; ws.print_title_cols="A:D"
    ws.page_setup.orientation="landscape"; ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=0
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_margins.left=ws.page_margins.right=0.2; ws.page_margins.top=ws.page_margins.bottom=0.35

def mk_units(rows,mcodes):
    us=[]
    for r in rows:
        if r["unit"] is None: continue
        firm={mcodes[0]:pd(r["m1"]),mcodes[1]:pd(r["m2"]),mcodes[2]:pd(r["m3"]),mcodes[3]:pd(r["m4"])}
        lbl=r["unit"] if isinstance(r["unit"],str) else f"{int(r['unit'])}"
        us.append({"label":lbl,"firm":firm})
    return us

wb=openpyxl.Workbook()
ws_e=wb.active; ws_e.title="Elevator"
ec=[c for c,_ in ELEV_MILESTONES]
lh=mk_units(data["lh"],ec); rh=mk_units(data["rh"],ec)
build_tab(ws_e,"G500 ELEVATOR  —  531335",
          "Return-to-Green Operation Tracker   •   Firm customer ship dates are committed   •   Each cell = required operation-finish date to hold ship",
          ELEVATOR_OPS, ELEV_MILESTONES, [("LH",lh),("RH",rh)], compmap=ELEV_COMPLETION, actuals=ELEV_ACTUALS)

ws_a=wb.create_sheet("Aeronose")
rc=[c for c,_ in RAD_MILESTONES]
rad=mk_units(data["rad"],rc)
build_tab(ws_a,"AERONOSE RADOME  —  C48178",
          "Return-to-Green Operation Tracker   •   Firm customer ship dates are committed   •   Each cell = required operation-finish date to hold ship",
          RADOME_OPS, RAD_MILESTONES, [("RADOME",rad)], compmap=RAD_COMPLETION, actuals=RAD_ACTUALS)

out=r"C:/Users/ryan.c.miller/Downloads/RTG Operation Tracker 2026.xlsx"
wb.save(out); print("saved",out)
