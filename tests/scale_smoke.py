"""Optional synthetic scale check; not a phone benchmark. Run from the package root."""
import json
from pathlib import Path
import resource
import tempfile
import time
from test_diff import fixture, d, move

COUNT = 20000
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    data = fixture()
    template = data['records'][1]
    data['records'] = data['records'][:1]
    for i in range(COUNT):
        row = dict(template, name='Method' + str(i))
        move(row, 0x2000 + i * 32)
        data['records'].append(row)
    old, new = root / 'old.json', root / 'new.json'
    old.write_text(json.dumps(data), encoding='utf-8')
    for row in data['records'][1:]:
        move(row, int(row['native_offset'], 16) + 16, base=0x90000000)
    data['records'][1:] = reversed(data['records'][1:])
    new.write_text(json.dumps(data), encoding='utf-8')
    start = time.monotonic()
    report = d.compare(d.Dump(old), d.Dump(new))
    elapsed = time.monotonic() - start
    assert len(report['matches']) == COUNT
    assert report['summary']['native_states'] == {'rva_changed': COUNT}
    assert all(m['native']['rva_delta'] == '+0x10' for m in report['matches'])
    assert next(m for m in report['matches'] if m['old_id'] == 1)['new_id'] == COUNT
    print('Synthetic methods per input:', COUNT)
    print('Input sizes bytes:', old.stat().st_size, new.stat().st_size)
    print('Compare seconds:', round(elapsed, 3))
    print('Process maximum RSS (KiB on Linux):', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    print('PASS: all methods matched despite reordered IDs; every RVA delta is +0x10')
