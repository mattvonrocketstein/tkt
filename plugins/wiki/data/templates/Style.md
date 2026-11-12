# Style

> **Template.** This page has not been filled in yet. Follow [Agent Home](/wiki?name=agents/Home) and each
> *Instructions* block below, then delete this note and the *Instructions* blocks. Keep the
> *Conventions* section: it governs every later edit to this page.

## Conventions

- **Describe the house style as practiced.** Derive rules from the code, config, and history, not from general
  best practice. Where the codebase is inconsistent, say so and name the side new work follows.
- **Tools first.** When a formatter, linter, or config file enforces a rule, name the tool, its config file, and
  the command that runs it, and do not restate its rules here.
- **Rules with examples.** Each rule is one line, with a short do / don't example where the difference is not obvious.
- **Only what a newcomer would get wrong.** Skip rules that every competent contributor already follows.
- **Words** follow [Lexicon](/wiki?name=templates/Lexicon).
- **Current:** change a rule in the same commit that changes the practice or the tool config.

## Tooling

*Instructions:* formatters, linters, type checkers, and pre-commit hooks: one row each.

| Tool | Config | Command | Enforced in CI |
| --- | --- | --- | --- |
| example | `path/to/config` | `make lint` | yes |

## Code

*Instructions:* conventions the tools do not enforce: naming, file and module layout, error handling,
logging, comments, dependencies, and anything the project does differently from its language's norms.

## Tests

*Instructions:* where tests live, how they are named, the command to run them, and what a change is expected
to come with (a regression test per bug fix, for example).

## Commits and reviews

*Instructions:* branch names, commit message form, what goes in one commit, and how changes reach the main
branch. Quote two real commit messages that show the form.

## Writing

*Instructions:* voice and format for docs, comments, tickets, and these pages: tone, tense, heading case,
line length, and how much to explain.
