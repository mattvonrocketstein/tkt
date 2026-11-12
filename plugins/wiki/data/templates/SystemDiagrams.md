# System Diagrams

> **Template.** This page has not been filled in yet. Follow [Agent Home](/wiki?name=agents/Home) and each
> *Instructions* block below, then delete this note and the *Instructions* blocks. Keep the
> *Conventions* section: it governs every later edit to this page.

## Conventions

- **Dialect:** mermaid for every diagram. Use pikchr only where exact placement carries meaning
  (a physical, network, or memory layout). Never ascii art. See [Formatting Help](/wiki?name=agents/FormattingHelp).
- **Size:** at most about 12 nodes per diagram. When a picture needs more, draw the coarse version and
  split the detail into its own subsection with its own diagram.
- **Names:** label nodes with the names used in the code (module, binary, table, service), so a reader
  can search for them, and use the same name for the same thing in every diagram on the page.
- **Plain syntax:** a mermaid diagram that fails to parse shows as plain text with no error. Use simple
  ids (`api`, `db`), labels in double quotes (`api["HTTP API"]`), no styling, no `click`, no html in labels.
- **Prose:** one to three sentences under each diagram saying what to notice, not a restatement of every arrow.
- **Current:** this page draws the system as it is. Change it in the same commit that changes what it draws.

## Overview

*Instructions:* one `flowchart LR` of the whole system: its major parts as nodes, and arrows labelled
with how they talk (call, http, queue, file, sql). Draw people and outside systems at the edges, using
the `(( ))` circle shape. Follow it with two or three sentences on what the system is for and who uses it.

## Components

*Instructions:* one entry per node in the overview, as a table with these columns:

| Component | Responsibility | Code | Tickets |
| --- | --- | --- | --- |
| `example` | one sentence on what it owns | `src/example/` | [](<hash>) |

Draw a component's insides only when they matter to someone changing it, as a subsection here with its
own small `flowchart`.

## Control flow

*Instructions:* what drives the system and in what order: entry points (commands, requests, jobs,
events), what each one calls, and where control branches, retries, or hands off to another process.
Use a `flowchart TD` with decision nodes (`check{"valid?"}`) for branching inside one process, or a
`sequenceDiagram` when the story is calls passing between processes. One diagram per important entry
point, starting with the most used one.

## Data flow

*Instructions:* how data moves and changes shape for the most important operation: where it enters,
each place it is transformed or stored, and where it leaves. Use a `flowchart LR` with data stores as
cylinders (`db[("orders")]`) and arrows labelled with what moves along them. If the system has a
persistent data model, add an `erDiagram` of the main tables or records, keys and relations only.

## Lifecycle

*Instructions:* if anything has states (a process, a request, a record, a ticket), draw them with
`stateDiagram-v2`: every state, the event or command on each transition, and the start and end states.
One diagram per thing that has states. Delete this section if nothing does.

## Open questions

*Instructions:* a bullet list of what was unclear, contradictory, or planned while drawing the above,
each linked to a ticket. File a ticket for any that has none.
