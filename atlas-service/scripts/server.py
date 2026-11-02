#!/usr/bin/env python3
"""Loopback-only static server and resilient three-hour refresh scheduler."""
import contextlib
import fcntl
import json
import mimetypes
import os
import time
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT=Path(__file__).resolve().parents[1]
INTERVAL=10800
STATE={'updating':False,'lastAttemptAt':None,'lastResult':None}

def load_data(root):
    try:
        data=json.loads((Path(root)/'dist/latest.json').read_text(encoding='utf-8'))
        if not isinstance(data,dict): return {}
        if not isinstance(data.get('status'),dict): data['status']={}
        return data
    except (OSError, ValueError): return {}

def is_due(data, now=None):
    now=now or datetime.now(timezone.utc)
    try:
        if not isinstance(data,dict) or not isinstance(data.get('topUpdatedAt'),str): return True
        stamp=datetime.fromisoformat(data['topUpdatedAt'].replace('Z','+00:00'))
        if stamp.tzinfo is None: return True
        return (now-stamp).total_seconds() >= INTERVAL
    except (ValueError, KeyError, TypeError): return True

@contextlib.contextmanager
def update_lock(root=ROOT):
    path=Path(root)/'.runtime'; path.mkdir(exist_ok=True)
    with (path/'update.lock').open('a') as handle:
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            yield False; return
        try: yield True
        finally: fcntl.flock(handle,fcntl.LOCK_UN)

def run_child(command, timeout, stop=None):
    """Own the child process group, including gh, until exit or cancellation."""
    if stop is not None and stop.is_set(): raise RuntimeError('Update cancelled')
    child=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    deadline=time.monotonic()+timeout
    try:
        while True:
            if stop is not None and stop.is_set(): raise RuntimeError('Update cancelled')
            if time.monotonic() >= deadline: raise subprocess.TimeoutExpired(command,timeout)
            try: return child.wait(timeout=min(.2,max(.001,deadline-time.monotonic())))
            except subprocess.TimeoutExpired: pass
    finally:
        if child.poll() is None:
            try: os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try: os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                child.wait()

def refresh(root=ROOT, force=False, stop=None):
    root=Path(root)
    with update_lock(root) as acquired:
        if not acquired: return False
        STATE.update(updating=True,lastAttemptAt=datetime.now(timezone.utc).isoformat())
        try:
            command=[sys.executable,str(root/'scripts/collect.py'),'--output',str(root/'data/latest.json')]
            if force: command.append('--force')
            # Child diagnostics may include remote response text; never publish them.
            if run_child(command,1800,stop): raise RuntimeError('Collection failed')
            if run_child([sys.executable,str(root/'scripts/build.py')],120,stop): raise RuntimeError('Build failed')
            STATE['lastResult']='ok'; return True
        except (OSError, subprocess.SubprocessError, RuntimeError):
            STATE['lastResult']='Update failed; serving previous build'; return False
        finally: STATE['updating']=False

def scheduler(root,stop):
    while not stop.is_set():
        try:
            if is_due(load_data(root)): refresh(root,stop=stop)
        except Exception:
            # An invalid file or transient filesystem error must not kill scheduling.
            STATE.update(updating=False,lastResult='Update failed; serving previous build')
        # Retry failed/overlapping work within five minutes, including after wake.
        stop.wait(300)

def make_server(root=ROOT,port=4173):
    root=Path(root)
    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self): self.respond(False)
        def do_GET(self): self.respond(True)
        def log_message(self,*args): pass
        def respond(self,body):
            path=unquote(urlsplit(self.path).path)
            if path=='/healthz':
                data=load_data(root)
                payload=json.dumps({'ready':(root/'dist/index.html').is_file(),'topUpdatedAt':data.get('topUpdatedAt'),'status':data.get('status',{}).get('state'),'update':dict(STATE)}).encode()
                self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(payload))); self.end_headers()
                if body: self.wfile.write(payload)
                return
            parts=path.strip('/').split('/')
            if any(p in ('.','..') or p.startswith('.') for p in parts) or '\\' in path or '\x00' in path:
                self.send_error(404); return
            live=(root/'dist').resolve()
            target=(live/('index.html' if path=='/' else path.lstrip('/'))).resolve()
            if live not in target.parents or not target.is_file():
                self.send_error(404,'No published page yet; refresh is pending'); return
            try: payload=target.read_bytes()
            except OSError: self.send_error(404); return
            self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(str(target))[0] or 'application/octet-stream'); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','no-cache'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers()
            if body: self.wfile.write(payload)
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)

def main():
    stop=threading.Event(); http=make_server()
    worker=threading.Thread(target=scheduler,args=(ROOT,stop),daemon=True); worker.start()
    def shutdown(*args):
        stop.set(); threading.Thread(target=http.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,shutdown); signal.signal(signal.SIGINT,shutdown)
    try: http.serve_forever()
    finally: stop.set(); http.server_close(); worker.join(timeout=6)

if __name__=='__main__': main()
