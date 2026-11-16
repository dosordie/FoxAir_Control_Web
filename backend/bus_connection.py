"""One process-owned LTE socket, serialized with active operations.

Browser ownership uses a 90 second renewable lease; permanent mode is driven
by private server configuration. Background receiving never sends telegrams.
"""
from contextlib import contextmanager
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
_source=None


def wanted(mode,now=None):
    return mode=='permanent' or (mode=='browser' and (time.monotonic() if now is None else now)<_lease_until)


def lease():
    global _lease_until
    with _guard:_lease_until=time.monotonic()+90
    start()
    return status()


def status():
    with _guard:return {**_state,'lease_seconds':max(0,round(_lease_until-time.monotonic()))}


def observe(frames):
    with _guard:
        for frame in frames:
            slave,func,start,count,payload,*_=frame
            if func==16 and frame[9] == 'word-frame' and slave in (0,99):
                data=payload[1:]
                if len(data)!=count*2:continue
                now=time.time()
                for i in range(count):_words[start+i]=(int.from_bytes(data[i*2:i*2+2],'big'),now)
            _state['last_rx']=time.time()


def observed_words():
    with _guard:return {str(reg):{'raw':raw,'age_seconds':round(time.time()-stamp,1),'quality':'observed'} for reg,(raw,stamp) in _words.items()}


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
    global _entry,_source
    from backend.warmlink import WarmlinkSession
    if _entry and _entry[0]!=endpoint:close()
    if _source != endpoint:
        with _guard:_words.clear();_state["last_rx"]=None
        _source=endpoint
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
