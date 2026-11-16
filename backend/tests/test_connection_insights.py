from datetime import datetime,timezone,timedelta
import unittest
from unittest.mock import Mock,patch

from backend import bus_connection as bus,cloud_insights as cloud
from backend.settings import Endpoint
from backend.cloud_read import CloudError


class ConnectionTests(unittest.TestCase):
    def test_browser_lease_expires_and_permanent_does_not_depend_on_it(self):
        with patch.object(bus,'_lease_until',100):
            self.assertTrue(bus.wanted('browser',99))
            self.assertFalse(bus.wanted('browser',100))
            self.assertTrue(bus.wanted('permanent',10000))
            self.assertFalse(bus.wanted('on_demand',99))

    def test_operations_reuse_one_socket_and_discard_poisoned_session(self):
        endpoint=Endpoint('private',2001)
        with patch.object(bus,'_entry',None),patch('backend.bus_connection.socket.create_connection') as create:
            with bus.operation(endpoint) as first:pass
            with bus.operation(endpoint) as second:self.assertIs(first,second)
            create.assert_called_once()
            with bus.operation(endpoint) as second:second.poisoned=True
            self.assertIsNone(bus._entry)
            create.return_value.close.assert_called_once()

    def test_observed_block_is_distinct_from_write_intent(self):
        frame=(99,16,2045,2,b'\x04\x00\x01\x00\x02',b'',b'',0,0,'word-frame')
        with patch.object(bus,'_words',{}):
            bus.observe([frame])
            self.assertEqual(bus.observed_words()['2046']['raw'],2)
            self.assertEqual(bus.observed_words()['2046']['quality'],'observed')
            bus.observe([(*frame[:2],2047,*frame[3:9],'short-write')])
            self.assertNotIn('2047',bus.observed_words())


class CloudInsightTests(unittest.TestCase):
    def setUp(self):
        self.reader=Mock();self.reader.device_code='private-device';self.reader._ok.return_value=True
        self.patches=[patch.object(cloud,'_cache',{}),patch.object(cloud,'_attempts',{}),
                      patch('backend.cloud_insights.credentials',return_value=('user','secret','private-device')),
                      patch('backend.cloud_insights._reader',return_value=self.reader)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def test_history_window_alias_and_timezone_validation(self):
        cloud.history_args('2078+9','2026-11-01 00:00:00','2026-11-16 00:00:00','month',1)
        for address,start,end,zone in [('9999','2026-11-01 00:00:00','2026-11-16 00:00:00',1),('2045','bad','bad',1),('2045','2026-01-01 00:00:00','2026-11-16 00:00:00',1),('2045','2026-11-01 00:00:00','2026-11-16 00:00:00',2)]:
            with self.assertRaises(ValueError):cloud.history_args(address,start,end,'day',zone)
    def test_empty_ota_is_successful_no_update_and_cached(self):
        self.reader._request_auth.return_value={'objectResult':[]}
        result=cloud.request('ota');self.assertFalse(result['available'])
        self.assertTrue(cloud.request('ota')['cached'])
        self.reader._request_auth.assert_called_once()
    def test_failed_requests_are_rate_limited_too(self):
        self.reader._request_auth.side_effect=CloudError('Cloud-Fehler')
        with self.assertRaises(CloudError):cloud.request('ota')
        with self.assertRaises(ValueError):cloud.request('ota')
        self.reader._request_auth.assert_called_once()
    def test_current_day_zero_is_not_claimed_as_complete_consumption(self):
        today=datetime.now(timezone(timedelta(hours=1))).strftime('%Y-%m-%d')
        self.reader._request_auth.return_value={'objectResult':{'valueList':[{'dateTime':today+' 00:00:00','addressValue':'0.000'},{'dateTime':'bad','addressValue':'NaN'}]}}
        result=cloud.request('history',{'address':'2078+9'})
        self.assertEqual(len(result['points']),1);self.assertTrue(result['points'][0]['incomplete'])
    def test_hour_only_history_labels_become_browser_parseable_timestamps(self):
        self.reader._request_auth.return_value={'objectResult':{'valueList':[{'dateTime':'2026-11-16 23','addressValue':'35.1'}]}}
        result=cloud.request('history',{'address':'2046'})
        self.assertEqual(result['points'][0]['time'],'2026-11-16T23:00:00+01:00')

    def test_metadata_does_not_expose_identifiers_or_create_grants(self):
        self.reader._request_auth.return_value={'objectResult':[{'address':'2157','content':'PV_Power','deviceCode':'private','token':'secret','write_allowed':True}]}
        result=cloud.request('metadata')
        self.assertEqual(result['items'],[{'address':'2157','content':'PV_Power'}])
