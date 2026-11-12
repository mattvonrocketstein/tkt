# Lexicon

> **Template.** This page has not been filled in yet. Follow [Agent Home](/wiki?name=agents/Home) and each
> *Instructions* block below, then delete this note and the *Instructions* blocks. Keep the
> *Conventions* section: it governs every later edit to this page.

## Conventions

- **One meaning per term.** If a word is used two ways, say so in the entry and say which one wins.
- **The code's spelling.** Give the identifier the code uses for a term (class, table, flag, field) in backticks,
  so a reader can search for it. Where the code and the docs use different words, list both and mark the one to use.
- **Short entries.** One or two sentences. Link to [System Diagrams](/wiki?name=templates/SystemDiagrams) or a ticket
  instead of explaining at length.
- **Alphabetical** within each section.
- **Use the terms.** Tickets, commits, and other pages use the preferred term from this page. Add a term here
  before relying on it elsewhere.
- **Current:** change an entry in the same commit that changes what it names.

## Domain

*Instructions:* the words the project's users and problem space use, independent of how the code is built.
One row each:

| Term | Meaning | In code |
| --- | --- | --- |
| example | one or two sentences | `Example` |

## System

*Instructions:* names for the parts of this system: components, processes, files, stores, states, and
the like, using the same names as the System Diagrams page. Same table shape as above.

## Abbreviations

*Instructions:* acronyms and short forms found in the code, docs, and tickets, each with its expansion and
a link to its row above when it has one.

| Short | Stands for |
| --- | --- |

## Avoid

*Instructions:* words that are ambiguous, outdated, or wrong here, each with the term to use instead and
why. Include old names still found in the code or history.

| Avoid | Use instead | Why |
| --- | --- | --- |
