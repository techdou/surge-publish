#!/usr/bin/env python3
"""Unit tests for surge-publish skill.

Covers the pure (non-network) helpers: ANSI stripping, URL extraction,
project pre-flight checks, .surgeignore parsing, ignore-file merging.
Network commands (publish/list/etc.) are not tested here because they
require surge credentials; the fail-fast auth guard is tested instead.

Run: python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import surge_common as sc  # noqa: E402


SAMPLE_SITE = Path(__file__).resolve().parent.parent / "assets" / "sample-site"


class TestStripAnsi(unittest.TestCase):
    def test_strips_color_codes(self):
        text = "\x1b[34mSurge.sh\x1b[39m \x1b[93mStatic Web Publishing\x1b[39m"
        self.assertEqual(sc._strip_ansi(text), "Surge.sh Static Web Publishing")

    def test_passes_plain_text(self):
        self.assertEqual(sc._strip_ansi("hello"), "hello")

    def test_handles_none(self):
        self.assertEqual(sc._strip_ansi(None), "")


class TestExtractPublishedUrl(unittest.TestCase):
    def test_extracts_url(self):
        out = "Success! - Published to https://shiny-example.surge.sh"
        self.assertEqual(sc.extract_published_url(out), "shiny-example.surge.sh")

    def test_no_url_returns_none(self):
        self.assertIsNone(sc.extract_published_url("no urls here"))

    def test_empty(self):
        self.assertIsNone(sc.extract_published_url(""))


class TestSurgeAvailable(unittest.TestCase):
    """The skill must not crash if surge isn't on PATH; it should report False."""

    def test_returns_bool(self):
        self.assertIsInstance(sc.surge_available(), bool)

    def test_version_is_none_or_string(self):
        v = sc.surge_version()
        self.assertTrue(v is None or isinstance(v, str))


class TestCheckProject(unittest.TestCase):
    def test_sample_site_passes(self):
        chk = sc.check_project(SAMPLE_SITE)
        self.assertEqual(chk.issues, [], f"sample site should have no issues, got: {chk.issues}")
        self.assertTrue(chk.has_index)
        self.assertTrue(chk.has_404)
        self.assertTrue(chk.has_surgeignore)

    def test_missing_path(self):
        chk = sc.check_project(Path("/no/such/path/xyz"))
        self.assertTrue(any("does not exist" in i for i in chk.issues))

    def test_empty_dir_no_index(self):
        with tempfile.TemporaryDirectory() as d:
            chk = sc.check_project(Path(d))
            self.assertTrue(any("index.html" in i and "200.html" in i for i in chk.issues))

    def test_200_shell_substitutes_for_index(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "200.html").write_text("<html></html>")
            chk = sc.check_project(Path(d))
            self.assertFalse(any("index.html" in i for i in chk.issues))

    def test_cname_read(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.html").write_text("<html></html>")
            (Path(d) / "CNAME").write_text("example.com\n")
            chk = sc.check_project(Path(d))
            self.assertEqual(chk.cname, "example.com")

    def test_empty_cname_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.html").write_text("<html></html>")
            (Path(d) / "CNAME").write_text("")
            chk = sc.check_project(Path(d))
            self.assertTrue(any("CNAME" in i and "empty" in i for i in chk.issues))

    def test_sensitive_env_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.html").write_text("<html></html>")
            (Path(d) / ".env").write_text("SECRET=abc")
            chk = sc.check_project(Path(d))
            self.assertTrue(any(".env" in i for i in chk.issues))

    def test_sensitive_env_covered_by_surgeignore(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.html").write_text("<html></html>")
            (Path(d) / ".env").write_text("SECRET=abc")
            (Path(d) / ".surgeignore").write_text(".env\n")
            chk = sc.check_project(Path(d))
            self.assertFalse(any(".env" in i for i in chk.issues))

    def test_node_modules_warning_without_surgeignore(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.html").write_text("<html></html>")
            (Path(d) / "node_modules").mkdir()
            chk = sc.check_project(Path(d))
            self.assertTrue(any("node_modules" in n for n in chk.notes))


class TestMergeIgnoreFiles(unittest.TestCase):
    def test_merges_gitignore_and_surgeignore(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".gitignore").write_text("node_modules/\n*.log\n")
            (Path(d) / ".surgeignore").write_text(".env\n")
            body = sc.merge_ignore_files(Path(d))
            self.assertIn("node_modules/", body)
            self.assertIn("*.log", body)
            self.assertIn(".env", body)

    def test_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".gitignore").write_text("foo\nbar\n")
            (Path(d) / ".surgeignore").write_text("bar\nbaz\n")
            body = sc.merge_ignore_files(Path(d))
            # "bar" should appear only once
            self.assertEqual(body.count("bar"), 1)
            self.assertIn("foo", body)
            self.assertIn("baz", body)

    def test_empty_when_neither_exists(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sc.merge_ignore_files(Path(d)), "")


class TestAuthFailFast(unittest.TestCase):
    """When unauthenticated and no token, run_surge must raise immediately
    rather than letting surge hang on an interactive prompt."""

    def test_run_surge_raises_without_auth(self):
        # Temporarily strip auth env vars so whoami() returns unauthenticated.
        saved = {k: os.environ.pop(k, None) for k in ("SURGE_TOKEN", "SURGE_LOGIN")}
        try:
            with self.assertRaises(sc.SurgeError) as ctx:
                sc.run_surge(["list"], require_auth=True)
            self.assertIn("Not authenticated", str(ctx.exception))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


class TestSurgeResult(unittest.TestCase):
    def test_ok_property(self):
        r = sc.SurgeResult(command=["x"], returncode=0, stdout="", stderr="")
        self.assertTrue(r.ok)
        r2 = sc.SurgeResult(command=["x"], returncode=1, stdout="", stderr="")
        self.assertFalse(r2.ok)


if __name__ == "__main__":
    unittest.main()
