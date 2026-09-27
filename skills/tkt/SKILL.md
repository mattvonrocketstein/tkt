---
name: tkt
description: File, read, update, and close tickets in a project's fossil ticket tracker through the tkt command. Use when the human mentions tickets, the tracker, tkt, or .tkt.fossil, asks to file or record a bug or todo, asks what is open, or when work fixes, blocks, or relates to an existing ticket.
allowed-tools: Bash(tkt:*)
---

# tkt

`tkt` is a ticket tracker over fossil. A ticket is a **description** plus **comments**. The
description is the current statement of the problem and is rewritten in place. Comments
are an append-only log beside it. Both are markdown.

Run `tkt help` for the full verb list. This skill covers how to use it well.

## Before the first call

```bash
command -v tkt && tkt list
```

| Result | Action |
| --- | --- |
| `tkt` not found | Stop and give the human the install step from the tkt README. Do not fall back to raw `fossil` commands. |
| `no tracker at ...` | Ask the human before running `tkt init`, since it creates a file in their repository. |
| `schema predates the ... field` | Run `tkt init`. It is idempotent and only migrates. |
| `found a tracker under the old name` | Give the human the rename it names. Do not rename the file yourself. |
| `is not a tkt tracker` | Stop and report it. Never pass `--adopt` without the human's explicit yes for that repository. |

## Commands

Always pass bodies on stdin, never as an argument. Use a quoted heredoc: the quoted
delimiter keeps backticks, dollars, and angle brackets literal.

```bash
tkt new title='foo explodes' tags='compiler oop' <<'EOF'
## Symptom

`make foo` exits 2 with `unbound variable: bar`.
EOF
```

When a hook or permission rule blocks heredocs, or the body is long, write it to a draft
file with the Write tool and pipe it. Move or delete the draft once it is filed.

```bash
cat /tmp/ticket-body.md | tkt new title='foo explodes'
```

`tkt new` prints the new uuid. Its first ten characters are the id to use afterwards.

| Intent | Command |
| --- | --- |
| Read one ticket | `tkt show <id>` |
| List open tickets | `tkt list`, or `tkt list status=all tag=<word>` |
| What to work on | `tkt todo`, the 10 newest open tickets; `tkt todo 5 -f json` for fewer, as json |
| What is most urgent | `tkt triage`, only the top severity present among open tickets |
| Find a ticket | `tkt search <text>` |
| Restate the problem | `tkt edit <id> <<'EOF'` ... |
| Add to the record | `tkt comment <id> <<'EOF'` ... |
| Replace tags | `tkt tag <id> compiler oop`, or `--clear` |
| Declare what it waits on | `tkt block <id> <other-id>...`, or `--clear` |
| Change one field | `tkt set <id> severity Critical` |
| Close | `tkt close <id> <<'EOF'` ... |

Optional fields for `new`: `type`, `status`, `severity`, `priority`, `subsystem`, `tags`,
`foundin`. An unknown field name fails, so fix the spelling and rerun.

Never use `tkt run` for a write that a verb covers, and never edit `.tkt.fossil` directly.
`tkt run` is the human's escape hatch.

## Questions the verbs don't answer

Use `tkt sql` for any read-only question: what is ready to work, what went stale, counts
by tag. It can't change anything, so it's always safe to run.

- Run `tkt sql --schema` first. It explains the tables and gives two example queries.
- Pass the query as an argument, or on stdin for anything longer than a line.
- Never use `tkt run sql`. That is the human's unrestricted escape hatch.

```bash
tkt sql "select severity, count(*) as n from ticket where status != 'Closed' group by severity;"
```

## Search before filing

Run `tkt search <key term>` before `tkt new`. When a ticket already covers the problem,
comment on it or rewrite its description instead of filing a duplicate.

## Ticket structure

Someone acts on a ticket later without the context you have now, so write the destination,
not the journey. Four sections carry almost every description:

- **Symptom**: the real error text, quoted.
- **Repro**: the shortest command that shows it.
- **Cause**: where the defect lives, stated flatly.
- **Result** or **Todo**: what was fixed and what test pins it, or what is still owed.

Leave out what you tried first, what you ruled out, and commentary on tooling or process.
Put that in a notes file, not in the ticket.

## Edit or comment

| Situation | Verb |
| --- | --- |
| The description is wrong or out of date | `tkt edit`: rewrite the whole description. The old text stays in fossil's history. |
| New evidence, a status note, a partial fix | `tkt comment` |
| Comments have pushed the ticket out of the four sections | `tkt edit` to fold them back in, not another comment |

`tkt edit` replaces the description. Run `tkt show <id>` first and carry forward what
still holds.

## Cross-references

- **See also**: write `[<uuid>]` in any description or comment. `tkt` rewrites it into a
  link, and `tkt show` on the other ticket lists it under `Referenced by`. A code span such
  as `` `<uuid>` `` does not link.
- **Waits on**: use `tkt block` only when this ticket cannot proceed until the other one
  closes. Record only the waits-on direction; `tkt show` derives the reverse.

## Closing

Close a ticket yourself only when all three hold:

1. The fix is committed.
2. A test pins it.
3. You watched that test pass.

The closing comment names the commit and the test:

```bash
tkt close 896eb890 <<'EOF'
Fixed in abc1234, pinned by test_foo_unbound.
EOF
```

For any other resolution, pass `resolution=`, for example `resolution=Works_As_Designed`.
A fix that is uncommitted or unverified stays open, with a comment saying what is still
owed.

## Web ui

`tkt serve` runs in the foreground until stopped, and prints its url as its first line.
Each tracker has one server: a new `tkt serve`, from any terminal, stops the old one first.

- **Check first:** `tkt status` prints the url when a server is running, and fails when
  none is.
- **Offer, then start:** start a server only when the human wants the web ui. Run
  `tkt serve` as a background command, and tell the human three things: the url, that the
  server runs inside this session, and that running `tkt serve` in their own terminal
  takes it over there, in the foreground where they can watch and Ctrl-C it.
- **Port:** the default is 9080 for every project, so `serve` fails with `port ... is taken`
  when another project is already serving. Do not stop that other server. Pick a free port
  and pass it, `tkt serve port=9081`, and tell the human that adding `TKT_PORT=9081` to the
  project's `.env` beside `.tkt.fossil` makes it the default. Never edit `.env` yourself
  unless asked. `TKT_PORT` in the environment beats `.env`, and `port=` beats both.
- **Stop:** `tkt stop` works from anywhere.
- **What the human can do there:** file, edit, comment on, close, and reopen tickets.
  Blockers are command-line only.

## Reporting

When you mention a ticket to the human, give its id and title. When `tkt status`
succeeds, also give the link: its url with `/ticket` replaced by `/tktview/<id>`.
