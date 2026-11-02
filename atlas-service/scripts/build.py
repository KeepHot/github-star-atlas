#!/usr/bin/env python3
"""Build an allowlisted public site; switch live generation atomically."""
import argparse
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def prune_generations(directory, active, now=None):
    now = time.time() if now is None else now
    candidates = sorted((p for p in Path(directory).iterdir() if p.is_dir() and not p.is_symlink()), key=lambda p:p.stat().st_mtime, reverse=True)
    keep = set(candidates[:3]) | {Path(active)}
    for old in candidates:
        if old not in keep and now-old.stat().st_mtime > 3600:
            shutil.rmtree(old, ignore_errors=True)

def build(root=ROOT, export=None):
    root = Path(root)
    data = json.loads((root/'data/latest.json').read_text(encoding='utf-8'))
    if data.get('schemaVersion') != 1 or len(data.get('repositories', [])) != data.get('targetCount') or not data.get('targetCount'):
        raise ValueError('Refusing incomplete dataset')
    template = (root/'web/index.html').read_text(encoding='utf-8')
    if template.count('<!-- ATLAS_DATA -->') != 1:
        raise ValueError('Expected exactly one ATLAS_DATA injection point')
    encoded = json.dumps(data, ensure_ascii=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    page = template.replace('<!-- ATLAS_DATA -->','<script>window.ATLAS_DATA='+encoded+';</script>')
    css = (root/'web/styles.css').read_text(encoding='utf-8')
    js = (root/'web/app.js').read_text(encoding='utf-8')
    generations = root/'.builds'; generations.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='site-',dir=str(generations)))
    committed=False
    try:
        (stage/'index.html').write_text(page,encoding='utf-8')
        (stage/'styles.css').write_text(css,encoding='utf-8')
        (stage/'app.js').write_text(js,encoding='utf-8')
        (stage/'latest.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        standalone=page.replace('<link rel="stylesheet" href="./styles.css">','<style>'+css+'</style>').replace('<script src="./app.js"></script>','<script>'+js.replace('</script','<\\/script')+'</script>')
        export = Path(export) if export else root.parent/'deliverables/GitHub-Star-Top2000.html'
        export.parent.mkdir(parents=True,exist_ok=True)
        temp_export=export.with_suffix('.tmp'); temp_export.write_text(standalone,encoding='utf-8'); os.replace(str(temp_export),str(export))
        link=root/'.dist-next'
        if link.is_symlink() or link.exists(): link.unlink()
        link.symlink_to(stage.relative_to(root),target_is_directory=True)
        live=root/'dist'
        if live.exists() and not live.is_symlink():
            # One-time migration from an old directory. Subsequent switches are atomic.
            backup=generations/'legacy'
            if backup.exists(): shutil.rmtree(backup)
            live.rename(backup)
        os.replace(str(link),str(live))
        committed=True
        try: prune_generations(generations, stage)
        except OSError: pass  # Housekeeping cannot roll back a published generation.
    except Exception:
        if not committed: shutil.rmtree(stage,ignore_errors=True)
        raise
    return root/'dist'

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--export',type=Path)
    args=parser.parse_args(); build(export=args.export)
    print('Built public site and standalone export')
