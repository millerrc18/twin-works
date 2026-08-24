from datetime import date
# Elevator closes (last 8wk): RH 6/30, LH/RH 8/03,8/06,8/06,8/13,8/14,8/15
elev=[('6/30'),('8/03'),('8/06'),('8/06'),('8/13'),('8/14'),('8/15')]
# Radome closes: 6/24,7/02,7/10,7/11,7/24,7/31,8/10,8/14
rad=[('6/24'),('7/02'),('7/10'),('7/11'),('7/24'),('7/31'),('8/10'),('8/14')]
def cad(dates, label, cutoff):
    dd=[date(2026,int(m),int(x)) for m,x in (s.split('/') for s in dates)]
    recent=[x for x in dd if x>=cutoff]
    if len(recent)<2: 
        print(f"{label}: <2 in window"); return
    span=(recent[-1]-recent[0]).days
    print(f"{label} since {cutoff.strftime('%m/%d')}: {len(recent)} units over {span}d = {span/(len(recent)-1):.1f} days/unit")
print("=== FULL 8 weeks ===")
cad(elev,'Elevator',date(2026,6,24)); cad(rad,'Radome',date(2026,6,24))
print("=== LAST 3 WEEKS (since 7/29) ===")
cad(elev,'Elevator',date(2026,7,29)); cad(rad,'Radome',date(2026,7,29))
print("=== LAST 2 WEEKS (since 8/05) ===")
cad(elev,'Elevator',date(2026,8,5)); cad(rad,'Radome',date(2026,8,5))
