# vinny worktree setup

## `link_worktree_node_modules.py` — a `node_modules` in seconds

A fresh vinny worktree needs `node_modules` before `tsc` or `jest` will run, and `yarn install`
takes minutes (plus a native redis build that fails harmlessly). This builds one from a worktree
that already has it, in about two seconds.

```bash
./link_worktree_node_modules.py ~/src/vinny-worktrees/my-branch
./link_worktree_node_modules.py ~/src/vinny-worktrees/my-branch --donor ~/src/vinny-worktrees/other
./link_worktree_node_modules.py ~/src/vinny-worktrees/my-branch --check
```

### Why not just symlink `node_modules`

Because it silently resolves your code to someone else's branch.

Yarn installs each workspace package as a **relative** symlink:

```
node_modules/@vinny/data-collection-types -> ../../libs/data-collection-types
```

If `node_modules` is itself a symlink to another worktree, `../..` is resolved through that
worktree's real path, so `@vinny/*` lands on the **donor's** `libs/` — its branch, its edits. With
two people changing `libs/` packages, both typecheck and test against the wrong tree and nothing
warns. It shows up as "module has no exported member X" for a symbol you just wrote.

So this script makes `node_modules` a real directory and links per entry:

| entry | link |
|---|---|
| third-party package | symlink to the donor's copy — shared, nobody edits them |
| workspace package | the **same relative target**, recreated locally, so it resolves in *your* worktree |

Workspace packages are detected by their symlink target rather than an allowlist, so every
workspace root (`apps/*`, `libs/*`, `libs/mongo-schemas/*`, `libs/data-layer/*`, `testing/*`,
`tools/*`) is handled without listing them.

### `--check` answers two questions

Two different things go wrong, and only one of them is about links.

**Where does `@vinny/*` point.** Worth running whenever a typecheck reports a symbol you know you
just wrote:

```
INFO data-collection-types -> /Users/you/src/vinny-worktrees/my-branch/libs/data-collection-types OK
```

A `WRONG WORKTREE` line means you are compiling the donor's code.

**Is anything the branch declares simply absent.** This is lockfile drift: the donor installed
before your branch — or `main` — added a dependency, so the package is not there at all. It
surfaces a long way from the cause. `eslint-plugin-local-rules` is the one that bites in practice,
because eslint fails resolving the plugin before it lints anything, which reads like a broken
eslint config.

Measured against a donor whose install predates current `main`: `origin/main` declares 238 root
dependencies, 6 of which were missing — `eslint-plugin-local-rules`, `amqplib`,
`amqp-connection-manager`, `@node-oauth/oauth2-server`, `@types/cookie`, `portless`. So:

```
ERROR 6 declared dependencies are absent — the donor's install predates them, so run a real
      `yarn install` in this worktree: @node-oauth/oauth2-server, @types/cookie, amqplib, ...
```

A branch off a `main` that has moved needs a real `yarn install`. This script is for worktrees
sharing a base with the donor.

### Caveat

The donor's `node_modules` has to stay put — the third-party links point into it. Rebuild after the
donor runs `yarn install` and changes a dependency version.
