from routers import ELEVATOR_CURES, RADOME_CURES
def floor(cures, name):
    tot=sum(c[2] for c in cures)
    print(f"{name}: {len(cures)} cure/gate rows, total dwell = {tot} hr = {tot/24:.1f} calendar days")
    for after,label,dwell,note in cures:
        print(f"   after op{after:>4}  {dwell:>4}h  {label}")
    return tot
e=floor(ELEVATOR_CURES,"ELEVATOR"); print()
r=floor(RADOME_CURES,"RADOME")
print(f"\nELEVATOR cure floor: {e/24:.1f} cal-days   RADOME cure floor: {r/24:.1f} cal-days")
