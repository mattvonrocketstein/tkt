PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
PYTHON ?= python3
VENV ?= .venv
SCRIPT ?= tkt
SKILL ?= skills/tkt/SKILL.md

.PHONY: clean init build test install skill
.SILENT:

clean:
	rm -rf .pytest_cache
	find . -name __pycache__ -type d -prune -not -path './$(VENV)/*' -exec rm -rf {} +

init: $(VENV)/bin/pytest

$(VENV)/bin/pytest:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --quiet pytest
	echo "tkt: test env ready in $(VENV)"

build:
	echo "tkt: nothing to build, the script runs as is"

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
