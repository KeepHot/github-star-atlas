#!/usr/bin/env python3
"""Official GitHub collector. Python 3.9+, no third-party dependencies."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PERIODS = ('daily', 'weekly', 'monthly')
CATEGORIES = {'learn','lists','agent','ai','web','backend','dev','ops','apps','media','security','data'}

class CollectionError(RuntimeError):
    pass

class LockBusy(CollectionError):
    pass

def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))

def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError): return default

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

@contextmanager
def update_lock(output):
    # flock releases automatically on process death; the lock inode is never removed.
    import fcntl
    path = Path(str(output) + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise LockBusy('Another update is running') from None
        try: yield
        finally: fcntl.flock(lock, fcntl.LOCK_UN)

class GitHubClient:
    def __init__(self, timeout=35, retries=3, max_wait=65):
        self.timeout, self.retries, self.max_wait = timeout, retries, max_wait
        self.last_search_at = 0.0
        self.token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        self.use_gh = not self.token and bool(shutil.which('gh'))
        if self.use_gh:
            try:
                self.use_gh = subprocess.run(['gh','auth','status'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10).returncode == 0
            except (OSError, subprocess.TimeoutExpired): self.use_gh = False

    def get(self, url, api=False):
        for attempt in range(self.retries + 1):
            wait = min(2 ** attempt * 3, self.max_wait)
            try:
                if api and self.use_gh:
                    result = subprocess.run(['gh','api','--include',url,'-H','Accept: application/vnd.github+json'], capture_output=True, text=True, timeout=self.timeout)
                    head, separator, body = result.stdout.replace('\r\n','\n').partition('\n\n')
                    if result.returncode:
                        headers = dict((k.strip().lower(),v.strip()) for line in head.splitlines()[1:] if ':' in line for k,v in [line.split(':',1)])
                        try: wait = max(wait,float(headers.get('retry-after',0)),float(headers.get('x-ratelimit-reset',0))-time.time()+1)
                        except ValueError: pass
                        if wait > self.max_wait: raise CollectionError('GitHub rate limit exceeds bounded retry window')
                        raise CollectionError('GitHub CLI request failed')
                    return json.loads(body if separator else result.stdout)
                headers = {'User-Agent': 'GitHub-Star-Atlas/1.0', 'Accept': 'application/vnd.github+json' if api else 'text/html'}
                if api and self.token: headers['Authorization'] = 'Bearer ' + self.token
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=self.timeout) as response:
                    body = response.read().decode('utf-8')
                return json.loads(body) if api else body
            except urllib.error.HTTPError as error:
                if error.code not in (403,429,500,502,503,504): raise CollectionError('GitHub HTTP request failed (%s)' % error.code) from None
                reset = error.headers.get('X-RateLimit-Reset')
                retry = error.headers.get('Retry-After')
                try: wait = max(wait, float(retry or 0), float(reset or 0)-time.time()+1)
                except ValueError: pass
                if wait > self.max_wait: raise CollectionError('GitHub rate limit exceeds bounded retry window') from None
            except (OSError, ValueError, subprocess.TimeoutExpired, CollectionError): pass
            if wait > self.max_wait: raise CollectionError('GitHub rate limit exceeds bounded retry window') from None
            if attempt == self.retries: raise CollectionError('GitHub request failed after bounded retries') from None
            time.sleep(wait)

    def search(self, lo, hi, page, per_page):
        delay = 2.2 - (time.monotonic() - self.last_search_at)
        if delay > 0: time.sleep(delay)
        self.last_search_at = time.monotonic()
        print('GitHub search stars %s..%s page %s' % (lo,hi,page), file=__import__('sys').stderr, flush=True)
        query = 'is:public fork:false stars:%s..%s' % (lo,hi)
        params = urllib.parse.urlencode({'q':query,'sort':'stars','order':'desc','per_page':per_page,'page':page})
        return self.get('https://api.github.com/search/repositories?' + params, api=True)

def _fetch_top(search, target=2000, ceiling=1000, page_size=100, upper=2147483647):
    """Traverse disjoint integer ranges high-first. Never accept partial search data."""
    found, seen = [], set()
    def visit(lo, hi):
        if len(found) >= target: return
        first = search(lo, hi, 1, page_size)
        incomplete = first.get('incomplete_results', False)
        count = first.get('total_count')
        if not isinstance(count, int) or count < 0: raise CollectionError('Invalid GitHub search count')
        if count > ceiling or incomplete:
            maximum = first.get('items', [{}])[0].get('stargazers_count') if first.get('items') else None
            if not incomplete and isinstance(maximum, int) and lo <= maximum < hi: hi = maximum
            if lo == hi: raise CollectionError('Star tie exceeds GitHub search ceiling or incomplete result')
            middle = (lo+hi)//2
            visit(middle+1, hi)
            visit(lo, middle)
            return
        remaining = min(count, target-len(found))
        previous = None
        for page in range(1, math.ceil(remaining/page_size)+1):
            result = first if page == 1 else search(lo, hi, page, page_size)
            if result.get('incomplete_results'): raise CollectionError('Search changed during pagination')
            items = result.get('items', [])
            expected = min(page_size, count-(page-1)*page_size)
            if len(items) != expected: raise CollectionError('Missing search results')
            for row in items[:remaining-(page-1)*page_size]:
                name, stars = row.get('full_name'), row.get('stargazers_count')
                if not name or name.lower() in seen or not isinstance(stars, int) or not lo <= stars <= hi or row.get('private') or row.get('fork') or (previous is not None and stars > previous):
                    raise CollectionError('Duplicate or inconsistent search results')
                seen.add(name.lower()); found.append(row); previous = stars
    if upper > 1000000:
        probe = search(1000001, upper, 1, page_size)
        if not probe.get('incomplete_results') and probe.get('total_count') == 0:
            upper = 1000000
        elif not probe.get('incomplete_results') and probe.get('items'):
            upper = probe['items'][0]['stargazers_count']
    visit(0, upper)
    if len(found) != target: raise CollectionError('Top repository collection is incomplete')
    return sorted(found, key=lambda row: (-row['stargazers_count'], row['full_name'].lower()))

def fetch_top(search, target=2000, ceiling=1000, page_size=100, upper=2147483647):
    for attempt in range(3):
        try:
            return _fetch_top(search, target, ceiling, page_size, upper)
        except CollectionError:
            if attempt == 2: raise

class TrendingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.rows, self.row = [], [], None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'article' and 'Box-row' in attrs.get('class','').split():
            self.row = {'name':None,'original':'','language':None,'stars':None,'periodStars':None}
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):
            self.stack.append((tag,attrs,[]))
    def handle_data(self, text):
        for _, _, chunks in self.stack: chunks.append(text)
    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack)-1,-1,-1) if self.stack[i][0] == tag), None)
        if index is None: return
        _, attrs, chunks = self.stack[index]
        text = ' '.join(''.join(chunks).split())
        if self.row is not None:
            href = attrs.get('href','')
            if tag == 'a' and any(t == 'h2' for t,_,_ in self.stack) and re.fullmatch(r'/[\w.-]+/[\w.-]+/?',href): self.row['name'] = href.strip('/')
            if tag == 'p': self.row['original'] = text
            if attrs.get('itemprop') == 'programmingLanguage': self.row['language'] = text
            if tag == 'a' and href.endswith('/stargazers'):
                match = re.search(r'[\d,]+', text)
                if match: self.row['stars'] = int(match.group().replace(',',''))
            match = re.search(r'([\d,]+)\s+stars?\s+(?:today|this week|this month)',text)
            if match and tag == 'span': self.row['periodStars'] = int(match.group(1).replace(',',''))
            if tag == 'article': self.rows.append(self.row); self.row = None
        del self.stack[index:]

def decorate(name, original, editorial):
    override = editorial.get(name, {})
    summary = override.get('summary') or original or ''
    category = override.get('category', 'dev')
    return {'category': category if category in CATEGORIES else 'dev', 'summary':summary,'original':original or '', 'summarySource':'editorial' if override.get('summary') else 'original'}

def parse_trending(html, editorial=None):
    parser = TrendingParser(); parser.feed(html)
    rows, seen = [], set()
    for row in parser.rows:
        name = row['name']
        if not name or name.lower() in seen or row['stars'] is None or row['periodStars'] is None: raise CollectionError('Invalid GitHub Trending markup')
        seen.add(name.lower())
        row.update(decorate(name,row['original'],editorial or {}))
        row.update(rank=len(rows)+1, url='https://github.com/'+name)
        rows.append(row)
    if not rows: raise CollectionError('GitHub Trending returned no repositories')
    return rows

def collect_trend(period, fetch, old, editorial, now):
    source = 'https://github.com/trending?since=' + period
    try:
        return {'updatedAt':now,'source':source,'status':'ok','error':None,'repositories':parse_trending(fetch(source),editorial)}
    except Exception:
        return {'updatedAt':old.get('updatedAt'),'source':source,'status':'stale' if old.get('repositories') else 'error','error':'GitHub Trending collection failed','repositories':old.get('repositories',[])}

def valid_snapshot(snapshot):
    try:
        return isinstance(snapshot, dict) and isinstance(snapshot.get('stars'), dict) and parse_time(snapshot['at']).tzinfo is not None
    except (ValueError, TypeError, KeyError, AttributeError): return False

def observed_growth(name, stars, snapshots, now):
    snapshots = [s for s in snapshots if valid_snapshot(s)]
    growth = {}
    for period, days in [('daily',1),('weekly',7),('monthly',30)]:
        target = now-timedelta(days=days)
        # Baselines must be within 12 hours of the desired boundary; never substitute a week-old value for one day.
        eligible = [s for s in snapshots if target-timedelta(hours=12) <= parse_time(s['at']) <= target and name in s['stars']]
        baseline = max(eligible, key=lambda s:s['at']) if eligible else None
        growth[period] = stars-baseline['stars'][name] if baseline else None
    return growth

def collect(output=ROOT/'data/latest.json', force=False, client=None, target=2000):
    output = Path(output)
    with update_lock(output):
        old = read_json(output, {})
        now = datetime.now(timezone.utc); stamp = iso(now)
        if not isinstance(old, dict): old = {}
        try: recent = old.get('topUpdatedAt') and now-parse_time(old['topUpdatedAt']) < timedelta(hours=3)
        except (ValueError, TypeError, AttributeError): recent = False
        if not force and recent: return old
        client = client or GitHubClient()
        # A failed full top collection leaves latest.json untouched.
        rows = fetch_top(client.search, target=target)
        editorial = read_json(output.parent/'editorial.json', {})
        history_dir = output.parent/'history'
        snapshots = [read_json(p) for p in sorted(history_dir.glob('*.json'))]
        snapshots = [s for s in snapshots if valid_snapshot(s) and parse_time(s['at']) >= now-timedelta(days=36)]
        repos = []
        for rank,row in enumerate(rows,1):
            name = row['full_name']; stars = row['stargazers_count']
            item = dict(rank=rank,name=name,url='https://github.com/'+name,stars=stars,language=row.get('language'),archived=bool(row.get('archived')),growth=observed_growth(name,stars,snapshots,now))
            item.update(decorate(name,row.get('description'),editorial)); repos.append(item)
        trends = {p:collect_trend(p, client.get, old.get('trending',{}).get(p,{}), editorial, stamp) for p in PERIODS}
        errors = [p + ': GitHub Trending collection failed' for p in PERIODS if trends[p]['status'] != 'ok']
        snapshot = {'at':stamp,'stars':{r['name']:r['stars'] for r in repos}}
        snapshots.append(snapshot)
        result = dict(schemaVersion=1,generatedAt=stamp,topUpdatedAt=stamp,targetCount=target,source='https://api.github.com/search/repositories',repositories=repos,trending=trends,status={'state':'partial' if errors else 'ok','lastAttemptAt':stamp,'lastSuccessAt':stamp,'errors':errors},history={'oldestSnapshotAt':snapshots[0]['at'],'snapshotCount':len(snapshots)})
        atomic_json(history_dir/(now.strftime('%Y%m%dT%H%M%S%fZ')+'.json'), snapshot)
        atomic_json(output, result)
        for path in history_dir.glob('*.json'):
            previous = read_json(path)
            if valid_snapshot(previous) and parse_time(previous['at']) < now-timedelta(days=36): path.unlink()
        return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'data/latest.json')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    try:
        result = collect(args.output, args.force)
        print('Collected %s repositories; status=%s' % (len(result['repositories']),result['status']['state']))
    except LockBusy:
        print('Another collection is running.', file=__import__('sys').stderr)
        return 75
    except CollectionError as error:
        print('Collection failed: %s; previous complete snapshot preserved.' % error, file=__import__('sys').stderr)
        return 1
    except Exception:
        print('Collection failed; previous complete snapshot preserved.', file=__import__('sys').stderr)
        return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
