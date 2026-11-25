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
    (2035, 26),
    (2072, 1),
    (2077, 1),
    (2115, 1),
)
LTE_DASHBOARD_BLOCKS = ((1011, 20), (1158, 1), (2012, 66), (2115, 2))
DIAGNOSTIC_FIELDS = {
    "pump_feedback": 2116,
    "evaporator": 2049,
    "evi_in": 2063,
    "evi_out": 2064,
    "fan_one": 2074,
    "fan_two": 2075,
    "compressor_starts": 2023,
    "compressor_hours": 2032,
    "buffer_temperature": 2052,
    "low_pressure": 2069,
    "discharge_temperature": 2053,
    "suction_temperature": 2051,
}
DASHBOARD_FIELDS = {
    **DIAGNOSTIC_FIELDS,
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
    "electrical_power": 2054,
    "thermal_power": 2059,
    "cop": 2060,
    "pump_pwm": 2115,
}

# core/at_compensation.py in the reviewed desktop source. The 0 °C point
# shares MAIN 1235 with the linear offset; CP1-4 is not that point.
AT_CURVE_POINTS = (
    (-20, 1250),
    (-10, 1251),
    (-5, 1252),
    (0, 1235),
    (5, 1253),
    (10, 1254),
    (20, 1255),
)
