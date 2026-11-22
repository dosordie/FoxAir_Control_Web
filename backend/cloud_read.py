"""PHNIX / Linked-Go cloud reader with source-validated full-catalog support.

Protocol format is based on the existing FoxAir_Control cloud/warmlink_api.py.
Only source-catalog codes are sent. Credentials and access tokens never leave
the server. The only control payload permitted is the reviewed app heartbeat.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

from backend.cloud_config import credentials
import urllib.error
import urllib.request
from typing import Any

from backend.catalog import load_registers
from backend.cloud_mapping_overrides import PUMP_REGISTERS

API_ROOT = "https://cloud.linked-go.com:449/crmservice/api"
_TIMEOUT = 12
_cloud_lock = threading.RLock()
_client: "CloudReader | None" = None
_client_key: tuple[str, str, str] | None = None

# Confirmed FoxAir_Control mappings. Additional cloud mappings are added
# only after confirmation with the upstream register/code resolver.
CLOUD_REGISTERS: dict[int, str] = {
    **PUMP_REGISTERS,  # GL9 live-confirmed numeric aliases: FoxAir_Control#185.
    1011: "Power",
    2012: "ModeState",
    2047: "T08",
    2048: "T04",
    2077: "T39",
    2035: "T40",
    2036: "T41",
    2045: "T01",  # Main water inlet/return, not AC branch T40
    2046: "T02",  # Main water outlet/supply, not AC branch T41
    2014: "2014",  # Firmware-selected temperature setpoint (not R02 base)

    1158: "R02",
    1030: "H22",
    2054: "2054",
    2059: "2059",
    2060: "2060",
    2072: "T31",  # Actual compressor frequency, not T30 requested frequency
}

DASHBOARD_MAPPING = {
    "power": 1011,
    "mode": 2012,
    "flow": 2077,
    "tank": 2047,
    "outdoor": 2048,
    "return": 2045,
    "supply": 2046,
    "target": 1158,
    "selected_target": 2014,
    "compressor_frequency": 2072,
    "silent": 1030,
    "electrical_power": 2054,
    "thermal_power": 2059,
    "cop": 2060,
    "pump_pwm": 2115,
}


class CloudError(RuntimeError):
    """Fixed/sanitized error text only. Never embed credential or server body."""


class UnsupportedCloudCode(CloudError):
    """Only raised when provider explicitly rejects a code as unsupported."""


def cloud_configured() -> bool:
    return all(credentials())


def cloud_settings() -> tuple[str, str, str]:
    result = credentials()
    if not all(result):
        raise CloudError("PHNIX-Cloud noch nicht eingerichtet")
    return result


class CloudReader:
    def __init__(self, username: str, password: str, device_code: str):
        self.username = username
        self.password = password
        self.device_code = device_code
        self.token: str | None = None
        self.login_method: str | None = None
        self.last_heartbeat: float = 0.0
        self._service_devices: dict[str, dict[str, str]] = {}

    def _post(self, endpoint: str, body: dict[str, Any], *, token: str | None = None,
              method: str = "POST") -> dict[str, Any]:
        endpoints = ("app/user/login", "app/device/getDataByCode", "app/user/getUserInfo",
                     "app/device/deviceList", "app/device/getDeviceStatus",
                     "house/info/listOwnerHouses", "houseRelDevice/v4/selectHouseToDeviceData",
                     "app/device/control", "app/device/control?lang=en",
                     "device/snapshot/listCollectData", "app/device/ota/judgeUpgradeList",
                     "app/device/getControlDetailStatusByDeviceCode",
                     "app/device/queryDeviceById", "app/product/queryProductById",
                     "app/protocal/getEnumDataByDetailId", "app/device/ai/getAiInfoByDeviceCode")
        if endpoint not in endpoints or method not in ("GET", "POST"):
            raise CloudError("Cloud-Endpunkt nicht zugelassen")
        content = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{API_ROOT}/{endpoint}",
            data=content if method == "POST" else None,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json;charset=utf-8",
                "User-Agent": "FoxAir-Control-Web/0.1",
                **({"x-token": token} if token else {}),
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                if response.status != 200:
                    raise CloudError("Cloud-HTTP-Fehler")
                if int(response.headers.get("Content-Length", "0") or 0) > 262144:
                    raise CloudError("Cloud-Antwort zu groß")
                data = json.loads(response.read(262145))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise CloudError("Cloud-Zugriff abgelehnt") from None
            if exc.code in (400, 422) and endpoint == "app/device/getDataByCode":
                # Desktop client isolates invalid candidates for HTTP 4xx
                # responses too. Keep provider text internal, never log it.
                try:
                    raw = json.loads(exc.read(8192).decode("utf-8"))
                    if isinstance(raw, dict):
                        raw["http_status"] = exc.code
                        return raw
                except (OSError, ValueError, UnicodeDecodeError):
                    pass
            raise CloudError("Cloud-HTTP-Fehler") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CloudError("Cloud-Netzwerkfehler oder Timeout") from None
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise CloudError("Ungültige Cloud-Antwort") from None
        if not isinstance(data, dict):
            raise CloudError("Unerwartete Cloud-Antwort")
        return data

    @staticmethod
    def _ok(response: dict[str, Any]) -> bool:
        return bool(
            response.get("isReusltSuc") or
            response.get("isResultSuc") or
            response.get("success")
        )

    @staticmethod
    def _expired(response: dict[str, Any]) -> bool:
        code = str(response.get("error_code") or response.get("code") or "")
        message = str(response.get("error_msg") or response.get("message") or "").lower()
        return code in {"401", "-100"} or ("login" in message and "again" in message)

    def login(self) -> None:
        md5 = hashlib.md5(self.password.encode("utf-8")).hexdigest()
        variants = {
            "md5": (md5, False),
            "md5md5": (hashlib.md5(md5.encode("utf-8")).hexdigest(), False),
            "plain": (self.password, False),
            "md5+app": (md5, True),
            "md5md5+app": (hashlib.md5(md5.encode("utf-8")).hexdigest(), True),
            "plain+app": (self.password, True),
        }
        # As in FoxAir_Control; re-use last successful method to minimize requests.
        order = ([self.login_method] if self.login_method else []) + list(variants)
        for method in dict.fromkeys(order):
            pw, extended = variants[method]
            payload: dict[str, Any] = {"userName": self.username, "password": pw}
            if extended:
                payload.update({"loginSource": "app", "areaCode": "", "appId": "16",
                                "type": "2", "lang": "en"})
            result = self._post("app/user/login", payload)
            obj = result.get("objectResult")
            if self._ok(result) and isinstance(obj, dict):
                token = obj.get("x-token") or obj.get("token") or obj.get("xToken")
                if token and isinstance(token, str):
                    self.token = token
                    self.login_method = method
                    from backend.cloud_state import log_event
                    log_event("auth", "Cloud-Anmeldung erfolgreich")
                    return
        from backend.cloud_state import log_event
        log_event("error", "Cloud-Anmeldung abgelehnt")
        raise CloudError("Cloud-Anmeldung fehlgeschlagen (Zugangsdaten prüfen)")

    def _request_auth(self, endpoint: str, payload: dict[str, Any],
                      *, method: str = "POST") -> dict[str, Any]:
        """Post one known cloud request, with one authentication renewal."""
        if not self.token:
            self.login()
        try:
            response = self._post(endpoint, payload, token=self.token) if method == "POST" else self._post(
                endpoint, payload, token=self.token, method="GET")
        except CloudError as exc:
            if str(exc) != "Cloud-Zugriff abgelehnt":
                raise
            self.token = None
            self.login()
            response = self._post(endpoint, payload, token=self.token) if method == "POST" else self._post(
                endpoint, payload, token=self.token, method="GET")
        if self._expired(response):
            self.token = None
            self.login()
            response = self._post(endpoint, payload, token=self.token) if method == "POST" else self._post(
                endpoint, payload, token=self.token, method="GET")
        return response

    def app_heartbeat(self) -> bool:
        """Known operational freshness trigger (not a general control endpoint).

        From FoxAir_Control live polling RE: app_heartbeat=23205, no appId,
        settle 1s before reading live codes. Never used for a static read or
        during initial UI visit. Throttled across concurrent web clients.
        """
        now = time.monotonic()
        if self.last_heartbeat and now - self.last_heartbeat < 25:
            return False
        self.last_heartbeat = now   # Even a failed call must be rate limited.
        try:
            response = self._request_auth("app/device/control", {
                "param": [{
                    "deviceCode": self.device_code,
                    "protocolCode": "app_heartbeat",
                    "value": "23205",
                }],
            })
            if self._ok(response):
                time.sleep(1.0)
                return True
        except CloudError:
            # Do not make an incidental telemetry refresh fail because the
            # cloud rejects a nonessential heartbeat.
            pass
        return False

    def device_status(self) -> dict[str, Any]:
        """Optional selected-device status, without raw identifiers or secrets."""
        response = self._request_auth(
            "app/device/getDeviceStatus", {"deviceCode": self.device_code},
        )
        if not self._ok(response):
            raise CloudError("Cloud-Gerätestatus nicht verfügbar")
        obj = response.get("objectResult")
        if not isinstance(obj, dict):
            return {}
        # Conservative allowlist; never return serials, SIM IDs, tokens or nested trees.
        fields = (
            "deviceStatus", "isFault", "dtuSignalIntensity", "dtuSoftwareVer",
            "deviceName", "deviceNickName", "model", "custModel",
            "onlineState", "deviceOnline", "lastOnlineTime",
        )
        return {k: obj[k] for k in fields if k in obj and
                (obj[k] is None or isinstance(obj[k], (str, int, float, bool)))}

    @staticmethod
    def _device_fields(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = (
            "deviceCode", "deviceNickName", "deviceName", "model", "custModel",
            "deviceStatus", "isFault", "dtuSoftwareVer", "dtuSignalIntensity",
            "isShared", "houseName", "houseRoleType", "discoverySource",
        )
        rows: dict[str, dict[str, Any]] = {}
        for raw in devices:
            if not isinstance(raw, dict):
                continue
            code = str(raw.get("deviceCode") or "").strip()
            if not code:
                continue
            row = rows.setdefault(code, {"deviceCode": code})
            for key in allowed:
                val = raw.get(key)
                if isinstance(val, (str, int, float, bool)) and (key not in row or row[key] in ("", None)):
                    row[key] = val
        return list(rows.values())

    def devices(self) -> list[dict[str, Any]]:
        """Merge deviceList and house/room listings as in FoxAir_Control."""
        from backend.cloud_state import log_event
        path = Path(__file__).resolve().parents[1] / "data" / "warmlink_product_ids.json"
        product_ids = json.loads(path.read_text(encoding="utf-8"))["product_ids"]
        collected: list[dict[str, Any]] = []
        errors = 0

        def items_from(response: dict[str, Any]) -> list[dict[str, Any]]:
            obj = response.get("objectResult")
            if isinstance(obj, list):
                return [v for v in obj if isinstance(v, dict)]
            if isinstance(obj, dict):
                for key in ("records", "list", "rows", "data"):
                    val = obj.get(key)
                    if isinstance(val, list):
                        return [v for v in val if isinstance(v, dict)]
                if obj.get("deviceCode"):
                    return [obj]
            return []

        try:
            response = self._request_auth("app/device/deviceList", {
                "productIds": product_ids, "pageIndex": "1", "pageSize": "999",
            })
            if self._ok(response):
                collected.extend(items_from(response))
            else:
                errors += 1
                log_event("warn", "Cloud-Geräteliste hat keine gültige Antwort geliefert")
        except CloudError:
            errors += 1
            log_event("warn", "Cloud-Geräteliste nicht erreichbar")

        # Mirrors desktop's house discovery; deviceList alone is incomplete
        # for shared devices. Owner/room metadata is stripped to a safe allowlist.
        try:
            houses = self._request_auth("house/info/listOwnerHouses", {}, method="GET")
            if self._ok(houses):
                for house in items_from(houses)[:30]:
                    house_id = str(house.get("id") or house.get("houseId") or "").strip()
                    if not house_id:
                        continue
                    try:
                        data = self._request_auth("houseRelDevice/v4/selectHouseToDeviceData", {
                            "appId": 16, "houseId": house_id, "level": 0,
                        })
                    except CloudError:
                        errors += 1
                        continue
                    obj = data.get("objectResult")
                    if not self._ok(data) or not isinstance(obj, dict):
                        continue
                    areas = obj.get("data")
                    if not isinstance(areas, list):
                        continue
                    for area in areas:
                        if not isinstance(area, dict):
                            continue
                        direct = area.get("houseRelDeviceList") or []
                        for device in direct:
                            if isinstance(device, dict):
                                collected.append({**device, "houseName": house.get("houseName", "")})
                        for room in area.get("roomInfoResultList") or []:
                            if not isinstance(room, dict):
                                continue
                            for device in room.get("houseRelDeviceList") or []:
                                if isinstance(device, dict):
                                    collected.append({**device, "houseName": house.get("houseName", "")})
        except CloudError:
            errors += 1
            log_event("warn", "Cloud-Hausliste nicht erreichbar")

        # These internal IDs are used only for read-only protocol discovery.
        # Do not add them to the public device-field allowlist.
        self._service_devices = {}
        for row in collected:
            if isinstance(row,dict) and row.get('deviceCode'):
                self._service_devices.setdefault(str(row['deviceCode']),{}).update(
                    {key:str(row[key]) for key in ('deviceId','productId') if row.get(key)})
        result = self._device_fields(collected)
        log_event("device", "Cloud-Geräteübersicht gelesen", count=len(result))
        if not result and errors:
            raise CloudError("Cloud-Geräteübersicht unvollständig: Geräteliste/Hausliste fehlgeschlagen")
        return result

    def service_protocol(self) -> str:
        """Follow the captured device -> product -> protocol lookup privately."""
        self.devices()
        source = self._service_devices.get(self.device_code, {})
        device_id = source.get('deviceId')
        if not device_id:
            raise CloudError('Interne Cloud-Gerätezuordnung fehlt')
        reply = self._request_auth('app/device/queryDeviceById', {'deviceId':device_id})
        device = reply.get('objectResult')
        if not self._ok(reply) or not isinstance(device,dict) or device.get('deviceCode') != self.device_code:
            raise CloudError('Cloud-Gerätezuordnung nicht bestätigt')
        product_id = device.get('productId')
        if not product_id or (source.get('productId') and str(product_id) != source['productId']):
            raise CloudError('Cloud-Produktzuordnung nicht bestätigt')
        reply = self._request_auth('app/product/queryProductById', {'id':str(product_id)})
        product = reply.get('objectResult')
        if not self._ok(reply) or not isinstance(product,dict):
            raise CloudError('Cloud-Produktinformationen nicht verfügbar')
        if product.get('productId') is not None and str(product['productId']) != str(product_id):
            raise CloudError('Cloud-Produktzuordnung geändert')
        protocol = product.get('protocalId')
        if not isinstance(protocol,(str,int)) or isinstance(protocol,bool) or not str(protocol).strip():
            raise CloudError('Hersteller-Protokollkennung fehlt')
        return str(protocol)

    def read_codes(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        from backend.cloud_state import catalog
        allowlist = {r["code"] for r in catalog()} | set(CLOUD_REGISTERS.values())
        codes = list(dict.fromkeys(codes))
        if not codes or len(codes) > 50 or any(code not in allowlist for code in codes):
            raise CloudError("Cloud-Code nicht im geprüften Katalog")
        response = self._request_auth(
            "app/device/getDataByCode",
            {"deviceCode": self.device_code, "protocalCodes": codes},
        )
        if not self._ok(response):
            # Only split batches on explicitly unsupported codes. Never bisect
            # transient HTTP, auth, network or rate-limit errors.
            message = str(response.get("error_msg") or response.get("message") or "").lower()
            status = str(response.get("http_status") or response.get("status") or "")
            markers = ("unsupported", "not support", "invalid code", "unknown code",
                       "protocol code", "protocal code", "parameter code")
            if status not in ("401", "429", "500", "502", "503", "504") and any(
                item in message for item in markers
            ):
                raise UnsupportedCloudCode("Cloud-Code von API nicht unterstützt")
            raise CloudError("Cloud-Leseabfrage abgelehnt")
        raw = response.get("objectResult")
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = next((raw[k] for k in ("data", "list", "records", "rows")
                          if isinstance(raw.get(k), list)), [raw])
        else:
            raise CloudError("Cloud lieferte keine lesbaren Werte")

        output: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or item.get("protocalCode")
                       or item.get("protocolCode") or item.get("name") or "").strip()
            if not code and len(item) == 1:
                code, value = next(iter(item.items()))
            else:
                value = item.get("value", item.get("dataValue", item.get("val", item.get("currentValue"))))
            if code not in codes or value in (None, "") or item.get("supported") is False:
                continue
            if not isinstance(value, (str, int, float, bool)):
                continue
            # API usually supplies engineering values. Do not apply the local
            # Modbus raw /10 conversion to a Cloud value a second time.
            meta = {key: item[key] for key in
                    ("unit", "dataType", "rangeStart", "rangeEnd")
                    if key in item and isinstance(item[key], (str, int, float))}
            output[code] = {"value": value, **meta}
        return output


def _reader() -> CloudReader:
    global _client, _client_key
    params = cloud_settings()
    if _client is None or params != _client_key:
        _client = CloudReader(*params)
        _client_key = params
    return _client


def optional_dashboard_codes():
    from backend.cloud_state import catalog
    from backend.register_definitions import DIAGNOSTIC_FIELDS
    from backend.routes.overview import settings

    layout = settings()
    keys = set(layout["mobile"]) | set(layout["desktop"])
    wanted = {register: key for key, register in DIAGNOSTIC_FIELDS.items() if key in keys}
    if not wanted:
        return {}
    definitions = load_registers()
    options = {}
    for entry in catalog():
        register = entry.get("register")
        if register not in wanted or entry.get("confidence") != "confirmed":
            continue
        key = wanted[register]
        code = entry["code"]
        if key not in options or code == definitions.get(str(register), {}).get("code"):
            options[key] = code
    return options


def read_dashboard(*, live: bool = False) -> dict[str, Any]:
    from backend.cloud_state import live_codes, merge, log_event
    from backend.device_name import refresh_name
    optional_codes = optional_dashboard_codes()
    with _cloud_lock:
        client = _reader()
        refresh_name(client)
        if live:
            client.app_heartbeat()
        codes = list(dict.fromkeys([CLOUD_REGISTERS[r] for r in DASHBOARD_MAPPING.values()]
                                    + list(optional_codes.values()) + (live_codes() if live else [])))
        values: dict[str, dict[str, Any]] = {}
        for offset in range(0, len(codes), 50):
            chunk = codes[offset:offset+50]
            try:
                values.update(client.read_codes(chunk))
            except UnsupportedCloudCode:
                # A previously confirmed live code may no longer be supported
                # after a firmware change: keep dashboard readable.
                for code in chunk:
                    try:
                        values.update(client.read_codes([code]))
                    except CloudError:
                        pass
    merge(values)
    log_event("live" if live else "read", "Cloud-Livewerte aktualisiert" if live
              else "Cloud-Übersicht gelesen", count=len(values))
    output = project_dashboard(values)
    for key, code in optional_codes.items():
        row = values.get(code)
        if row and row.get('value') is not None:
            output[key] = {**row, 'raw': None, 'quality': row.get('quality', 'fresh')}
    return output


def cached_dashboard() -> dict[str, Any]:
    from backend.cloud_state import cached_raw_values
    return project_dashboard(cached_raw_values(), stale=True)


def project_dashboard(values: dict[str, dict[str, Any]],
                      *, stale: bool = False) -> dict[str, Any]:
    definitions = load_registers()
    output: dict[str, dict[str, Any] | None] = {}
    for key, register in DASHBOARD_MAPPING.items():
        cloud_code = CLOUD_REGISTERS[register]
        row = values.get(cloud_code)
        if row is None:
            output[key] = None
            continue
        definition = definitions.get(str(register), {})
        unit = definition.get("unit") or ("°C" if definition.get("type") == "TEMP1" else "")
        value = row["value"]
        # Translate explicit enum states, not already scaled physical measurements.
        mapping = definition.get("value_map")
        if isinstance(mapping, dict):
            from backend.cloud_state import display_label
            label = display_label(register, value)
            value = label if label is not None else value
        output[key] = {
            "value": value, "raw": None, "unit": row.get("unit") or unit,
            "quality": row.get("quality", "stale") if stale else row.get("quality", "fresh"),
            "timestamp": row.get("timestamp") if stale else None,
        }
    # The firmware-selected runtime setpoint is distinct from the user R02
    # baseline (e.g. 35 °C). Prefer valid 2014; do NOT add an unverified
    # cloud offset, since 2014 already includes the active control selection.
    # Some installations report 0/empty for unavailable status values.
    selected = output.pop("selected_target", None)
    baseline = output.get("target")
    if selected:
        try:
            candidate = float(str(selected["value"]).replace(",", "."))
        except (TypeError, ValueError):
            candidate = 0.0
        if 5 <= candidate <= 80:
            output["base_target"] = baseline
            output["target"] = {**selected, "source_code": "2014",
                                "label": "Aktueller Wassersollwert"}
        else:
            output["base_target"] = baseline
    else:
        output["base_target"] = baseline
    if output.get("target"):
        output["target"].setdefault("source_code", "R02")
        output["target"].setdefault("label", "Heizungs-Basissollwert")
    return output


def read_register(register: int) -> dict[str, Any]:
    from backend.cloud_state import catalog, merge
    code = CLOUD_REGISTERS.get(register)
    from backend.timers import SCHEMAS
    timer_code = next((schema[register] for schema in SCHEMAS.values() if register in schema), None)
    code = timer_code or code
    if not code:
        # Only confirmed register mappings may be requested this way.
        matches = [c for c in catalog() if c.get("register") == register
                   and c.get("confidence") == "confirmed"]
        if matches:
            # Prefer the matching local code where multiple Cloud aliases exist.
            local_code = str(load_registers().get(str(register), {}).get("code") or "")
            preferred = next((c.get("write_code") for c in matches if c.get("write_code")), None)
            chosen = next((c for c in matches if c["code"] == (preferred or local_code)), matches[0])
            code = chosen["code"]
    if not code:
        raise CloudError("Keine bestätigte Cloud-Zuordnung für dieses Register")
    with _cloud_lock:
        account = credentials()
        row = _reader().read_codes([code]).get(code)
        if credentials() != account:
            raise CloudError("Cloud-Konto während des Lesens gewechselt")
    if not row:
        raise CloudError("Cloud liefert für dieses Register keinen Wert")
    merge({code: row}, source=account)
    definition = load_registers().get(str(register), {})
    edit_value = row["value"]
    from backend.parameter_write import timer_kind
    if timer_kind(register):
        from backend.timers import cloud_word, scaled
        word = cloud_word(register, row["value"])
        if str(definition.get("type")).upper() == "TIME_HHMM":
            edit_value = f"{word >> 8:02d}:{word & 255:02d}"
        elif not scaled(register):
            edit_value = word
    return {
        "edit_value": edit_value,
        "value": row["value"],
        "raw": None,
        "unit": row.get("unit") or definition.get("unit") or
                ("°C" if definition.get("type") == "TEMP1" else ""),
    }


def discover_devices() -> list[dict[str, Any]]:
    from backend.device_name import remember_name
    with _cloud_lock:
        account = credentials()
        rows = _reader().devices()
        remember_name(next((row for row in rows if row.get("deviceCode") == account[2]), {}), account)
        return rows


def selected_device_status() -> dict[str, Any]:
    from backend.device_name import remember_name
    with _cloud_lock:
        account = credentials()
        row = _reader().device_status()
        remember_name(row, account)
        return row
