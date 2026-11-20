"""Temporary read-only mappings backed by desktop issue #185 (GL9 live evidence).

Remove after the pinned desktop exporter provides these confirmed aliases.
No interpretation or alias is assigned to the empty T_PWM_* candidates.
"""

EVIDENCE = "https://github.com/dosordie/FoxAir_Control/issues/185"
PUMP_REGISTERS = {2115: "2115", 2116: "2116"}


def supplement_catalog(rows):
    result = [dict(row) for row in rows]
    indexed = {row["code"]: row for row in result}
    for register, code in PUMP_REGISTERS.items():
        existing = indexed.get(code)
        if existing and existing.get("register") not in (None, register):
            raise ValueError("Conflicting confirmed pump mapping")
        if (
            existing
            and existing.get("confidence") == "confirmed"
            and existing.get("register") == register
        ):
            row = existing
        else:
            row = {
                **(existing or {}),
                "code": code,
                "register": register,
                "name": "UP PWM aktuell"
                if register == 2115
                else "PWM-Rückmeldung der UP",
                "kind": "live",
                "group": "T",
                "unit": "%",
                "confidence": "confirmed",
                "cloud_dataType": "DIGI1",
                "retry_when_empty": False,
                "mapping_source": EVIDENCE,
                "description": "GL9-Livevergleich 20.11.2026: numerischer Cloudcode entspricht MAIN. "
                + (
                    "Pumpen-PWM-Ausgang in Prozent."
                    if register == 2115
                    else "Lokales Mapping in Prozent; physikalische Feedback-Einheit nicht unabhängig cloudbestätigt."
                ),
            }
            if existing:
                result[result.index(existing)] = row
            else:
                result.append(row)
        row.update(
            write_allowed=False,
            write_code=None,
            write_values={},
            write_min=None,
            write_max=None,
        )
    return result
