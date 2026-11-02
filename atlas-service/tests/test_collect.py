import importlib.util
import pathlib
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

PATH = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'collect.py'
spec = importlib.util.spec_from_file_location('collect', PATH)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def repo(n, stars):
    return {'full_name': 'o/r' + str(n), 'stargazers_count': stars, 'html_url': 'https://github.com/o/r' + str(n), 'fork': False, 'private': False}

class CollectorTests(unittest.TestCase):
    def test_top_splits_disjoint_ranges_and_pages(self):
        rows = [repo(i, 30-i//2) for i in range(18)]
        calls = []
        def search(lo, hi, page, per_page):
            calls.append((lo, hi, page))
            selected = sorted([r for r in rows if lo <= r['stargazers_count'] <= hi], key=lambda r: -r['stargazers_count'])
            return {'total_count': len(selected), 'incomplete_results': False, 'items': selected[(page-1)*per_page:page*per_page]}
        result = c.fetch_top(search, target=10, ceiling=6, page_size=3, upper=32)
        self.assertEqual([r['stargazers_count'] for r in result], [r['stargazers_count'] for r in rows[:10]])
        self.assertEqual(len({r['full_name'] for r in result}), 10)
        self.assertGreater(len(calls), 3)

    def test_rejects_incomplete_duplicate_and_unsplittable(self):
        for response in [dict(total_count=2, incomplete_results=True, items=[]), dict(total_count=2, items=[repo(1, 1), repo(1, 1)])]:
            with self.assertRaises(c.CollectionError):
                c.fetch_top(lambda *args: response, target=2, upper=1)
        with self.assertRaises(c.CollectionError):
            c.fetch_top(lambda *args: dict(total_count=8, items=[]), target=2, upper=0, ceiling=3)

    def test_search_consistency_failure_retries_complete_attempt(self):
        calls = []
        def search(*args):
            calls.append(args)
            return dict(total_count=1,incomplete_results=len(calls)==1,items=[repo(1,5)])
        self.assertEqual(c.fetch_top(search,target=1,upper=10)[0]['full_name'],'o/r1')
        self.assertEqual(len(calls),3)

    def test_upper_bound_uses_actual_maximum(self):
        calls = []
        def search(lo,hi,page,size):
            calls.append((lo,hi))
            rows = [repo(i,100-i) for i in range(10) if lo <= 100-i <= hi]
            return dict(total_count=len(rows),items=rows[(page-1)*size:page*size])
        c.fetch_top(search,target=5,ceiling=6,page_size=3)
        self.assertLess(len(calls),10)

    def test_trending_preserves_rank_and_period_count(self):
        html = '''<article class="Box-row"><h2><a href="/owner/repo"> owner / repo </a></h2><p>A &amp; B</p><span itemprop="programmingLanguage">Python</span><a href="/owner/repo/stargazers"><svg></svg>12,345</a><span class="d-inline-block float-sm-right">1,234 stars this week</span></article><article class="Box-row"><h2><a href="/a/b">a / b</a></h2><p>Second</p><a href="/a/b/stargazers">400</a><span>20 stars this week</span></article>'''
        rows = c.parse_trending(html)
        self.assertEqual([(r['name'], r['rank'], r['periodStars']) for r in rows], [('owner/repo', 1, 1234), ('a/b', 2, 20)])
        self.assertEqual(rows[0]['stars'], 12345)
        self.assertEqual(rows[0]['original'], 'A & B')
        with self.assertRaises(c.CollectionError): c.parse_trending('<html>rate limit</html>')

    def test_growth_requires_real_baseline(self):
        now = datetime(2026,11,3,tzinfo=timezone.utc)
        snapshots = [{'at': c.iso(now-timedelta(days=7)), 'stars': {'o/r': 50}}]
        growth = c.observed_growth('o/r', 80, snapshots, now)
        self.assertEqual(growth, {'daily': None, 'weekly': 30, 'monthly': None})

    def test_trend_failure_retains_timestamp_and_rows(self):
        old = {'updatedAt': 'old', 'repositories': [{'name':'a/b'}]}
        result = c.collect_trend('weekly', lambda url: (_ for _ in ()).throw(RuntimeError('secret')), old, {}, 'new')
        self.assertEqual(result['updatedAt'], 'old')
        self.assertEqual(result['repositories'], old['repositories'])
        self.assertEqual(result['status'], 'stale')
        self.assertNotIn('secret', result['error'])

    def test_excessive_retry_window_never_sleeps(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        client = c.GitHubClient.__new__(c.GitHubClient)
        client.timeout, client.retries, client.max_wait = 1, 1, 65
        client.token, client.use_gh = None, True
        response = SimpleNamespace(returncode=1,stdout='HTTP/2.0 429 Too Many Requests\nRetry-After: 3601\n\n{}')
        with patch.object(c.subprocess,'run',return_value=response), patch.object(c.time,'sleep') as sleep:
            with self.assertRaises(c.CollectionError): client.get('https://api.github.com/test',api=True)
            sleep.assert_not_called()

    def test_corrupt_json_and_snapshot_timestamp_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/'bad.json'
            path.write_text('{bad')
            self.assertEqual(c.read_json(path,{}),{})
        self.assertEqual(c.observed_growth('x/y',10,[{'at':'broken','stars':{}}],datetime.now(timezone.utc)),dict(daily=None,weekly=None,monthly=None))

    def test_cli_auth_honors_retry_after_without_exposing_output(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        client = c.GitHubClient.__new__(c.GitHubClient)
        client.timeout, client.retries, client.max_wait = 1, 1, 65
        client.token, client.use_gh = None, True
        responses = [SimpleNamespace(returncode=1,stdout='HTTP/2.0 429 Too Many Requests\nRetry-After: 4\n\n{}'), SimpleNamespace(returncode=0,stdout='HTTP/2.0 200 OK\nContent-Type: application/json\n\n{"ok":true}')]
        with patch.object(c.subprocess,'run',side_effect=responses), patch.object(c.time,'sleep') as sleep:
            self.assertEqual(client.get('https://api.github.com/test',api=True),{'ok':True})
            sleep.assert_called_once_with(4)

    def test_failed_top_preserves_previous_bytes(self):
        class Broken:
            def search(self, *args):
                raise c.CollectionError('network')
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d)/'latest.json'
            path.write_text('{"old":true}')
            with self.assertRaises(c.CollectionError):
                c.collect(path, force=True, client=Broken(), target=2)
            self.assertEqual(path.read_text(), '{"old":true}')

    def test_complete_collection_editorial_and_history(self):
        class Fake:
            def search(self, lo, hi, page, per_page):
                rows = [repo(1,100),repo(2,90)]
                return dict(total_count=2,incomplete_results=False,items=rows)
            def get(self, url):
                return '<article class="Box-row"><h2><a href="/o/r1">o/r1</a></h2><a href="/o/r1/stargazers">100</a><span>5 stars today</span></article>'
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d)/'latest.json'
            c.atomic_json(path.parent/'editorial.json', {'o/r1':{'category':'learn','summary':'中文'}})
            result = c.collect(path, force=True, client=Fake(), target=2)
            self.assertEqual(result['repositories'][0]['summarySource'],'editorial')
            self.assertEqual(result['repositories'][0]['growth'],dict(daily=None,weekly=None,monthly=None))
            self.assertEqual(result['status']['state'],'ok')
            self.assertEqual(len(list((path.parent/'history').glob('*.json'))),1)
            self.assertEqual(c.collect(path, client=object()),result)

    def test_atomic_json_and_exclusive_lock(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)/'latest.json'
            c.atomic_json(p, {'ok': 1})
            self.assertEqual(c.read_json(p), {'ok':1})
            with c.update_lock(p):
                with self.assertRaises(c.LockBusy):
                    with c.update_lock(p): pass
            with c.update_lock(p): pass

if __name__ == '__main__': unittest.main()
