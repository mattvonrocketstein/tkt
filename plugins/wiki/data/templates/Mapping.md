# Mapping

> **Template.** This page has not been filled in yet. Follow [Agent Home](/wiki?name=agents/Home) and each
> *Instructions* block below, then delete this note and the *Instructions* blocks. Keep the
> *Conventions* section: it governs every later edit to this page.

## Conventions

- **Working notes, not a reference.** This is the raw map of what has been found while exploring the code. It may be
  messy, partial, and wrong. [System Diagrams](/wiki?name=templates/SystemDiagrams) is the curated picture; this page
  is where material for it is gathered.
- **Discovered, not designed.** Record what the code actually contains, as found, with the path or command that
  shows it. No conceptual or planned parts.
- **Mark confidence.** Tag each claim *confirmed* (read or ran it), *likely* (inferred from names or partial reading),
  or *guess*. Upgrade the tag when you check it.
- **Append freely, prune carefully.** Add findings as you go. Delete a finding only when it is shown wrong, or once it
  has been promoted, and leave a line saying where it went.
- **Promote what settles.** When part of the map stops changing, move it into System Diagrams,
  [Lexicon](/wiki?name=templates/Lexicon), or [Workflows](/wiki?name=templates/Workflows), and link to it from here.
- **Crude diagrams are fine.** A rough mermaid sketch, even a large one, beats none; tidy it when it is promoted.

## Folders and files

*Instructions:* the directory tree as far as it has been explored, one line per folder or notable file on what it
appears to hold, with a confidence tag. Note generated, vendored, and dead-looking code. A trimmed `tree` or
`ls` listing in a `text` fence is a fine start.

## Entry points

*Instructions:* every way execution starts that you have found (binaries, scripts, `main` functions, routes, jobs,
hooks, tests), with path and confidence.

## Symbols

*Instructions:* the types, functions, tables, config keys, and constants that keep coming up, one row each,
with where they are defined and a confidence tag.

| Symbol | Kind | Defined at | What it seems to do |
| --- | --- | --- | --- |
| `example` | function | `src/example.py:42` | *likely:* one line |

## Useful commands

*Instructions:* commands that helped explore: searches that find things (`grep`/`rg` patterns, `git log -S`),
introspection and debug flags, ways to dump state, queries against local data. Each with one line on what it
shows. Everyday build and test commands belong on Workflows; move a command there once it becomes routine.

## Dependencies

*Instructions:* external services, libraries that shape the design, and internal modules that everything imports.
Which parts depend on which, as found.

## Sketches

*Instructions:* rough diagrams made while exploring, newest first, each with a date and the question it was
answering.

## Unknowns

*Instructions:* what is still unexplored or unexplained: directories not yet read, code whose purpose is unclear,
contradictions between findings. Remove an entry when it is answered and record the answer above.
