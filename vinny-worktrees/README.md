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

`--check` verifies the result and is worth running if a typecheck reports a symbol you know exists:

```
INFO data-collection-types -> /Users/you/src/vinny-worktrees/my-branch/libs/data-collection-types OK
```

A `WRONG WORKTREE` line there means you are looking at the donor's code.

### Caveat

The donor's `node_modules` has to stay put — the third-party links point into it. Rebuild after the
donor runs `yarn install` and changes a dependency version.
