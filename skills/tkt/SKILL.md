---
name: tkt
description: File, read, update, and close tickets in a project's fossil ticket tracker through the tkt command. Use when the human mentions tickets, the tracker, tkt, or .tkt.fossil, asks to file or record a bug or todo, asks what is open, or when work fixes, blocks, or relates to an existing ticket.
allowed-tools: Bash(tkt:*)
---

# tkt

`tkt` is a ticket tracker over fossil. A ticket is a **description** plus **comments**. The
description is the current statement of the problem and is rewritten in place. Comments
are an append-only log beside it. Both are markdown.

Beyond plain markdown, both render ```` ```mermaid ```` and ```` ```pikchr ```` fences as diagrams and
highlight fences that name a language. A bare `[<hash>]` links to that ticket. Prefer a diagram
or a highlighted fence to ascii art. The full rules are on the tracker's `agents/FormattingHelp` wiki
page (`tkt status` prints the url; the page is `/wiki?name=agents/FormattingHelp`).

Run `tkt help` for the full verb list. This skill covers how to use it well.

## When invoked as /tkt

The human typed: `/tkt $ARGUMENTS`

Skip this section when that line shows no `/tkt` invocation. Otherwise act on the first match below.
The **active ticket** is the one most recently shown, filed, or changed in this conversation.

| Arguments | Do this |
| --- | --- |
| *(none)* | Run `tkt triage` and summarize it in a few lines. Name the active ticket, if any. |
| one hex word of 4+ characters matching exactly one ticket | Run `tkt show <id>` and summarize it: the problem, its state, and what is owed. It becomes the active ticket. |
| such a hex word, then an instruction | That ticket becomes the active ticket; follow the instruction for it, as below. Project actions run this way, as `/tkt <id> groom`. |
| `wiki map [focus]`, `map [focus]` | Work on the project's `Mapping` page; see *Map and diagram* below. |
| `wiki system [focus]`, `diagram [focus]` | Work on the project's `SystemDiagrams` page; see *Map and diagram* below. |
| `wiki ...` (anything else) | Treat it as a free-form instruction about the wiki. Read `agents/Home` first. |
| anything else | An instruction about the active ticket. First state the active ticket's id and title; if there is none, ask which ticket. Named instructions follow. |

Named instructions:

- `groom`: rewrite the description into the four sections, folding in what the comments
  settled; fix tags, severity, and links to related tickets. Show the result.
- `plan`: read the ticket and the code it touches, then propose steps. Change nothing.
- `review`: review the code against the ticket's requirements (its Symptom and Todo, and what
  the comments settled). Change nothing.
  - A closed ticket: say so first, then review anyway.
  - The work is usually the uncommitted diff (`git status`, `git diff HEAD`). It may also be
    partly committed already: check `git log` for commits naming the ticket or touching its files.
  - Report each requirement as met, partial, or missing, with `file:line`; then defects and
    risks beyond the requirements.
  - When `tkt` prints `running inside project action`, post the review as one comment on the
    ticket (`tkt comment <id>`). Otherwise reply in the session and post nothing.
- `close`: close only when the rules under *Closing* hold; otherwise say what is still owed.
- `note <text>`: add `<text>` as a comment, tidied into the ticket's voice.

### Map and diagram

The page is `Mapping` or `SystemDiagrams`. If it does not exist, start it with
`tkt wiki cp templates/<Name> <Name>`. Read `agents/Home` and the page, then follow its
*Conventions* and *Instructions*.

These jobs have no natural end, so work in bounded passes:

- With a focus (`/tkt map the serve lifecycle`), cover that focus. Without one, pick the most
  useful gap: an empty section, the *Unknowns* list, or the area the conversation is about.
- Stop after one substantial pass: about two sections, or one area explored in depth. Save
  with `tkt wiki put <Name> --base <version>` before stopping.
- Then report: what you added or changed, what is still missing, and the focus you suggest
  for the next pass. Do not start that pass unasked.

## Before the first call

```bash
tkt list
```

Run it alone, as written: every `tkt` call is a plain command starting with `tkt`, never chained with
`&&`, `;` or a pipe, so it matches a `Bash(tkt:*)` permission and runs where other commands are refused.

| Result | Action |
| --- | --- |
| `tkt: command not found` | Stop and give the human the install step from the tkt README. Do not fall back to raw `fossil` commands. |
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
| Make it a subtask | `tkt parent <id> <parent-id>`, or `--clear`; one level deep |
| List a ticket's subtasks | `tkt list parent=<id>` |
| Change one field | `tkt set <id> severity Critical` |
| Close | `tkt close <id> <<'EOF'` ... |

Optional fields for `new`: `type`, `status`, `severity`, `priority`, `subsystem`, `tags`,
`foundin`, `parent`. An unknown field name fails, so fix the spelling and rerun.

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
  Blockers and parents are command-line only.

## Wiki

The tracker's wiki holds the project pages agents keep current. Start every wiki task at
`agents/Home`: it lists the pages and the rules for them.

| Intent | Command |
| --- | --- |
| List pages | `tkt wiki ls`, or `tkt wiki ls templates` |
| Read a page | `tkt wiki get <page>`; stderr gives its version |
| Write a page | `tkt wiki put <page> --base <version> <<'EOF'` ... |
| Start a page from a template | `tkt wiki cp templates/<Name> <Name>` |
| Retire a page | `tkt wiki rm <page> --base <version>` |

- Always `get` before `put`, and pass the version it printed as `--base`, so a human's edit made
  in between is never overwritten. When `put` reports the page changed, `get` it again and redo
  the edit on the new text.
- `put` replaces the whole page. Carry forward everything that still holds, including the
  page's *Conventions* section.
- Never write `agents/` pages, which humans own. `--force` exists for when the human asks.
- Use `cp` only from `templates/`. Fill the copy in; leave the template as it is.

## Actions

Project actions are commands the human can run from buttons in the web ui. `tkt action list`
shows them; `tkt action run <name> [<id>]` runs one as its button does, streaming its log and
exiting with its code. They need jq.

- They come from the `actions` key of `.tkt.json` beside the tracker: json once its whole-line `//`
  comments are dropped. Each is `{"name", "label", "icon", "command": [argv...], "comment"}`; `{ticket}`,
  `{repo}`, and `{tkt}` (tkt's own path) are filled in, `icon` is a tabler icon name, and `comment: true`
  posts the result to the ticket the run started from. The `config/Actions` wiki page is no longer read.
- `"skill": ["groom"]` instead of a command runs the top-level `agent` argv with its `{prompt}` set to
  `/tkt {ticket} groom`, so such a job may be you, running this skill.
- An action whose command uses `{ticket}` is a ticket action and needs an id; any other is a
  project action, where an id is optional and only says which ticket gets the comment.
  `tkt action list` shows each one's scope.
- Add or change actions only when the human asks: they run commands on their machine.
  Never edit `.tkt.json` unasked.
- `tkt action clean [--keep <n>]` retires old finished jobs to the temp dir; it deletes nothing.
- Prefer an existing action over an ad-hoc command when it does what the human wants, so the
  run lands in the same job history the web ui shows.

## Reporting

When you mention a ticket to the human, give its id and title. When `tkt status`
succeeds, also give the link: its url with `/ticket` replaced by `/tktview/<id>`.
