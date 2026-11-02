import importlib.util
import tempfile
import sys
import threading
import unittest
import urllib.request
import urllib.error
import json
import subprocess
import time
from unittest.mock import patch
from pathlib import Path
from datetime import datetime, timezone, timedelta
SPEC=importlib.util.spec_from_file_location('atlas_server',Path(__file__).parents[1]/'scripts/server.py')
server=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(server)

class ServerTests(unittest.TestCase):
    def test_launchd_absolute_python_and_path(self):
        script=Path(__file__).parents[1]/'scripts'
        sys.path.insert(0,str(script))
        try:
            import manage
            config=manage.launch_config()
            self.assertTrue(Path(config['ProgramArguments'][0]).is_absolute())
            self.assertIn('/opt/homebrew/bin',config['EnvironmentVariables']['PATH'])
            self.assertTrue(config['KeepAlive'])
        finally: sys.path.remove(str(script))
    def test_install_copy_preserves_newer_data_and_allowlist(self):
        script=Path(__file__).parents[1]/'scripts'; sys.path.insert(0,str(script))
        try:
            import manage
            with tempfile.TemporaryDirectory() as tmp:
                source=Path(tmp)/'source'; target=Path(tmp)/'app'
                for root in (source,target): (root/'data/history').mkdir(parents=True)
                (source/'scripts').mkdir(); (source/'web').mkdir()
                for name in ('manage.py','server.py','build.py','collect.py'):
                    (source/'scripts'/name).write_text('pass')
                for name in ('index.html','styles.css','app.js'): (source/'web'/name).write_text('asset')
                (source/'data/editorial.json').write_text('{}')
                (source/'data/latest.json').write_text('{"topUpdatedAt":"2026-01-01T00:00:00Z"}')
                (target/'data/latest.json').write_text('{"topUpdatedAt":"2026-02-01T00:00:00Z"}')
                (source/'data/history/a.json').write_text('new')
                (target/'data/history/a.json').write_text('existing')
                (source/'data/history/b.json').write_text('missing')
                (source/'web/token.txt').write_text('SECRET')
                manage.deploy_copy(source,target)
                self.assertIn('2026-02', (target/'data/latest.json').read_text())
                self.assertEqual((target/'data/history/a.json').read_text(),'existing')
                self.assertEqual((target/'data/history/b.json').read_text(),'missing')
                self.assertFalse((target/'web/token.txt').exists())
                self.assertFalse(any(p.is_symlink() for p in target.rglob('*')))
                self.assertEqual(manage.launch_config(target)['WorkingDirectory'],str(target))
                plist=Path(tmp)/'service.plist'
                with plist.open('wb') as handle: manage.plistlib.dump(manage.launch_config(target),handle)
                with patch.object(manage,'PLIST',plist), patch.object(manage,'INSTALLED',target):
                    self.assertEqual(manage.active_root(),target)
        finally: sys.path.remove(str(script))
    def test_due(self):
        now=datetime.now(timezone.utc)
        self.assertFalse(server.is_due({'topUpdatedAt':now.isoformat()},now))
        self.assertTrue(server.is_due({'topUpdatedAt':(now-timedelta(seconds=10801)).isoformat()},now))
        self.assertTrue(server.is_due({}))
    def test_mutex(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with server.update_lock(root) as first:
                self.assertTrue(first)
                with server.update_lock(root) as second: self.assertFalse(second)
    def test_refresh_busy_and_failure_preserve_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with server.update_lock(root):
                with patch.object(server,'run_child') as run:
                    self.assertFalse(server.refresh(root)); run.assert_not_called()
            with patch.object(server,'run_child') as run:
                run.return_value=1
                self.assertFalse(server.refresh(root))
                self.assertEqual(run.call_count,1)
                self.assertFalse(server.STATE['updating'])
    def test_invalid_json_and_timestamps_are_due(self):
        for data in [None,[],{'topUpdatedAt':7},{'topUpdatedAt':'2026-01-01T00:00:00'},{'topUpdatedAt':'bad'}]:
            self.assertTrue(server.is_due(data))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'dist').mkdir()
            for raw in ['null','[]','{broken','{"status":null}']:
                (root/'dist/latest.json').write_text(raw)
                data=server.load_data(root)
                self.assertIsInstance(data,dict)
                self.assertIsInstance(data.get('status',{}),dict)
    def test_scheduler_survives_refresh_error(self):
        stop=threading.Event()
        class StopAfterTwo:
            calls=0
            def is_set(self): return self.calls>=2
            def wait(self,seconds): self.calls+=1
        with patch.object(server,'load_data',return_value={}),patch.object(server,'refresh',side_effect=OSError('temporary')) as refresh:
            server.scheduler(Path('/tmp'),StopAfterTwo())
            self.assertEqual(refresh.call_count,2)
    def test_cancellation_reaps_owned_child(self):
        stop=threading.Event(); children=[]
        real_popen=subprocess.Popen
        def capture(*args,**kwargs):
            child=real_popen(*args,**kwargs); children.append(child); stop.set(); return child
        started=time.monotonic()
        with patch.object(server.subprocess,'Popen',side_effect=capture):
            with self.assertRaisesRegex(RuntimeError,'cancelled'):
                server.run_child([sys.executable,'-c','import time; time.sleep(60)'],60,stop)
        self.assertLess(time.monotonic()-started,4)
        self.assertIsNotNone(children[0].poll())
    def test_cancelled_update_never_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop=threading.Event(); stop.set()
            with patch.object(server.subprocess,'Popen') as popen:
                self.assertFalse(server.refresh(Path(tmp),stop=stop))
                popen.assert_not_called()
    def test_health_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'dist').mkdir(); (root/'dist/index.html').write_text('hello'); (root/'secret').write_text('SECRET')
            http=server.make_server(root,0)
            thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
            base='http://127.0.0.1:'+str(http.server_port)
            try:
                self.assertIn(b'hello',urllib.request.urlopen(base).read())
                self.assertIn(b'"ready": true',urllib.request.urlopen(base+'/healthz').read())
                for path in ['/../secret','/%2e%2e/secret','/%2e%2e%2fsecret','/.hidden']:
                    with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(base+path)
            finally: http.shutdown(); http.server_close(); thread.join()
