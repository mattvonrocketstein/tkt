PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
PYTHON ?= python3
VENV ?= .venv
SCRIPT ?= tkt
SKILL ?= skills/tkt/SKILL.md
DOCS_PAGES ?= README.md $(wildcard docs/*.md)
DOCS_IMG ?= docs/img/hdr
DOCS_REPO ?= mattvonrocketstein/tkt
DOCS_PORT ?= 6419
MDHEADERS = $(PYTHON) docs/tools/mdheaders.py --img $(DOCS_IMG)

.PHONY: clean init build test install skill docs.headers docs.check docs.test docs.serve
.SILENT:

clean:
	rm -rf .pytest_cache
	find . -name __pycache__ -type d -prune -not -path './$(VENV)/*' -exec rm -rf {} +

init: $(VENV)/bin/pytest

$(VENV)/bin/pytest:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --quiet pytest
	echo "tkt: test env ready in $(VENV)"

build: skill

test: init
	$(VENV)/bin/pytest -q tests/

skill:
	grep -q '^SKILL_MD$$' "$(SCRIPT)" || { echo "tkt: no skill copy found in $(SCRIPT)"; exit 1; }
	awk -v src="$(SKILL)" \
	  '/^SKILL_MD$$/ { skip = 0 } !skip { print } /<<.SKILL_MD.$$/ { while ((getline line < src) > 0) print line; skip = 1 }' \
	  "$(SCRIPT)" > "$(SCRIPT).tmp"
	if cmp -s "$(SCRIPT).tmp" "$(SCRIPT)"; then \
	  echo "tkt: the skill copy in $(SCRIPT) already matches $(SKILL)"; \
	else \
	  cat "$(SCRIPT).tmp" > "$(SCRIPT)"; \
	  echo "tkt: synced the skill copy in $(SCRIPT) from $(SKILL)"; \
	fi
	rm -f "$(SCRIPT).tmp"

install:
	install -d "$(BINDIR)"
	install -m 0755 tkt "$(BINDIR)/tkt"
	echo "tkt: installed $(BINDIR)/tkt"
	case ":$$PATH:" in \
	  *":$(BINDIR):"*) ;; \
	  *) echo "tkt: warning: $(BINDIR) is not on PATH. Add it in your shell profile:"; \
	     echo "  export PATH=\"$(BINDIR):\$$PATH\""; \
	     echo "or install system-wide instead:"; \
	     echo "  sudo make install PREFIX=/usr/local" ;; \
	esac

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
