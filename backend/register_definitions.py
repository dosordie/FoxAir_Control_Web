"""Reviewed MAIN addresses and block layouts from FoxAir_Control 34ce0ed.

These are transport definitions, not implicit write grants or Cloud candidates.
"""

LTE_INIT_BLOCKS = tuple(
    (start, 90) for start in (1001, 1091, 1181, 1271, 1361, 1451, 2001, 2091)
)
STANDARD_DASHBOARD_BLOCKS = (
    (1011, 1),
    (1030, 1),
    (1158, 1),
    (2012, 3),
    (2035, 14),
    (2072, 1),
    (2077, 1),
)
LTE_DASHBOARD_BLOCKS = ((1011, 20), (1158, 1), (2012, 66))
DASHBOARD_FIELDS = {
    "power": 1011,
    "mode": 2012,
    "flow": 2077,
    "tank": 2047,
    "outdoor": 2048,
    "return": 2045,
    "supply": 2046,
    "target": 1158,
    "base_target": 1158,
    "compressor_frequency": 2072,
    "silent": 1030,
}
