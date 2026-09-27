"""Interface tests for the tkt script, each against a fresh tracker copied from one initialized template."""

import os
import pty
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tkt"
BASH = shutil.which(os.environ.get("TKT_BASH", "bash"))
TOOLS = "fossil sed mktemp rm dirname basename ps grep sleep cat sh".split()


def run(*args, db=None, input="", cwd=None, path=None, extra=None):
    env = {k: v for k, v in os.environ.items() if k != "TKT_DB"}
    if db is not None:
        env["TKT_DB"] = str(db)
    if path is not None:
        env["PATH"] = str(path)
    env.update(extra or {})
    return subprocess.run(
        [BASH, str(SCRIPT), *args],
        input=input,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


def run_tty(*args, db, **env):
    """Run tkt with stdout and stderr on a pseudo-terminal, returning everything it printed."""
    full = {k: v for k, v in os.environ.items() if k not in ("TKT_DB", "NO_COLOR", "NOCOLOR")}
    full.update(TKT_DB=str(db), TERM="xterm-256color")
    full.update(env)
    parent, child = pty.openpty()
    proc = subprocess.Popen([BASH, str(SCRIPT), *args], stdin=subprocess.DEVNULL, stdout=child, stderr=child, env=full)
    os.close(child)
    out = b""
    while True:
        try:
            chunk = os.read(parent, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    proc.wait()
    os.close(parent)
    return out.decode()


@pytest.fixture(scope="session")
def template(tmp_path_factory):
    db = tmp_path_factory.mktemp("template") / "tracker.fossil"
    r = run("init", db=db)
    assert r.returncode == 0, r.stderr
    return db


class Tracker:
    def __init__(self, db, cwd):
        self.db = db
        self.cwd = cwd

    def __call__(self, *args, input=""):
        return run(*args, db=self.db, input=input, cwd=self.cwd)

    def ok(self, *args, input=""):
        r = self(*args, input=input)
        assert r.returncode == 0, r.stderr
        return r.stdout

    def fails(self, *args, input="", match):
        r = self(*args, input=input)
        assert r.returncode != 0, r.stdout
        assert re.search(match, r.stderr), r.stderr
        return r.stderr

    def new(self, title, body="", **fields):
        out = self.ok("new", f"title={title}", *(f"{k}={v}" for k, v in fields.items()), input=body)
        return re.search(r"succeeded for ([0-9a-f]{40})", out).group(1)[:10]

    def show(self, id):
        return self.ok("show", id)

    def sql(self, query):
        return self.ok("run", "sql", query).strip()


@pytest.fixture
def tkt(template, tmp_path):
    db = tmp_path / "tracker.fossil"
    shutil.copy(template, db)
    return Tracker(db, tmp_path)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / "sub").mkdir(parents=True)
    return root


@pytest.fixture
def no_git_path(tmp_path):
    bin = tmp_path / "bin"
    bin.mkdir()
    for tool in TOOLS:
        (bin / tool).symlink_to(shutil.which(tool))
    return bin


def plain_fossil(path):
    subprocess.run(["fossil", "init", str(path)], check=True, capture_output=True)
    return path


def config(db, name):
    return run("run", "sql", f"select value from config where name='{name}';", db=db).stdout.strip()


class TestSurface:
    def test_help_lists_every_verb(self):
        out = run("help").stdout
        for verb in "init new show list search edit comment tag block set close serve stop status sql skill run".split():
            assert f"tkt {verb}" in out

    def test_unknown_verb_fails(self):
        r = run("frobnicate")
        assert r.returncode != 0
        assert "unknown verb: frobnicate" in r.stderr

    def test_missing_tracker_names_init(self, tmp_path):
        r = run("list", db=tmp_path / "absent.fossil")
        assert r.returncode != 0
        assert "run: tkt init" in r.stderr

    def test_outside_git_before_init_names_the_path(self, tmp_path):
        r = run("list", cwd=tmp_path)
        assert r.returncode != 0
        assert f"no tracker at {tmp_path}/.tkt.fossil" in r.stderr


class TestLocation:
    def test_tracker_under_old_name_is_refused(self, template, project):
        shutil.copy(template, project / ".fossil.db")
        for verb in ("list", "init"):
            r = run(verb, cwd=project)
            assert r.returncode != 0
            assert "rename it to .tkt.fossil" in r.stderr
        assert not (project / ".tkt.fossil").exists()

    def test_init_uses_cwd_and_is_found_from_below(self, project):
        assert run("init", cwd=project).returncode == 0
        assert (project / ".tkt.fossil").is_file()
        assert run("list", cwd=project / "sub").returncode == 0

    def test_nearest_tracker_wins(self, template, project):
        shutil.copy(template, project / ".tkt.fossil")
        shutil.copy(template, project / "sub" / ".tkt.fossil")
        assert run("new", "title=lands in sub", cwd=project / "sub").returncode == 0
        assert "lands in sub" in run("list", cwd=project / "sub").stdout
        assert run("list", cwd=project).stdout == ""

    def test_works_without_git_cli(self, tmp_path, no_git_path):
        work = tmp_path / "work"
        work.mkdir()
        assert run("init", cwd=work, path=no_git_path).returncode == 0
        r = run("new", "title=no git", cwd=work, path=no_git_path)
        assert r.returncode == 0, r.stderr
        assert run("run", "sql", "select coalesce(foundin,'') from ticket;", cwd=work, path=no_git_path).stdout.strip() == ""

    def test_plain_repo_under_old_name_is_ignored(self, project):
        plain_fossil(project / ".fossil.db")
        assert run("init", cwd=project).returncode == 0
        assert (project / ".tkt.fossil").is_file()


class TestInit:
    def test_is_idempotent(self, tkt):
        a = tkt.new("survives reinit")
        tkt.ok("init")
        assert "survives reinit" in tkt.show(a)

    def test_writes_version_row(self, tkt):
        assert re.fullmatch(r"\d+\.\d+\.\d+", config(tkt.db, "tkt-version"))

    def test_stale_schema_is_refused_until_init(self, tkt):
        tkt.sql("update config set value=replace(value,'blockers TEXT,','') where name='ticket-table';")
        tkt.ok("run", "rebuild")
        tkt.fails("list", match="predates the blockers field")
        tkt.ok("init")
        tkt.ok("list")

    def test_tracker_without_version_row_is_accepted(self, tkt):
        tkt.sql("delete from config where name='tkt-version';")
        tkt.sql("update config set value=cast(value as blob) where name='ticket-table';")
        tkt.ok("init")
        assert config(tkt.db, "tkt-version")

    def test_refuses_plain_fossil_repo(self, tmp_path):
        db = plain_fossil(tmp_path / "project.fossil")
        menu = config(db, "mainmenu")
        r = run("init", db=db)
        assert r.returncode != 0
        assert "is not a tkt tracker" in r.stderr and "--adopt" in r.stderr
        assert config(db, "mainmenu") == menu
        assert config(db, "tkt-version") == ""

    def test_adopt_converts_plain_fossil_repo(self, tmp_path):
        db = plain_fossil(tmp_path / "project.fossil")
        r = run("init", "--adopt", db=db)
        assert r.returncode == 0, r.stderr
        assert config(db, "tkt-version")
        assert run("list", db=db).returncode == 0

    def test_unknown_argument_fails(self, tkt):
        tkt.fails("init", "--force", match="only --adopt")

    def test_installs_web_ui(self, tkt):
        assert config(tkt.db, "index-page") == "/ticket"
        assert config(tkt.db, "default-skin") == ""
        menu = config(tkt.db, "mainmenu")
        for entry in ("Tickets /ticket", "Admin /setup"):
            assert entry in menu
        assert "skin=" not in menu
        assert "builtin/skins/blitz/css.txt?mimetype=text/css" in config(tkt.db, "header")
        assert 'id="tkt-theme"' in config(tkt.db, "header")
        assert "html[data-theme=dark]" in config(tkt.db, "css")
        assert config(tkt.db, "footer") and config(tkt.db, "details")
        titles = tkt.sql("select title from reportfmt order by title;").split("\n")
        for t in ("All Tickets", "Open Tickets", "Critical and Severe", "Recent Activity", "By Tag", "Blocked", "Recently Closed"):
            assert t in titles
        assert 'name="description"' in config(tkt.db, "ticket-newpage")
        edit = config(tkt.db, "ticket-editpage")
        assert 'name="description"' in edit and "text/x-markdown" in edit
        assert "status=Closed&amp;resolution=Fixed" in config(tkt.db, "ticket-viewpage")


class TestNew:
    def test_title_is_required(self, tkt):
        tkt.fails("new", match="title is required")

    def test_misspelled_field_fails(self, tkt):
        tkt.fails("new", "title=x", "subsytem=core", match="unknown field: subsytem")
        assert tkt.ok("list", "status=all") == ""

    def test_defaults(self, tkt):
        a = tkt.new("defaults")
        assert f"{a} | Open | Important | - | defaults" in tkt.show(a)

    def test_body_is_literal_markdown(self, tkt):
        body = "## Repro\n\n- run `make foo` with $HOME and it's <angle>\n- observe\n"
        a = tkt.new("literal", body)
        assert body.strip() in tkt.show(a)

    def test_body_is_stored_as_markdown(self, tkt):
        tkt.new("mime", "text")
        assert tkt.sql("select distinct mimetype from ticketchng;") == "text/x-markdown"


class TestIds:
    def test_prefix_resolves(self, tkt):
        a = tkt.new("prefixed")
        assert "prefixed" in tkt.show(a[:4])

    def test_unknown_prefix_fails(self, tkt):
        tkt.new("one")
        tkt.fails("show", "ffffffff", match="matches no single ticket")

    def test_non_hex_is_rejected(self, tkt):
        tkt.fails("show", "c2'; drop", match="not a ticket id")


class TestBody:
    def test_edit_replaces_description(self, tkt):
        a = tkt.new("edited", "old text")
        tkt.ok("edit", a, input="new text")
        out = tkt.show(a)
        assert "new text" in out and "old text" not in out

    def test_comment_appends(self, tkt):
        a = tkt.new("commented", "desc")
        tkt.ok("comment", a, input="first")
        tkt.ok("comment", a, input="second")
        out = tkt.show(a)
        assert out.index("desc") < out.index("first") < out.index("second")

    def test_empty_stdin_fails(self, tkt):
        a = tkt.new("empty")
        for verb in ("edit", "comment"):
            tkt.fails(verb, a, match="nothing on stdin")

    def test_bare_hash_becomes_link_and_backlink(self, tkt):
        a = tkt.new("target")
        b = tkt.new("source", f"see [{a}]")
        assert f"see []({a})" in tkt.show(b)
        assert re.search(rf"## Referenced by\n\n- {b} \| Open \| source", tkt.show(a))


class TestTags:
    def test_replace(self, tkt):
        a = tkt.new("tagged", tags="one two")
        tkt.ok("tag", a, "three", "four")
        assert "| three four |" in tkt.show(a)

    def test_from_stdin(self, tkt):
        a = tkt.new("tagged")
        tkt.ok("tag", a, input="  x\ny  ")
        assert "| x y |" in tkt.show(a)

    def test_clear(self, tkt):
        a = tkt.new("tagged", tags="one")
        tkt.ok("tag", a, "--clear")
        assert f"{a} | Open | Important | - |" in tkt.show(a)

    def test_empty_input_does_not_clear(self, tkt):
        a = tkt.new("tagged", tags="keep")
        tkt.fails("tag", a, match="use --clear")
        assert "| keep |" in tkt.show(a)


class TestBlockers:
    def test_both_directions(self, tkt):
        a = tkt.new("waits")
        b = tkt.new("holds")
        tkt.ok("block", a, b[:6])
        assert re.search(rf"## Blocked by\n\n- {b} \| Open \| holds", tkt.show(a))
        assert re.search(rf"## Blocks\n\n- {a} \| Open \| waits", tkt.show(b))

    def test_self_block_fails(self, tkt):
        a = tkt.new("self")
        tkt.fails("block", a, a, match="cannot block itself")

    def test_unknown_id_leaves_set_unchanged(self, tkt):
        a = tkt.new("waits")
        b = tkt.new("holds")
        tkt.ok("block", a, b)
        tkt.fails("block", a, "ffffffff", match="matches no single ticket")
        assert "## Blocked by" in tkt.show(a)

    def test_empty_input_does_not_clear(self, tkt):
        a = tkt.new("waits")
        b = tkt.new("holds")
        tkt.ok("block", a, b)
        tkt.fails("block", a, match="use --clear")
        assert "## Blocked by" in tkt.show(a)

    def test_clear(self, tkt):
        a = tkt.new("waits")
        b = tkt.new("holds")
        tkt.ok("block", a, b)
        tkt.ok("block", a, "--clear")
        assert "## Blocked by" not in tkt.show(a)
        assert "## Blocks" not in tkt.show(b)


class TestSet:
    def test_field(self, tkt):
        a = tkt.new("severe")
        tkt.ok("set", a, "severity", "Critical")
        assert f"{a} | Open | Critical |" in tkt.show(a)

    def test_unknown_field_fails(self, tkt):
        a = tkt.new("severe")
        tkt.fails("set", a, "sevrity", "x", match="unknown field: sevrity")

    def test_guarded_fields_name_their_verb(self, tkt):
        a = tkt.new("guarded")
        cases = {"comment": "comment", "icomment": "comment", "description": "edit", "tags": "tag", "blockers": "block"}
        for field, verb in cases.items():
            tkt.fails("set", a, field, "x", match=f"use: tkt {verb}")

    def test_option_like_value_is_refused_and_not_written(self, tkt):
        a = tkt.new("dash", type="Feature_Request")
        tkt.fails("set", a, "type", "-q", match="looks like a fossil option")
        assert tkt.sql("select type from ticket;") == "Feature_Request"

    def test_option_like_tag_is_refused(self, tkt):
        a = tkt.new("dash", tags="keep")
        tkt.fails("tag", a, "-R", match="looks like a fossil option")
        assert "| keep |" in tkt.show(a)


class TestClose:
    def test_defaults_to_fixed_with_comment(self, tkt):
        a = tkt.new("closing")
        tkt.ok("close", a, input="Fixed in abc1234.")
        assert tkt.sql("select status, resolution from ticket;") == "Closed|Fixed"
        assert "Fixed in abc1234." in tkt.show(a)

    def test_resolution(self, tkt):
        a = tkt.new("closing")
        tkt.ok("close", a, "resolution=Works_As_Designed")
        assert tkt.sql("select resolution from ticket;") == "Works_As_Designed"

    def test_unknown_argument_fails(self, tkt):
        a = tkt.new("closing")
        tkt.fails("close", a, "reslution=x", match="unknown field: reslution")


class TestClean:
    def test_force_purges_only_closed(self, tkt):
        a = tkt.new("keep me")
        b = tkt.new("drop me")
        tkt.ok("close", b)
        tkt.ok("clean", "--force")
        out = tkt.ok("list", "status=all")
        assert a in out and b not in out

    def test_without_force_off_a_terminal_refuses(self, tkt):
        b = tkt.new("drop me")
        tkt.ok("close", b)
        tkt.fails("clean", match="--force")
        assert b in tkt.ok("list", "status=all")

    def test_nothing_closed_is_fine(self, tkt):
        a = tkt.new("open")
        tkt.ok("clean", "--force")
        assert a in tkt.ok("list")

    def test_unknown_argument_fails(self, tkt):
        tkt.fails("clean", "--forse", match="usage")


class TestListAndSearch:
    def test_default_hides_closed(self, tkt):
        a = tkt.new("open one")
        b = tkt.new("closed one")
        tkt.ok("close", b)
        out = tkt.ok("list")
        assert a in out and b not in out
        assert b in tkt.ok("list", "status=all")
        assert tkt.ok("list", "status=Closed").startswith(b)

    def test_wip_counts_as_open(self, tkt):
        a = tkt.new("in progress", status="WIP")
        assert a in tkt.ok("list")

    def test_tag_filter_matches_whole_tags(self, tkt):
        a = tkt.new("compiler", tags="compiler oop")
        tkt.new("compile", tags="compile")
        out = tkt.ok("list", "tag=compiler")
        assert out.startswith(a)
        assert len(out.splitlines()) == 1

    def test_quote_in_filter_is_literal(self, tkt):
        tkt.new("x")
        assert tkt.ok("list", "status=it's") == ""

    def test_search_reaches_comments_and_quotes(self, tkt):
        a = tkt.new("quiet")
        tkt.ok("comment", a, input="it's in the comment")
        assert a in tkt.ok("search", "IT'S IN")

    def test_search_needs_text(self, tkt):
        tkt.fails("search", match="usage")


class TestSql:
    def test_select_prints_markdown(self, tkt):
        tkt.new("queried")
        out = tkt.ok("sql", "select title from ticket;")
        assert out.splitlines()[0].strip("| ").startswith("title")
        assert re.search(r"\|\s*queried\s*\|", out)

    def test_query_on_stdin(self, tkt):
        tkt.new("one")
        assert re.search(r"\|\s*1\s*\|", tkt.ok("sql", input="select count(*) as n from ticket;"))

    def test_sql_error_fails(self, tkt):
        tkt.fails("sql", "select nope from ticket;", match="no such column: nope")

    def test_empty_query_fails(self, tkt):
        tkt.fails("sql", match="usage")

    def test_write_is_refused_and_rows_survive(self, tkt):
        tkt.new("kept")
        tkt.fails("sql", "delete from ticket;", match="readonly database")
        assert re.search(r"\|\s*kept\s*\|", tkt.ok("sql", "select title from ticket;"))

    def test_escapes_are_refused(self, tkt, tmp_path):
        target = tmp_path / "escaped.txt"
        tkt.fails("sql", f"select writefile('{target}','x');", match="safe mode")
        tkt.fails("sql", f".once {target}", match="safe mode")
        tkt.fails("sql", ".system echo ran", match="safe mode")
        tkt.fails("sql", f".open {tmp_path / 'other.db'}", match="safe mode")
        tkt.fails("sql", "select readfile('/etc/hosts');", match="safe mode")
        assert not target.exists() and not (tmp_path / "other.db").exists()

    def test_schema_notes_and_their_examples_run(self, tkt):
        ready = tkt.new("ready")
        waiting = tkt.new("waiting")
        done = tkt.new("done")
        busy = tkt.new("busy")
        tkt.ok("block", ready, done)
        tkt.ok("block", waiting, busy)
        tkt.ok("close", done)
        notes = tkt.ok("sql", "--schema")
        for column in ("ticket.blockers", "ticketchng.icomment", "backlink.srctype"):
            assert column in notes
        blocks = [block.splitlines() for block in notes.split("\n\n")]
        examples = ["\n".join(lines[1:]) for lines in blocks if len(lines) > 1 and lines[1].lstrip().startswith("select")]
        assert len(examples) == 2
        blocks_ready = tkt.ok("sql", examples[0])
        assert ready in blocks_ready and waiting not in blocks_ready
        tkt.ok("sql", examples[1])


class TestSkill:
    SOURCE = SCRIPT.parent / "skills" / "tkt" / "SKILL.md"

    def test_bundled_copy_matches_repository(self):
        assert run("skill").stdout == self.SOURCE.read_text()

    def test_install_for_user(self, tmp_path):
        r = run("skill", "install", extra={"HOME": str(tmp_path), "CLAUDE_CONFIG_DIR": ""})
        assert r.returncode == 0, r.stderr
        assert (tmp_path / ".claude" / "skills" / "tkt" / "SKILL.md").read_text() == self.SOURCE.read_text()

    def test_install_honors_claude_config_dir(self, tmp_path):
        r = run("skill", "install", extra={"CLAUDE_CONFIG_DIR": str(tmp_path / "cfg")})
        assert r.returncode == 0, r.stderr
        assert (tmp_path / "cfg" / "skills" / "tkt" / "SKILL.md").is_file()

    def test_install_for_project(self, project):
        r = run("skill", "install", "--project", cwd=project)
        assert r.returncode == 0, r.stderr
        assert (project / ".claude" / "skills" / "tkt" / "SKILL.md").is_file()

    def test_install_refuses_a_symlinked_skill(self, tmp_path):
        target = tmp_path / "clone-skill"
        target.mkdir()
        (tmp_path / "cfg" / "skills").mkdir(parents=True)
        (tmp_path / "cfg" / "skills" / "tkt").symlink_to(target)
        r = run("skill", "install", extra={"CLAUDE_CONFIG_DIR": str(tmp_path / "cfg")})
        assert r.returncode != 0 and "is a symlink" in r.stderr
        assert not (target / "SKILL.md").exists()

    def test_unknown_argument_fails(self):
        r = run("skill", "uninstall")
        assert r.returncode != 0 and "usage: tkt skill" in r.stderr


class TestColor:
    def test_terminal_gets_color(self, tkt):
        tkt.new("colored", severity="Critical")
        out = run_tty("list", db=tkt.db)
        assert "\x1b[32mOpen" in out and "\x1b[31mCritical" in out

    def test_error_prefix_is_red_on_terminal(self, tkt):
        assert "\x1b[31mtkt:" in run_tty("show", "ffffffff", db=tkt.db)

    def test_no_color_variables_disable_it(self, tkt):
        tkt.new("plain")
        for var in ("NO_COLOR", "NOCOLOR"):
            out = run_tty("list", db=tkt.db, **{var: "1"})
            assert "| Open |" in out and "\x1b[" not in out

    def test_dumb_terminal_disables_it(self, tkt):
        tkt.new("plain")
        out = run_tty("list", db=tkt.db, TERM="dumb")
        assert "| Open |" in out and "\x1b[" not in out

    def test_pipes_stay_plain(self, tkt):
        a = tkt.new("plain")
        assert "\x1b[" not in tkt.ok("list") + tkt.ok("show", a)
        assert "\x1b[" not in tkt.fails("show", "ffffffff", match="no single ticket")


class TestServer:
    def test_stop_with_nothing_serving(self, tkt):
        r = tkt("stop")
        assert r.returncode == 0
        assert "nothing serving" in r.stderr

    def test_status_fails_with_nothing_serving(self, tkt):
        tkt.fails("status", match="nothing serving")

    def test_stale_pid_file_is_ignored(self, tkt):
        Path(f"{tkt.db}.pid").write_text("1 9080\n")
        tkt.fails("status", match="nothing serving")
        tkt.ok("stop")
        assert not Path(f"{tkt.db}.pid").exists()

    def test_bad_port_fails(self, tkt):
        tkt.fails("serve", "port=abc", match="not a port")
