#!/usr/bin/env bash

# tet: proposals for a tkt tracker. Any tkt write can be proposed instead of made; a human accepts or rejects it on a
# review page, and accepting applies it.
#
# tkt knows nothing of tet. To propose, tet runs tkt with a shim named fossil first on its PATH: tet itself. tkt
# validates and resolves as usual, and every fossil write it makes (ticket add or set, wiki create or commit) is
# recorded instead of run, while reads pass through to the real fossil. Accepting replays those writes, after checking
# that the target has not changed since. Proposals live in fx_proposal, beside fossil's own tables: the fx_ prefix
# keeps it through fossil rebuild and lets report sql read it. It does not sync to clones, so it is working state; an
# applied proposal leaves its record on the ticket or page.
# tet sources tkt for its shared helpers (locate, sqlq, lit, the cgi plumbing); sourcing runs none of tkt's cli.
# tkt is $TET_TKT, else the tkt link in .tkt/ext, one level above this ext/tet/main (reached through .tkt/bin/tet or
# directly), else the one on PATH
tet_tkt() {
  local self=$0 real
  case "$self" in */*) ;; *) self=$(command -v "$self") ;; esac
  real=$(readlink -f "$self" 2>/dev/null || printf '%s' "$self")
  if [ -n "${TKT_LIB:-}" ]; then printf '%s' "$TKT_LIB"
  elif [ -n "${TET_TKT:-}" ]; then printf '%s' "$TET_TKT"
  elif [ -x "$(dirname "$(dirname "$real")")/tkt" ]; then printf '%s' "$(dirname "$(dirname "$real")")/tkt"
  else command -v tkt || { printf 'tet: tkt not found beside tet or on PATH; set TET_TKT\n' >&2; exit 1; }
  fi
}
# as the shim, the fossil first on PATH is tet's stand-in; drop it so fossil means the real one again
TET_AS_FOSSIL=${TET_SHIM:-}
unset TET_SHIM
if [ -n "${TET_DIR:-}" ] && [ -n "$TET_AS_FOSSIL" ]; then PATH=${PATH#"$TET_DIR:"}; fi
TET_LIB=$(tet_tkt)
# the tkt to run back as a command: the one that ran tet, when it says which, else the file tet sources
TET_TKT=${TET_TKT:-${TKT_SELF:-$TET_LIB}}
# shellcheck source=tkt
source "$TET_LIB"
set -eo pipefail

PROG=tet

PROPOSABLE='new edit comment tag block parent set close wiki'
WRITES="'ticket add' 'ticket set' 'wiki create' 'wiki commit'"

usage() {
  cat <<'EOF'
tet: proposals for a tkt tracker. tkt itself never runs or mentions tet.

  tet init                              create or migrate the proposals table; the review page is served at
                                        /ext/tkt/ext/tet/main.sh while tkt serve runs
  tet propose [--run R] [--why W] [--group G] <tkt verb> [args...]
                                        run a tkt write verb, recording its changes instead of making them;
                                        prints "proposed <id>". stdin goes to tkt as usual. run defaults to
                                        $TET_RUN, else manual. proposable: new edit comment tag block parent set
                                        close wiki
  tet list                              pending proposals, as markdown
  tet accept <id>...                    accept and apply pending proposals
  tet reject <id>...                    reject pending proposals
  tet help

The tracker is $TKT_DB, else the nearest .tkt.fossil here or above.
EOF
}

# this file's own path with links resolved, which the stand-in for fossil runs
real_path() {
  local self=$0
  case "$self" in */*) ;; *) self=$(command -v "$self") ;; esac
  readlink -f "$self" 2>/dev/null || printf '%s' "$self"
}

ready() { [ "$(sqlq "select count(*) from pragma_table_info('fx_proposal') where name='writes';")" = 1 ]; }

verb_init() {
  [ -f "$REPO" ] || die "no tracker at $REPO; run tkt init first"
  # earlier shapes of the table, from before tet, only ever held trial rows
  if [ "$(sqlq "select count(*) from pragma_table_info('fx_proposal');")" != 0 ] && ! ready; then
    sqlq 'drop table fx_proposal;'
    note 'replaced an earlier fx_proposal table'
  fi
  [ -f "$PLUGIN_SQL/schema.sql" ] || die "missing $PLUGIN_SQL/schema.sql"
  sqlq ".read '$PLUGIN_SQL/schema.sql'" "delete from reportfmt where title in ('Proposals','Decided Proposals');"
  note "ready at $REPO; the review page is $PLUGIN_URL/main.sh while tkt serve runs"
}

# the target's version now, in the terms base was recorded in: a ticket's tkt_mtime, or a wiki page's artifact
version_of() {
  case "$1" in
    wiki:*) sqlq "select b.uuid from event e join blob b on b.rid=e.objid where e.type='w' and substr(e.comment,2)=$(lit "${1#wiki:}") order by e.mtime desc, e.objid desc limit 1;" ;;
    ?*) sqlq "select tkt_mtime from ticket where substr(tkt_uuid,1,10)=$(lit "$1");" ;;
  esac
}

# --- the shim: tet run as fossil, inside a proposal. a write is appended to $TET_DIR/writes as a json object of its
# arguments (without -R) and, for wiki writes, the page text, since its temp file is gone by apply time
shim() {
  local -a args=()
  case "${1:-} ${2:-}" in 'ticket add'|'ticket set'|'wiki create'|'wiki commit') ;; *) exec fossil "$@" ;; esac
  while [ $# -gt 0 ]; do
    if [ "$1" = -R ] && [ $# -ge 2 ]; then REPO=$2; shift 2; continue; fi
    args+=("$1"); shift
  done
  local a words= file=NULL target= base= body= i
  for i in "${!args[@]}"; do
    a=${args[$i]}
    if [ "${args[0]}" = wiki ] && [ "$i" = 3 ]; then file="cast(readfile($(lit "$a")) as text)"; a=@file; fi
    words="$words${words:+,}$(lit "$a")"
  done
  sqlq "select json_object('argv', json_array($words), 'file', $file);" >>"$TET_DIR/writes"
  case "${args[0]} ${args[1]}" in
    'ticket set') target=${args[2]}; base=$(version_of "$target") ;;
    'wiki commit') target="wiki:${args[2]}"; base=$(version_of "$target") ;;
    'wiki create') target="wiki:${args[2]}" ;;
  esac
  [ -e "$TET_DIR/target" ] || { printf '%s' "$target" >"$TET_DIR/target"; printf '%s' "$base" >"$TET_DIR/base"; }
  # what a reviewer reads: the description or comment a ticket write carries, or the page text
  if [ ! -s "$TET_DIR/body" ]; then
    if [ "${args[0]}" = wiki ]; then sqlq "select $file;" >"$TET_DIR/body"
    else
      for i in "${!args[@]}"; do
        case "${args[$i]}" in description|+icomment) printf '%s' "${args[$((i + 1))]:-}" >"$TET_DIR/body"; break ;; esac
      done
    fi
  fi
}

verb_propose() {
  local run=${TET_RUN:-manual} why= grp= rc=0 id writes
  while [ $# -gt 0 ]; do
    case "$1" in
      --run|--why|--group) [ $# -ge 2 ] || die "$1 needs a value"
        case "$1" in --run) run=$2 ;; --why) why=$2 ;; --group) grp=$2 ;; esac; shift 2 ;;
      --) shift; break ;;
      *) break ;;
    esac
  done
  [ $# -gt 0 ] || die 'usage: tet propose [--run R] [--why W] [--group G] <tkt verb> [args...]'
  case " $PROPOSABLE " in *" $1 "*) ;; *) die "$1 cannot be proposed; proposable verbs: $PROPOSABLE" ;; esac
  ready || die 'tracker has no proposals table; run tet init'
  TET_DIR=$(mktemp -d)
  # tkt finds this stand-in as fossil; it runs this file by its extension, so the file itself need not be executable
  printf '#!/bin/sh\nTET_SHIM=1 exec bash %s "$@"\n' "'$(real_path)'" >"$TET_DIR/fossil"
  chmod +x "$TET_DIR/fossil"
  : >"$TET_DIR/writes"
  # tkt's own output is about the change it believes it made, so it goes to stderr; stdout carries the proposal id
  TET_DIR=$TET_DIR PATH="$TET_DIR:$PATH" TKT_DB=$REPO "$TET_TKT" "$@" >&2 || rc=$?
  if [ "$rc" -ne 0 ]; then rm -rf "$TET_DIR"; exit "$rc"; fi
  if [ ! -s "$TET_DIR/writes" ]; then rm -rf "$TET_DIR"; die "tkt $1 made no change, so there is nothing to propose"; fi
  writes="[$(paste -sd, "$TET_DIR/writes")]"
  local argv= a
  for a in "$@"; do argv="$argv${argv:+,}$(lit "$a")"; done
  # many proposers write at once; wait out a writer's lock rather than fail on it
  id=$(sqlq '.timeout 10000' "insert into fx_proposal(run,grp,verb,argv,writes,body,target,base,why,created_by)
    values($(lit "$run"),nullif($(lit "$grp"),''),$(lit "$1"),json_array($argv),json($(lit "$writes")),
    nullif(cast(readfile($(lit "$TET_DIR/body")) as text),''),nullif($(lit "$(cat "$TET_DIR/target")"),''),
    nullif($(lit "$(cat "$TET_DIR/base")"),''),nullif($(lit "$why"),''),$(lit "${USER:-}")) returning id;")
  rm -rf "$TET_DIR"
  [ -n "$id" ] || die 'recording the proposal failed'
  printf 'proposed %s\n' "$id"
}

# apply one accepted proposal: refuse a target that changed since it was proposed, else replay its writes in order,
# stopping at the first failure. the outcome and fossil's output land in status and result
apply() {
  local id=$1 target base now out= status= n k word in rc
  [ "$(sqlq "select count(*) from fx_proposal where id=$id and status='accepted';")" = 1 ] || return 0
  target=$(sqlq "select coalesce(target,'') from fx_proposal where id=$id;")
  base=$(sqlq "select coalesce(base,'') from fx_proposal where id=$id;")
  if [ -n "$base" ]; then
    now=$(version_of "$target")
    [ "$now" = "$base" ] || { status=failed; out="target changed since proposed (was $base, now ${now:-gone}); nothing written"; }
  fi
  if [ -z "$status" ]; then
    n=$(sqlq "select json_array_length(writes) from fx_proposal where id=$id;")
    for ((k = 0; k < n; k++)); do
      local -a argv=()
      # words come back as hex, so a word holding a newline or a bar survives the trip through the sql shell
      while IFS= read -r word; do argv+=("$(printf '%b' "$(printf '%s' "$word" | sed 's/../\\x&/g')")"); done \
        < <(sqlq "select hex(j.value) from fx_proposal p, json_each(p.writes, '\$[$k].argv') j where p.id=$id order by j.key;")
      case " $WRITES " in *"'${argv[0]:-} ${argv[1]:-}'"*) ;; *)
        status=failed; out="$out${out:+$'\n'}refused write: ${argv[*]:0:2}"; break ;; esac
      in=
      if [ "${argv[3]:-}" = @file ]; then
        in=$(mktemp)
        sqlq "select writefile($(lit "$in"), json_extract(writes, '\$[$k].file')) from fx_proposal where id=$id;" >/dev/null
        argv[3]=$in
      fi
      rc=0
      out="$out${out:+$'\n'}$(fossil "${argv[@]}" -R "$REPO" 2>&1)" || rc=$?
      [ -z "$in" ] || rm -f "$in"
      if [ "$rc" -ne 0 ]; then status=failed; out="$out"$'\n'"stopped after $k of $n writes"; break; fi
    done
    status=${status:-applied}
  fi
  sqlq '.timeout 10000' "update fx_proposal set status=$(lit "$status"), result=$(lit "$out"), applied_at=datetime('now') where id=$id;" >/dev/null
}

# record decisions for pending proposals, then apply the accepted ones in id order
decide() {
  local d=$1 who=$2 id sql=
  shift 2
  for id in "$@"; do
    case "$id" in ''|*[!0-9]*) die "not a proposal id: $id" ;; esac
    sql="$sql update fx_proposal set status=$(lit "$d"), decided_by=$(lit "$who"), decided_at=datetime('now') where id=$id and status='pending';"
  done
  sqlq '.timeout 10000' "begin;$sql commit;" >/dev/null
  if [ "$d" = accepted ]; then for id in $(printf '%s\n' "$@" | sort -n); do apply "$id"; done; fi
}

verb_accept() { [ $# -gt 0 ] || die 'usage: tet accept <id>...'; ready || die 'run tet init'; decide accepted "${USER:-}" "$@"; verb_status "$@"; }
verb_reject() { [ $# -gt 0 ] || die 'usage: tet reject <id>...'; ready || die 'run tet init'; decide rejected "${USER:-}" "$@"; verb_status "$@"; }
verb_status() { sqlq "select id || ' ' || status || coalesce(': ' || replace(result, char(10), ' '), '') from fx_proposal where id in ($(IFS=,; echo "$*")) order by id;"; }

verb_list() {
  ready || die 'run tet init'
  { printf '.mode markdown\n.headers on\n'
    printf "select id, verb, coalesce(target,'') as target, (select group_concat(value,' ') from json_each(argv)) as command, coalesce(why,'') as why, run from fx_proposal where status='pending' order by run, grp, id;\n"
  } | fossil sql -R "$REPO"
}

# --- the review page: fossil's /ext CGI. this file is .tkt/ext/tet/main, and tkt serve passes .tkt/ext as the
# extroot; its js and css beside it are served as static files. routes, under /ext/tet/main.sh:
#   GET  /           pending proposals to decide, and recent outcomes
#   POST /decide     d=<id>:<accept|reject>, repeated: record and apply; with ajax=1 answer with the settled rows
# output opening with a fossil-doc div is wrapped in the repository's skin, so the page wears tkt's styles

# tkt's cgi_env, plus the tracker's root url for links out of /ext
tet_cgi_env() {
  cgi_env
  plugin_use
  ROOT=${BASE%%/ext/*}
}

# every value of one field in a urlencoded string, one per line; bash's printf decodes the \x escapes
form_fields() {
  printf '%s\n' "$2" | tr '&' '\n' | sed -n "s/^$1=//p" | while IFS= read -r v; do
    v=${v//+/ }
    printf '%b\n' "${v//%/\\x}"
  done
}

# rows are built in sql, which escapes every value it puts into markup, so a body or a result holding html shows as text
hx() { printf "replace(replace(replace(replace(coalesce(%s,''),'&','&amp;'),'<','&lt;'),'>','&gt;'),'\"','&quot;')" "$1"; }
cmd_sql() { printf "(select group_concat(case when value glob '*[ ]*' or value = '' then quote(value) else value end, ' ') from json_each(p.argv))"; }
target_sql() {
  printf "case when p.target is null then '' when p.target like 'wiki:%%' then '<a href=\"%s/wiki?name=' || %s || '\">' || %s || '</a>' else '<a href=\"%s/tktview/' || p.target || '\">' || p.target || '</a>' end" \
    "$ROOT" "$(hx 'substr(p.target,6)')" "$(hx 'substr(p.target,6)')" "$ROOT"
}
expander_sql() {
  printf "case when trim(coalesce(%s,'')) = '' then '' else '<details><summary>' || %s || '</summary><pre>' || %s || '</pre></details>' end" \
    "$1" "$(hx "substr(trim($1),1,min(80,instr(trim($1)||char(10),char(10))-1))")" "$(hx "$1")"
}
# the accept button says what accepting does
accept_label_sql() {
  printf "case p.verb when 'new' then 'File' when 'edit' then 'Rewrite' when 'comment' then 'Comment' when 'tag' then 'Tag' when 'block' then 'Block' when 'parent' then 'Reparent' when 'set' then 'Set' when 'close' then 'Close' when 'wiki' then 'Write page' else 'Accept' end"
}

pending_rows() {
  sqlq "select '<tr data-proposal=\"' || p.id || '\"><td><input type=\"checkbox\" class=\"tet-pick\" aria-label=\"Select proposal ' || p.id || '\"> ' || p.id || '</td>'
    || '<td>' || $(hx p.verb) || '</td><td>' || $(target_sql) || '</td><td>' || $(hx 'coalesce(t.title,substr(p.target,6))') || '</td>'
    || '<td><code>' || $(hx "$(cmd_sql)") || '</code></td><td>' || $(expander_sql p.body) || '</td><td>' || $(hx p.why) || '</td><td>' || $(hx p.run) || '</td>'
    || '<td><span class=\"tkt-ago\" data-utc=\"' || p.created_at || '\">' || p.created_at || '</span></td>'
    || '<td class=\"tet-decide\"><button type=\"button\" data-d=\"accept\">' || $(accept_label_sql) || '</button><button type=\"button\" data-d=\"reject\">Reject</button></td></tr>'
    from fx_proposal p left join ticket t on p.target not like 'wiki:%' and substr(t.tkt_uuid,1,10)=p.target
    where p.status='pending' order by p.run, p.grp, p.id;"
}

# settled rows, newest first: the recent ones, or exactly the ids given (what a submit just decided)
settled_rows() {
  local where="p.status<>'pending'" limit='limit 50'
  if [ -n "$1" ]; then where="p.id in ($1) and $where"; limit=; fi
  sqlq "select '<tr data-proposal=\"' || p.id || '\" class=\"tet-settled-' || p.status || '\"><td>' || p.id || '</td>'
    || '<td><span class=\"tet-state tet-state-' || p.status || '\">' || p.status || '</span></td>'
    || '<td>' || $(hx p.verb) || '</td><td>' || $(target_sql) || '</td><td><code>' || $(hx "$(cmd_sql)") || '</code></td>'
    || '<td>' || $(expander_sql p.result) || '</td><td>' || $(hx p.decided_by) || '</td>'
    || '<td><span class=\"tkt-ago\" data-utc=\"' || coalesce(p.applied_at,p.decided_at) || '\">' || coalesce(p.applied_at,p.decided_at) || '</span></td></tr>'
    from fx_proposal p where $where order by coalesce(p.applied_at,p.decided_at) desc, p.id desc $limit;"
}

route_page() {
  local n
  printf 'Status: 200\r\nContent-Type: text/html; charset=utf-8\r\n\r\n'
  printf "<div class='fossil-doc' data-title='Proposals'>\n"
  if ! ready; then printf '<p>This tracker has no proposals table; run <code>tet init</code>.</p></div>\n'; return; fi
  n=$(sqlq "select count(*) from fx_proposal where status='pending';")
  printf '<link rel="stylesheet" href="%s%s/css/tet.css">\n' "$ROOT" "$PLUGIN_URL"
  printf '<div id="tet">\n'
  card_open tet-card-pending "Pending <span class=\"tkt-card-meta tet-pending-count\">$n</span>"
  printf '<div class="tet-bar"><label><input type="checkbox" class="tet-pickall"> All</label>'
  printf '<button type="button" data-bulk="accept">Accept checked</button><button type="button" data-bulk="reject">Reject checked</button>'
  printf '<button type="button" data-bulk="">Undecide checked</button><span class="tet-count"></span>'
  printf '<form method="post" action="%s/decide"><button type="submit" class="tet-submit" disabled>Submit</button></form></div>\n' "$BASE"
  printf '<table class="report tet-pending"><thead><tr><th>Proposal</th><th>Verb</th><th>Ticket</th><th>Title</th><th>Command</th><th>Body</th><th>Why</th><th>Run</th><th>Created</th><th>Decide</th></tr></thead><tbody>\n'
  pending_rows
  printf '</tbody></table>\n<p class="tet-empty"%s>Nothing pending.</p>\n' "$([ "$n" = 0 ] || echo ' hidden')"
  card_close
  card_open tet-card-settled 'Settled <span class="tkt-card-meta">most recent 50</span>'
  printf '<table class="report tet-settled"><thead><tr><th>Proposal</th><th>Status</th><th>Verb</th><th>Ticket</th><th>Command</th><th>Result</th><th>By</th><th>Settled</th></tr></thead><tbody>\n'
  settled_rows
  printf '</tbody></table>\n'
  card_close
  printf '</div>\n'
  printf '<script src="%s%s/js/tet.js"></script>\n' "$ROOT" "$PLUGIN_URL"
  printf '</div>\n'
}

# only pending proposals change, so a stale page or a second submit cannot overturn a decision; one bad decision
# refuses the whole batch
route_decide() {
  local d body acc=() rej=() all=
  [ "$REQUEST_METHOD" = POST ] || cgi_fail_text 405 'decisions are sent only by a POST'
  cgi_same_origin || cgi_fail_text 403 "refused a request from another site (referer: ${HTTP_REFERER:-none})"
  ready || cgi_fail_text 503 'this tracker has no proposals table; run tet init'
  body=$(cgi_body)
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    case "$d" in
      *[!0-9]*:accept|*[!0-9]*:reject|:*) cgi_fail_text 400 "bad decision: $d" ;;
      *:accept) acc+=("${d%:*}") ;;
      *:reject) rej+=("${d%:*}") ;;
      *) cgi_fail_text 400 "bad decision: $d" ;;
    esac
    all="$all${all:+,}${d%:*}"
  done < <(form_fields d "$body")
  [ -n "$all" ] || cgi_fail_text 400 'no decisions sent'
  [ ${#rej[@]} -eq 0 ] || decide rejected "$USER" "${rej[@]}"
  [ ${#acc[@]} -eq 0 ] || decide accepted "$USER" "${acc[@]}"
  if [ "$(printf '%s\n' "$body" | tr '&' '\n' | sed -n 's/^ajax=//p' | head -n 1)" = 1 ]; then
    printf 'Content-Type: text/html; charset=utf-8\r\n\r\n'
    settled_rows "$all"
    return
  fi
  printf 'Status: 303 See Other\r\nLocation: %s\r\n\r\n' "$HTTP_REFERER"
}

cgi_main() {
  tet_cgi_env
  case "${PATH_INFO:-}" in
    '') route_page ;;
    /decide) route_decide ;;
    *) cgi_fail 404 "no page ${PATH_INFO}" ;;
  esac
}

main() {
  if [ -n "$TET_AS_FOSSIL" ] && [ -n "${TET_DIR:-}" ]; then shim "$@"; return; fi
  if [ $# -eq 0 ] && [ -n "${GATEWAY_INTERFACE:-}" ] && [ -n "${FOSSIL_REPOSITORY:-}" ]; then cgi_main; return; fi
  local verb=${1:-help}
  [ $# -eq 0 ] || shift
  case "$verb" in
    help|-h|--help) usage; return ;;
    init|propose|list|accept|reject) ;;
    *) usage >&2; die "unknown verb: $verb" ;;
  esac
  locate
  plugin_use
  [ -f "$REPO" ] || die "no tracker at $REPO; run tkt init first"
  "verb_$verb" "$@"
}

main "$@"
