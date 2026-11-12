#!/usr/bin/env bash

# wiki: the tracker's project wiki, as a tkt plugin. tkt runs it for `tkt wiki ...`; its init seeds the pages agents
# start from: agents/Home and the templates, from .tkt/data/wiki. its main menu entries are
# configured under plugins.wiki in tkt.json
# tkt is the file the tkt that ran this plugin names, else the tkt beside the folder of plugins this one is in
tkt=${TKT_LIB:-$(dirname "$(dirname "$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")")")/tkt}
# shellcheck source=../../tkt
source "$tkt"
set -eo pipefail
PROG=wiki

# every markdown file under a folder, at any depth; the shell walks it, so the folder may be one only the shell can read
md_files() {
  local f
  for f in "$1"/*; do
    if [ -d "$f" ]; then md_files "$f"
    elif [ -f "$f" ] && [ "${f%.md}" != "$f" ]; then printf '%s\n' "$f"; fi
  done
}

# pages the project owns once seeded: each $DATA_DIR/wiki/<page>.md is the wiki page <page>, so the folder mirrors
# page names (agents/Home.md, templates/Style.md). init creates a missing page and never touches it again.
# agents/Home is the steering page agents start from; templates/* are project-agnostic starting points they fill in
seed_templates() {
  local t page
  [ -d "$PLUGIN_DATA" ] || return 0
  while IFS= read -r t; do
    page=${t#"$PLUGIN_DATA/"}; page=${page%.md}
    fx wiki export "$page" >/dev/null 2>&1 && continue
    fx wiki create "$page" "$t" --mimetype text/x-markdown >/dev/null
  done < <(md_files "$PLUGIN_DATA" | sort)
}

# wiki pages, for agents keeping the project's pages current. pages are markdown; a page emptied by rm is hidden
# by fossil and treated as absent here. each page's latest version id lets put and rm refuse a stale write (--base)
wiki_name() {
  case "$1" in
    '') die 'a page name is required' ;;
    /*|*/|*//*) die "bad page name: $1" ;;
    branch/*|tag/*|checkin/*) die "fossil reserves the ${1%%/*}/ prefix for its own notes; pick another name" ;;
  esac
}
# the latest version of a page as 'uuid|mark', where mark is - for an emptied page; nothing when it never existed
wiki_head() {
  sqlq "select b.uuid || '|' || substr(e.comment,1,1) from event e join blob b on b.rid=e.objid where e.type='w' and substr(e.comment,2)=$(lit "$1") order by e.mtime desc, e.objid desc limit 1;"
}
wiki_exists() { local h; h=$(wiki_head "$1"); [ -n "$h" ] && [ "${h##*|}" != - ]; }
wiki_version() { local h; h=$(wiki_head "$1"); h=${h%%|*}; printf '%s' "${h:0:10}"; }
# a write needs --force for agents/ pages, which agents are told not to edit, and --base must match the latest version
wiki_guard() {
  local page=$1 base=$2 force=$3 cur
  case "$page" in agents/*) [ -n "$force" ] || die "$page steers agents and is edited by humans; pass --force if you were asked to change it" ;; esac
  [ -z "$base" ] && return 0
  cur=$(wiki_version "$page")
  case "$cur" in "$base"*) [ -n "$cur" ] && return 0 ;; esac
  die "$page changed since version $base (now ${cur:-absent}); run tkt wiki show $page and redo the edit"
}
wiki_write() {
  local f
  f=$(mktemp)
  printf '%s\n' "$2" >"$f"
  if wiki_head "$1" | grep -q .; then fx wiki commit "$1" "$f" --mimetype text/x-markdown >/dev/null
  else fx wiki create "$1" "$f" --mimetype text/x-markdown >/dev/null; fi
  rm -f "$f"
}
wiki_usage() { die 'usage: tkt wiki ls|list [prefix] | get|show <page> | put <page> [--base <v>] [--force] | rm <page> [--base <v>] [--force] | cp|copy <page> <new-page> [--force]'; }

verb_wiki() {
  need
  local sub=${1:-} page= dst= base= force= body cur
  [ $# -eq 0 ] || shift
  while [ $# -gt 0 ]; do
    case "$1" in
      --base) [ $# -ge 2 ] || wiki_usage; base=$2; shift 2 ;;
      --base=*) base=${1#--base=}; shift ;;
      --force) force=1; shift ;;
      -*) wiki_usage ;;
      *) if [ -z "$page" ]; then page=$1; elif [ -z "$dst" ]; then dst=$1; else wiki_usage; fi; shift ;;
    esac
  done
  case "$sub" in
    list|ls)
      [ -z "$dst$base$force" ] || wiki_usage
      local where='' pre=${page%/}
      [ -z "$pre" ] || where="and (page=$(lit "$pre") or substr(page,1,$(( ${#pre} + 1 )))=$(lit "$pre/"))"
      sqlq "with w as (select substr(comment,2) as page, comment, mtime, objid, row_number() over (partition by substr(comment,2) order by mtime desc, objid desc) as n from event where type='w')
        select '| Page | Size | Updated |' || char(10) || '| --- | --- | --- |' union all
        select * from (select '| ' || page || ' | ' || (select size from blob where rid=w.objid) || ' | ' || datetime(mtime) || ' |' from w where n=1 and comment not like '-%' $where order by page collate nocase);" | paint ;;
    show|get)
      [ -n "$page" ] && [ -z "$dst$base$force" ] || wiki_usage
      wiki_name "$page"
      wiki_exists "$page" || die "no wiki page $page; tkt wiki list shows them"
      fx wiki export "$page"
      note "$page is at version $(wiki_version "$page"); tkt wiki put $page --base $(wiki_version "$page") refuses if it changes first" ;;
    put)
      [ -n "$page" ] && [ -z "$dst" ] || wiki_usage
      wiki_name "$page"
      wiki_guard "$page" "$base" "$force"
      body=$(slurp editor)
      [ -n "$(printf '%s' "$body" | tr -d ' \t\n')" ] || die 'nothing on stdin; to retire a page use tkt wiki rm'
      if wiki_exists "$page" && [ "$(fx wiki export "$page")" = "$body" ]; then note "$page is unchanged"; return; fi
      if wiki_exists "$page"; then cur=updated; else cur=created; fi
      wiki_write "$page" "$body"
      note "$cur $page, now at version $(wiki_version "$page")" ;;
    rm)
      [ -n "$page" ] && [ -z "$dst" ] || wiki_usage
      wiki_name "$page"
      wiki_exists "$page" || die "no wiki page $page"
      wiki_guard "$page" "$base" "$force"
      local f; f=$(mktemp)
      fx wiki commit "$page" "$f" --mimetype text/x-markdown >/dev/null
      rm -f "$f"
      note "removed $page; its history stays in fossil" ;;
    copy|cp)
      [ -n "$page" ] && [ -n "$dst" ] && [ -z "$base" ] || wiki_usage
      wiki_name "$page"; wiki_name "$dst"
      wiki_exists "$page" || die "no wiki page $page"
      # copying is for starting a page from a template; any other copy is usually a rename gone wrong
      case "$page" in templates/*) ;; *) [ -n "$force" ] || die "$page is not a template; copying it duplicates its content, so pass --force if that is what you want" ;; esac
      ! wiki_exists "$dst" || die "$dst already exists; use tkt wiki put $dst to replace it"
      case "$dst" in agents/*) [ -n "$force" ] || die "$dst steers agents and is edited by humans; pass --force if you were asked to create it" ;; esac
      wiki_write "$dst" "$(fx wiki export "$page")"
      note "copied $page to $dst, now at version $(wiki_version "$dst")" ;;
    *) wiki_usage ;;
  esac
}

locate
plugin_use
[ -f "$REPO" ] || die "no tracker at $REPO; run tkt init first"
case "${1:-}" in
  init)
    seed_templates || note "agent home and template pages: seeding them failed"
    note "ready at $REPO" ;;
  *) verb_wiki "$@" ;;
esac
