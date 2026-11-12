# the wiki plugin: tkt wiki, and the pages its init seeds
import os
import re
import shutil

import pytest

from test_tkt import Tracker, install_plugins, run


# a tracker initialized with the wiki plugin installed beside it, so init has seeded its pages
@pytest.fixture(scope="session")
def template(tmp_path_factory):
    root = tmp_path_factory.mktemp("wiki-template")
    install_plugins(root, "wiki")
    db = root / "tracker.fossil"
    r = run("init", db=db)
    assert r.returncode == 0, r.stderr
    return db


@pytest.fixture
def tkt(template, tmp_path):
    install_plugins(tmp_path, "wiki")
    db = tmp_path / "tracker.fossil"
    shutil.copy(template, db)
    return Tracker(db, tmp_path)


class TestWikiSeeding:
    def test_seeds_agent_home(self, tkt):
        home = tkt.ok("run", "wiki", "export", "agents/Home")
        assert "templates/SystemDiagrams" in home and "Keep pages current" in home
        assert "/uv/help/formatting.md" in home

    def test_without_the_plugin_tkt_has_no_wiki_verb(self, tmp_path):
        db = tmp_path / "tracker.fossil"
        assert run("init", db=db).returncode == 0
        r = run("wiki", "ls", db=db)
        if os.environ.get("TKT_CMD") and r.returncode == 0:
            pytest.skip("the tkt under test carries the wiki plugin itself")
        assert r.returncode != 0 and "unknown verb: wiki" in r.stderr

    def test_seeds_template_only_when_missing(self, tkt):
        def page():
            return tkt.ok("run", "wiki", "export", "templates/SystemDiagrams")
        assert "*Instructions:*" in page()
        term = tkt.ok("run", "wiki", "export", "templates/Lexicon")
        assert "## Avoid" in term
        style = tkt.ok("run", "wiki", "export", "templates/Style")
        assert "## Tooling" in style
        flows = tkt.ok("run", "wiki", "export", "templates/Workflows")
        assert "## Recover" in flows
        mapping = tkt.ok("run", "wiki", "export", "templates/Mapping")
        assert "## Unknowns" in mapping
        tkt.ok("run", "wiki", "commit", "templates/SystemDiagrams", "-", "--mimetype", "text/x-markdown", input="# filled in\n")
        tkt.ok("run", "wiki", "commit", "agents/Home", "-", "--mimetype", "text/x-markdown", input="# ours\n")
        tkt.ok("init")
        assert page().strip() == "# filled in"
        home = tkt.ok("run", "wiki", "export", "agents/Home")
        assert home.strip() == "# ours"


class TestWiki:
    def version(self, tkt, page):
        r = tkt("wiki", "show", page)
        assert r.returncode == 0, r.stderr
        return re.search(r"at version ([0-9a-f]{10})", r.stderr).group(1)

    def test_put_creates_then_updates_and_show_prints_it(self, tkt):
        r = tkt("wiki", "put", "notes/Plan", input="# Plan\n\none\n")
        assert r.returncode == 0 and "created notes/Plan" in r.stderr
        assert tkt.ok("wiki", "show", "notes/Plan") == "# Plan\n\none\n"
        r = tkt("wiki", "put", "notes/Plan", input="# Plan\n\ntwo\n")
        assert "updated notes/Plan" in r.stderr
        assert "two" in tkt.ok("wiki", "show", "notes/Plan")

    def test_put_stores_markdown_and_skips_unchanged_text(self, tkt):
        tkt.ok("wiki", "put", "notes/Plan", input="# Plan\n")
        r = tkt("wiki", "put", "notes/Plan", input="# Plan\n")
        assert "unchanged" in r.stderr
        assert tkt.sql("select count(*) from event where type='w' and substr(comment,2)='notes/Plan';") == "1"
        uuid = tkt.sql("select b.uuid from event e join blob b on b.rid=e.objid where e.type='w' and substr(e.comment,2)='notes/Plan';")
        assert "N text/x-markdown" in tkt.ok("run", "artifact", uuid)

    def test_put_refuses_an_empty_body(self, tkt):
        tkt.fails("wiki", "put", "notes/Plan", input="  \n", match="tkt wiki rm")

    def test_put_rewrites_bare_ticket_hashes(self, tkt):
        id = tkt.new("linked")
        tkt.ok("wiki", "put", "notes/Plan", input=f"see [{id}]\n")
        assert f"[]({id})" in tkt.ok("wiki", "show", "notes/Plan")

    def test_base_refuses_a_stale_write(self, tkt):
        tkt.ok("wiki", "put", "notes/Plan", input="one\n")
        v = self.version(tkt, "notes/Plan")
        tkt.ok("wiki", "put", "notes/Plan", "--base", v, input="two\n")
        tkt.fails("wiki", "put", "notes/Plan", "--base", v, input="three\n", match="changed since version")
        tkt.fails("wiki", "rm", "notes/Plan", "--base", v, match="changed since version")
        assert "two" in tkt.ok("wiki", "show", "notes/Plan")

    def test_rm_hides_the_page_from_show_and_list(self, tkt):
        tkt.ok("wiki", "put", "notes/Plan", input="one\n")
        tkt.ok("wiki", "rm", "notes/Plan")
        tkt.fails("wiki", "show", "notes/Plan", match="no wiki page")
        assert "notes/Plan" not in tkt.ok("wiki", "list")
        tkt.fails("wiki", "rm", "notes/Plan", match="no wiki page")
        tkt.ok("wiki", "put", "notes/Plan", input="back\n")
        assert "back" in tkt.ok("wiki", "show", "notes/Plan")

    def test_list_filters_by_prefix(self, tkt):
        tkt.ok("wiki", "put", "notes/Plan", input="x\n")
        tkt.ok("wiki", "put", "notesy", input="x\n")
        out = tkt.ok("wiki", "list", "notes")
        assert "| notes/Plan |" in out and "notesy" not in out and "templates/" not in out
        assert "| templates/Style |" in tkt.ok("wiki", "list")

    def test_copy_starts_a_page_from_a_template(self, tkt):
        tkt.ok("wiki", "copy", "templates/Style", "Style")
        assert tkt.ok("wiki", "show", "Style") == tkt.ok("wiki", "show", "templates/Style")
        tkt.fails("wiki", "copy", "templates/Style", "Style", match="already exists")
        tkt.fails("wiki", "copy", "templates/Nope", "Nope", match="no wiki page")
        tkt.fails("wiki", "cp", "Style", "Style2", match="not a template")
        tkt.ok("wiki", "cp", "Style", "Style2", "--force")
        assert tkt.ok("wiki", "get", "Style2") == tkt.ok("wiki", "show", "Style")
        assert "| Style2 |" in tkt.ok("wiki", "ls")

    def test_agents_pages_need_force(self, tkt):
        tkt.fails("wiki", "put", "agents/Home", input="x\n", match="--force")
        tkt.fails("wiki", "rm", "agents/Home", match="--force")
        tkt.fails("wiki", "copy", "templates/Style", "agents/Style", match="--force")
        tkt.ok("wiki", "put", "agents/Home", "--force", input="# ours\n")
        assert tkt.ok("wiki", "show", "agents/Home") == "# ours\n"

    def test_rejects_bad_names_and_usage(self, tkt):
        tkt.fails("wiki", "put", "branch/trunk", input="x\n", match="reserves")
        tkt.fails("wiki", "put", "/lead", input="x\n", match="bad page name")
        tkt.fails("wiki", "show", match="usage: tkt wiki")
        tkt.fails("wiki", "put", "x", "--bogus", input="x\n", match="usage: tkt wiki")
        tkt.fails("wiki", match="usage: tkt wiki")
