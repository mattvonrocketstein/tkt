# omni: the omnibus distribution of tkt, one actually portable executable -- an amk binary whose payload holds the tkt script, a fossil built with cosmocc, and what tkt ships in .tkt; amk supplies the entry, bash, jq and the tools on PATH.
SHELL := bash
.SHELLFLAGS ?= -euo pipefail -c
MAKEFLAGS = -s -S --warn-undefined-variables
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# amk is a pinned release with the payload flags; while no version is set, the amk on PATH is used, or one given as amk=PATH.
amk.version :=
amk.sha256  :=
amk.file     = amk-$(amk.version).ape
amk.url      = https://github.com/Robot-Wranglers/ape-make/releases/download/v$(amk.version)/amk
amk.pinned   = $(if $(amk.version),$(HERE)$(amk.file))
amk ?= $(or $(amk.pinned),amk)

# Every input is pinned by version and digest; upstream ships no checksum files.
fossil.version := 2.28
fossil.tarball := fossil-src-$(fossil.version).tar.gz
fossil.url     := https://fossil-scm.org/home/tarball/version-$(fossil.version)/$(fossil.tarball)
fossil.sha256  := 84c18824ca227e7602d2408b663c3747f754ad306ed5c73ddab959d6589538a6

cosmocc.version := 4.0.2
cosmocc.zip     := cosmocc-$(cosmocc.version).zip
cosmocc.url     := https://cosmo.zip/pub/cosmocc/$(cosmocc.zip)
cosmocc.mirror  := https://github.com/jart/cosmopolitan/releases/download/$(cosmocc.version)/$(cosmocc.zip)
cosmocc.sha256  := 85b8c37a406d862e656ad4ec14be9f6ce474c1b436b9615e91a55208aced3f44

# cosmocc.dir may name an installed copy, which then skips the download; the wrapper finds its helpers beside itself, so PATH points into bin/ and never at a symlink.
cosmocc.dir ?= $(HERE)cosmocc
cosmocc.env  = PATH="$(cosmocc.dir)/bin:$$PATH"
deps.files   = $(HERE)$(fossil.tarball) $(if $(filter $(HERE)cosmocc,$(cosmocc.dir)),$(HERE)$(cosmocc.zip)) $(amk.pinned)

sha256 := $(shell command -v sha256sum 2>/dev/null || echo 'shasum -a 256')
jobs   := $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)

# Fossil is compiled as released, with no source change; what cosmopolitan lacks comes from a header every file is given.
fossil.src := build/fossil-$(fossil.version)
fossil.include := $(HERE)src/getpass.h
# The bundled zlib, archived by hand: its own makefile leaves an empty libz.a under cosmoar.
zlib.objs := adler32 compress crc32 deflate gzclose gzlib gzread gzwrite infback inffast inflate inftrees trees uncompr zutil
# No openssl yet, so no https sync; json for tkt's machine-readable verbs.
# _COSMO_SOURCE exposes cosmopolitan's extensions, pledge among them, which configure finds and fossil then calls.
fossil.configure := CC=cosmocc BCC=cc CFLAGS='-Os -D_COSMO_SOURCE -include $(fossil.include)' --static --json --with-openssl=none --with-zlib=tree

# out/ holds the artifact; everything rebuildable stays under build/.
fossil.ape   := build/fossil
artifact     := out/tkt
# The payload, by its path under /zip: the entry amk boots, the script and the launcher template under libexec/, fossil under bin/, and under share/tkt/plugins the plugins, which tkt searches in place.
entry.src      := $(HERE)src/entry.sh
launcher.src   := $(HERE)src/launcher.sh
payload.script := $(HERE)../tkt
payload.dir    := $(HERE)../plugins
# A plugin is a folder with a main, holding everything it owns; links, config, jobs and the server pid belong to each project and never ship.
payload.plugins = $(patsubst $(payload.dir)/%/main.sh,%,$(wildcard $(payload.dir)/*/main.sh))
payload.files   = $(entry.src) $(launcher.src) $(payload.script) $(shell find $(addprefix $(payload.dir)/,$(payload.plugins)) -type f 2>/dev/null)
payload.members := /zip/__main__.sh /zip/libexec/tkt /zip/libexec/launcher.sh /zip/bin/fossil
# The deliverable lands beside this Makefile, where a caller can find it without knowing the layout.
deliverable  := tkt

# Progress speaks on stderr under one label, leaving stdout to whatever a target produces.
tty.bold := $(shell test -t 2 && tput bold 2>/dev/null)
tty.dim  := $(shell test -t 2 && tput dim 2>/dev/null)
tty.red  := $(shell test -t 2 && tput setaf 1 2>/dev/null)
tty.off  := $(shell test -t 2 && tput sgr0 2>/dev/null)
log  = printf '$(tty.dim)tkt/omni$(tty.off) $(tty.bold)%s$(tty.off) %s\n' "$(strip $(1))" "$(strip $(2))" >&2
die  = { printf '$(tty.red)tkt/omni $(strip $(1)) failed$(tty.off) %s\n' "$(strip $(2))" >&2; exit 1; }
show = printf '%-8s %-28s %-6s %s\n' '$(strip $(1))' '$(strip $(2))' \
         "$$(du -sh '$(strip $(2))' 2>/dev/null | cut -f1 || echo -)" '$(strip $(3))'

.PHONY: tkt deps verify amk toolchain unpack build repack smoke stat clean help
.DEFAULT_GOAL := tkt

help:
	@# List the targets.
	$(call log, help, usage: make tkt for the deliverable -- make stat says what is built)
	grep -hE '^[a-z][a-z. ]*:([^=]|$$)' $(HERE)Makefile | cut -d: -f1 | tr ' ' '\n' | sort | tr '\n' ' '; echo

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

tkt:
	@# The deliverable, from nothing: a clean rebuild that lands ./tkt once smoke passes.
	$(call log, tkt, clean rebuild of $(deliverable) -- expect a few minutes)
	$(MAKE) clean
	$(MAKE) deps unpack build smoke
	install -m 0755 $(artifact) $(deliverable)
	$(call log, tkt, build succeeded -- landed at $(HERE)$(deliverable))

deps: $(deps.files) verify
	@# Fetch every pinned input that is not already here, then verify all of them.

$(HERE)$(fossil.tarball): url := $(fossil.url)
$(HERE)$(cosmocc.zip): url := $(cosmocc.url) $(cosmocc.mirror)
$(amk.pinned): url := $(amk.url)
$(deps.files):
	@# The first url is the home of the input; any after it are mirrors, tried in turn, and verify checks the digest whichever answered.
	$(call log, deps, fetching $(notdir $@) from $(firstword $(url)))
	for u in $(url); do curl -fsSL --connect-timeout 30 --retry 3 --retry-all-errors "$$u" -o "$@.part" && break; \
	  $(call log, deps, $$u did not answer); false; done \
	  || $(call die, deps, could not fetch $(notdir $@) from $(words $(url)) url(s) -- partial file left at $@.part)
	mv "$@.part" "$@"
	case "$@" in *.ape) chmod +x "$@" ;; esac

verify:
	@# Check every download against its pinned digest.
	$(call log, verify, checking $(words $(deps.files)) download(s) against their pinned digests)
	cd $(HERE) && printf '%s  %s\n' \
	  $(fossil.sha256) $(fossil.tarball) \
	  $(if $(filter $(HERE)cosmocc,$(cosmocc.dir)),$(cosmocc.sha256) $(cosmocc.zip)) \
	  $(if $(amk.version),$(amk.sha256) $(amk.file)) \
	| $(sha256) --strict -c ->/dev/null \
	  || $(call die, verify, a download does not match its pin -- remove it and rerun make deps)

amk: $(amk.pinned)
	@# The amk the artifact is made from, alone: the pinned release fetched and checked against its digest, else the one the amk variable names.
	[ -z '$(amk.version)' ] || { cd $(HERE) && printf '%s  %s\n' $(amk.sha256) $(amk.file) | $(sha256) --strict -c ->/dev/null; } \
	  || $(call die, amk, $(amk.file) does not match its pin -- remove it and rerun make amk)
	command -v $(amk) >/dev/null || $(call die, amk, no amk at '$(amk)' -- pin a release in amk.version or put one on PATH or pass amk=PATH)
	$(amk) --help 2>&1 | grep -q -- --bundle-main || $(call die, amk, the amk at $$(command -v $(amk)) has no --bundle-main -- it is too old)
	$(call log, amk, using $$(command -v $(amk)))

toolchain: $(cosmocc.dir)/bin/cosmocc
	@# Unpack cosmocc beside the downloads unless cosmocc.dir names an installed copy.
$(HERE)cosmocc/bin/cosmocc: $(HERE)$(cosmocc.zip)
	$(call log, toolchain, unpacking $(cosmocc.zip) into $(HERE)cosmocc)
	mkdir -p $(HERE)cosmocc
	unzip -q -o $< -d $(HERE)cosmocc
	chmod +x $(HERE)cosmocc/bin/*
	touch $@

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

unpack: $(fossil.src)/.unpacked
	@# Unpack fossil as released into a fresh tree.
$(fossil.src)/.unpacked: $(HERE)$(fossil.tarball)
	$(call log, unpack, unpacking $(fossil.tarball) into $(fossil.src))
	rm -rf $(fossil.src) && mkdir -p $(fossil.src)
	tar xzf $< -C $(fossil.src) --strip-components=1
	touch $@

build: $(artifact)
	@# Fossil compiled in its tree as a fat ape, with zlib archived for both arches; then the payload copied into amk.
$(fossil.src)/compat/zlib/libz.a: $(fossil.src)/.unpacked $(cosmocc.dir)/bin/cosmocc
	$(call log, build, zlib from fossil's compat tree for both arches)
	cd $(@D) && env $(cosmocc.env) bash -c 'for o in $(zlib.objs); do cosmocc -O2 -c $$o.c -o $$o.o; done' \
	  && rm -f libz.a .aarch64/libz.a \
	  && env $(cosmocc.env) cosmoar rcs libz.a $(addsuffix .o,$(zlib.objs))
$(fossil.ape): $(fossil.src)/compat/zlib/libz.a $(fossil.include)
	$(call log, build, fossil $(fossil.version) for cosmocc -- log at $(fossil.src)/build.log)
	cd $(fossil.src) && env $(cosmocc.env) ./configure $(fossil.configure) >build.log 2>&1 \
	  || $(call die, build, configure -- see the tail of $(fossil.src)/build.log)
	cd $(fossil.src) && env $(cosmocc.env) make -j$(jobs) >>build.log 2>&1 \
	  || $(call die, build, compile -- see the tail of $(fossil.src)/build.log)
	mkdir -p $(@D) && install -m 0755 $(fossil.src)/fossil $@

repack:
	@# The artifact from the fossil already compiled: the payload staged and copied into amk, seconds; a change to the payload needs no compile.
	[ -x $(fossil.ape) ] || $(call die, repack, no compiled $(fossil.ape) -- run make build first)
	$(MAKE) $(artifact)

$(artifact): $(fossil.ape) $(payload.files) | amk
	[ -n '$(payload.plugins)' ] || $(call die, build, no plugin under $(payload.dir) to bundle)
	$(call log, build, staging tkt and fossil with plugin(s) $(payload.plugins) for the payload)
	rm -rf build/payload && mkdir -p build/payload/libexec build/payload/bin build/payload/share/tkt/plugins
	install -m 0644 $(payload.script) $(launcher.src) build/payload/libexec/
	install -m 0755 $(fossil.ape) build/payload/bin/fossil
	for p in $(payload.plugins); do cp -R $(payload.dir)/$$p build/payload/share/tkt/plugins/; done
	@# Two copies of amk: the first gains the entry, the second the rest of the payload.
	mkdir -p $(@D) && rm -f $@ build/tkt.entry
	$(amk) --bundle-main $(entry.src) --out build/tkt.entry >/dev/null
	cd build/payload && sh ../tkt.entry --bundle-cp libexec bin share /zip/ --out $(abspath $@) >/dev/null
	$(call log, build, artifact $@ is ready)

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

# A host with no ape loader registered cannot exec the file directly; sh runs the bootstrap.
# PATH holds only the system dirs, so a pass proves the payload's fossil, bash and jq, never the host's; the home and the cache start empty.
omni.run = env PATH=/usr/bin:/bin HOME="$$t/home" USER="$${USER:-tkt}" XDG_CACHE_HOME="$$t/cache" sh $(abspath $(artifact))
smoke: $(artifact)
	@# The ape header, the payload, then tkt from a cold cache: the version banner, a scratch tracker with one ticket, and each shipped plugin found inside the binary with nothing copied out.
	$(call log, smoke, $(artifact) against a scratch tracker)
	head -c 6 $(artifact) | grep -qx 'MZqFpD' || $(call die, smoke, $(artifact) has no ape header)
	members=$$(sh $(artifact) --bundle-ls); \
	  for m in $(payload.members) $(foreach p,$(payload.plugins),/zip/share/tkt/plugins/$(p)/main.sh); do \
	    grep -qx "$$m" <<<"$$members" || $(call die, smoke, no $$m in the payload); done; \
	  ! grep -qE '^/zip/share/tkt/(jobs/|tkt\.pid$$|tkt\.json$$)' <<<"$$members" || $(call die, smoke, a project's own state in the payload)
	t=$$(mktemp -d) && trap 'rm -rf "$$t"' EXIT; mkdir "$$t/home" "$$t/w"; \
	  [ "$$($(omni.run) version)" = "$$(bash $(payload.script) version)" ] || $(call die, smoke, version banner); \
	  [ -x "$$(echo $$t/cache/amk/*/bin/fossil)" ] || $(call die, smoke, the payload's tools did not unpack into the cache); \
	  cd "$$t/w" \
	  && $(omni.run) init >/dev/null 2>&1 \
	  && echo body | $(omni.run) new title=smoke >/dev/null \
	  && $(omni.run) list | grep -q smoke \
	  || $(call die, smoke, scratch tracker round trip); \
	  $(omni.run) skill | grep -qx '## Plugins' || $(call die, smoke, tkt did not find the plugins the binary carries); \
	  [ ! -e .tkt/plugins ] || $(call die, smoke, plugins were copied into the project)
	$(call log, smoke, passed)

stat:
	@# What is built here: the artifact and the inputs kept to stay incremental.
	printf '%-8s %-28s %-6s %s\n' kind path size what
	$(call show, deliver, $(deliverable), the copy make tkt lands for a caller)
	$(call show, artifact, $(artifact), amk with the tkt payload -- for smoke and release)
	$(call show, input, $(fossil.ape), fossil as compiled -- a payload member)
	$(call show, input, $(fossil.src), the fossil tree as released)
	$(call show, input, $(cosmocc.dir), the toolchain)

clean:
	@# Drop the deliverable, build trees and outputs; the downloads and cosmocc stay.
	$(call log, clean, dropping $(deliverable) build out -- the downloads and cosmocc stay)
	rm -rf $(deliverable) build out
