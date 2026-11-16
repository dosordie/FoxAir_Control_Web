import asyncio
from contextlib import contextmanager
import json
import unittest
from unittest.mock import AsyncMock,Mock,call,patch

from backend import bus_connection as bus,register_scan as scan
from backend.main import lte_events,lte_snapshot,LTE_READ_BLOCKS,DASHBOARD_FIELDS
from backend.rtu import with_crc
from backend.settings import Endpoint
from backend.warmlink import WarmlinkSession


class BlockReadTests(unittest.TestCase):
    def test_wire_read_uses_fc03_and_ninety_words(self):
        words=list(range(90))
        response=with_crc(b'\x63\x03\xb4'+b''.join(word.to_bytes(2,'big') for word in words))
        sock=Mock();sock.recv.side_effect=[response[:19],response[19:]]
        client=WarmlinkSession(sock,Endpoint('private',2001))
        with patch.object(client,'quiet'):
            self.assertEqual(client.read_holding(1001,90),words)
        sock.sendall.assert_called_once_with(with_crc(bytes.fromhex('63 03 03 e9 00 5a')))

    def test_dashboard_blocks_cover_needed_words_with_at_most_ninety_per_read(self):
        covered={reg for start,count in LTE_READ_BLOCKS for reg in range(start,start+count)}
        self.assertTrue(set(DASHBOARD_FIELDS.values())|{2014} <= covered)
        self.assertEqual(len(LTE_READ_BLOCKS),3)
        self.assertTrue(all(0<count<=90 for _,count in LTE_READ_BLOCKS))


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.endpoint=Endpoint('private',2001)
        self.client=Mock();self.client.read_holding.side_effect=lambda start,count:list(range(count))
        @contextmanager
        def connection(endpoint):yield self.client
        self.patches=[patch.object(scan,'_job',{'status':'running','completed':0,'total':8,'error':None}),
                      patch.object(scan,'_source',self.endpoint),patch.object(scan,'_finished',0),
                      patch.object(scan,'warmlink_endpoint',return_value=self.endpoint),patch.object(scan,'open_warmlink',side_effect=connection)]
        for item in self.patches:item.start()
    def tearDown(self):
        for item in reversed(self.patches):item.stop()

    def test_all_eight_blocks_are_sequential_and_complete(self):
        scan._run(self.endpoint)
        self.assertEqual(self.client.read_holding.call_args_list,[call(start,90) for start in (1001,1091,1181,1271,1361,1451,2001,2091)])
        self.assertEqual(scan.status()['status'],'complete')
        self.assertEqual(scan.status()['completed'],8)
        self.client.write_one.assert_not_called()

    def test_first_unclear_response_aborts_without_retry(self):
        self.client.read_holding.side_effect=[list(range(90)),TimeoutError('private response')]
        scan._run(self.endpoint)
        self.assertEqual(scan.status()['status'],'partial')
        self.assertEqual(scan.status()['completed'],1)
        self.assertEqual(self.client.read_holding.call_count,2)
        self.assertNotIn('private response',scan.status()['error'])

    def test_multiple_tabs_share_running_or_recent_job(self):
        with patch.object(scan.threading,'Thread') as worker:
            self.assertFalse(scan.start()['started'])
            worker.assert_not_called()
            scan._job['status']='complete'
            with patch.object(scan,'_finished',scan.time.monotonic()):
                self.assertFalse(scan.start()['started'])
            worker.assert_not_called()

    def test_configuration_change_aborts_before_next_transmission(self):
        with patch.object(scan,'warmlink_endpoint',side_effect=[self.endpoint,None]):scan._run(self.endpoint)
        self.assertEqual(self.client.read_holding.call_count,1)
        self.assertEqual(scan._job['status'],'partial')


class CacheTests(unittest.TestCase):
    def test_headers_and_virtual_ids_never_reach_browser_and_latest_source_wins(self):
        endpoint=Endpoint('private',2001)
        with patch.object(bus,'_source',endpoint),patch.object(bus,'_words',{2046:(380,1000),2091:(12345,1000),2001:(12345,1000)}), \
             patch.object(bus,'_readings',{2046:(381,1100),1091:(999,1100),91102:(33,1100)}),patch.object(bus.time,'time',return_value=1200):
            values=bus.register_values(endpoint)
            self.assertEqual(set(values),{'2046'})
            self.assertEqual(values['2046']['value'],38.1)
            self.assertEqual(values['2046']['quality'],'fresh')
            self.assertEqual(bus.register_values(Endpoint('other',2001)),{})
            self.assertNotIn('2091',bus.observed_words())
            with patch.object(bus.time,'time',return_value=1500):self.assertEqual(bus.register_values(endpoint)['2046']['quality'],'stale')

    def test_observer_cannot_merge_data_from_old_endpoint(self):
        endpoint=Endpoint('new',2001)
        with patch.object(bus,'_source',endpoint),patch.object(bus,'_words',{}):
            bus.observe([(99,16,2046,1,b'\x02\x01\x7c',b'',b'',0,0,'word-frame')],Endpoint('old',2001))
            self.assertEqual(bus.observed_words(),{})

    def test_snapshot_does_not_open_or_read_bus(self):
        with patch('backend.main.warmlink_endpoint',return_value=None),patch('backend.bus_connection.socket.create_connection') as create:
            self.assertEqual(lte_snapshot()['values'],{})
        create.assert_not_called()


class PushTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_sends_initial_snapshot_then_only_changes_and_removals(self):
        request=Mock();request.is_disconnected=AsyncMock(return_value=False)
        base={'connection':{},'metrics':{},'scan':{}}
        snapshots=[{**base,'values':{'2046':{'value':38},'2045':{'value':35}}},
                   {**base,'values':{'2046':{'value':38.1}}}]
        with patch('backend.main.lte_snapshot',side_effect=snapshots),patch('asyncio.sleep',new=AsyncMock()):
            response=await lte_events(request)
            iterator=response.body_iterator
            first=json.loads((await anext(iterator))[6:].strip())
            second=json.loads((await anext(iterator))[6:].strip())
            await iterator.aclose()
        self.assertTrue(first['reset'])
        self.assertFalse(second['reset'])
        self.assertEqual(second['values'],{'2046':{'value':38.1}})
        self.assertEqual(second['removed'],['2045'])
        self.assertEqual(response.headers['x-accel-buffering'],'no')
