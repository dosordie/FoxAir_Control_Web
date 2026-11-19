"""Source-backed timer words and disable/parameters/enable readback barriers.

Schema: FoxAir_Control 34ce0ed cloud/operating_timer.py,
cloud/cloud_write_helpers.py and dialogs/timer_editor_dialog.py.
Requests contain complete raw baselines, never inferred defaults.
"""
from contextlib import contextmanager
from decimal import Decimal
import threading
import time

from backend.cloud_config import credentials
from backend.cloud_read import _reader, _cloud_lock, CloudError
from backend.cloud_state import merge, log_event
from backend.cloud_write import WriteValidationError, WriteConflictError
from backend.settings import warmlink_endpoint, standard_endpoint
from backend.rtu import open_rtu
from backend.warmlink import open_warmlink

SILENT = dict(zip(range(1244, 1250), ('Timer_Mute_On_En', 'TimerMuteOnHour', 'TimerMuteOnMinute', 'Timer_Mute_Off_En', 'TimerMuteOffHour', 'TimerMuteOffMinute')))
WEEKLY = {**{1256+i:f'KG{i+1}' for i in range(12)},1268:'KG13~KG28',1269:'KG29~KG44',1270:'KG45~KG60'}
OPERATING = {**{1281+(n-1)*7+i:f'M{n} {suffix}' for n in range(1,7) for i,suffix in enumerate(('Start','End','Hot Water Target','Heating Target','Cooling Target','Mode','Max. Power'))},1323:'M1_2 Enalbe',1324:'M3_4 Enalbe',1325:'M5_6 Enalbe'}
SCHEMAS = {'silent': SILENT, 'weekly': WEEKLY, 'operating': OPERATING}
_lock = threading.RLock()
_last_write = 0.0


def schema(kind):
    if kind not in SCHEMAS:
        raise WriteValidationError('Unbekanntes Zeitprogramm')
    return SCHEMAS[kind]


def scaled(reg):
    return 1281 <= reg <= 1322 and (reg-1281) % 7 in (2,3,4,6)


def mask(reg):
    return reg in (1268,1269,1270,1323,1324,1325)


def cloud_word(reg, value):
    if isinstance(value, bool) or value in (None, ''):
        raise WriteValidationError('Fehlender Timerwert')
    text = str(value).strip().replace(',', '.')
    if mask(reg) and len(text) == 16 and set(text) <= {'0','1'}:
        return int(text,2)
    try:
        number = Decimal(text) * (10 if scaled(reg) else 1)
        if not number.is_finite() or number != number.to_integral_value() or not -32768 <= number <= 65535:
            raise ValueError()
        return int(number) & 65535
    except (ValueError, ArithmeticError):
        raise WriteValidationError('Ungültiges Timerwort') from None


def validate(kind, values, expected=None):
    regs = schema(kind)
    if set(values) != {str(reg) for reg in regs}:
        raise WriteValidationError('Vollständige Timer-Ausgangswerte erforderlich')
    for key, word in values.items():
        if isinstance(word, bool) or not isinstance(word,int) or not 0 <= word <= 65535:
            raise WriteValidationError('Ganzzahliges 16-Bit-Timerwort erforderlich')
        reg = int(key)
        if expected is not None and expected.get(key) == word:
            continue
        if kind == 'silent':
            maximum = (1,23,59,1,23,59)[reg-1244]
            if word > maximum:
                raise WriteValidationError('Ungültige Silent-Zeit oder Freigabe')
        elif (kind == 'weekly' and reg < 1268) or (kind == 'operating' and reg < 1323 and (reg-1281)%7 in (0,1)):
            if word >> 8 > 23 or word & 255 > 59:
                raise WriteValidationError('Uhrzeit außerhalb 00:00–23:59')
        elif kind == 'operating' and reg < 1323:
            offset = (reg-1281)%7
            if offset in (2,3,4) and not 50 <= word <= 700:
                raise WriteValidationError('Timer-Sollwert außerhalb 5–70 °C')
            if offset == 5 and word not in (0,1,2,3,4,9):
                raise WriteValidationError('Unbekannte Timer-Betriebsart')
            if offset == 6 and word > 32767:
                raise WriteValidationError('Ungültige Timer-Leistungsgrenze')


def phases(kind, old, desired):
    """Disable only programs whose parameters change, preserve partner bytes."""
    schema(kind)
    interim = dict(old)
    changed = {int(key) for key in desired if desired[key] != old[key]}
    if kind == 'silent' and changed:
        for reg in (1244,1247): interim[str(reg)] = 0
    elif kind == 'weekly':
        for program in range(6):
            if any(1256+program*2+i in changed for i in (0,1)):
                reg, shift = 1268+program//2, 8*(program%2)
                interim[str(reg)] &= ~(128 << shift)
    elif kind == 'operating':
        for program in range(6):
            if any(1281+program*7+i in changed for i in range(7)):
                reg, shift = 1323+program//2, 8*(program%2)
                interim[str(reg)] &= ~(128 << shift)
    disable = {k:v for k,v in interim.items() if v != old[k]}
    flags = {1244,1247} if kind == 'silent' else {r for r in schema(kind) if mask(r)}
    parameters = {k:v for k,v in desired.items() if int(k) not in flags and v != old[k]}
    final = {k:v for k,v in desired.items() if int(k) in flags and v != interim[k]}
    # Explicit deactivations also run before parameters.
    for key in list(final):
        active = 1 if kind == 'silent' else 0x8080
        if not final[key] & active:
            disable[key] = final.pop(key)
    return [phase for phase in (disable,parameters,final) if phase]


@contextmanager
def connection(transport):
    from backend.transport_selection import allows
    if not allows(transport):
        raise WriteValidationError('Andere Verbindung ist global ausgewählt')
    if transport == 'cloud':
        account = credentials()
        with _cloud_lock:
            client = _reader()
            yield client, account
    elif transport == 'warmlink_raw':
        endpoint = warmlink_endpoint()
        if endpoint is None:
            raise WriteValidationError('LTE-Anschluss nicht eingerichtet')
        with open_warmlink(endpoint) as client:
            yield client, endpoint
    elif transport == 'standard_modbus':
        endpoint = standard_endpoint()
        if endpoint is None: raise WriteValidationError('Standard-Modbus nicht eingerichtet')
        with open_rtu(endpoint) as client:
            yield client, endpoint
    else:
        raise WriteValidationError('Verbindung unterstützt keine Timer')


def check_connection(transport, identity):
    if (credentials() if transport == 'cloud' else standard_endpoint() if transport == 'standard_modbus' else warmlink_endpoint()) != identity:
        raise WriteConflictError('Verbindung während der Timerprüfung geändert')


def read_words(kind, transport, client):
    regs = schema(kind)
    if transport == 'cloud':
        rows = client.read_codes(list(regs.values()))
        if any(code not in rows for code in regs.values()):
            raise WriteValidationError('Timer nicht vollständig lesbar; keine Vorgabewerte eingesetzt')
        return {str(reg):cloud_word(reg,rows[code].get('value')) for reg,code in regs.items()}
    first, last = min(regs),max(regs)
    words = client.read_holding(first,last-first+1)
    return {str(reg):words[reg-first] for reg in regs}


def wire_value(reg, word):
    return format(Decimal(word if word < 32768 else word-65536)/10,'f') if scaled(reg) else f'{word:016b}' if mask(reg) else str(word)


def cache_words(kind,transport,words,identity):
    if transport == 'cloud':
        merge({code:{'value':wire_value(reg,words[str(reg)])} for reg,code in schema(kind).items()},source=identity)


def read(kind, transport):
    schema(kind)
    if transport == 'display_modbus':
        from backend.display_bus import manager
        manager.lease()
        available = manager.values()
        if any(str(reg) not in available for reg in schema(kind)):
            raise WriteValidationError('Display-Zeitprogramm noch unvollständig; alle Werte vom Bus lesen')
        return {'values':{str(reg):available[str(reg)]['raw'] for reg in schema(kind)},'transport':transport,'kind':kind}

    with _lock, connection(transport) as (client, identity):
        words = read_words(kind,transport,client)
        check_connection(transport,identity)
        cache_words(kind,transport,words,identity)
        return {'values':words,'transport':transport,'kind':kind}


def check_target_limits(kind, desired, current, transport, client):
    if kind != 'operating': return
    # Same source-backed baseline bounds as R01/R02/R03. Only changed targets
    # need limits; unavailable unused programs are never filled with defaults.
    bounds = {2:(1176,'R36','R37'),3:(1164,'R10','R11'),4:(1162,'R08','R09')}
    for offset,(first,low_code,high_code) in bounds.items():
        targets=[desired[str(1281+n*7+offset)] for n in range(6)
                 if desired[str(1281+n*7+offset)] != current[str(1281+n*7+offset)]]
        if not targets: continue
        if transport == 'cloud':
            rows = client.read_codes([low_code,high_code])
            try:
                limits=[Decimal(str(rows[c]['value']))*10 for c in (low_code,high_code)]
            except (KeyError,ValueError,ArithmeticError):
                raise WriteValidationError('Timer-Sollwertgrenzen nicht lesbar') from None
        else: limits=client.read_holding(first,2)
        low,high=limits
        if not all(Decimal(v).is_finite() for v in limits) or not 50 <= low <= high <= 700 or any(not low <= value <= high for value in targets):
            raise WriteValidationError('Timer-Sollwert außerhalb der frisch gelesenen Grenzen')


def write(kind, transport, desired, expected):
    global _last_write
    validate(kind,desired,expected)
    # Baselines may contain unsupported values; they are compared, never applied.
    if set(expected) != set(desired):
        raise WriteValidationError('Timer-Ausgangswerte fehlen')
    with _lock, connection(transport) as (client, identity):
        if time.monotonic()-_last_write < 5:
            raise WriteConflictError('Nächster Timerauftrag frühestens nach fünf Sekunden')
        current = read_words(kind,transport,client)
        if current != expected:
            raise WriteConflictError('Timer wurde inzwischen geändert; neu lesen')
        check_target_limits(kind,desired,current,transport,client)
        check_connection(transport,identity)
        plan = phases(kind,current,desired)
        if not plan:
            return {'confirmed':True,'status':'unchanged','values':current}
        _last_write = time.monotonic()
        applied = 0
        for phase in plan:
            try:
                check_connection(transport,identity)
                if transport == 'cloud':
                    payload = {'appId':'16','param':[]}
                    for key, word in phase.items():
                        reg = int(key)
                        value = wire_value(reg,word)
                        payload['param'].append({'deviceCode':client.device_code,'protocolCode':schema(kind)[reg],'value':value})
                    reply = client._post('app/device/control?lang=en',payload,token=client.token)
                    if not client._ok(reply): raise CloudError('Timerauftrag abgelehnt')
                else:
                    for key, word in phase.items(): client.write_one(int(key),word)
                time.sleep(.8)
                fresh = read_words(kind,transport,client)
                check_connection(transport,identity)
                expected_step = {**current,**phase}
                if fresh != expected_step: raise ValueError('Timer-Readback abweichend')
                current = fresh
                cache_words(kind,transport,current,identity)
                applied += 1
                log_event('timer','Timerstufe per Readback bestätigt')
            except (OSError,ValueError,CloudError):
                log_event('timer-error','Timerauftrag gestoppt; keine Wiederholung, Freigaben können deaktiviert bleiben')
                return {'confirmed':False,'status':'unconfirmed','applied_phases':applied,
                        'message':'Timerauftrag nicht vollständig bestätigt. Nicht erneut senden; Werte neu lesen. Freigaben können deaktiviert geblieben sein.'}
        return {'confirmed':True,'status':'confirmed','values':current}
