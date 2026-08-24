from datetime import datetime as DT, date
from routers import ELEVATOR_OPS, ELEVATOR_CURES
import capacity_engine as ce
from capacity_engine import simulate
AS_OF=DT(2026,8,19,12,0)
def d(m,dd): return date(2026,m,dd)
ELEV=[('LH 232','1455596',3850,d(8,21)),('LH 233','1456550',3300,d(8,28)),('LH 229','1452748',3300,d(9,4)),
('LH 234','1457061',2210,d(9,11)),('LH 235','1458317',1950,d(9,18)),('LH 236','1459236',1930,d(9,25)),
('LH 237','1460167',1930,d(10,2)),('LH 238','1460758',1100,d(10,9)),('LH 239','1461523',None,d(10,16)),
('RH 227','1452749',3750,d(8,21)),('RH 231','1456551',3400,d(8,28)),('RH 232','1457063',3010,d(9,4)),
('RH 233','1458318',2010,d(9,11)),('RH 235','1460168',1800,d(9,18)),('RH 234','1459237',1550,d(9,25)),
('RH 236','1460759',1300,d(9,25)),('RH 237','1461524',400,d(10,2))]
units=[dict(serial=s,so=so,maxop=mo,commit=c,program='ELEV') for s,so,mo,c in ELEV]
print("Tuning WC221 (paint) daily budget to hit ~6.6 days/unit:")
for paint in [27,18,12,9,6]:
    ce.WC_DAILY['221']=paint
    res=simulate(units,{'ELEV':ELEVATOR_OPS},{'ELEV':ELEVATOR_CURES},AS_OF)
    fins=sorted(res[s]['finish'] for s,_,_,_ in ELEV)
    span=(fins[-1]-fins[0]).days
    dpu=span/max(len(fins)-1,1)
    rh227=res['RH 227']['finish']
    print(f"  paint={paint:>3}hr/day -> {dpu:.1f} days/unit, last={fins[-1].strftime('%m/%d')}, RH227={rh227.strftime('%a %m/%d')}")
