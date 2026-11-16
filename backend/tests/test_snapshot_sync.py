import json
from pathlib import Path
import tempfile
import unittest

from scripts.sync_registers import FILES, ROOT, manifest, validate, verify


class SnapshotSyncTests(unittest.TestCase):
    def setUp(self):
        self.source = {name: (ROOT / 'data' / name).read_text(encoding='utf-8') for name in FILES}

    def test_snapshot_is_reproducible(self):
        validate(self.source)
        windows = {n: s.replace('\n', '\r\n') for n, s in self.source.items()}
        self.assertEqual(manifest('a' * 40, self.source), manifest('a' * 40, windows))

    def test_unknown_write_metadata_rejected(self):
        doc = json.loads(self.source[FILES[0]])
        doc['1158']['mode'] = 'write-anything'
        self.source[FILES[0]] = json.dumps(doc)
        with self.assertRaisesRegex(ValueError, 'Schreibrechte'):
            validate(self.source)

    def test_missing_type_and_dangling_reference_rejected(self):
        doc = json.loads(self.source[FILES[0]])
        del doc['1158']['type']
        with self.assertRaisesRegex(ValueError, 'Fehlendes Feld'):
            validate({**self.source, FILES[0]: json.dumps(doc)})
        knowledge = json.loads(self.source[FILES[2]])
        knowledge['65535'] = {'description': 'Unknown reference'}
        with self.assertRaisesRegex(ValueError, 'unbekannte Register'):
            validate({**self.source, FILES[2]: json.dumps(knowledge)})

    def test_reviewable_change_requires_new_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name, content in self.source.items():
                (target / name).write_text(content, encoding='utf-8')
            (target / 'upstream.json').write_text(json.dumps(manifest('a' * 40, self.source)), encoding='utf-8')
            verify(target)
            doc = json.loads(self.source[FILES[0]])
            doc['1158']['name'] = 'Reviewable upstream change'
            (target / FILES[0]).write_text(json.dumps(doc), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Prüfsummen'):
                verify(target)
