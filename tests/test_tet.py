"""Interface tests for tet, the proposals companion to tkt, each against a fresh tracker copied from one template."""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from test_tkt import BASH, PLUGINS, TKT as TKT_ARGV, Tracker, install_plugins, run

TKT = Path(__file__).resolve().parent.parent / "tkt"


# tet is a plugin: the copy installed beside the tracker, else this repository's own
def tet_main(db):
    main = Path(db).parent / ".tkt" / "plugins" / "tet" / "main.sh"
    return main if main.exists() else PLUGINS / "tet" / "main.sh"


# tet's command line: the plugin's main by default, or through a distribution's tkt, which runs the copy installed beside
# the tracker with its own fossil and bash, as a user's `tkt tet` does
def tet_argv(db):
    return [*TKT_ARGV, "tet"] if os.environ.get("TKT_CMD") else [BASH, str(tet_main(db))]


def tet(*args, db, input="", cwd=None, extra=None, stdin=None):
    env = {k: v for k, v in os.environ.items() if k not in ("TKT_DB", "TET_RUN")}
    env.update(TKT_DB=str(db), TKT_CDN="file:///nonexistent/tkt-cdn", **(extra or {}))
    return subprocess.run([*tet_argv(db), *args], input=input, capture_output=True, text=True, env=env, cwd=cwd)


# proposals can target wiki pages, so the wiki plugin is installed too; tkt init runs both plugins' inits
@pytest.fixture(scope="session")
def template(tmp_path_factory):
    root = tmp_path_factory.mktemp("tet-template")
    install_plugins(root, "tet", "wiki")
    db = root / "tracker.fossil"
    r = run("init", db=db)
    assert r.returncode == 0, r.stderr
    return db


@pytest.fixture
def tkt(template, tmp_path):
    install_plugins(tmp_path, "tet", "wiki")
    db = tmp_path / "tracker.fossil"
    shutil.copy(template, db)
    assert tet("init", db=db).returncode == 0
    return Tracker(db, tmp_path)


def propose(tkt, *args, input="", run_name="r1", flags=()):
    r = tet("propose", "--run", run_name, *flags, *args, db=tkt.db, input=input)
    assert r.returncode == 0, r.stderr
    m = re.fullmatch(r"proposed (\d+)\n", r.stdout)
    assert m, r.stdout
    return int(m.group(1))


def row(tkt, pid, cols):
    return tkt.sql(f"select {cols} from fx_proposal where id={pid};")


def cgi(tkt, path="", body="", method=None, referer="http://localhost:1/ext/tet/main.sh"):
    env = {
        "GATEWAY_INTERFACE": "CGI/1.0",
        "FOSSIL_REPOSITORY": tkt.db.name,
        "SCRIPT_NAME": "/ext/tet/main.sh",
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "REQUEST_METHOD": method or ("POST" if body else "GET"),
        "REQUEST_SCHEME": "http",
        "HTTP_HOST": "localhost:1",
        "HTTP_REFERER": referer,
        "CONTENT_LENGTH": str(len(body)),
        # fossil writes only as a user the repository knows; init makes the os user its admin
        "FOSSIL_USER": os.environ.get("USER", ""),
        "FOSSIL_NONCE": "n0nce",
    }
    r = subprocess.run([BASH, str(tet_main(tkt.db))], input=body, capture_output=True, text=True, env=env, cwd=tkt.db.parent)
    head, _, page = r.stdout.replace("\r\n", "\n").partition("\n\n")
    return dict(line.split(": ", 1) for line in head.splitlines()), page


class TestSeparation:
    def test_tkt_never_mentions_tet_or_proposals(self):
        text = TKT.read_text()
        assert "tet" not in re.findall(r"\b\w+\b", text)
        assert "fx_proposal" not in text and "propos" not in text.replace("propose steps", "")

    def test_tkt_init_keeps_proposals(self, tkt):
        t = tkt.new("kept")
        propose(tkt, "close", t)
        tkt.ok("init")
        tkt.ok("run", "rebuild")
        assert tkt.sql("select count(*) from fx_proposal;") == "1"

    def test_tkt_init_links_and_runs_the_plugin(self, tkt):
        r = tkt("init")
        assert "init tet: ok" in r.stderr
        # the link is for a plugin of the tracker's own; one a distribution carries stays inside it
        link = tkt.db.parent / ".tkt" / "bin" / "tet"
        if os.environ.get("TKT_CMD"):
            assert not link.exists()
        else:
            assert os.readlink(link) == "../plugins/tet/main.sh"
        assert tkt.ok("tet", "list") == ""

    def test_init_needs_a_tracker(self, tmp_path):
        r = tet("init", db=tmp_path / "none.fossil")
        assert r.returncode != 0 and "tkt init" in r.stderr

    def test_init_replaces_earlier_table_shapes(self, tkt):
        tkt.sql("drop table fx_proposal;")
        tkt.sql("create table fx_proposal(id integer primary key, kind text, target text, payload text, status text);")
        t = tkt.new("x")
        r = tet("propose", "close", t, db=tkt.db)
        assert r.returncode != 0 and "tet init" in r.stderr
        assert tet("init", db=tkt.db).returncode == 0
        propose(tkt, "close", t)


class TestPropose:
    def test_edit_is_recorded_not_made(self, tkt):
        t = tkt.new("orig", "old body")
        before = tkt.show(t)
        pid = propose(tkt, "edit", t[:6], input="new body\n", flags=("--why", "clearer"))
        assert tkt.show(t) == before
        assert row(tkt, pid, "verb, argv, target, status, run, why") == f'edit|["edit","{t[:6]}"]|{t}|pending|r1|clearer'
        assert row(tkt, pid, "body") == "new body"

    @pytest.mark.parametrize("args,stdin,writes", [
        (["comment", "{t}"], "a note", 1),
        (["tag", "{t}", "a", "b"], "", 1),
        (["set", "{t}", "severity", "Minor"], "", 1),
        (["close", "{t}", "resolution=Duplicate"], "dupe of x", 2),
        (["block", "{t}", "{o}"], "", 1),
        (["parent", "{t}", "{o}"], "", 1),
    ])
    def test_each_ticket_verb_records_its_writes_and_base(self, tkt, args, stdin, writes):
        t, o = tkt.new("target"), tkt.new("other")
        before = tkt.sql("select count(*) from ticketchng;")
        pid = propose(tkt, *[a.format(t=t, o=o) for a in args], input=stdin)
        assert tkt.sql("select count(*) from ticketchng;") == before
        n, target, base, mtime = row(tkt, pid, "json_array_length(writes), target, base, (select tkt_mtime from ticket where substr(tkt_uuid,1,10)=target)").split("|")
        assert int(n) == writes and target == t and base == mtime

    def test_new_has_no_target(self, tkt):
        pid = propose(tkt, "new", "title=split child", input="body")
        assert tkt.sql("select count(*) from ticket;") == "0"
        assert row(tkt, pid, "verb, target is null, base is null, body") == "new|1|1|body"

    def test_wiki_put_records_page_text_and_version(self, tkt):
        tkt.ok("wiki", "put", "notes/a", input="v1")
        version = tkt("wiki", "get", "notes/a").stderr.split("version ")[1].split(";")[0]
        pid = propose(tkt, "wiki", "put", "notes/a", input="v2")
        assert tkt.ok("wiki", "get", "notes/a").strip() == "v1"
        target, base, text = row(tkt, pid, "target, substr(base,1,10), json_extract(writes,'$[0].file')").split("|")
        assert (target, base, text.strip()) == ("wiki:notes/a", version, "v2")

    def test_group_and_run_from_flags_or_environment(self, tkt):
        t = tkt.new("x")
        pid = propose(tkt, "close", t, run_name="groom-2", flags=("--group", "g1"))
        assert row(tkt, pid, "run, grp") == "groom-2|g1"
        r = tet("propose", "close", t, db=tkt.db, extra={"TET_RUN": "env-run"})
        assert row(tkt, int(r.stdout.split()[1]), "run") == "env-run"

    def test_only_write_verbs_can_be_proposed(self, tkt):
        for verb in (["show", "x"], ["clean", "--force"], ["run", "sql", "select 1;"], ["init"], ["action", "list"]):
            r = tet("propose", *verb, db=tkt.db)
            assert r.returncode != 0 and "cannot be proposed" in r.stderr, verb
        assert tkt.sql("select count(*) from fx_proposal;") == "0"

    def test_tkt_validation_still_runs(self, tkt):
        for args in (["close", "ffffff"], ["edit", "ffffff"], ["new", "bogus=1"], ["set", "ffffff", "severity", "x"]):
            r = tet("propose", *args, db=tkt.db, input="x")
            assert r.returncode != 0, args
        assert tkt.sql("select count(*) from fx_proposal;") == "0"

    def test_a_verb_that_changes_nothing_is_not_proposed(self, tkt):
        tkt.ok("wiki", "put", "notes/a", input="same")
        r = tet("propose", "wiki", "put", "notes/a", db=tkt.db, input="same")
        assert r.returncode != 0 and "nothing to propose" in r.stderr

    def test_quoting_survives(self, tkt):
        t = tkt.new("q")
        pid = propose(tkt, "tag", t, "o'brien")
        assert row(tkt, pid, "argv") == f'["tag","{t}","o\'brien"]'
        pid = propose(tkt, "comment", t, input="it's `fine` $HOME | bar")
        assert row(tkt, pid, "body") == "it's `fine` $HOME | bar"

    def test_open_stdin_pipe_does_not_hang_a_verb_without_a_body(self, tkt):
        # an agent's shell leaves stdin as a pipe nobody closes; tag reads no body, so it must not wait on it
        t = tkt.new("x")
        env = {k: v for k, v in os.environ.items() if k != "TKT_DB"}
        env["TKT_DB"] = str(tkt.db)
        p = subprocess.Popen([*tet_argv(tkt.db), "propose", "tag", t, "a"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=env)
        try:
            out = p.stdout.read()
            p.wait(timeout=20)
        finally:
            p.stdin.close()
            p.kill()
        assert out.startswith("proposed ")

    def test_concurrent_proposers_all_land(self, tkt):
        t = tkt.new("busy")
        env = {k: v for k, v in os.environ.items() if k != "TKT_DB"}
        env.update(TKT_DB=str(tkt.db), TET_RUN="par")
        procs = [subprocess.Popen([*tet_argv(tkt.db), "propose", "comment", t], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, env=env) for _ in range(12)]
        results = [p.communicate(f"note {i}") for i, p in enumerate(procs)]
        assert all(p.returncode == 0 for p in procs), [e for _, e in results]
        assert tkt.sql("select count(*) from fx_proposal where run='par';") == "12"


class TestApply:
    def outcome(self, tkt, pid):
        return row(tkt, pid, "status, result")

    def test_accepted_edit_lands(self, tkt):
        t = tkt.new("x", "old body")
        pid = propose(tkt, "edit", t, input="new body with 'quotes' and\nlines")
        assert tet("accept", str(pid), db=tkt.db).returncode == 0
        assert self.outcome(tkt, pid).startswith("applied")
        assert "new body with 'quotes' and\nlines" in tkt.show(t)

    def test_close_applies_both_its_writes(self, tkt):
        t = tkt.new("x")
        pid = propose(tkt, "close", t, "resolution=Duplicate", input="dupe of y")
        tet("accept", str(pid), db=tkt.db)
        shown = tkt.show(t)
        assert "Closed" in shown and "dupe of y" in shown

    def test_tag_and_new_apply(self, tkt):
        t = tkt.new("target")
        tag = propose(tkt, "tag", t, "a", "b")
        kid = propose(tkt, "new", "title=child | with bar", f"parent={t}", input="kid")
        tet("accept", str(tag), str(kid), db=tkt.db)
        assert self.outcome(tkt, tag).startswith("applied") and self.outcome(tkt, kid).startswith("applied")
        assert "child | with bar" in tkt.ok("list", f"parent={t}")
        assert tkt.sql(f"select tags from ticket where substr(tkt_uuid,1,10)='{t}';") == "a b"

    def test_stale_target_is_not_written(self, tkt):
        t = tkt.new("x", "v1")
        pid = propose(tkt, "edit", t, input="proposed")
        time.sleep(1.1)
        tkt.ok("edit", t, input="human edit")
        tet("accept", str(pid), db=tkt.db)
        status, result = self.outcome(tkt, pid).split("|", 1)
        assert status == "failed" and "target changed since proposed" in result
        assert "human edit" in tkt.show(t)

    def test_a_second_proposal_on_the_same_ticket_goes_stale(self, tkt):
        # both recorded the ticket's version before either landed, so once one applies the other is stale. the
        # staleness check cannot tell a human's edit from a sibling proposal's; groups are meant to answer that
        t = tkt.new("target")
        first = propose(tkt, "comment", t, input="a note")
        second = propose(tkt, "close", t, input="dupe")
        time.sleep(1.1)
        tet("accept", str(first), str(second), db=tkt.db)
        assert self.outcome(tkt, first).startswith("applied")
        assert self.outcome(tkt, second).startswith("failed|target changed since proposed")

    def test_wiki_put_applies_and_goes_stale(self, tkt):
        tkt.ok("wiki", "put", "notes/a", input="v1")
        a = propose(tkt, "wiki", "put", "notes/a", input="v2")
        b = propose(tkt, "wiki", "put", "notes/a", input="v3")
        tet("accept", str(a), str(b), db=tkt.db)
        assert tkt.ok("wiki", "get", "notes/a").strip() == "v2"
        assert self.outcome(tkt, a).startswith("applied") and self.outcome(tkt, b).startswith("failed")

    def test_a_tampered_write_is_refused(self, tkt):
        t = tkt.new("x")
        pid = propose(tkt, "close", t)
        tkt.sql(f"update fx_proposal set writes=json_array(json_object('argv',json_array('sql','select 1;'))) where id={pid};")
        tet("accept", str(pid), db=tkt.db)
        assert self.outcome(tkt, pid) == "failed|refused write: sql select 1;"

    def test_reject_never_writes_and_decisions_are_final(self, tkt):
        t = tkt.new("x")
        pid = propose(tkt, "close", t)
        tet("reject", str(pid), db=tkt.db)
        tet("accept", str(pid), db=tkt.db)
        assert self.outcome(tkt, pid) == "rejected|" and "Open" in tkt.show(t)


class TestPage:
    def test_page_shows_pending_and_settled_cards(self, tkt):
        t = tkt.new("target <b>")
        p1 = propose(tkt, "comment", t, input="<script>x</script> first line\nsecond", flags=("--why", "a & b"))
        p2 = propose(tkt, "close", t)
        cgi(tkt, "/decide", body=f"d={p2}:reject")
        h, page = cgi(tkt)
        assert h["Status"] == "200" and page.startswith("<div class='fossil-doc' data-title='Proposals'>")
        pending, settled = page.split("tet-card-settled")
        assert f'data-proposal="{p1}"' in pending and f'data-proposal="{p2}"' not in pending
        assert f'data-proposal="{p2}"' in settled and "tet-state-rejected" in settled
        assert ">Comment</button>" in pending
        assert "<script>x" not in page and "&lt;script&gt;x&lt;/script&gt; first line" in page
        assert "target &lt;b&gt;" in page and "a &amp; b" in page
        assert f'href="/tktview/{t}"' in pending
        # the page's script and styles are the plugin's own files, served beside its main
        assert '<script src="/ext/tkt/ext/tet/js/tet.js"></script>' in page
        assert '<link rel="stylesheet" href="/ext/tkt/ext/tet/css/tet.css">' in page

    def test_empty_queue_says_so(self, tkt):
        _, page = cgi(tkt)
        assert '<p class="tet-empty">Nothing pending.</p>' in page

    def test_decide_records_applies_and_redirects_back(self, tkt):
        t = tkt.new("x")
        a, b, c = (propose(tkt, "comment", t, input=f"n{i}") for i in range(3))
        back = "http://localhost:1/ext/tet/main.sh"
        h, _ = cgi(tkt, "/decide", body=f"d={a}%3Aaccept&d={b}%3Areject", referer=back)
        assert h["Status"] == "303 See Other" and h["Location"] == back
        me = os.environ.get("USER", "")
        assert row(tkt, a, "status, decided_by") == f"applied|{me}"
        assert row(tkt, b, "status, decided_by") == f"rejected|{me}"
        assert row(tkt, c, "status") == "pending"

    def test_ajax_decide_answers_with_the_settled_rows(self, tkt):
        t = tkt.new("x")
        a = propose(tkt, "tag", t, "z")
        b = propose(tkt, "comment", t, input="note")
        h, page = cgi(tkt, "/decide", body=f"d={a}%3Aaccept&d={b}%3Areject&ajax=1")
        assert h["Content-Type"].startswith("text/html") and page.count("<tr ") == 2
        assert f'data-proposal="{a}" class="tet-settled-applied"' in page
        assert f'data-proposal="{b}" class="tet-settled-rejected"' in page

    def test_bad_requests_change_nothing(self, tkt):
        t = tkt.new("x")
        a, b = propose(tkt, "close", t), propose(tkt, "close", t)
        for body in (f"d={a}:maybe", "d=1x:accept", "d=:accept", "", f"d={a}:accept&d={b}:nope"):
            h, _ = cgi(tkt, "/decide", body=body, method="POST")
            assert h["Status"] == "400", body
        assert cgi(tkt, "/decide", method="GET")[0]["Status"] == "405"
        assert cgi(tkt, "/decide", body=f"d={a}:accept", referer="http://evil.example/")[0]["Status"] == "403"
        assert row(tkt, a, "status") == "pending"

    def test_wiki_target_links_to_the_page(self, tkt):
        tkt.ok("wiki", "put", "notes/a", input="v1")
        propose(tkt, "wiki", "put", "notes/a", input="v2")
        _, page = cgi(tkt)
        assert 'href="/wiki?name=notes/a"' in page
