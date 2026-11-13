PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
PYTHON ?= python3
VENV ?= .venv
DOCS_PAGES ?= README.md $(wildcard docs/*.md)
DOCS_IMG ?= docs/img/hdr
DOCS_REPO ?= mattvonrocketstein/tkt
DOCS_PORT ?= 6419
MDHEADERS = $(PYTHON) docs/tools/mdheaders.py --img $(DOCS_IMG)

VERSION ?=

.PHONY: clean init test stamp install install.slim docs docs.headers docs.check docs.test docs.serve omni omni.%
.SILENT:

# stamp writes a release's version into the script, which ships as a release asset; the Release workflow runs it on its own checkout, never on the repository
stamp:
	[ -n "$(VERSION)" ] || { echo "tkt: stamp needs VERSION=X.Y.Z" >&2; exit 1; }
	perl -pi -e 's/^TKT_VERSION=.*/TKT_VERSION=$(VERSION)/' tkt
	[ "$$(bash ./tkt version)" = "tkt $(VERSION)" ] || { echo "tkt: the script does not report $(VERSION) after stamping" >&2; exit 1; }

clean:
	rm -rf .pytest_cache
	find . -name __pycache__ -type d -prune -not -path './$(VENV)/*' -exec rm -rf {} +

init: $(VENV)/bin/pytest

$(VENV)/bin/pytest:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --quiet pytest
	echo "tkt: test env ready in $(VENV)"

test: init
	$(VENV)/bin/pytest -q tests/

# install puts the omnibus on the host: one file with fossil, jq and bash inside, built first when it is not there yet
install: omni/tkt
install: installed := omni/tkt
install: what := the omnibus
# install.slim puts the script alone there, for a host that has fossil, jq and bash of its own
install.slim: installed := tkt
install.slim: what := the script alone

omni/tkt:
	echo "tkt: no omnibus built yet, building it; make install.slim installs the script alone" >&2
	$(MAKE) -C omni tkt

install install.slim:
	install -d "$(BINDIR)"
	install -m 0755 "$(installed)" "$(BINDIR)/tkt"
	echo "tkt: installed $(BINDIR)/tkt, $(what)"
	case ":$$PATH:" in \
	  *":$(BINDIR):"*) ;; \
	  *) echo "tkt: warning: $(BINDIR) is not on PATH. Add it in your shell profile:"; \
	     echo "  export PATH=\"$(BINDIR):\$$PATH\""; \
	     echo "or install system-wide instead:"; \
	     echo "  sudo make $@ PREFIX=/usr/local" ;; \
	esac

# phony, or make would see the docs/ directory and call it up to date
docs: docs.headers

docs.headers:
	$(MDHEADERS) $(DOCS_PAGES)

docs.check:
	$(MDHEADERS) --check $(DOCS_PAGES) \
	  || { echo "tkt: a docs header is out of date, run make docs.headers" >&2; exit 1; }

docs.test: init
	$(VENV)/bin/pytest -q -p no:cacheprovider docs/tools

docs.serve:
	command -v gh >/dev/null || { echo "tkt: docs.serve renders through gh api, and gh is not on PATH" >&2; exit 1; }
	echo "tkt: serving docs at http://localhost:$(DOCS_PORT)/" >&2
	$(PYTHON) docs/tools/preview.py $(DOCS_REPO) $(DOCS_PORT)

# the omnibus distribution: tkt, fossil and what tkt ships in .tkt as one portable file; the targets live in omni/Makefile, reached as omni.<target>.
omni:
	$(MAKE) -C omni tkt

omni.%:
	$(MAKE) -C omni $*
