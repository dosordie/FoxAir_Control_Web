"""One process-owned LTE socket, serialized with active operations.

Browser ownership uses a 90 second renewable lease; permanent mode is driven
by private server configuration. Background receiving never sends telegrams.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import socket
import threading
import time

_guard=threading.RLock()
_io=threading.RLock()
_entry=None
_lease_until=0.0
_thread=None
_state={'connected':False,'mode':'on_demand','error':None,'last_rx':None}
_words={}
_readings={}
_source=None


def select_source(endpoint):
    global _source
    with _guard:
        if _source != endpoint:
            _words.clear()
            _readings.clear()
            _state['last_rx']=None
            _source=endpoint


def record_read(endpoint, start, words):
    with _guard:
        if _source != endpoint:return
        now=time.time()
        for i,raw in enumerate(words):_readings[start+i]=(raw,now)


def public_value(reg):
    # Each 90-word packet starts with private identification/header words.
    from backend.catalog import load_registers
    starts=(1001,1091,1181,1271,1361,1451,2001,2091)
    if not any(start+10 <= reg < start+90 for start in starts):return False
    entry=load_registers().get(str(reg))
    return entry is not None and str(entry.get('type','')).upper() not in ('ASCII','BLOCK')


def register_values(endpoint):
    from backend.catalog import load_registers,format_raw,register_group
    with _guard:
        if endpoint is None or _source != endpoint:return {}
        observed=dict(_words);active=dict(_readings);connected=_state['connected']
    definitions=load_registers()
    result={}
    for reg in observed.keys()|active.keys():
        if not public_value(reg):continue
        raw,stamp=observed.get(reg,(None,0));quality='observed'
        if reg in active and active[reg][1]>=stamp:
            raw,stamp=active[reg];quality='fresh'
        if time.time()-stamp>300 or (quality=='observed' and not connected):quality='stale'
        value,unit=format_raw(raw,definitions[str(reg)])
        result[str(reg)]={'register':reg,'raw':raw,'value':value,'unit':unit,'quality':quality,
                          'timestamp':datetime.fromtimestamp(stamp,timezone.utc).isoformat(),'transport':'warmlink_raw',
                          'code':definitions[str(reg)].get('code') or '',
                          'name':definitions[str(reg)].get('name') or f'Register {reg}',
                          'group':register_group(definitions[str(reg)],str(reg))}
    return result


def wanted(mode,now=None):
    return mode=='permanent' or (mode=='browser' and (time.monotonic() if now is None else now)<_lease_until)


def lease():
    global _lease_until
    with _guard:_lease_until=time.monotonic()+90
    start()
    return status()


def status():
    with _guard:return {**_state,'lease_seconds':max(0,round(_lease_until-time.monotonic()))}


def observe(frames, endpoint=None):
    with _guard:
        if endpoint is not None and endpoint != _source:return
        for frame in frames:
            slave,func,start,count,payload,*_=frame
            if func==16 and frame[9] == 'word-frame' and slave in (0,99):
                data=payload[1:]
                if len(data)!=count*2:continue
                now=time.time()
                for i in range(count):_words[start+i]=(int.from_bytes(data[i*2:i*2+2],'big'),now)
            _state['last_rx']=time.time()


def observed_words():
    with _guard:return {str(reg):{'raw':raw,'age_seconds':round(time.time()-stamp,1),'quality':'observed'} for reg,(raw,stamp) in _words.items() if public_value(reg)}


def observed_metrics(fields, endpoint):
    """Decode only catalog-backed MAIN values from this configured source.

    A broadcast is an observation, never a write acknowledgement. Preserve its
    arrival timestamp so HTTP refreshes cannot make old bus data fresh again.
    """
    values=register_values(endpoint)
    def metric(reg):
        row=values.get(str(reg))
        return {k:row[k] for k in ('value','unit','raw','timestamp','quality')} if row else None
    result = {name: item for name, reg in fields.items() if (item := metric(reg)) is not None}
    selected = metric(2014)
    if selected and selected['quality'] != 'stale' and isinstance(selected['value'], (float, int)) and 5 <= selected['value'] <= 80:
        result['target'] = {**selected, 'source_code': '2014', 'label': 'Aktueller Wassersollwert'}
    elif 'target' in result:
        result['target'].update(source_code='R02', label='Heizungs-Basissollwert')
    return result


def bus_lock(endpoint):
    from backend.rtu import _bus_guard,_bus_locks
    with _bus_guard:return _bus_locks.setdefault((endpoint.host,endpoint.port),threading.Lock())


def close():
    global _entry
    if _entry:
        _entry[1].sock.close()
        _entry=None
    with _guard:_state['connected']=False


def connect(endpoint):
    global _entry
    from backend.warmlink import WarmlinkSession
    if _entry and _entry[0]!=endpoint:close()
    select_source(endpoint)
    if _entry is None:
        sock=socket.create_connection((endpoint.host,endpoint.port),timeout=endpoint.timeout)
        _entry=(endpoint,WarmlinkSession(sock,endpoint))
    with _guard:_state.update(connected=True,error=None)
    return _entry[1]


@contextmanager
def operation(endpoint):
    with _io, bus_lock(endpoint):
        client=connect(endpoint)
        try:yield client
        except (OSError,ValueError):
            close()
            raise
        finally:
            if client.poisoned:close()


def run():
    from backend.settings import warmlink_config,warmlink_endpoint
    from backend.cloud_state import log_event
    while True:
        endpoint=warmlink_endpoint()
        mode=warmlink_config().get('connection_mode','on_demand')
        with _guard:_state['mode']=mode
        previous=_entry[0] if _entry else None
        target=previous or endpoint
        if target is not None:
            lock=bus_lock(target)
            if not _io.acquire(timeout=.1):
                time.sleep(.15)
                continue
            if lock.acquire(timeout=.1):
                try:
                    if not endpoint or not wanted(mode) or (previous and endpoint!=previous):close()
                    if endpoint and wanted(mode):
                        client=connect(endpoint)
                        client.receive(.15)
                except (OSError,ValueError):
                    close()
                    with _guard:_state['error']='LTE-Verbindung unterbrochen; erneuter Verbindungsversuch'
                    log_event('lte-error','Dauerverbindung unterbrochen; kein Schreib-Retry')
                    time.sleep(2)
                finally:lock.release();_io.release()
            else:_io.release()
        time.sleep(.15)


def start():
    global _thread
    with _guard:
        if _thread is None or not _thread.is_alive():
            _thread=threading.Thread(target=run,daemon=True,name='lte-connection')
            _thread.start()
