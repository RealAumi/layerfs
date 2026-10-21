"""Single full run; observe control attempts without changing scenario logic."""
import importlib.util
import json
import pathlib
import time

repo = pathlib.Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('ignore_e2e', repo / 'docs/mp2/run-ignore-e2e.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
control = h.ctl
ledger = h.RECEIPTS / 'mount-control-samples.jsonl'


def observe(container, operation, *args, **kw):
    if operation not in ('mount', 'unmount'):
        return control(container, operation, *args, **kw)
    start = time.monotonic_ns()
    row = dict(container=container, operation=operation, args=args, start_ns=start)
    with ledger.open('a') as f:
        f.write(json.dumps({**row, 'state': 'started'}) + '\n')
    try:
        result = control(container, operation, *args, **kw)
        row.update(state='returned', exit=result.returncode, output=h.redact(result.stdout))
        return result
    except BaseException as error:
        row.update(state='raised', error=h.redact(repr(error)))
        raise
    finally:
        row['elapsed_ns'] = time.monotonic_ns() - start
        with ledger.open('a') as f:
            f.write(json.dumps(row) + '\n')


h.ctl = observe
h.e2e()
