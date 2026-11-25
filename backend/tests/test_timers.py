from contextlib import contextmanager
import unittest
from unittest.mock import Mock,patch

from backend import timers
from backend.cloud_write import WriteValidationError,WriteConflictError,_format_value


class TimerSchemaTests(unittest.TestCase):
    def test_standard_is_accepted_by_timer_write_api(self):
        from backend.main import TimerWrite
        self.assertEqual(TimerWrite(transport='standard_modbus', values={}, expected={}).transport, 'standard_modbus')

    def test_m1_summary_uses_only_low_enable_byte_and_display_cache(self):
        rows = {
            '1323': {'raw': 0x8001, 'quality': 'observed'},
            '1287': {'raw': 25, 'quality': 'observed'},
            '1281': {'raw': 0x1600, 'quality': 'observed'},
            '1282': {'raw': 0x061E, 'quality': 'observed'},
        }
        with patch('backend.transport_selection.paused', return_value=False), \
             patch('backend.display_bus.manager.lease'), \
             patch('backend.timers.cached_timer_words') as cached, \
             patch('backend.timers.connection') as connection:
            cached.side_effect = lambda registers: (
                {key: row['raw'] for key, row in rows.items()}, {}
            )
            self.assertEqual(timers.read_m1('display_modbus'), {
                'enabled': False, 'max_kw': 2.5, 'stale': False,
                'window': {'start': 1320, 'end': 390, 'days': 1},
            })
            rows['1323']['raw'] |= 0x80
            self.assertTrue(timers.read_m1('display_modbus')['enabled'])
            del rows['1287']
            self.assertIsNone(timers.read_m1('display_modbus')['max_kw'])
            rows['1282']['raw'] = 0xFFFF
            self.assertIsNone(timers.read_m1('display_modbus')['window'])
            connection.assert_not_called()

    def test_partial_display_timer_uses_lte_words_and_exact_cloud_format(self):
        stored = {
            '1281': {'raw': 0x0600, 'transport': 'warmlink_raw', 'timestamp': '2026-11-24T06:00:00Z'},
            '1287': {'raw': None, 'value': '2.5', 'code': 'M1 Max. Power', 'transport': 'cloud',
                     'timestamp': '2026-11-24T06:00:00Z'},
            '1323': {'raw': None, 'value': '1000000010000001', 'code': 'M1_2 Enalbe',
                     'transport': 'cloud', 'timestamp': '2026-11-24T06:00:00Z'},
        }
        with patch('backend.transport_selection.paused', return_value=False), \
             patch('backend.display_bus.manager.lease'), \
             patch('backend.last_values.store.values', return_value=stored), \
             patch('backend.timers.connection') as connection:
            result = timers.read('operating', 'display_modbus')
        self.assertEqual(result['values'], {'1281': 0x0600, '1287': 25, '1323': 0x8081})
        self.assertEqual(result['sources']['1281']['transport'], 'warmlink_raw')
        self.assertTrue(result['read_only'])
        connection.assert_not_called()

    def test_word_scaling_and_mask_payloads(self):
        self.assertEqual(timers.cloud_word(1284,'35.1'),351)
        self.assertEqual(timers.cloud_word(1323,'1000000110000010'),0x8182)
        self.assertEqual(timers.cloud_word(1281,'1570'),0x0622)
        for value in ('NaN','1.23','',None,True):
            with self.assertRaises(WriteValidationError):timers.cloud_word(1284,value)

    def test_operating_schema_matches_desktop(self):
        self.assertEqual(timers.OPERATING[1283],'M1 Hot Water Target')
        self.assertEqual(timers.OPERATING[1284],'M1 Heating Target')
        self.assertEqual(timers.OPERATING[1325],'M5_6 Enalbe')
        self.assertEqual(timers.WEEKLY[1270],'KG45~KG60')

    def test_mask_partner_byte_survives_disable_and_reenable(self):
        old={str(r):0 for r in timers.OPERATING}
        old['1323']=0xC181
        desired={**old,'1284':351}
        phases=timers.phases('operating',old,desired)
        self.assertEqual(phases,[{'1323':0xC101},{'1284':351},{'1323':0xC181}])

    def test_weekly_high_byte_program_preserves_low_byte(self):
        old={str(r):0 for r in timers.WEEKLY};old['1268']=0x82C3
        desired={**old,'1258':0x0600}
        self.assertEqual(timers.phases('weekly',old,desired),[{'1268':0x02C3},{'1258':0x0600},{'1268':0x82C3}])

    def test_silent_disabled_before_time_and_enable_last(self):
        old={str(r):0 for r in timers.SILENT};old['1244']=1
        desired={**old,'1245':22,'1246':30}
        self.assertEqual(timers.phases('silent',old,desired),[{'1244':0},{'1245':22,'1246':30},{'1244':1}])

    def test_bad_times_and_incomplete_drafts_rejected(self):
        old={str(r):0 for r in timers.WEEKLY}
        for word in (0x1800,0x0060,65536,True):
            with self.assertRaises(WriteValidationError):timers.validate('weekly',{**old,'1256':word})
        with self.assertRaises(WriteValidationError):timers.validate('weekly',{'1256':0})

    def test_unknown_unchanged_unused_parameters_not_written(self):
        old={str(r):0 for r in timers.OPERATING}
        timers.validate('operating',old,old)
        with self.assertRaises(WriteValidationError):timers.validate('operating',{**old,'1284':40},old)

    def test_changed_target_requires_live_source_limits(self):
        old={str(r):0 for r in timers.OPERATING};old['1284']=350
        client=Mock();client.read_holding.return_value=[250,400]
        timers.check_target_limits('operating',{**old,'1284':380},old,'warmlink_raw',client)
        client.read_holding.assert_called_once_with(1164,2)
        with self.assertRaises(WriteValidationError):
            timers.check_target_limits('operating',{**old,'1284':410},old,'warmlink_raw',client)

    def test_original_unknown_values_do_not_become_writes(self):
        old={str(r):0 for r in timers.OPERATING};old['1283']=65535
        self.assertEqual(timers.phases('operating',old,old),[])
        self.assertEqual(timers.wire_value(1283,65535),'-0.1')

    def test_power_and_silent_are_binary_only(self):
        for code in ('Power','H22'):
            self.assertEqual(_format_value(code,1)[1],'1')
            for value in (2,-1,'NaN',True):
                with self.assertRaises(WriteValidationError):_format_value(code,value)


class TimerWriteTests(unittest.TestCase):
    def setUp(self):
        self.client=Mock();self.client.device_code='test-device';self.client.token='test-token'
        self.client._ok.return_value=True
        self.old={str(r):0 for r in timers.SILENT};self.old['1244']=1
        self.desired={**self.old,'1245':22}
        @contextmanager
        def connection(_transport):yield self.client,'test'
        self.patches=[patch('backend.timers.connection',connection),patch('backend.timers.check_connection'),
            patch('backend.timers.time.sleep'),patch('backend.timers.cache_words'),patch.object(timers,'_last_write',0)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()

    def test_conflict_sends_no_control(self):
        with patch('backend.timers.read_words',return_value={**self.old,'1245':1}):
            with self.assertRaises(WriteConflictError):timers.write('silent','cloud',self.desired,self.old)
        self.client._post.assert_not_called()

    def test_unchanged_sends_nothing(self):
        with patch('backend.timers.read_words',return_value=self.old):
            result=timers.write('silent','cloud',self.old,self.old)
        self.assertEqual(result['status'],'unchanged');self.client._post.assert_not_called()

    def test_no_enable_after_failed_parameter_readback(self):
        disabled={**self.old,'1244':0}
        with patch('backend.timers.read_words',side_effect=[self.old,disabled,disabled]):
            result=timers.write('silent','cloud',self.desired,self.old)
        self.assertFalse(result['confirmed'])
        self.assertEqual(self.client._post.call_count,2)
        payloads=[c.args[1]['param'] for c in self.client._post.call_args_list]
        self.assertEqual(payloads[0][0]['protocolCode'],'Timer_Mute_On_En')
        self.assertEqual(payloads[0][0]['value'],'0')
        self.assertEqual(payloads[1][0]['protocolCode'],'TimerMuteOnHour')

    def test_three_confirmed_phases_enable_last(self):
        disabled={**self.old,'1244':0};parameters={**disabled,'1245':22}
        with patch('backend.timers.read_words',side_effect=[self.old,disabled,parameters,self.desired]):
            result=timers.write('silent','warmlink_raw',self.desired,self.old)
        self.assertTrue(result['confirmed'])
        self.assertEqual([c.args for c in self.client.write_one.call_args_list],[(1244,0),(1245,22),(1244,1)])

    def test_timeout_never_retries_or_enables(self):
        self.client.write_one.side_effect=TimeoutError()
        with patch('backend.timers.read_words',return_value=self.old):
            result=timers.write('silent','warmlink_raw',self.desired,self.old)
        self.assertFalse(result['confirmed']);self.client.write_one.assert_called_once_with(1244,0)
