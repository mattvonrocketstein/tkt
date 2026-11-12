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

### When invoked as /tkt wiki

| Arguments | Do this |
| --- | --- |
| `wiki map [focus]`, `map [focus]` | Work on the project's `Mapping` page; see *Map and diagram* below. |
| `wiki system [focus]`, `diagram [focus]` | Work on the project's `SystemDiagrams` page; see *Map and diagram* below. |
| `wiki ...` (anything else) | Treat it as a free-form instruction about the wiki. Read `agents/Home` first. |

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
