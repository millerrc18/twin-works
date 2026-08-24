# IFS op-completion sweep as of 2026-08-16.
# Rule: ops with op_no < cutoff => C ; op_no == cutoff => C only if maxop_closed.
# Fully shipped/closed units => ALL ops C ("ALL").
# Units not released (no SO) => no completion (all future dates).

# key = unit label as it appears on the tracker (e.g. "LH 229", "508")
# value = ("cutoff", op_no, closed_bool)  OR  ("ALL",)  OR  None

ELEV_COMPLETION = {
    # closed / shipped
    "LH 228": ("ALL",), "LH 230": ("ALL",), "LH 231": ("ALL",),
    "RH 226": ("ALL",), "RH 228": ("ALL",), "RH 230": ("ALL",),
    # started
    "LH 229": ("cutoff",3215,True),
    "LH 232": ("cutoff",3800,False),
    "LH 233": ("cutoff",3230,True),
    "LH 234": ("cutoff",2300,False),
    "LH 235": ("cutoff",1930,True),
    "LH 236": ("cutoff",1930,True),
    "LH 237": ("cutoff",1800,True),
    "LH 238": ("cutoff",1000,False),
    "RH 227": ("cutoff",3400,False),
    "RH 229": ("cutoff",1450,False),
    "RH 231": ("cutoff",3300,False),
    "RH 232": ("cutoff",2750,True),
    "RH 233": ("cutoff",2050,False),
    "RH 234": ("cutoff",1300,True),
    "RH 235": ("cutoff",1600,False),
    "RH 236": ("cutoff",1000,False),
}

RAD_COMPLETION = {
    # shipped
    "373": ("ALL",),
    # started
    "508": ("cutoff",775,False),
    "509": ("cutoff",780,False),
    "511": ("cutoff",695,False),
    "513": ("cutoff",775,False),
    "514": ("cutoff",730,False),
    "515": ("cutoff",775,False),
    "516": ("cutoff",630,False),
    "517": ("cutoff",625,False),
    "518": ("cutoff",590,False),
    "519": ("cutoff",575,False),
    "520": ("cutoff",570,False),
    "521": ("cutoff",450,False),
    "522": ("cutoff",250,True),
    "523": ("cutoff",290,True),
    # stale repair-buffer units (2024-25), real value-add cutoff (ignore 9998 hold)
    "355": ("cutoff",650,True),
    "358": ("cutoff",650,True),
    "361": ("cutoff",570,True),
    "397": ("cutoff",580,True),
    "430": ("cutoff",697,False),
    "460": ("cutoff",570,True),
}
