"""The actual runtime Mount acknowledgement is named mount for mount-branch."""
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BENCH=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BENCH))
from engine import workspace,fixtures,identity,receipts


class ImportMountProtocol(unittest.TestCase):
    def scenario(self,folder,*,wrong_fork=False,short_mount=False):
        target='b'*64;cid='c'*64;source=folder/'store.sqlite';source.write_bytes(b'held exact Init')
        manifest=folder/'installed.manifest';manifest.write_bytes(b'actual SDK manifest')
        workload=folder/'workload-linux';workload.write_bytes(b'sealed original native verifier')
        row={'init':{'fields':{'root':target,'stack':'31'+'a'*32}},'verification':{},
            'clone':{'volume':'layerfs-fsb-sample-'+'d'*16},'additional_containers':['e'*64]}
        row['installation']={'schema':'fs-bench-pro-public-init-install-v1','status':'PASS','global_profile':'Disposable/WAL/OFF',
            'volume':row['clone']['volume'],'container':'e'*64,'manifest':str(manifest),
            'manifest_sha256':identity.sha256(manifest),'store_sha256':identity.sha256(source)}
        called=[]
        class Stream:
            def __init__(self):self.messages=[]
            def write(inner,raw):
                inner.messages.append(raw);called.append(('write',raw))
                return len(raw)-1 if short_mount and raw.startswith(b'mount-branch\t') else len(raw)
            def close(inner):pass
        class Runtime:
            send=workspace.cell_runner.EventProcess.send
            def __init__(inner,*args):
                inner.container=cid;inner.rows=[];inner.selector=inner.raw=inner.stderr=None
                inner.process=SimpleNamespace(stdin=Stream(),stdout=None,wait=lambda **kwargs:0)
                inner.retained=False
            def event(inner,expected,deadline):
                called.append(('expect',expected,deadline))
                wire=inner.process.stdin.messages[-1].decode().strip().split('\t',2) if inner.process.stdin.messages else []
                if not wire:actual='protocol_ready';fields={}
                else:
                    operation=wire[0];actual={'mount-branch':'mount','observe':'external_snapshot','stop':'container_stopped'}.get(operation,operation)
                    fields={}
                    if expected=='finished' and inner.rows[-1]['event']=='container_stopped':actual='finished'
                    if operation=='fork':
                        identifier=Path(wire[2]).read_text().split('\t')[1]
                        fields={'branch_id':identifier,'root':'f'*64 if wrong_fork else target,'head':'-','stack':row['init']['fields']['stack']}
                    elif operation=='mount-branch':
                        fields={'key':wire[1],'directory':'/workspaces/1','root':target,'branch_label':'verify-import',
                            'workspace_incarnation':wire[1],'workspace_namespace':1}
                    elif operation=='verify':fields={'exit_code':'0','command_sha256':identity.sha256(Path(wire[2]))}
                    elif operation=='cleanup':fields={'state':'Gone'}
                event={'event':actual,'fields':fields,'value':cid if actual=='container_stopped' else '',
                       'sequence':len(inner.rows)+1,'span':{'duration_ns':6481041 if actual=='mount' else 1}}
                inner.rows.append(event)
                if expected!=actual:
                    raise TimeoutError('original event wall stop: '+expected+'; actual acknowledged '+actual)
                return event
            def retain(inner,error):inner.retained=True;return {'state':'HOST_FENCE_ONLY_REMOTE_UNKNOWN'}
        owner=Runtime()
        def command(argv,out,label,seconds,**options):
            called.append(('docker',argv,label));path=Path(out)/(label+'.stdout')
            path.write_text(json.dumps({'NanoCpus':2000000000,'Memory':2147483648,'MemorySwap':2147483648,'PidsLimit':256}) if label=='import-verifier-profile-readback' else '')
            return {'stdout':str(path),'stderr':str(path)}
        case={'id':'dedup-cross-file-anchor-1','v016_case':'dedup-cross-file-anchor-1'}
        build={'socket':'/socket','binaries':{'runtime':{'path':'/runtime'},'daemon':{'path':'/daemon'},'workload-linux':{'path':str(workload)}}}
        prepared={'source_uid':501,'source_gid':20}
        stack=ExitStack()
        for module,name,options in (
            (workspace.cell_runner,'EventProcess',{'return_value':owner}),
            (fixtures,'stage',{'return_value':{}}),(receipts,'command',{'side_effect':command}),
            (workspace,'ordinary_resource_guard',{'return_value':{}}),
            (workspace,'verify_native_receipt',{'return_value':{'status':'PASS'}}),
            (workspace.cell_runner,'snapshot_observations',{'return_value':None}),
        ):stack.enter_context(patch.object(module,name,**options))
        return stack,case,prepared,build,row,owner,called

    def test_actual_mount_ack_is_consumed_once_and_original_native_terminal_schedule_completes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);stack,case,prepared,build,row,owner,calls=self.scenario(folder)
            with stack:workspace.verify_import_mount(case,prepared,build,folder,row,{'work':workspace.time.monotonic()+41,'cleanup':workspace.time.monotonic()+45})
            writes=[call[1].decode().split('\t')[0].strip() for call in calls if call[0]=='write']
            self.assertEqual(writes,['fork','mount-branch','verify','unmount','cleanup','observe','stop'])
            expectations=[call[1] for call in calls if call[0]=='expect']
            self.assertEqual(expectations,['protocol_ready','fork','mount','verify','unmount','cleanup','external_snapshot','container_stopped','finished'])
            self.assertEqual(row['cleanup'],'Gone');self.assertEqual(row['custody'],'KNOWN_STOP')
            self.assertFalse(owner.retained)
            self.assertFalse(any('rm' in call[1] for call in calls if call[0]=='docker'))

    def test_wrong_original_fork_root_refuses_before_any_mount_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);stack,case,prepared,build,row,owner,calls=self.scenario(folder,wrong_fork=True)
            with stack:
                with self.assertRaisesRegex(ValueError,'Fork differs'):
                    workspace.verify_import_mount(case,prepared,build,folder,row,{'work':workspace.time.monotonic()+41,'cleanup':workspace.time.monotonic()+45})
            self.assertEqual([call[1].decode().split('\t')[0].strip() for call in calls if call[0]=='write'],['fork'])
            self.assertTrue(owner.retained)

    def test_short_mount_branch_write_is_not_resent_or_claimed_unmounted(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);stack,case,prepared,build,row,owner,calls=self.scenario(folder,short_mount=True)
            with stack:
                with self.assertRaisesRegex(RuntimeError,'short'):
                    workspace.verify_import_mount(case,prepared,build,folder,row,{'work':workspace.time.monotonic()+41,'cleanup':workspace.time.monotonic()+45})
            self.assertEqual([call[1].decode().split('\t')[0].strip() for call in calls if call[0]=='write'],['fork','mount-branch'])
            self.assertTrue(owner.retained)
            self.assertNotIn('cleanup',row)


if __name__=='__main__':unittest.main()
