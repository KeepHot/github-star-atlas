#!/usr/bin/env python3
"""Manage the local Atlas process or macOS login service."""
import argparse
import json
import os
import plistlib
import signal
import shutil
from datetime import datetime, timezone
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from server import ROOT, refresh

LABEL='local.github-star-atlas'
RUNTIME=ROOT/'.runtime'
PLIST=Path.home()/'Library/LaunchAgents'/ (LABEL+'.plist')
DOMAIN='gui/'+str(os.getuid())
INSTALLED=Path.home()/'Library/Application Support/GitHubStarAtlas'

def active_root():
    if PLIST.exists():
        try:
            with PLIST.open('rb') as handle: config=plistlib.load(handle)
            configured=Path(config['WorkingDirectory'])
            if configured.resolve()==INSTALLED.resolve(): return INSTALLED
        except (OSError,KeyError,ValueError,plistlib.InvalidFileException): pass
    return ROOT

def atomic_copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_name(target.name+'.install-tmp')
    shutil.copyfile(str(source),str(temp))
    os.replace(str(temp),str(target))

def snapshot_time(path):
    try:
        value=json.loads(path.read_text())['topUpdatedAt']
        return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
    except (OSError,KeyError,ValueError,TypeError): return datetime.min.replace(tzinfo=timezone.utc)

def deploy_copy(source,target):
    source=Path(source); target=Path(target)
    if source.resolve()==target.resolve(): return
    for folder,names in [('scripts',('manage.py','server.py','build.py','collect.py')),('web',('index.html','styles.css','app.js')),('data',('editorial.json',))]:
        for name in names: atomic_copy(source/folder/name,target/folder/name)
    latest=source/'data/latest.json'; destination=target/'data/latest.json'
    if latest.is_file() and (not destination.exists() or snapshot_time(latest)>snapshot_time(destination)):
        atomic_copy(latest,destination)
    (target/'data/history').mkdir(parents=True,exist_ok=True)
    for history in (source/'data/history').glob('*.json'):
        destination=target/'data/history'/history.name
        if history.is_file() and not destination.exists(): atomic_copy(history,destination)

def launchctl(*args):
    return subprocess.run(['launchctl',*args],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode

def pid(root=None):
    root=Path(root or active_root()); runtime=root/'.runtime'
    try:
        value=int((runtime/'server.pid').read_text()); os.kill(value,0)
        command=subprocess.run(['ps','-p',str(value),'-o','command='],capture_output=True,text=True).stdout
        return value if str(root/'scripts/server.py') in command else None
    except (OSError,ValueError): return None

def start():
    if PLIST.exists():
        launchctl('bootstrap',DOMAIN,str(PLIST)); launchctl('kickstart',DOMAIN+'/'+LABEL); return
    root=active_root(); runtime=root/'.runtime'
    if pid(root): print('Already running'); return
    runtime.mkdir(exist_ok=True)
    with (runtime/'server.log').open('ab') as log:
        child=subprocess.Popen([sys.executable,str(root/'scripts/server.py')],cwd=str(root),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    (runtime/'server.pid').write_text(str(child.pid)); time.sleep(.4)
    if child.poll() is not None: raise RuntimeError('Server exited; inspect .runtime/server.log')
    print('Started http://127.0.0.1:4173')

def stop():
    if PLIST.exists(): launchctl('bootout',DOMAIN,str(PLIST))
    for root in {ROOT,active_root(),INSTALLED}:
        value=pid(root)
        if value: os.kill(value,signal.SIGTERM)
        (root/'.runtime/server.pid').unlink(missing_ok=True)
    print('Stopped')

def launch_config(root=None):
    root=Path(root or ROOT); runtime=root/'.runtime'
    return {'Label':LABEL,'ProgramArguments':[str(Path(sys.executable).resolve()),str(root/'scripts/server.py')],'EnvironmentVariables':{'PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'},'WorkingDirectory':str(root),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'StandardOutPath':str(runtime/'server.log'),'StandardErrorPath':str(runtime/'server.log')}

def install():
    if sys.platform!='darwin': raise RuntimeError('launchd install requires macOS')
    stop()
    deploy_copy(ROOT,INSTALLED)
    (INSTALLED/'.runtime').mkdir(exist_ok=True); PLIST.parent.mkdir(parents=True,exist_ok=True)
    result=subprocess.run([sys.executable,str(INSTALLED/'scripts/build.py'),'--export',str(INSTALLED.parent/'deliverables/GitHub-Star-Top2000.html')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if result.returncode: raise RuntimeError('Installed build failed; service has not been restarted')
    config=launch_config(INSTALLED)
    with PLIST.open('wb') as handle: plistlib.dump(config,handle)
    if launchctl('bootstrap',DOMAIN,str(PLIST)): raise RuntimeError('launchd bootstrap failed')
    print('Installed login service: '+str(PLIST))

def status():
    try:
        with urllib.request.urlopen('http://127.0.0.1:4173/healthz',timeout=3) as response: print(json.dumps(json.load(response),ensure_ascii=False,indent=2))
    except OSError: print('Not serving http://127.0.0.1:4173'); return 1
    return 0

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['start','stop','status','update','install','uninstall']); args=parser.parse_args()
    try:
        if args.command=='start': start()
        elif args.command=='stop': stop()
        elif args.command=='status': return status()
        elif args.command=='update':
            if not refresh(active_root(),force=True): print('Update failed or another update holds the lock'); return 1
            print('Updated')
        elif args.command=='install': install()
        elif args.command=='uninstall': stop(); PLIST.unlink(missing_ok=True); print('Uninstalled login service')
    except (OSError,RuntimeError) as error: print(str(error),file=sys.stderr); return 1
    return 0

if __name__=='__main__': sys.exit(main())
