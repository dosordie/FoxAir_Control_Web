"""Bounded, cached read-only WarmLink 3.5 observations from issue 7."""
from datetime import datetime,timedelta,timezone
import math
import secrets
import threading
import time

from backend.cloud_config import credentials
from backend.cloud_read import _reader,_cloud_lock,CloudError

ADDRESSES={'2045','2046','2047','2048','2078+9'}
_cache={}
_attempts={}
_lock=threading.RLock()
_details={}


def history_args(address,start,end,frequency,zone):
    if address not in ADDRESSES or frequency not in ('day','month') or zone!=1:
        raise ValueError('Unbekannte Historienadresse, Frequenz oder Zeitzone')
    try:
        first=datetime.strptime(start,'%Y-%m-%d %H:%M:%S')
        last=datetime.strptime(end,'%Y-%m-%d %H:%M:%S')
    except ValueError:
        raise ValueError('Datum im Format JJJJ-MM-TT HH:MM:SS erforderlich') from None
    if not first<last or last-first>timedelta(days=31):
        raise ValueError('Historienfenster muss größer null und höchstens 31 Tage sein')
    return {'address':address,'startTime':start,'endTime':end,'frequency':frequency,'timeZone':zone}


def request(kind,payload=None):
    payload=payload or {}
    endpoints={'history':'device/snapshot/listCollectData','ota':'app/device/ota/judgeUpgradeList',
               'metadata':'app/device/getControlDetailStatusByDeviceCode',
               'enum':'app/protocal/getEnumDataByDetailId'}
    if kind not in endpoints:raise ValueError('Unbekannte Cloud-Abfrage')
    with _lock,_cloud_lock:
        account=credentials()
        key=(account,kind,tuple(sorted(payload.items())))
        now=time.monotonic()
        old=_cache.get(key)
        if old and now-old[0]<300:return {**old[1],'cached':True}
        # Bound memory and request load for different history windows.
        attempt_key=(account,kind)
        if attempt_key in _attempts and now-_attempts[attempt_key]<10:
            raise ValueError('Nächste Cloud-Abfrage frühestens nach zehn Sekunden')
        if len(_attempts)>=64:_attempts.pop(next(iter(_attempts)))
        _attempts[attempt_key]=now
        client=_reader()
        body={'deviceCode':client.device_code,**payload}
        if kind=='metadata':
            body.update(pageIndex=1,pageSize=9999,paramName='',num='',protocalId=client.service_protocol())
        elif kind=='enum':
            detail=_details.get((account,payload.get('key')))
            if not detail:raise ValueError('Servicekatalog erneut laden; Eintrag ist nicht mehr verfügbar')
            body={'detailId':detail}
        reply=client._request_auth(endpoints[kind],body)
        if not client._ok(reply):raise CloudError('Cloud-Zusatzabfrage abgelehnt')
        obj=reply.get('objectResult')
        result={'checked_at':datetime.now(timezone.utc).isoformat(),'cached':False}
        if kind=='ota':
            if not isinstance(obj,list):raise CloudError('Unbekanntes OTA-Antwortschema')
            result.update(available=bool(obj),count=len(obj))
        elif kind=='metadata':
            if not isinstance(obj,dict) or not isinstance(obj.get('dataList'),list):raise CloudError('Unbekanntes Metadaten-Antwortschema')
            allowed=('address','num','content','dataValue','tranferUnit','rangeStart','rangeEnd')
            # Only opaque process-local references reach the browser, never the
            # manufacturer's detail/protocol IDs, account or device metadata.
            for key in list(_details):
                if key[0]==account:del _details[key]
            result['items']=[]
            for row in obj['dataList'][:500]:
                if not isinstance(row,dict):continue
                public={k:str(row[k])[:180] for k in allowed if k in row and isinstance(row[k],(str,int,float,bool))}
                if row.get('detailId') and isinstance(row['detailId'],(str,int)):
                    if len(_details)>=2000:_details.pop(next(iter(_details)))
                    reference=secrets.token_urlsafe(12)
                    _details[(account,reference)]=str(row['detailId'])
                    public['enum_key']=reference
                result['items'].append(public)
            for row in result['items']:
                if 'dataValue' in row:
                    try:
                        number=float(row['dataValue'])
                        if not math.isfinite(number) or abs(number)>1000000:row.pop('dataValue',None)
                    except ValueError:row.pop('dataValue',None)
            result['source']='Hersteller-Servicekatalog; keine bestätigten Zuordnungen oder Schreibrechte'
            result['count']=len(result['items'])
        elif kind=='enum':
            if not isinstance(obj,list):raise CloudError('Unbekanntes Enum-Antwortschema')
            allowed=('value','meaning','enMeaning','description','code','descriptionValue')
            result['items']=[{k:str(row[k])[:300] for k in allowed if isinstance(row.get(k),(str,int,float,bool))}
                             for row in obj[:100] if isinstance(row,dict)]
            result['count']=len(result['items'])
        else:
            if not isinstance(obj,dict) or not isinstance(obj.get('valueList'),list):raise CloudError('Unbekanntes Historien-Antwortschema')
            points=[]
            today=datetime.now(timezone(timedelta(hours=1))).date()
            for row in obj['valueList'][:2000]:
                if not isinstance(row,dict):continue
                try:
                    stamp=str(row['dateTime'])[:32]
                    parsed=datetime.fromisoformat(stamp)
                    parsed=parsed.replace(tzinfo=timezone(timedelta(hours=1))) if parsed.tzinfo is None else parsed.astimezone(timezone(timedelta(hours=1)))
                    stamp=parsed.isoformat()
                    value=float(row['addressValue'])
                    if not math.isfinite(value):continue
                except (KeyError,ValueError,TypeError):continue
                points.append({'time':stamp,'value':value,'incomplete':payload['address']=='2078+9' and parsed.date()==today})
            points.sort(key=lambda p:p['time'])
            result.update(points=points,address=payload['address'],unit='kWh' if payload['address']=='2078+9' else '°C',
                          title=str(obj.get('title') or '')[:160])
        if credentials()!=account:raise CloudError('Cloud-Konto während der Abfrage geändert')
        if len(_cache)>=64:_cache.pop(next(iter(_cache)))
        _cache[key]=(now,result)
        return result
