"""Shared, bounded FC03 initialization from FoxAir_Control warmlink_worker.

Eight sequential 90-word blocks; first ambiguous response aborts the job. No
retries, no parallel scan per browser, no writes or standard/display traffic.
"""
import threading
import time

from backend.settings import warmlink_endpoint
from backend.warmlink import open_warmlink

BLOCKS=tuple((start,90) for start in (1001,1091,1181,1271,1361,1451,2001,2091))
_lock=threading.RLock()
_job={'status':'idle','completed':0,'total':len(BLOCKS),'error':None}
_source=None
_finished=0.0


def status():
    with _lock:
        if _source != warmlink_endpoint():return {'status':'idle','completed':0,'total':len(BLOCKS),'error':None}
        return dict(_job)


def _run(endpoint):
    global _finished
    try:
        with open_warmlink(endpoint) as client:
            for start,count in BLOCKS:
                if warmlink_endpoint()!=endpoint:raise ValueError('source changed')
                words=client.read_holding(start,count)
                if len(words)!=count:raise ValueError('incomplete read')
                with _lock:_job['completed']+=1
        with _lock:_job.update(status='complete',error=None)
    except (OSError,ValueError):
        with _lock:_job.update(status='partial' if _job['completed'] else 'error',
            error='LTE-Blockabfrage abgebrochen; bestätigte Teilwerte bleiben erhalten. Kein automatischer Wiederholungsversuch.')
    finally:
        with _lock:_finished=time.monotonic()


def start():
    global _source
    endpoint=warmlink_endpoint()
    if endpoint is None:raise ValueError('LTE-Anschluss noch nicht aktiviert')
    with _lock:
        if _job['status']=='running':return {**status(),'started':False}
        # A second tab shares the same recent scan; explicit future re-reads
        # remain possible without creating a per-browser train of bus traffic.
        if _source==endpoint and time.monotonic()-_finished<30:
            return {**status(),'started':False}
        _source=endpoint
        _job.update(status='running',completed=0,error=None)
        threading.Thread(target=_run,args=(endpoint,),daemon=True,name='lte-register-scan').start()
        return {**status(),'started':True}
