# Workflows

> **Template.** This page has not been filled in yet. Follow [Agent Home](/wiki?name=agents/Home) and each
> *Instructions* block below, then delete this note and the *Instructions* blocks. Keep the
> *Conventions* section: it governs every later edit to this page.

## Conventions

- **Commands, not prose.** Each task is the exact command to run, in a `bash` fence, from the repository root
  unless it says otherwise, with one line on what it does and how long it takes when that is more than a minute.
- **Verified.** Every command here has been run and works. Mark one you could not run with *(unverified)* and why.
- **Prefer the project's wrappers.** When a `Makefile`, script, or task runner covers a task, give that, not the
  raw tool command it calls.
- **Rules live elsewhere.** Formatting and lint rules belong on [Style](/wiki?name=templates/Style); this page only says
  how to run the tools.
- **Current:** change a command in the same commit that changes it.

## Setup

*Instructions:* from a fresh clone to a working build: prerequisites with versions, install steps, and any
env vars or local config files to create (name the example file to copy, never real secrets).

## Build and run

*Instructions:* how to build, how to run the system locally, and how to tell it is up (a url, a port, a
log line).

## Test

*Instructions:* how to run all tests, one file, and one test by name, plus anything slow or needing a
service, and how to skip it.

## Check before committing

*Instructions:* the commands to run before a commit (format, lint, type check, tests), in order, ideally one
command that runs them all.

## Release

*Instructions:* how a version is cut and shipped, or "not applicable" with a reason.

## Recover

*Instructions:* how to get back to a clean state when something breaks: clean build outputs, reset local
data, rebuild caches, stop stray processes. Say what each one destroys.
