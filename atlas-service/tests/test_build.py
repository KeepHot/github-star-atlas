import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('atlas_build', Path(__file__).parents[1] / 'scripts/build.py')
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

class BuildTests(unittest.TestCase):
    def test_safe_embedding_and_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'web').mkdir(); (root/'data').mkdir()
            (root/'web/index.html').write_text('<style></style><!-- ATLAS_DATA --><link rel="stylesheet" href="./styles.css"><script src="./app.js"></script>')
            (root/'web/styles.css').write_text('body{}')
            (root/'web/app.js').write_text('console.log(1)')
            (root/'data/latest.json').write_text(json.dumps({'schemaVersion':1,'targetCount':1,'repositories':[{'name':'</script><script>bad()'}]}))
            build.build(root, root/'export.html')
            page = (root/'dist/index.html').read_text()
            self.assertNotIn('</script><script>bad()', page)
            self.assertIn('\\u003c/script', page)
            self.assertEqual({p.name for p in (root/'dist').iterdir()}, {'index.html','app.js','styles.css','latest.json'})
            self.assertNotIn('src="./app.js"', (root/'export.html').read_text())
    def test_generation_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i in range(6):
                path=root/str(i); path.mkdir(); os.utime(path,(i,i))
            build.prune_generations(root,root/'0',now=10000)
            self.assertEqual({p.name for p in root.iterdir()},{'0','3','4','5'})
    def test_pruning_failure_cannot_remove_published_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'web').mkdir(); (root/'data').mkdir()
            (root/'web/index.html').write_text('<!-- ATLAS_DATA -->')
            (root/'web/styles.css').write_text('body{}')
            (root/'web/app.js').write_text('')
            (root/'data/latest.json').write_text(json.dumps({'schemaVersion':1,'targetCount':1,'repositories':[{'name':'safe/repo'}]}))
            with patch.object(build,'prune_generations',side_effect=OSError('permissions')):
                build.build(root,root/'export.html')
            self.assertTrue((root/'dist/index.html').is_file())
            self.assertIn('safe/repo',(root/'dist/index.html').read_text())
    def test_invalid_build_preserves_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'dist').mkdir(); (root/'dist/index.html').write_text('good')
            with self.assertRaises(Exception): build.build(root, root/'export.html')
            self.assertEqual((root/'dist/index.html').read_text(), 'good')
