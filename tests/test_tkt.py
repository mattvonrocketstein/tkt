"""Interface tests for the tkt script, each against a fresh tracker copied from one initialized template."""

import json
import os
import pty
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tkt"
BASH = shutil.which(os.environ.get("TKT_BASH", "bash"))
# the tkt under test, as an argv: this checkout's script by default, or a distribution such as TKT_CMD="sh /abs/tkt.com"
TKT = shlex.split(os.environ.get("TKT_CMD", "")) or [BASH, str(SCRIPT)]
# what tkt names as itself, for {tkt}, the CGI link, and a job's PATH: the script, or the distribution's binary
SELF = Path(TKT[-1]).resolve()
# a bare fossil, for the few fixtures that build a repo tkt has never touched
FOSSIL = shlex.split(os.environ.get("TKT_FOSSIL", "fossil"))
# a test that reaches inside the script, such as swapping the fossil it finds on PATH, which a distribution pins to its own
script_only = pytest.mark.skipif(bool(os.environ.get("TKT_CMD")), reason="reaches inside the tkt script; TKT_CMD names a distribution")
# a distribution carries its own fossil, so the host's is linked only when there is one
TOOLS = [t for t in "fossil sed mktemp mkdir mv rm dirname basename ps grep sleep cat sh".split() if shutil.which(t)]
# what a plugin's init and a distribution's own start need besides
TOOLS += [t for t in "ln find sort readlink cmp chmod".split() if shutil.which(t)]


def names_this_tkt(path):
    """Whether a path tkt gave out as itself is the tkt under test: the script exactly, or for a distribution, which may
    name a launcher beside its binary, any file that runs as it."""
    if not os.environ.get("TKT_CMD"):
        return Path(path).resolve() == SELF
    return subprocess.run([str(path), "version"], capture_output=True, text=True).stdout == run("version").stdout


def run(*args, db=None, input="", cwd=None, path=None, extra=None):
    env = {k: v for k, v in os.environ.items() if k != "TKT_DB"}
    if db is not None:
        env["TKT_DB"] = str(db)
    if path is not None:
        env["PATH"] = str(path)
    # init fetches page scripts; tests never reach the network unless a test points TKT_CDN somewhere
    env.setdefault("TKT_CDN", "file:///nonexistent/tkt-cdn")
    env.update(extra or {})
    return subprocess.run(
        [*TKT, *args],
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
    proc = subprocess.Popen([*TKT, *args], stdin=subprocess.DEVNULL, stdout=child, stderr=child, env=full)
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


# a raw query through fossil, one value per column with a bar between: an older fossil quotes values unless told the mode
SQL = ("run", "sql", "-list")


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
        return self.ok(*SQL, query).strip()


@pytest.fixture
def tkt(template, tmp_path):
    db = tmp_path / "tracker.fossil"
    shutil.copy(template, db)
    return Tracker(db, tmp_path)


# the plugins tkt ships, in this repository's plugins folder: one folder each, holding everything the plugin owns
PLUGINS = SCRIPT.parent / "plugins"


# lay out plugins beside a tracker as a project has its own, one folder each under the plugins folder of .tkt, with tkt beside them
def install_plugins(root, *names, always=False):
    # a distribution carries these plugins itself, and its own copies are the ones to test
    if os.environ.get("TKT_CMD") and not always:
        return
    plugins = root / ".tkt" / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    if not (plugins / "tkt").exists():
        (plugins / "tkt").symlink_to(SCRIPT)
    for name in names:
        shutil.copytree(PLUGINS / name, plugins / name, dirs_exist_ok=True)


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
    subprocess.run([*FOSSIL, "init", str(path)], check=True, capture_output=True)
    return path


def config(db, name):
    return run(*SQL, f"select value from config where name='{name}';", db=db).stdout.strip()


class TestSurface:
    def test_help_lists_every_verb(self):
        out = run("help").stdout
        for verb in "init new show list search todo triage edit comment tag block parent set close serve start stop status sql action skill run".split():
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
        assert run(*SQL, "select coalesce(foundin,'') from ticket;", cwd=work, path=no_git_path).stdout.strip() == ""

    def test_plain_repo_under_old_name_is_ignored(self, project):
        plain_fossil(project / ".fossil.db")
        assert run("init", cwd=project).returncode == 0
        assert (project / ".tkt.fossil").is_file()


class TestInit:
    def test_is_idempotent(self, tkt):
        a = tkt.new("survives reinit")
        tkt.ok("init")
        assert "survives reinit" in tkt.show(a)

    def test_reinit_keeps_custom_ticket_common(self, tkt):
        tkt.sql("update config set value='set subsystem_choices {mine}' where name='ticket-common';")
        tkt.ok("init")
        assert config(tkt.db, "ticket-common") == "set subsystem_choices {mine}"

    def test_writes_version_row(self, tkt):
        assert re.fullmatch(r"\d+\.\d+\.\d+", config(tkt.db, "tkt-version"))

    def test_stale_schema_is_refused_until_init(self, tkt):
        tkt.sql("update config set value=replace(value,'blockers TEXT,','') where name='ticket-table';")
        tkt.ok("run", "rebuild")
        tkt.fails("list", match="predates the blockers field")
        tkt.ok("init")
        tkt.ok("list")

    def test_tracker_without_parent_migrates(self, tkt):
        a = tkt.new("kept", tags="old")
        tkt.sql("update config set value=replace(value,'parent TEXT,','') where name='ticket-table';")
        tkt.ok("run", "rebuild")
        tkt.fails("list", match="predates the parent field")
        tkt.ok("init")
        p = tkt.new("epic")
        tkt.ok("parent", a, p)
        assert "| old |" in tkt.show(a) and "## Parent" in tkt.show(a)

    def test_seeds_formatting_guide_once(self, tkt):
        # an unversioned file, not a wiki page, replaced only when its text changes
        guide = tkt.ok("run", "uv", "cat", "help/formatting.md")
        assert "```mermaid" in guide and "`python`" in guide
        assert tkt.sql("select count(*) from tag where tagname='wiki-agents/FormattingHelp';").strip() == "0"
        assert tkt.sql("select count(*) from reportfmt where title='Wiki Pages';").strip() == "1"
        before = tkt.ok("run", "uv", "list")
        tkt.ok("init")
        assert tkt.ok("run", "uv", "list") == before

    def test_empties_the_old_guide_page(self, tkt):
        tkt.ok("run", "wiki", "create", "agents/FormattingHelp", "-", "--mimetype", "text/x-markdown", input="# old guide\n")
        assert "emptied the agents/FormattingHelp wiki page" in tkt("init").stderr
        page = tkt.ok("run", "wiki", "export", "agents/FormattingHelp")
        assert page.strip() == ""

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
        assert "Reports /ticket" in menu
        # the wiki's entries come from the wiki plugin's menu config, not the core menu
        assert "Project Wiki" not in menu
        # recent activity is the title link, so it has no menu entry
        assert "Recent Activity" not in menu
        assert "skin=" not in menu
        assert "builtin/skins/blitz/css.txt?mimetype=text/css" in config(tkt.db, "header")
        assert 'id="tkt-theme"' in config(tkt.db, "header")
        assert "html[data-theme=dark]" in config(tkt.db, "css")
        css = config(tkt.db, "css")
        assert "a.tkt-facet" in css and "#f2dcdc" not in css
        assert tkt.sql("select count(*) from reportfmt where owner='tkt' and (sqlcode like '%bgcolor%' or cols <> '');") == "0"
        assert "function facets()" in config(tkt.db, "header") and "function zoomButtons()" in config(tkt.db, "header")
        assert "div.container { max-width: none; width: 84%; }" in css and "header .container { display: flex;" in css
        assert tkt.sql("select count(*) from reportfmt where owner='tkt' and sqlcode like '%subsystem%';") == "7"
        common = config(tkt.db, "ticket-common")
        assert "set subsystem_choices {\n  automation\n  tests\n  docs\n  cli\n  devx\n  ux\n  ui\n}" in common
        assert "Code_Defect" in common
        assert config(tkt.db, "footer") and config(tkt.db, "details")
        titles = tkt.sql("select title from reportfmt order by title;").split("\n")
        for t in ("All Tickets", "Open Tickets", "Critical and Severe", "Recent Activity", "By Tag", "Blocked", "Recently Closed", "Tagged Tickets", "By State"):
            assert t in titles
        assert 'name="description"' in config(tkt.db, "ticket-newpage")
        edit = config(tkt.db, "ticket-editpage")
        assert 'name="description"' in edit and "text/x-markdown" in edit
        view = config(tkt.db, "ticket-viewpage")
        assert "status=Closed&amp;resolution=Fixed" in view
        assert view.count('markdown "<!-- -->\\n\\n$') == 2


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


class TestHighlight:
    def test_on_by_default(self, tkt):
        header = config(tkt.db, "header")
        assert header.count("cdnjs.cloudflare.com/ajax/libs/prism/") == 2
        assert 'integrity="sha384-' in header and "defer" in header
        assert header.index("prism-core") < header.index('<script nonce="$nonce">\n(function(){')
        csp = config(tkt.db, "default-csp")
        assert "'nonce-$nonce' https://cdnjs.cloudflare.com" in csp and csp.startswith("default-src 'self'")
        assert ".token.keyword" in config(tkt.db, "css") and "html[data-theme=dark] .token.keyword" in config(tkt.db, "css")

    def test_env_turns_it_off_at_init_and_at_serve(self, tkt):
        r = run("init", db=tkt.db, cwd=tkt.cwd, extra={"TKT_HIGHLIGHT": "0"})
        assert r.returncode == 0, r.stderr
        assert "prism" not in config(tkt.db, "header")
        assert 'id="tkt-theme"' in config(tkt.db, "header")
        import socket

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        p = subprocess.Popen([*TKT, "serve", f"port={port}"], cwd=tkt.cwd, env={**os.environ, "TKT_DB": str(tkt.db)},
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert p.stdout.readline().startswith("http://localhost:")
            assert "prism-core" in config(tkt.db, "header")
        finally:
            p.terminate()
            p.wait(timeout=10)
            tkt.ok("stop")


class TestMermaid:
    def test_on_by_default_and_lazy(self, tkt):
        header = config(tkt.db, "header")
        assert header.count("cdnjs.cloudflare.com/ajax/libs/mermaid/") == 1
        assert "integrity='sha512-" in header and "code.language-mermaid" in header
        # fetched by script only on pages with a block, so no static script tag for it
        assert '<script nonce="$nonce" src="https://cdnjs.cloudflare.com/ajax/libs/mermaid' not in header
        # claims the blocks before prism's deferred scripts register their listener
        assert header.index("language-mermaid") < header.index("prism-core")

    def test_env_turns_it_off(self, tkt):
        r = run("init", db=tkt.db, cwd=tkt.cwd, extra={"TKT_MERMAID": "0"})
        assert r.returncode == 0, r.stderr
        header = config(tkt.db, "header")
        assert "mermaid" not in header and "prism-core" in header


PRISM_CORE = "prism/1.29.0/components/prism-core.min.js"
MERMAID_JS = "mermaid/12.3.0/mermaid.min.js"


# the page scripts init stored; the formatting guide, also unversioned, is not one of them
def stored(tkt):
    return tkt.sql("select name from unversioned where name not like 'help/%' order by name;").split()


class TestOfflineAssets:
    def mirror(self, root, files):
        for name, body in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(body)
        return {"TKT_CDN": root.as_uri()}

    def test_unreachable_cdn_leaves_pages_on_it(self, tkt):
        assert stored(tkt) == []
        header = config(tkt.db, "header")
        assert "https://cdnjs.cloudflare.com/ajax/libs/" + PRISM_CORE in header
        assert "https://cdnjs.cloudflare.com/ajax/libs/" + MERMAID_JS in header

    def test_reports_what_it_could_not_fetch(self, tkt):
        r = run("init", db=tkt.db, cwd=tkt.cwd)
        assert r.returncode == 0, r.stderr
        assert "page scripts: fetching 54 from file:///nonexistent/tkt-cdn" in r.stderr
        assert "page scripts: 54 not stored" in r.stderr

    def test_stores_unpinned_grammars_from_the_mirror(self, tkt, tmp_path):
        env = self.mirror(tmp_path / "cdn", {"prism/1.29.0/components/prism-go.min.js": "Prism.languages.go={};"})
        r = run("init", db=tkt.db, cwd=tkt.cwd, extra=env)
        assert r.returncode == 0, r.stderr
        assert "page scripts: stored 1 in the tracker" in r.stderr
        assert stored(tkt) == ["prism/1.29.0/components/prism-go.min.js"]
        assert tkt.ok("run", "uv", "cat", "prism/1.29.0/components/prism-go.min.js") == "Prism.languages.go={};"

    def test_rejects_a_pinned_file_whose_hash_differs(self, tkt, tmp_path):
        env = self.mirror(tmp_path / "cdn", {PRISM_CORE: "tampered", MERMAID_JS: "tampered"})
        r = run("init", db=tkt.db, cwd=tkt.cwd, extra=env)
        assert r.returncode == 0, r.stderr
        assert f"page scripts: {PRISM_CORE} does not match its pinned hash, skipped" in r.stderr
        assert stored(tkt) == []

    def test_pages_load_stored_copies(self, tkt):
        (tkt.cwd / "core.js").write_text("core")
        (tkt.cwd / "mermaid.js").write_text("mermaid")
        user = tkt.sql("select login from user where cap glob '*s*' limit 1;")
        tkt.ok("run", "uv", "add", str(tkt.cwd / "core.js"), "--as", PRISM_CORE, "--user", user)
        tkt.ok("run", "uv", "add", str(tkt.cwd / "mermaid.js"), "--as", MERMAID_JS, "--user", user)
        tkt.ok("init")
        header = config(tkt.db, "header")
        assert f'src="$home/uv/{PRISM_CORE}" integrity="sha384-' in header
        assert f"s.src='$home/uv/{MERMAID_JS}'" in header
        # the autoloader is not stored, so it stays on the cdn
        assert "https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/" in header
        # a rerun keeps what is stored rather than fetching it again
        assert tkt.ok("run", "uv", "cat", PRISM_CORE) == "core"

    def test_nothing_to_fetch_says_nothing(self, tkt):
        r = run("init", db=tkt.db, cwd=tkt.cwd, extra={"TKT_HIGHLIGHT": "0", "TKT_MERMAID": "0"})
        assert "page scripts" not in r.stderr

    @script_only
    def test_a_failing_store_does_not_break_init(self, tkt, tmp_path):
        env = self.mirror(tmp_path / "cdn", {"prism/1.29.0/components/prism-go.min.js": "go"})
        bin = tmp_path / "bin"
        bin.mkdir()
        real = shutil.which("fossil")
        (bin / "fossil").write_text(f'#!/bin/sh\n[ "$1" = uv ] && {{ echo "uv is broken" >&2; exit 1; }}\nexec {real} "$@"\n')
        (bin / "fossil").chmod(0o755)
        r = run("init", db=tkt.db, cwd=tkt.cwd, extra={**env, "PATH": f"{bin}:{os.environ['PATH']}"})
        assert r.returncode == 0, r.stderr
        assert "page scripts: could not store them (uv is broken)" in r.stderr
        assert "ready at" in r.stderr and stored(tkt) == []

    def test_env_off_fetches_nothing(self, tkt, tmp_path):
        env = self.mirror(tmp_path / "cdn", {"prism/1.29.0/components/prism-go.min.js": "go"})
        r = run("init", db=tkt.db, cwd=tkt.cwd, extra={**env, "TKT_HIGHLIGHT": "0", "TKT_MERMAID": "0"})
        assert r.returncode == 0, r.stderr
        assert stored(tkt) == [] and "page scripts" not in r.stderr

    @pytest.mark.skipif(os.environ.get("TKT_NET") != "1", reason="reaches cdnjs; set TKT_NET=1")
    def test_fetches_everything_from_cdnjs(self, tkt):
        r = run("init", db=tkt.db, cwd=tkt.cwd, extra={"TKT_CDN": "https://cdnjs.cloudflare.com/ajax/libs"})
        assert r.returncode == 0, r.stderr
        names = stored(tkt)
        assert PRISM_CORE in names and MERMAID_JS in names and len(names) > 40


class TestGithubLinks:
    def test_absent_outside_git(self, tkt):
        assert "tkt-github" not in config(tkt.db, "header")

    def test_absent_without_a_github_remote(self, tkt):
        git(tkt.cwd, "init", "-q")
        git(tkt.cwd, "remote", "add", "origin", "https://gitlab.com/o/r.git")
        tkt.ok("init")
        assert "tkt-github" not in config(tkt.db, "header")

    @pytest.mark.parametrize("remote", ["git@github.com:o/r.git", "https://github.com/o/r", "ssh://git@github.com/o/r.git"])
    def test_init_links_actions_issues_and_main(self, tkt, remote):
        git(tkt.cwd, "init", "-q")
        git(tkt.cwd, "remote", "add", "origin", remote)
        tkt.ok("init")
        header = config(tkt.db, "header")
        # floated right, so markup order is reversed on screen: github sits beside the sitemap, right of the theme toggle
        assert header.index('class="tkt-github"') < header.index('id="tkt-theme"')
        for href in ("https://github.com/o/r", "https://github.com/o/r/actions", "https://github.com/o/r/issues", "https://github.com/o/r/tree/main"):
            assert f'href="{href}"' in header
        drop = header[header.index('id="tkt-ghdrop"'):]
        assert drop.index(">Actions<") < drop.index(">Issues<") < drop.index(">Main<")

    def test_main_follows_the_default_branch(self, tkt):
        git(tkt.cwd, "init", "-q")
        git(tkt.cwd, "remote", "add", "origin", "git@github.com:o/r.git")
        Path(tkt.cwd / ".git/refs/remotes/origin").mkdir(parents=True, exist_ok=True)
        git(tkt.cwd, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        tkt.ok("init")
        assert 'href="https://github.com/o/r/tree/trunk"' in config(tkt.db, "header")

    def test_serve_refreshes_the_header(self, tkt):
        import socket

        assert "tkt-github" not in config(tkt.db, "header")
        git(tkt.cwd, "init", "-q")
        git(tkt.cwd, "remote", "add", "origin", "git@github.com:o/r.git")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            port = s.getsockname()[1]
            tkt.fails("serve", f"port={port}", match="is taken")
            assert "tkt-github" not in config(tkt.db, "header")
        p = subprocess.Popen([*TKT, "serve", f"port={port}"], cwd=tkt.cwd, env={**os.environ, "TKT_DB": str(tkt.db)},
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert p.stdout.readline().startswith("http://localhost:")
            assert 'href="https://github.com/o/r/issues"' in config(tkt.db, "header")
        finally:
            p.terminate()
            p.wait(timeout=10)
            tkt.ok("stop")
        assert "nav.tkt-ghdrop" in config(tkt.db, "css")


class TestServeOpensBrowser:
    def serve_on_tty(self, tkt, tmp_path, **env):
        """Serve on a pty with a fake $BROWSER that records its argument, stop once the server is up, and return what it recorded."""
        import socket

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        seen = tmp_path / "seen"
        browser = tmp_path / "browser"
        browser.write_text(f"#!/bin/sh\nprintf '%s' \"$1\" >{seen}\n")
        browser.chmod(0o755)
        full = {k: v for k, v in os.environ.items() if k != "TKT_DB"}
        full.update(TKT_DB=str(tkt.db), BROWSER=str(browser), **env)
        parent, child = pty.openpty()
        proc = subprocess.Popen([*TKT, "serve", f"port={port}"], stdin=subprocess.DEVNULL, stdout=child, stderr=child, env=full, cwd=tkt.cwd)
        os.close(child)
        try:
            for _ in range(100):
                if seen.exists() or proc.poll() is not None:
                    break
                with socket.socket() as s:
                    if s.connect_ex(("127.0.0.1", port)) == 0 and env.get("TKT_OPEN") == "0":
                        time.sleep(0.5)
                        break
                time.sleep(0.1)
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            tkt.ok("stop")
            os.close(parent)
        return seen.read_text() if seen.exists() else None, port

    def test_opens_the_url_on_a_terminal(self, tkt, tmp_path):
        seen, port = self.serve_on_tty(tkt, tmp_path)
        assert seen == f"http://localhost:{port}/ticket"

    def test_tkt_open_zero_skips_it(self, tkt, tmp_path):
        seen, _ = self.serve_on_tty(tkt, tmp_path, TKT_OPEN="0")
        assert seen is None

    def test_no_terminal_skips_it(self, tkt, tmp_path):
        import socket

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        seen = tmp_path / "seen"
        browser = tmp_path / "browser"
        browser.write_text(f"#!/bin/sh\nprintf '%s' \"$1\" >{seen}\n")
        browser.chmod(0o755)
        p = subprocess.Popen([*TKT, "serve", f"port={port}"], cwd=tkt.cwd, env={**os.environ, "TKT_DB": str(tkt.db), "BROWSER": str(browser)},
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert p.stdout.readline().startswith("http://localhost:")
            for _ in range(50):
                with socket.socket() as s:
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        break
                time.sleep(0.1)
            time.sleep(0.5)
        finally:
            p.terminate()
            p.wait(timeout=10)
            tkt.ok("stop")
        assert not seen.exists()


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


class TestParent:
    def test_both_directions(self, tkt):
        p = tkt.new("epic")
        a = tkt.new("first")
        b = tkt.new("second")
        tkt.ok("parent", a, p[:6])
        tkt.ok("parent", b, p)
        assert re.search(rf"## Parent\n\n- {p} \| Open \| epic", tkt.show(a))
        assert re.search(rf"## Subtasks\n\n- {a} \| Open \| first\n- {b} \| Open \| second", tkt.show(p))

    def test_new_with_parent(self, tkt):
        p = tkt.new("epic")
        a = tkt.new("child", parent=p[:6])
        assert "## Parent" in tkt.show(a)

    def test_list_filters_by_parent(self, tkt):
        p = tkt.new("epic")
        a = tkt.new("child", parent=p)
        other = tkt.new("unrelated")
        out = tkt.ok("list", f"parent={p[:6]}")
        assert a in out and other not in out and p not in out

    def test_self_parent_fails(self, tkt):
        a = tkt.new("self")
        tkt.fails("parent", a, a, match="its own parent")

    def test_one_level_deep(self, tkt):
        p = tkt.new("epic")
        a = tkt.new("child", parent=p)
        b = tkt.new("grandchild")
        tkt.fails("parent", b, a, match="is itself a subtask")
        tkt.fails("new", "title=nested", f"parent={a}", match="is itself a subtask")
        tkt.fails("parent", p, b, match="has subtasks of its own")

    def test_one_parent_only(self, tkt):
        p = tkt.new("epic")
        q = tkt.new("other")
        a = tkt.new("child")
        tkt.fails("parent", a, p, q, match="one parent")
        tkt.fails("parent", a, match="use --clear")

    def test_parent_cannot_block_its_subtask(self, tkt):
        p = tkt.new("epic")
        a = tkt.new("child", parent=p)
        tkt.fails("block", a, p, match="cannot block its subtask")
        b = tkt.new("waits")
        tkt.ok("block", b, p)
        tkt.fails("parent", b, p, match="cannot block its subtask")
        assert "## Parent" not in tkt.show(b)

    def test_subtask_may_also_be_an_explicit_blocker(self, tkt):
        p = tkt.new("epic")
        a = tkt.new("child", parent=p)
        tkt.ok("block", p, a)
        assert "## Blocked by" in tkt.show(p)

    def test_unknown_id_fails(self, tkt):
        a = tkt.new("child")
        tkt.fails("parent", a, "ffffffff", match="matches no single ticket")

    def test_reparent_and_clear(self, tkt):
        p = tkt.new("epic")
        q = tkt.new("other")
        a = tkt.new("child", parent=p)
        tkt.ok("parent", a, q)
        assert "## Subtasks" not in tkt.show(p)
        assert "## Subtasks" in tkt.show(q)
        tkt.ok("parent", a, "--clear")
        assert "## Parent" not in tkt.show(a)
        assert "## Subtasks" not in tkt.show(q)

    def test_open_subtasks_block_the_parent(self, tkt):
        p = tkt.new("epic")
        a = tkt.new("child", parent=p)
        report = tkt.sql("select sqlcode from reportfmt where title='Blocked';")
        assert p in tkt.sql(report) and a in tkt.sql(report)
        tkt.ok("close", a)
        assert p not in tkt.sql(report)

    def test_close_warns_of_open_subtasks(self, tkt):
        p = tkt.new("epic")
        tkt.new("child", parent=p)
        r = run("close", p, db=tkt.db)
        assert r.returncode == 0 and "1 open subtask" in r.stderr


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
        cases = {"comment": "comment", "icomment": "comment", "description": "edit", "tags": "tag", "blockers": "block", "parent": "parent"}
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


class TestTodo:
    def seed(self, tkt):
        a = tkt.new("old minor", severity="Minor", subsystem="ui")
        b = tkt.new("closed critical", severity="Critical")
        tkt.ok("close", b)
        c = tkt.new("severe one", severity="Severe", subsystem="core")
        d = tkt.new("severe two", severity="Severe")
        return a, b, c, d

    def test_newest_open_first_with_the_four_columns(self, tkt):
        a, b, c, d = self.seed(tkt)
        rows = tkt.ok("todo").strip().split("\n")
        assert [r.split(" | ")[0] for r in rows] == [d, c, a]
        assert rows[1] == f"{c} | severe one | Severe | core"
        assert rows[2] == f"{a} | old minor | Minor | ui"
        assert b not in tkt.ok("todo")

    def test_n_limits(self, tkt):
        a, b, c, d = self.seed(tkt)
        rows = tkt.ok("todo", "2").strip().split("\n")
        assert [r.split(" | ")[0] for r in rows] == [d, c]

    def test_triage_keeps_only_the_top_severity_present(self, tkt):
        a, b, c, d = self.seed(tkt)
        for out in (tkt.ok("todo", "--triage"), tkt.ok("triage"), tkt.ok("triage", "1")):
            assert d in out and a not in out and b not in out
        assert c in tkt.ok("triage") and c not in tkt.ok("triage", "1")
        tkt.new("now critical", severity="Critical")
        out = tkt.ok("triage")
        assert "now critical" in out and c not in out and d not in out

    def test_empty(self, tkt):
        assert tkt.ok("todo") == ""
        assert tkt.ok("triage", "-f", "json").strip() == "[]"
        assert tkt.ok("todo", "-f", "md").strip() == ""

    def test_json(self, tkt):
        import json

        a, b, c, d = self.seed(tkt)
        rows = json.loads(tkt.ok("todo", "-f", "json"))
        assert [r["id"] for r in rows] == [d, c, a]
        assert rows[1] == {"id": c, "title": "severe one", "severity": "Severe", "subsystem": "core"}
        assert rows[2]["subsystem"] == "ui" and rows[0]["subsystem"] == "-"
        assert json.loads(tkt.ok("todo", "--format=json", "1")) == rows[:1]

    def test_markdown(self, tkt):
        a, b, c, d = self.seed(tkt)
        lines = tkt.ok("todo", "--format", "md").strip().split("\n")
        assert lines[0].split() == "| id | title | severity | subsystem |".split()
        assert set(lines[1]) <= set("|-")
        assert len(lines) == 5 and c in lines[3]

    def test_bad_arguments(self, tkt):
        tkt.fails("todo", "x", match="usage: tkt todo")
        tkt.fails("todo", "-f", match="usage: tkt todo")
        tkt.fails("todo", "-f", "yaml", match="unknown format: yaml")
        tkt.fails("triage", "--format=csv", match="unknown format: csv")

    def test_color_on_a_terminal_only(self, tkt):
        self.seed(tkt)
        assert "\x1b[" not in tkt.ok("todo")
        assert "\x1b[1m" in run_tty("todo", db=tkt.db)


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


@script_only
class TestLibrary:
    """Sourced, tkt is a library: it defines functions and runs nothing, so a plugin can use its helpers."""

    def source(self, script, db=None, args=(), extra=None):
        env = {k: v for k, v in os.environ.items() if k != "TKT_DB"}
        if db is not None:
            env["TKT_DB"] = str(db)
        env.update(extra or {})
        # the caller's own arguments must not reach tkt's command parser
        return subprocess.run([BASH, "-c", f'source "$0"\n{script}', str(SCRIPT), *args],
                              capture_output=True, text=True, env=env)

    def test_sourcing_runs_nothing(self):
        r = self.source("echo loaded", args=("bogus-verb", "x"))
        assert r.returncode == 0, r.stderr
        assert r.stdout == "loaded\n" and r.stderr == ""

    def test_sourcing_ignores_cgi_variables(self):
        r = self.source("echo loaded", extra={"GATEWAY_INTERFACE": "CGI/1.0", "FOSSIL_REPOSITORY": "x.fossil"})
        assert r.stdout == "loaded\n" and "Status:" not in r.stdout

    def test_sourcing_leaves_shell_options_alone(self):
        r = self.source('case $- in *e*) echo errexit;; esac; shopt -qo pipefail && echo pipefail; false; echo survived')
        assert r.stdout == "survived\n"

    def test_helpers_work_after_locate(self, tkt):
        t = tkt.new("from a plugin")
        r = self.source('set -eo pipefail; locate; need; sqlq "select title from ticket;"; resolve ' + t[:6] + '; echo; lit "o\'brien"',
                        db=tkt.db)
        assert r.returncode == 0, r.stderr
        assert r.stdout == f"from a plugin\n{t}\n'o''brien'"

    def test_use_repo_derives_every_path(self, tmp_path):
        r = self.source('use_repo /p/x/.tkt.fossil; printf "%s\\n" "$REPO" "$PROJECT_DIR" "$CONFIG_FILE" "$DOTENV_FILE" "$EXT_DIR" "$JOBS_DIR" "$PID_FILE"')
        assert r.stdout.split() == ["/p/x/.tkt.fossil", "/p/x", "/p/x/.tkt/tkt.json", "/p/x/.env",
                                    "/p/x/.tkt/ext", "/p/x/.tkt/jobs", "/p/x/.tkt/tkt.pid"]

    def test_find_repo_search_order(self, tmp_path):
        top = tmp_path / "top"
        (top / "a" / "b").mkdir(parents=True)
        (top / ".tkt.fossil").write_text("")
        def find(cwd, db=None):
            env = {k: v for k, v in os.environ.items() if k != "TKT_DB"}
            if db:
                env["TKT_DB"] = db
            return subprocess.run([BASH, "-c", 'source "$0"; find_repo', str(SCRIPT)], capture_output=True,
                                  text=True, env=env, cwd=cwd).stdout
        # the nearest tracker here or above; TKT_DB, relative to here, wins over it
        assert find(top / "a" / "b") == str(top / ".tkt.fossil")
        assert find(top / "a", db="own.fossil") == str(top / "a" / "own.fossil")
        # with none above, where init would make one: outside git, here
        lone = tmp_path / "lone"
        lone.mkdir()
        assert find(lone) == str(lone / ".tkt.fossil")

    def test_running_still_works(self, tkt):
        assert tkt("list").returncode == 0
        assert run("bogus-verb", db=tkt.db).returncode != 0


class TestPluginEntry:
    def ext(self, tkt, name):
        d = tkt.db.parent / ".tkt" / "plugins" / name
        d.mkdir(parents=True)
        return d

    def test_an_entry_file_runs_under_what_its_extension_names(self, tkt):
        # no first line naming an interpreter and no exec bit: the extension alone says what runs it
        entry = self.ext(tkt, "echo") / "main.sh"
        entry.write_text('printf "%s|" "$0" "$TKT_DB" "$@"\n')
        assert tkt.ok("echo", "a b", "c") == f"{entry}|{tkt.db}|a b|c|"

    def test_a_plugin_exits_with_its_own_code(self, tkt):
        (self.ext(tkt, "three") / "main.sh").write_text("exit 3\n")
        assert tkt("three").returncode == 3

    def test_a_plugin_without_an_entry_file_is_an_error(self, tkt):
        self.ext(tkt, "hollow")
        tkt.fails("hollow", match=r"plugin hollow has no entry file: .*/\.tkt/plugins/hollow holds no main or web with a supported extension \(sh micropy\)")

    def test_a_plugin_is_told_about_tkt_and_about_itself(self, tkt):
        d = self.ext(tkt, "facts")
        (d / "main.sh").write_text('printf "%s\\n" "$TKT_PLUGIN_NAME" "$TKT_PLUGIN_DIR" "$TKT_PLUGIN_URL" "$TKT_DB"; [ -f "$TKT_LIB" ] && [ -x "$TKT_SELF" ]\n')
        assert tkt.ok("facts").splitlines() == ["facts", str(d), "/ext/tkt/ext/facts", str(tkt.db)]

    def test_a_plugin_with_only_a_web_entry_offers_no_verb_and_no_init(self, tkt):
        (self.ext(tkt, "pageonly") / "web.sh").write_text("echo ran >&2\n")
        tkt.fails("pageonly", match="unknown verb: pageonly")
        r = tkt("init")
        assert r.returncode == 0 and "pageonly" not in r.stderr and "plugin init(s) failed" not in r.stderr

    def test_main_is_the_command_and_web_is_the_page(self, tkt):
        d = self.ext(tkt, "both")
        (d / "main.sh").write_text('echo "command $*"\n')
        (d / "web.sh").write_text('printf "Content-Type: text/plain\\r\\n\\r\\npage %s" "$SCRIPT_NAME"\n')
        assert tkt.ok("both", "x") == "command x\n"
        assert cgi(tkt, "/ext/both/web.sh")[1] == "page /ext/tkt/ext/both/web.sh"
        assert cgi(tkt, "/ext/both")[1] == "page /ext/tkt/ext/both"

    def test_an_entry_file_without_an_extension_is_not_one(self, tkt):
        legacy = self.ext(tkt, "legacy") / "main"
        legacy.write_text("#!/bin/sh\necho ran\n")
        legacy.chmod(0o755)
        tkt.fails("legacy", match="plugin legacy has no entry file")

    def test_init_reports_a_plugin_without_an_entry_file_and_carries_on(self, tkt):
        self.ext(tkt, "hollow")
        r = tkt("init")
        assert r.returncode == 0, r.stderr
        assert "plugin hollow has no entry file" in r.stderr and "1 plugin init(s) failed" in r.stderr


class TestConfigLayers:
    """The config is layers, nearer over farther: tkt's own, a folder of plugins' file, each plugin's, the tracker's."""

    pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="the config needs jq")

    def own(self, tkt, config):
        (tkt.db.parent / ".tkt").mkdir(exist_ok=True)
        (tkt.db.parent / ".tkt" / "tkt.json").write_text(config if isinstance(config, str) else json.dumps(config))

    def far(self, tmp_path, folder=None, greet=None):
        far = tmp_path / "far"
        (far / "greet").mkdir(parents=True, exist_ok=True)
        (far / "greet" / "main.sh").write_text("echo far\n")
        if folder is not None:
            (far / "tkt.json").write_text(folder if isinstance(folder, str) else json.dumps(folder))
        if greet is not None:
            (far / "greet" / "tkt.json").write_text(greet if isinstance(greet, str) else json.dumps(greet))
        return {"TKT_PLUGINS": str(far)}

    def rows(self, tkt, extra=None):
        out = run("action", "list", db=tkt.db, extra=extra).stdout
        return [[c.strip() for c in line.strip("|").split("|")] for line in out.splitlines()[2:]]

    def names(self, tkt, extra=None):
        return [r[0] for r in self.rows(tkt, extra)]

    def test_tkt_gives_clean_jobs_with_no_file_at_all(self, tkt):
        assert self.names(tkt) == ["clean-jobs"]

    def test_a_trackers_records_go_after_the_ones_it_inherits(self, tkt):
        self.own(tkt, {"actions": [{"name": "mine", "command": ["true"]}]})
        assert self.names(tkt) == ["clean-jobs", "mine"]

    def test_a_record_with_an_inherited_name_replaces_it_whole_and_in_place(self, tkt):
        self.own(tkt, {"actions": [{"name": "mine", "command": ["true"]}, {"name": "clean-jobs", "command": ["echo", "x"]}]})
        first = self.rows(tkt)[0]
        # the label falls back to the name and the icon is gone: nothing of the inherited record is left
        assert first[0] == "clean-jobs" and first[1] == "clean-jobs" and first[2] == "" and first[5] == "`echo x`"
        assert self.names(tkt) == ["clean-jobs", "mine"]

    def test_enabled_false_removes_an_inherited_record(self, tkt):
        self.own(tkt, {"actions": [{"name": "clean-jobs", "enabled": False}, {"name": "mine", "command": ["true"]}]})
        assert self.names(tkt) == ["mine"]

    def test_an_empty_list_still_inherits(self, tkt):
        self.own(tkt, {"actions": []})
        assert self.names(tkt) == ["clean-jobs"]

    def test_a_list_of_plain_values_is_one_value_and_the_nearer_wins(self, tkt, tmp_path):
        extra = self.far(tmp_path, folder={"agent": ["far", "{prompt}"]})
        def command(name):
            return next(r[5] for r in self.rows(tkt, extra) if r[0] == name)

        self.own(tkt, {"actions": [{"name": "polish", "skill": ["polish"]}]})
        assert command("polish") == "`far /tkt {ticket} polish`"
        self.own(tkt, {"agent": ["near", "{prompt}"], "actions": [{"name": "polish", "skill": ["polish"]}]})
        assert command("polish") == "`near /tkt {ticket} polish`"

    def test_a_plugin_brings_its_own_config_and_the_tracker_can_change_it(self, tkt, tmp_path):
        extra = self.far(tmp_path, greet={"actions": [{"name": "hello", "command": ["echo", "hi"]}]})
        assert self.names(tkt, extra) == ["clean-jobs", "hello"]
        assert self.names(tkt) == ["clean-jobs"]
        self.own(tkt, {"plugins": {"greet": {"actions": [{"name": "hello", "enabled": False}]}}})
        assert self.names(tkt, extra) == ["clean-jobs"]

    def test_a_plugins_config_is_that_of_the_copy_that_won(self, tkt, tmp_path):
        extra = self.far(tmp_path, greet={"actions": [{"name": "hello", "command": ["echo", "hi"]}]})
        own = tkt.db.parent / ".tkt" / "plugins" / "greet"
        own.mkdir(parents=True)
        (own / "main.sh").write_text("echo own\n")
        (own / "tkt.json").write_text(json.dumps({"actions": [{"name": "mine", "command": ["true"]}]}))
        assert self.names(tkt, extra) == ["clean-jobs", "mine"]

    def test_a_layer_that_is_not_json_is_skipped(self, tkt, tmp_path):
        extra = self.far(tmp_path, folder="// only a comment\n{ nope", greet={"actions": [{"name": "hello", "command": ["true"]}]})
        assert self.names(tkt, extra) == ["clean-jobs", "hello"]
        self.own(tkt, "{ nope")
        r = run("action", "list", db=tkt.db, extra=extra)
        assert "is not valid json" in r.stderr and "so it is ignored" in r.stderr
        assert self.names(tkt, extra) == ["clean-jobs", "hello"]

    def test_comment_lines_are_allowed_in_every_layer(self, tkt, tmp_path):
        extra = self.far(tmp_path, greet='// a plugin explains itself\n{"actions": [\n  // one action\n  {"name": "hello", "command": ["true"]}\n]}\n')
        self.own(tkt, '// so does a tracker\n{"actions": [{"name": "mine", "command": ["true"]}]}\n')
        # top-level actions are listed before the plugins' own, as ever
        assert self.names(tkt, extra) == ["clean-jobs", "mine", "hello"]


class TestOldPluginLayout:
    def test_init_moves_a_plugin_and_its_files_into_one_folder(self, tkt):
        dot = tkt.db.parent / ".tkt"
        (dot / "ext" / "old" / "css").mkdir(parents=True)
        (dot / "ext" / "old" / "main").write_text('echo "old $*"\n')
        (dot / "ext" / "old" / "css" / "old.css").write_text("a{}\n")
        (dot / "ext" / "tkt").symlink_to(SCRIPT)
        (dot / "sql" / "old").mkdir(parents=True)
        (dot / "sql" / "old" / "schema.sql").write_text("-- old\n")
        (dot / "skill").mkdir()
        (dot / "skill" / "old.md").write_text("## Old\n")
        r = tkt("init")
        assert r.returncode == 0 and f"moved the plugin old to {dot / 'plugins' / 'old'}" in r.stderr
        new = dot / "plugins" / "old"
        assert (new / "main.sh").is_file() and (new / "web" / "css" / "old.css").is_file()
        assert (new / "sql" / "schema.sql").is_file() and (new / "skill.md").is_file()
        # fossil's folder is left with the link to tkt alone, and the emptied folders are gone
        assert [p.name for p in (dot / "ext").iterdir()] == ["tkt"]
        assert not (dot / "sql").exists() and not (dot / "skill").exists()
        assert tkt.ok("old", "x") == "old x\n"


class TestPluginPath:
    """TKT_PLUGINS names more folders of plugins, searched after the tracker's own, in order."""

    def home(self, tmp_path, name, **plugins):
        home = tmp_path / name
        for plugin, says in plugins.items():
            (home / plugin).mkdir(parents=True)
            (home / plugin / "main.sh").write_text(f'echo "{says} $*"\n')
        return home

    def test_a_plugin_is_found_in_a_folder_on_the_path(self, tkt, tmp_path):
        far = self.home(tmp_path, "far", greet="far")
        assert run("greet", "you", db=tkt.db, extra={"TKT_PLUGINS": str(far)}).stdout == "far you\n"
        tkt.fails("greet", match="unknown verb: greet")

    def test_the_trackers_own_plugin_wins(self, tkt, tmp_path):
        far = self.home(tmp_path, "far", greet="far")
        self.home(tkt.db.parent / ".tkt", "plugins", greet="own")
        assert run("greet", db=tkt.db, extra={"TKT_PLUGINS": str(far)}).stdout == "own \n"

    def test_earlier_folders_win_and_empty_or_missing_ones_are_skipped(self, tkt, tmp_path):
        a, b = self.home(tmp_path, "a", greet="a"), self.home(tmp_path, "b", greet="b", only="b")
        path = f":{tmp_path / 'nowhere'}:{a}::{b}:"
        assert run("greet", db=tkt.db, extra={"TKT_PLUGINS": path}).stdout == "a \n"
        assert run("only", db=tkt.db, extra={"TKT_PLUGINS": path}).stdout == "b \n"

    def test_a_directory_without_an_entry_does_not_hide_a_later_plugin(self, tkt, tmp_path):
        far = self.home(tmp_path, "far", greet="far")
        (tkt.db.parent / ".tkt" / "plugins" / "greet" / "web" / "icons").mkdir(parents=True)
        assert run("greet", db=tkt.db, extra={"TKT_PLUGINS": str(far)}).stdout == "far \n"

    def test_a_plugins_files_are_the_ones_beside_it(self, tmp_path):
        install_plugins(tmp_path / "shipped", "tet", "wiki", always=True)
        extra = {"TKT_PLUGINS": str(tmp_path / "shipped" / ".tkt" / "plugins")}
        project = tmp_path / "project"
        project.mkdir()
        db = project / "tracker.fossil"
        r = run("init", db=db, extra=extra)
        assert r.returncode == 0, r.stderr
        assert "init tet: ok" in r.stderr and "init wiki: ok" in r.stderr
        # the wiki's seed pages and tet's schema came from the folder the plugins are in, and nothing was copied here
        assert "agents/Home" in run("wiki", "ls", db=db, extra=extra).stdout
        assert run("tet", "list", db=db, extra=extra).returncode == 0
        assert not (project / ".tkt" / "plugins").exists() and not (project / ".tkt" / "bin").exists()
        assert "\n## Plugins\n" in run("skill", cwd=project, extra={**extra, "TKT_DB": str(db)}).stdout


class TestSkill:
    # how tkt's own part of the skill opens: the front matter an agent reads to decide when to load it
    OPENING = "---\nname: tkt\ndescription: "

    def test_prints_its_own_part_outside_a_project(self, tmp_path):
        printed = run("skill", cwd=tmp_path).stdout
        assert printed.startswith(self.OPENING) and "allowed-tools: Bash(tkt:*)" in printed
        assert "tkt start" in self.own_part(printed)
        # outside any project no plugin adds a section, unless the tkt under test carries plugins of its own
        assert os.environ.get("TKT_CMD") or "\n## Plugins\n" not in printed

    def own_part(self, printed):
        return printed.split("\n## Plugins\n")[0]

    def test_install_for_user(self, tmp_path):
        r = run("skill", "install", extra={"HOME": str(tmp_path), "CLAUDE_CONFIG_DIR": ""})
        assert r.returncode == 0, r.stderr
        # the copy for every project is what tkt prints outside any one project
        installed = (tmp_path / ".claude" / "skills" / "tkt" / "SKILL.md").read_text()
        assert installed == run("skill", cwd=tmp_path).stdout

    def test_install_for_user_carries_the_plugins_on_the_search_path(self, tmp_path):
        far = tmp_path / "far"
        (far / "greet").mkdir(parents=True)
        (far / "greet" / "main.sh").write_text("echo hi\n")
        (far / "greet" / "skill.md").write_text("## Greet\n\nSay hi.\n")
        r = run("skill", "install", extra={"HOME": str(tmp_path / "h"), "CLAUDE_CONFIG_DIR": "", "TKT_PLUGINS": str(far)})
        assert r.returncode == 0, r.stderr
        installed = (tmp_path / "h" / ".claude" / "skills" / "tkt" / "SKILL.md").read_text()
        assert "\n## Plugins\n" in installed and "\n### Greet\n\nSay hi.\n" in installed

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

    def test_init_leaves_projects_without_an_agent_dir_alone(self, project):
        r = run("init", cwd=project)
        assert r.returncode == 0, r.stderr
        assert not any((project / d).exists() for d in (".claude", ".pi", ".agents"))
        assert "no .claude/, .pi/, or .agents/" in r.stderr

    def test_init_installs_into_existing_agent_dirs(self, project):
        (project / ".claude").mkdir()
        (project / ".pi").mkdir()
        (project / ".agents").mkdir()
        r = run("init", cwd=project)
        assert r.returncode == 0, r.stderr
        # a project's copy is what tkt prints there: its own part, then a section per installed plugin
        printed = run("skill", cwd=project).stdout
        assert printed.startswith(self.OPENING)
        for agent in (".claude", ".pi", ".agents"):
            assert (project / agent / "skills" / "tkt" / "SKILL.md").read_text() == printed
            assert f"found {agent}/, installed {agent}/skills/tkt/SKILL.md" in r.stderr
        r = run("init", cwd=project)
        assert "already current" in r.stderr

    def test_init_updates_a_stale_project_skill(self, project):
        (project / ".claude" / "skills" / "tkt").mkdir(parents=True)
        (project / ".claude" / "skills" / "tkt" / "SKILL.md").write_text("old\n")
        r = run("init", cwd=project)
        assert r.returncode == 0, r.stderr
        assert "updated .claude/skills/tkt/SKILL.md" in r.stderr
        printed = run("skill", cwd=project).stdout
        assert printed.startswith(self.OPENING)
        assert (project / ".claude" / "skills" / "tkt" / "SKILL.md").read_text() == printed

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

    def test_help_is_colored_on_terminal_with_the_same_text(self, tkt):
        out = run_tty("help", db=tkt.db)
        assert "\x1b[1maction\x1b[0m" in out and "\x1b[36m<id>\x1b[0m" in out and "\x1b[33m$EDITOR" in out
        plain = re.sub(r"\x1b\[[0-9]+m", "", out).replace("\r", "")
        assert plain == run("help").stdout
        assert "\x1b[" not in run("help").stdout

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

    def test_start_serves_in_the_background_until_stop(self, tkt):
        import socket
        import urllib.request

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        url = f"http://localhost:{port}/ticket"
        r = tkt("start", f"port={port}")
        try:
            assert r.returncode == 0, r.stderr
            assert r.stdout == url + "\n"
            assert "in the background" in r.stderr
            assert tkt.ok("status") == url + "\n"
            assert urllib.request.urlopen(url, timeout=10).status == 200
            again = tkt("start", f"port={port}")
            assert again.returncode == 0 and "stopped the server" not in again.stdout
            assert tkt.ok("status") == url + "\n"
        finally:
            assert "stopped the server" in tkt("stop").stderr
        tkt.fails("status", match="nothing serving")

    def test_start_says_why_the_server_did_not_come_up(self, tkt):
        import socket

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            r = tkt("start", f"port={s.getsockname()[1]}")
        assert r.returncode != 0
        assert "is taken" in r.stderr and "the server did not start" in r.stderr
        tkt.fails("status", match="nothing serving")

    def test_stale_pid_file_is_ignored(self, tkt):
        (tkt.db.parent / ".tkt").mkdir(exist_ok=True)
        (tkt.db.parent / ".tkt" / "tkt.pid").write_text("1 9080\n")
        tkt.fails("status", match="nothing serving")
        tkt.ok("stop")
        assert not (tkt.db.parent / ".tkt" / "tkt.pid").exists()

    def test_bad_port_fails(self, tkt):
        tkt.fails("serve", "port=abc", match="not a port")

    def test_taken_port_fails_before_the_pid_file(self, tkt):
        import socket

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            port = s.getsockname()[1]
            err = tkt.fails("serve", f"port={port}", match=f"port {port} is taken")
        assert "port=<n>" in err and "TKT_PORT" in err and ".env" in err
        assert not (tkt.db.parent / ".tkt" / "tkt.pid").exists()

    def test_dotenv_port_is_read_not_sourced(self, tkt):
        import socket

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            port = s.getsockname()[1]
            (tkt.db.parent / ".env").write_text(f'FOO=$(exit 3)\nexport TKT_PORT="{port}"  # here\n')
            tkt.fails("serve", match=f"port {port} is taken")
            with socket.socket() as other:
                other.bind(("127.0.0.1", 0))
                other.listen()
                env_port = other.getsockname()[1]
                r = run("serve", db=tkt.db, cwd=tkt.cwd, extra={"TKT_PORT": str(env_port)})
                assert f"port {env_port} is taken" in r.stderr
                r = run("serve", f"port={port}", db=tkt.db, cwd=tkt.cwd, extra={"TKT_PORT": str(env_port)})
                assert f"port {port} is taken" in r.stderr


def actions_page(*actions):
    """The actions list, for put_actions."""
    return list(actions)


def put_actions(tkt, actions):
    """A .tkt.json beside the tracker holding these actions, under leading // comments as tkt init writes them, with the
    action tkt itself gives switched off so a test sees only its own."""
    import json

    actions = [{"name": "clean-jobs", "enabled": False}, *actions]
    (tkt.db.parent / ".tkt.json").write_text("// a comment\n  // an indented one\n" + json.dumps({"actions": actions}, indent=2) + "\n")


def cgi(tkt, path="", query="", body="", method=None, referer="http://localhost:1/tktview/x", shell=None, extra=None):
    """One request to tkt as fossil's /ext CGI runs it: no arguments, the request in the environment and on stdin."""
    env = {
        "GATEWAY_INTERFACE": "CGI/1.0",
        "FOSSIL_REPOSITORY": tkt.db.name,
        "SCRIPT_NAME": "/ext/tkt",
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "REQUEST_METHOD": method or ("POST" if body else "GET"),
        "REQUEST_SCHEME": "http",
        "HTTP_HOST": "localhost:1",
        "HTTP_REFERER": referer,
        "CONTENT_LENGTH": str(len(body)),
        "FOSSIL_USER": os.environ.get("TKT_USER", os.environ.get("USER", "")),
    }
    env.update(extra or {})
    r = subprocess.run([shell or BASH, str(SCRIPT)], input=body, capture_output=True, text=True, env=env, cwd=tkt.db.parent)
    head, _, page = r.stdout.replace("\r\n", "\n").partition("\n\n")
    headers = dict(line.split(": ", 1) for line in head.splitlines())
    return headers, page


def wait_for(path, timeout=10):
    for _ in range(int(timeout / 0.05)):
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"{path} never appeared")


@pytest.mark.skipif(shutil.which("jq") is None, reason="actions need jq")
class TestActions:
    def put(self, tkt, *actions):
        put_actions(tkt, actions_page(*actions))

    def jobs(self, tkt):
        return sorted((tkt.db.parent / ".tkt" / "jobs").iterdir())

    def test_none_configured(self, tkt):
        (tkt.db.parent / ".tkt.json").unlink(missing_ok=True)
        r = tkt("action", "list")
        # with no file there is still the one action tkt itself gives
        assert r.stdout.splitlines() == ["| Action | Label | Icon | Scope | Comment | Command |", "| --- | --- | --- | --- | --- | --- |",
                                         "| clean-jobs | Clean Jobs | archive | project |  | `tkt action clean --keep 0` |"]
        assert "tkt init writes a starting one" in r.stderr

    def test_init_writes_a_default_with_clean_jobs(self, tkt):
        conf = tkt.db.parent / ".tkt" / "tkt.json"
        conf.unlink(missing_ok=True)
        assert "wrote " + str(conf) in tkt("init").stderr
        assert conf.read_text().startswith("// tkt project actions")
        r = tkt("action", "list")
        assert "| clean-jobs | Clean Jobs | archive | project |  | `tkt action clean --keep 0` |" in r.stdout
        assert "from " + str(conf) in r.stderr

    def test_init_never_overwrites_the_config(self, tkt):
        conf = tkt.db.parent / ".tkt.json"
        conf.write_text("mine")
        tkt.ok("init")
        assert conf.read_text() == "mine"

    def test_dot_tkt_config_is_preferred_over_the_old_file(self, tkt):
        self.put(tkt, {"name": "old", "command": ["true"]})
        new = tkt.db.parent / ".tkt" / "tkt.json"
        new.parent.mkdir(exist_ok=True)
        new.write_text(json.dumps({"actions": [{"name": "new", "command": ["true"]}]}))
        out = tkt.ok("action", "list")
        assert "| new |" in out and "| old |" not in out

    def test_init_moves_the_old_jobs_and_ext_dirs(self, tkt):
        # what sat in the old extension folder was plugins, so it ends up in the folder of plugins
        moves = ((".jobs", "jobs"), (".ext", "plugins"))
        for old, new in moves:
            (Path(f"{tkt.db}{old}") / "j1").mkdir(parents=True)
        tkt.ok("init")
        for old, new in moves:
            assert not Path(f"{tkt.db}{old}").exists() and (tkt.db.parent / ".tkt" / new / "j1").is_dir()

    def test_listed_from_the_file(self, tkt):
        self.put(tkt, {"name": "hi", "label": "Say hi", "icon": "hand-stop", "comment": True, "command": ["echo", "hi", "{ticket}"]})
        assert "| hi | Say hi | hand-stop | ticket | yes | `echo hi {ticket}` |" in tkt.ok("action", "list")

    def test_invalid_entries_are_skipped(self, tkt):
        self.put(tkt, {"name": "Bad Name", "command": ["true"]}, {"name": "nocmd"}, {"name": "empty", "command": []},
                 {"name": "ok", "icon": "../x", "command": ["true"]})
        rows = [l for l in tkt.ok("action", "list").splitlines()[2:]]
        assert rows == ["| ok | ok |  | project |  | `true` |"]

    def test_invalid_json_says_so(self, tkt):
        (tkt.db.parent / ".tkt.json").write_text("// fine\n{nope")
        r = tkt("action", "list")
        # the broken file is ignored, and what tkt itself gives is still there
        assert len(r.stdout.splitlines()) == 3 and "clean-jobs" in r.stdout
        assert ".tkt.json is not valid json" in r.stderr

    def test_the_old_wiki_page_is_ignored_with_a_note(self, tkt):
        tkt.ok("run", "wiki", "create", "config/Actions", "-", "--mimetype", "text/x-markdown", input="```json\n[{\"name\": \"wiki\", \"command\": [\"true\"]}]\n```\n")
        r = tkt("action", "list")
        assert "| wiki |" not in r.stdout
        assert "config/Actions wiki page is no longer read" in r.stderr

    def test_clean_retires_all_but_the_newest(self, tkt, tmp_path):
        jobs = tkt.db.parent / ".tkt" / "jobs"
        for i in range(5):
            d = jobs / f"2026010{i}-000000-x"
            d.mkdir(parents=True)
            (d / "action").write_text("x")
            (d / "exit").write_text("0")
        running = jobs / "20250101-000000-run"
        running.mkdir()
        (running / "pid").write_text(str(os.getpid()))
        out = run("action", "clean", "--keep", "2", db=tkt.db, cwd=tkt.cwd, extra={"TMPDIR": str(tmp_path)}).stdout
        assert "retired 3 job(s)" in out
        assert sorted(p.name for p in jobs.iterdir()) == ["20250101-000000-run", "20260103-000000-x", "20260104-000000-x"]
        retired = tmp_path / "tkt-jobs" / tkt.db.parent.name
        assert sorted(p.name for p in retired.iterdir()) == ["20260100-000000-x", "20260101-000000-x", "20260102-000000-x"]
        assert "nothing to retire" in tkt.ok("action", "clean", "--keep", "9")

    def test_clean_rejects_a_bad_count(self, tkt):
        assert "not a count" in tkt("action", "clean", "--keep", "x").stderr

    def test_needs_jq(self, tkt, no_git_path):
        if os.environ.get("TKT_CMD"):
            pytest.skip("a distribution carries its own jq")
        r = run("action", "list", db=tkt.db, path=no_git_path)
        assert r.returncode != 0 and "actions need jq" in r.stderr

    def test_run_streams_the_log_and_fills_placeholders(self, tkt):
        id = tkt.new("target")
        self.put(tkt, {"name": "show", "command": ["printf", "[%s]\\n", "an arg with spaces", "{ticket}", "{repo}"]})
        r = tkt("action", "run", "show", id)
        assert r.returncode == 0, r.stderr
        assert r.stdout.splitlines() == ["[an arg with spaces]", f"[{id}]", f"[{tkt.db}]"]

    def test_run_runs_from_the_tracker_directory(self, tkt):
        self.put(tkt, {"name": "pwd", "command": ["pwd", "-P"]})
        assert tkt.ok("action", "run", "pwd").strip() == str(tkt.db.parent.resolve())

    def test_run_exits_with_the_actions_code(self, tkt):
        self.put(tkt, {"name": "three", "command": ["sh", "-c", "echo out; exit 3"]})
        r = tkt("action", "run", "three")
        assert r.returncode == 3
        assert r.stdout == "out\n"
        assert "exit 3" in r.stderr

    def test_run_unknown_action_fails(self, tkt):
        tkt.fails("action", "run", "nope", match="no action named nope")

    def test_comment_posts_the_result_to_the_ticket(self, tkt):
        id = tkt.new("target")
        self.put(tkt, {"name": "say", "comment": True, "command": ["echo", "said it"]})
        tkt.ok("action", "run", "say", id)
        shown = tkt.show(id)
        assert "action `say` exited 0" in shown and "said it" in shown

    def test_usage(self, tkt):
        tkt.fails("action", match="usage: tkt action")
        tkt.fails("action", "run", match="usage: tkt action")

    def test_scope_is_inferred_from_the_ticket_placeholder(self, tkt):
        self.put(tkt, {"name": "proj", "command": ["true"]}, {"name": "tick", "command": ["echo", "id={ticket}"]})
        rows = tkt.ok("action", "list").splitlines()[2:]
        assert rows == ["| proj | proj |  | project |  | `true` |", "| tick | tick |  | ticket |  | `echo id={ticket}` |"]

    def test_a_ticket_action_needs_a_ticket(self, tkt):
        self.put(tkt, {"name": "tick", "command": ["echo", "{ticket}"]})
        tkt.fails("action", "run", "tick", match="tick is a ticket action")
        assert not (tkt.db.parent / ".tkt" / "jobs").exists()

    def test_a_project_action_takes_a_ticket_as_context(self, tkt):
        id = tkt.new("target")
        self.put(tkt, {"name": "proj", "command": ["echo", "plain"]})
        assert tkt.ok("action", "run", "proj", id) == "plain\n"
        [job] = self.jobs(tkt)
        assert (job / "ticket").read_text() == id

    def test_comment_without_a_ticket_says_it_was_not_posted(self, tkt):
        self.put(tkt, {"name": "proj", "comment": True, "command": ["true"]})
        r = tkt("action", "run", "proj")
        assert r.returncode == 0 and "comment not posted: no ticket" in r.stderr

    def test_comment_posted_is_recorded(self, tkt):
        id = tkt.new("target")
        self.put(tkt, {"name": "proj", "comment": True, "command": ["true"]})
        r = tkt("action", "run", "proj", id)
        assert f"comment posted to {id}" in r.stderr
        [job] = self.jobs(tkt)
        assert "succeeded" in (job / "post.log").read_text() and "succeeded" not in (job / "log").read_text()

    def test_tkt_placeholder_is_this_script(self, tkt):
        self.put(tkt, {"name": "self", "command": ["echo", "{tkt}"]})
        assert names_this_tkt(tkt.ok("action", "run", "self").strip())

    def test_plain_tkt_in_a_job_is_this_one(self, tkt):
        self.put(tkt, {"name": "which", "command": ["sh", "-c", "command -v tkt; tkt version"]})
        found, version = tkt.ok("action", "run", "which").splitlines()
        assert found == str(tkt.db.parent / ".tkt" / "ext" / "tkt") and names_this_tkt(found)
        assert version.startswith("tkt ")

    def test_tkt_inside_a_job_says_so(self, tkt):
        id = tkt.new("target")
        self.put(tkt, {"name": "peek", "command": ["sh", "-c", "tkt show {ticket} 2>&1 >/dev/null"]})
        out = tkt.ok("action", "run", "peek", id)
        [job] = self.jobs(tkt)
        assert f"running inside project action peek, job {job.name}" in out
        assert "running inside" not in tkt("show", id).stderr

    def test_job_records(self, tkt):
        self.put(tkt, {"name": "hi", "command": ["echo", "hi"]})
        tkt.ok("action", "run", "hi")
        [job] = self.jobs(tkt)
        assert (job / "action").read_text() == "hi"
        assert (job / "exit").read_text().strip() == "0"
        assert (job / "log").read_text() == "hi\n"


@pytest.mark.skipif(shutil.which("jq") is None, reason="actions need jq")
class TestActionsCgi:
    @pytest.fixture
    def ticket(self, tkt):
        id = tkt.new("target")
        put_actions(tkt, actions_page(
            {"name": "hi", "label": "Say <hi>", "comment": True, "command": ["echo", "hi", "{ticket}"]},
            {"name": "slow", "command": ["sleep", "30"]},
            {"name": "noisy", "command": ["seq", "1", "500"]},
        ))
        return id

    def job_of(self, headers):
        return headers["Location"].rsplit("/", 1)[1]

    def test_index_is_skinned_and_lists_buttons(self, tkt, ticket):
        h, page = cgi(tkt, query=f"ticket={ticket}")
        assert h["Status"] == "200"
        assert page.startswith("<div class='fossil-doc' data-title='Actions'>")
        assert page.count("<button ") == 3
        assert "Say &lt;hi&gt;" in page
        assert f'value="{ticket}"' in page

    def test_buttons_are_bare(self, tkt, ticket):
        h, page = cgi(tkt, "/buttons", f"ticket={ticket}")
        assert "fossil-doc" not in page
        # the row a ticket's page fetches holds ticket actions only; project actions stay on the actions page
        assert page.startswith('<div class="tkt-actions">') and page.count("<button ") == 1 and "Say &lt;hi&gt;" in page

    def test_no_actions_no_buttons(self, tkt):
        _, page = cgi(tkt, "/buttons", "ticket=")
        assert page == ""

    def test_run_redirects_to_its_job(self, tkt, ticket):
        h, _ = cgi(tkt, "/run/hi", body=f"ticket={ticket}")
        assert h["Status"] == "303 See Other"
        job = self.job_of(h)
        wait_for((tkt.db.parent / ".tkt" / "jobs") / job / "exit")
        _, page = cgi(tkt, f"/job/{job}")
        assert "exit 0" in page and f"hi {ticket}" in page
        assert "tkt-reload" not in page
        assert "action `hi` exited 0" in tkt.show(ticket)
        assert tkt.sql("select user from event where type='t' order by mtime desc limit 1;").strip("'") == os.environ.get("TKT_USER", os.environ["USER"])

    def test_a_running_action_is_not_started_twice(self, tkt, ticket):
        first = self.job_of(cgi(tkt, "/run/slow", body="ticket=")[0])
        try:
            second = self.job_of(cgi(tkt, "/run/slow", body="ticket=")[0])
            assert first == second
            _, page = cgi(tkt, f"/job/{first}")
            assert "running" in page and '<meta name="tkt-reload" content="2">' in page
        finally:
            pid = int(((tkt.db.parent / ".tkt" / "jobs") / first / "pid").read_text())
            os.kill(pid, 9)
            subprocess.run(["pkill", "-9", "-f", "^sleep 30$"])

    def test_a_killed_job_shows_as_died(self, tkt, ticket):
        job = self.job_of(cgi(tkt, "/run/slow", body="ticket=")[0])
        pid = int(((tkt.db.parent / ".tkt" / "jobs") / job / "pid").read_text())
        os.kill(pid, 9)
        subprocess.run(["pkill", "-9", "-f", "^sleep 30$"])
        time.sleep(0.2)
        _, page = cgi(tkt, f"/job/{job}")
        assert "died" in page and "tkt-reload" not in page
        assert self.job_of(cgi(tkt, "/run/slow", body="ticket=")[0]) != job
        subprocess.run(["pkill", "-9", "-f", "^sleep 30$"])

    def test_long_logs_show_their_tail(self, tkt, ticket):
        job = self.job_of(cgi(tkt, "/run/noisy", body="ticket=")[0])
        wait_for((tkt.db.parent / ".tkt" / "jobs") / job / "exit")
        _, page = cgi(tkt, f"/job/{job}")
        assert "last 200 of 500 lines" in page and "<pre>301\n" in page and "\n300\n" not in page
        _, page = cgi(tkt, f"/job/{job}", "full=1")
        assert "<pre>1\n" in page and "500 lines" in page and "last 200" not in page

    def test_job_page_is_cards_linking_back(self, tkt, ticket):
        job = self.job_of(cgi(tkt, "/run/hi", body=f"ticket={ticket}")[0])
        wait_for((tkt.db.parent / ".tkt" / "jobs") / job / "exit")
        _, page = cgi(tkt, f"/job/{job}")
        assert 'class="tkt-card tkt-card-fields"' in page and 'class="tkt-card tkt-card-log"' in page
        assert 'class="tkt-fold"' in page and 'class="tkt-copy"' in page
        assert '<span class="tkt-jobstate tkt-jobstate-ok">exit 0</span>' in page
        assert f'href="/ext/tkt?ticket={ticket}"' in page
        assert "Started:" in page and "took" in page

    def test_ticket_actions_show_only_with_a_ticket(self, tkt, ticket):
        _, page = cgi(tkt)
        assert page.count("<button ") == 2 and ">Say" not in page
        assert "From a ticket&rsquo;s page: Say &lt;hi&gt;." in page
        _, page = cgi(tkt, "/buttons", "ticket=")
        assert page == ""
        _, page = cgi(tkt, "/buttons", f"ticket={ticket}")
        assert page.count("<button ") == 1 and ">Say" in page
        _, page = cgi(tkt, query=f"ticket={ticket}")
        assert page.count("<button ") == 3

    def test_a_ticket_action_refuses_no_ticket(self, tkt, ticket):
        h, page = cgi(tkt, "/run/hi", body="ticket=")
        assert h["Status"] == "400" and "ticket action" in page

    def test_a_ticket_action_runs_once_per_ticket(self, tkt, ticket):
        put_actions(tkt, actions_page(
            {"name": "wait", "command": ["sh", "-c", "sleep 30", "{ticket}"]}, {"name": "slow", "command": ["sleep", "30"]}))
        other = tkt.new("other")
        try:
            a = self.job_of(cgi(tkt, "/run/wait", body=f"ticket={ticket}")[0])
            assert self.job_of(cgi(tkt, "/run/wait", body=f"ticket={ticket}")[0]) == a
            assert self.job_of(cgi(tkt, "/run/wait", body=f"ticket={other}")[0]) != a
            p = self.job_of(cgi(tkt, "/run/slow", body=f"ticket={ticket}")[0])
            assert self.job_of(cgi(tkt, "/run/slow", body=f"ticket={other}")[0]) == p
        finally:
            for job in (tkt.db.parent / ".tkt" / "jobs").iterdir():
                try:
                    os.kill(int((job / "pid").read_text()), 9)
                except ProcessLookupError:
                    pass
            subprocess.run(["pkill", "-9", "-f", "^sleep 30"])
            subprocess.run(["pkill", "-9", "-f", "^sh -c sleep 30"])

    def test_job_page_says_where_the_comment_went(self, tkt, ticket):
        job = self.job_of(cgi(tkt, "/run/hi", body=f"ticket={ticket}")[0])
        wait_for((tkt.db.parent / ".tkt" / "jobs") / job / "exit")
        _, page = cgi(tkt, f"/job/{job}")
        assert f"Comment:</td><td class=\"tktDspValue\">posted to {ticket}" in page
        put_actions(tkt, actions_page({"name": "proj", "comment": True, "command": ["true"]}))
        job = self.job_of(cgi(tkt, "/run/proj", body="ticket=")[0])
        wait_for((tkt.db.parent / ".tkt" / "jobs") / job / "exit")
        _, page = cgi(tkt, f"/job/{job}")
        assert "not posted: no ticket" in page

    def test_index_lists_jobs_as_a_report(self, tkt, ticket):
        _, page = cgi(tkt)
        assert "No jobs yet." in page
        job = self.job_of(cgi(tkt, "/run/hi", body=f"ticket={ticket}")[0])
        wait_for((tkt.db.parent / ".tkt" / "jobs") / job / "exit")
        _, page = cgi(tkt)
        assert 'class="tkt-card tkt-card-report"' in page and '<table class="report">' in page
        assert f'<a href="/ext/tkt/job/{job}">{job}</a>' in page and f'<a href="/tktview/{ticket}">{ticket}</a>' in page

    @pytest.mark.parametrize("kw,status", [
        (dict(path="/run/hi", method="GET"), "405"),
        (dict(path="/run/hi", body="ticket=", referer="http://evil.example/"), "403"),
        (dict(path="/run/hi", body="ticket=", referer=""), "403"),
        (dict(path="/run/nope", body="ticket="), "404"),
        (dict(path="/run/hi", body="ticket=zz"), "400"),
        (dict(path="/run/hi", body="ticket=abcdef"), "400"),
        (dict(query="ticket=../x"), "400"),
        (dict(path="/job/nope"), "404"),
        (dict(path="/job/.."), "400"),
        (dict(path="/elsewhere"), "404"),
    ])
    def test_refusals(self, tkt, ticket, kw, status):
        h, page = cgi(tkt, **kw)
        assert h["Status"] == status
        assert page.startswith("<div class='fossil-doc'") and page.rstrip().endswith("</div>")

    def test_runs_under_the_system_bash(self, tkt, ticket):
        # fossil starts the script with an empty PATH, so env finds /bin/bash, which is 3.2 on macOS
        h, page = cgi(tkt, query=f"ticket={ticket}", shell="/bin/bash")
        assert h["Status"] == "200" and page.count("<button ") == 3

    def test_jobs_get_the_server_users_home_and_local_bin(self, tkt):
        put_actions(tkt, actions_page({"name": "env", "command": ["sh", "-c", "echo $HOME; echo $PATH"]}))
        job = cgi(tkt, "/run/env", body="ticket=")[0]["Location"].rsplit("/", 1)[1]
        wait_for((tkt.db.parent / ".tkt" / "jobs") / job / "exit")
        home, path = ((tkt.db.parent / ".tkt" / "jobs") / job / "log").read_text().splitlines()
        assert home == os.path.expanduser("~")
        assert path.split(":")[:2] == [str(tkt.db.parent / ".tkt" / "ext"), f"{home}/.local/bin"]

    def test_header_has_the_page_reload_toggle(self, tkt):
        header = config(tkt.db, "header")
        assert "function reloadToggle()" in header and "'Page Reload: '" in header
        assert "'Zoom in','Page Reload','Toggle dark mode'" in header

    def test_ticket_view_fetches_the_buttons(self, tkt):
        view = config(tkt.db, "ticket-viewpage")
        assert "/ext/tkt/buttons?ticket=" in view and 'nonce=\\"$nonce\\"' in view


@pytest.mark.skipif(shutil.which("jq") is None, reason="actions need jq")
class TestActionsServed:
    def test_serve_runs_tkt_as_ext_cgi(self, tkt):
        """The whole path through a real fossil server: its /ext reaches tkt, whose buttons start a job."""
        import socket
        import urllib.request

        id = tkt.new("target")
        put_actions(tkt, actions_page({"name": "hi", "label": "Hi", "command": ["echo", "served"]}))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        p = subprocess.Popen([*TKT, "serve", f"port={port}"], cwd=tkt.cwd, env={**os.environ, "TKT_DB": str(tkt.db), "TKT_OPEN": "0"},
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://localhost:{port}"
        try:
            for _ in range(100):
                with socket.socket() as s:
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        break
                time.sleep(0.1)
            assert names_this_tkt(tkt.db.parent / ".tkt" / "ext" / "tkt")
            page = urllib.request.urlopen(f"{base}/ext/tkt?ticket={id}").read().decode()
            assert "<title>" in page and "<button title=\"Hi\">Hi</button>" in page
            req = urllib.request.Request(f"{base}/ext/tkt/run/hi", data=f"ticket={id}".encode(), headers={"Referer": f"{base}/tktview/{id}"})
            with urllib.request.urlopen(req) as r:
                assert "/ext/tkt/job/" in r.url
            [job] = (tkt.db.parent / ".tkt" / "jobs").iterdir()
            wait_for(job / "exit")
            assert (job / "log").read_text() == "served\n"
        finally:
            p.terminate()
            p.wait(timeout=10)
            tkt.ok("stop")


class TestPluginWeb:
    """tkt's own web handler serves a plugin's page and files from wherever the search finds the plugin."""

    PAGE = 'printf "Content-Type: text/plain\\r\\n\\r\\n%s|%s|%s|%s" "$SCRIPT_NAME" "$PATH_INFO" "$GATEWAY_INTERFACE" "$(cat)"\n'

    def plugin(self, plugins, name="echo", entry=PAGE):
        d = plugins / name
        (d / "web").mkdir(parents=True, exist_ok=True)
        if entry:
            (d / "main.sh").write_text(entry)
        return d

    def own(self, tkt):
        return tkt.db.parent / ".tkt" / "plugins"

    def test_a_page_runs_with_its_own_address_path_and_body(self, tkt):
        self.plugin(self.own(tkt))
        h, page = cgi(tkt, "/ext/echo/main.sh/sub/path", body="posted")
        assert h["Content-Type"] == "text/plain"
        assert page == "/ext/tkt/ext/echo/main.sh|/sub/path|CGI/1.0|posted"
        assert cgi(tkt, "/ext/echo")[1] == "/ext/tkt/ext/echo||CGI/1.0|"

    def test_a_static_file_is_served_with_its_type(self, tkt):
        d = self.plugin(self.own(tkt))
        (d / "web" / "css").mkdir()
        (d / "web" / "css" / "x.css").write_text("a{}\n")
        h, page = cgi(tkt, "/ext/echo/css/x.css")
        assert h["Content-Type"] == "text/css; charset=utf-8" and page == "a{}\n"

    def test_a_micropython_page_is_served(self, tkt):
        """A second language, end to end through a real server: a plugin with only a page, whose entry is MicroPython."""
        import socket
        import urllib.request

        if not (os.environ.get("TKT_CMD") or shutil.which("micropython")):
            pytest.skip("needs micropython, which a distribution may carry and this host lacks")
        d = self.plugin(self.own(tkt), name="hello", entry=None)
        (d / "web.micropy").write_text(
            "import os, sys\n"
            'sys.stdout.write("Content-Type: text/plain\\r\\n\\r\\n")\n'
            'facts = [os.getenv(n) for n in ("TKT_PLUGIN_NAME", "SCRIPT_NAME", "PATH_INFO", "QUERY_STRING")]\n'
            'sys.stdout.write("hello from %s at %s%s?%s" % tuple(facts))\n'
        )
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        r = tkt("start", f"port={port}")
        try:
            assert r.returncode == 0, r.stderr
            page = urllib.request.urlopen(f"http://localhost:{port}/ext/tkt/ext/hello/web.micropy/sub?x=1", timeout=10).read().decode()
            # fossil wraps a plain-text reply in the site's skin, so the plugin's line arrives inside a page
            assert "hello from hello at /ext/tkt/ext/hello/web.micropy/sub?x=1" in page
            tkt.fails("hello", match="unknown verb: hello")
        finally:
            tkt("stop")

    def test_only_the_web_folder_has_an_address(self, tkt):
        d = self.plugin(self.own(tkt))
        (d / "sql").mkdir()
        (d / "sql" / "schema.sql").write_text("create table t(x);\n")
        (d / "skill.md").write_text("## Echo\n")
        for path in ("/ext/echo/sql/schema.sql", "/ext/echo/skill.md", "/ext/echo/web/x", "/ext/echo/main"):
            h, page = cgi(tkt, path)
            assert h["Status"] == "404" and "create table" not in page and "Echo" not in page, path

    def test_pages_and_files_come_from_the_search_path_and_the_trackers_own_win(self, tkt, tmp_path):
        far = self.plugin(tmp_path / "far")
        (far / "web" / "a.txt").write_text("far a\n")
        (far / "web" / "b.txt").write_text("far b\n")
        own = self.plugin(self.own(tkt), entry=None)
        (own / "web" / "b.txt").write_text("own b\n")
        extra = {"TKT_PLUGINS": str(tmp_path / "far")}
        assert cgi(tkt, "/ext/echo/main.sh", extra=extra)[1].startswith("/ext/tkt/ext/echo/main.sh|")
        assert cgi(tkt, "/ext/echo/a.txt", extra=extra)[1] == "far a\n"
        assert cgi(tkt, "/ext/echo/b.txt", extra=extra)[1] == "own b\n"

    def test_refusals(self, tkt):
        self.plugin(self.own(tkt))
        self.plugin(self.own(tkt), name="hollow", entry=None)
        for path, status, says in (
            ("/ext/nope/main.sh", "404", "no plugin nope"),
            ("/ext/tkt/main.sh", "404", "no plugin tkt"),
            ("/ext/echo/missing.css", "404", "no file missing.css in plugin echo"),
            ("/ext/echo/../../tkt.json", "400", "bad path"),
            ("/ext/hollow/main.sh", "404", "plugin hollow has no entry file"),
        ):
            h, page = cgi(tkt, path)
            assert h["Status"] == status and says in page, path


class TestActionIcons:
    pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="actions need jq")

    def test_icon_is_a_cdn_image_beside_a_titled_label(self, tkt):
        put_actions(tkt, [{"name": "go", "label": "Go & run", "icon": "player-play", "command": ["true"]}])
        _, page = cgi(tkt)
        assert '<button title="Go &amp; run"><img class="tkt-action-icon" src="https://cdn.jsdelivr.net/npm/@tabler/icons@' in page
        assert '/outline/player-play.svg" alt="" width="16" height="16">Go &amp; run</button>' in page

    def test_config_card_shows_the_file(self, tkt):
        put_actions(tkt, [{"name": "go", "command": ["true"]}])
        _, page = cgi(tkt)
        assert 'id="config"' in page and "// a comment" in page


@pytest.mark.skipif(shutil.which("jq") is None, reason="actions need jq")
class TestSkillActions:
    AGENT = ["claude", "-p", "{prompt}", "--allowedTools", "Bash(tkt:*)"]

    def conf(self, tkt, **c):
        import json
        (tkt.db.parent / ".tkt.json").write_text("// x\n" + json.dumps(c))

    def test_skill_expands_through_the_agent(self, tkt):
        self.conf(tkt, agent=self.AGENT, actions=[{"name": "groom", "skill": ["groom"]}, {"name": "rev", "skill": ["review", "closely"]}])
        out = tkt.ok("action", "list")
        assert "| groom | groom |  | ticket |  | `claude -p /tkt {ticket} groom --allowedTools Bash(tkt:*)` |" in out
        assert "`claude -p /tkt {ticket} review closely --allowedTools" in out

    def test_skill_runs_the_agent_with_the_ticket(self, tkt):
        id = tkt.new("target")
        self.conf(tkt, agent=["printf", "[%s]\\n", "{prompt}"], actions=[{"name": "groom", "skill": ["groom"]}])
        r = tkt("action", "run", "groom", id)
        assert f"[/tkt {id[:10]} groom]" in r.stdout

    def test_without_an_agent_skill_actions_are_skipped(self, tkt):
        self.conf(tkt, actions=[{"name": "groom", "skill": ["groom"]}, {"name": "ok", "command": ["true"]}])
        out = tkt.ok("action", "list")
        assert "| ok |" in out and "groom" not in out
        self.conf(tkt, agent=["claude", "-p"], actions=[{"name": "groom", "skill": ["groom"]}])
        assert "groom" not in tkt.ok("action", "list")

    def test_command_wins_over_skill(self, tkt):
        self.conf(tkt, agent=self.AGENT, actions=[{"name": "both", "skill": ["groom"], "command": ["true"]}])
        assert "| both | both |  | project |  | `true` |" in tkt.ok("action", "list")
