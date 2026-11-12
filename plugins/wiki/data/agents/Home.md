# Agent Home

Start here. This page is maintained by `tkt` and rewritten by `tkt init`, so do not edit it: put project
knowledge in the pages it links to.

## Pages

| Page | What it holds | Kept current by |
| --- | --- | --- |
| [System Diagrams](/wiki?name=templates/SystemDiagrams) | how the system is built: parts, control flow, data flow, lifecycles | whoever changes what it draws |
| [Mapping](/wiki?name=templates/Mapping) | working notes from exploring the code, rough and partly unverified, feeding System Diagrams | anyone exploring; promote what settles |
| [Lexicon](/wiki?name=templates/Lexicon) | the project's vocabulary: domain and system terms, abbreviations, words to avoid | whoever introduces or renames a term |
| [Style](/wiki?name=templates/Style) | how code, tests, commits, and prose are written here | whoever changes the practice or its tools |
| [Workflows](/wiki?name=templates/Workflows) | the commands for setup, build, run, test, release, and recovery | whoever changes a command |
| [Formatting Help](/uv/help/formatting.md) | markdown, links, highlighting, and diagrams on this tracker | `tkt`; read only |
| [Wiki Pages](/rptview?title=Wiki+Pages) | every wiki page, filterable by prefix: [agents](/rptview?title=Wiki+Pages#prefix=agents), [templates](/rptview?title=Wiki+Pages#prefix=templates) | |

## Standing rules

- **Read before you change.** Read the pages above that touch your task before starting it.
- **Keep pages current.** Update a page in the same change that makes it wrong. A stale page is worse
  than none.
- **Sources, in order of trust:** the code, then the docs and these pages, then tickets. Where they
  disagree, follow the code and file a ticket about the mismatch.
- **Describe what exists.** Planned work lives in tickets, not in these pages.
- **Link, don't repeat.** Link tickets as `[](<hash>)` and other pages by name instead of copying them.
  Name code paths in backticks.
- **Keep the headings.** A page's section headings are its structure; keep them even when a section is
  short.

## Template pages

A page that opens with a **Template** note has not been filled in yet. Fill it in following its
*Instructions* blocks, then delete that note and those blocks. Keep everything else on the page,
including its *Conventions* section: those rules hold for every later edit.
