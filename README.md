# herdr-jj-sidebar

A [Herdr](https://herdr.dev) plugin that shows where you are in a
[Jujutsu](https://jj-vcs.dev) repo, and the state of that work, in Herdr's
Spaces sidebar.

```
● chezmoi
  djs/sidebar·2
  ↑1 *3
```

## Requirements

- Herdr 0.9.5 or newer
- jj 0.46.0 or newer
- Python 3.9 or newer
- macOS or Linux

## Install

```sh
herdr plugin install duncanjsp/herdr-jj-sidebar
```

Then add the plugin's tokens to the Spaces rows in `~/.config/herdr/config.toml`
and run `herdr server reload-config`:

```toml
[ui.sidebar.spaces]
rows = [
  ["state_icon", "workspace"],
  ["$jjs_bookmark"],
  ["$jjs_status"],
]
```

## What it shows

### `$jjs_bookmark`

The nearest local bookmark at or below `@`, followed by how many non-empty
changes sit above it. An empty `@` on top of the bookmark doesn't count.

| Shown | Meaning |
|---|---|
| `main` | `@` is on `main`, or is an empty change directly on top of it |
| `main·2` | two changes above `main` |
| `alpha beta` | both bookmarks point at the nearest change |
| `@xwkqnsls` | no bookmark is reachable from `@`; this is its change ID |

When `@` descends from several bookmarked changes, the closest one wins.

### `$jjs_status`

Up to three components in this order:

| Shown | Meaning |
|---|---|
| `!` | `@` has conflicts |
| `?` | the nearest bookmark isn't on a remote yet |
| `↑2` | the bookmark has 2 changes its remote doesn't |
| `↓1` | the remote has 1 change the bookmark doesn't |
| `⇅3` | both: usually 3 changes rebased since the last push, so it needs a force-push |
| `*3` | `@` changes 3 files |

The bookmark is compared with `origin` when it's tracked there, otherwise with
the first remote it's tracked on. Nothing is shown when it's in sync. Changes
already on `trunk()` aren't counted, so rebasing a pushed bookmark onto a newer
`main` shows your own changes, not everything that landed on `main`.

The plugin reads jj with `--ignore-working-copy`, so it never snapshots your
working copy behind your back. The file count reflects the last time jj
snapshotted it, which is any jj command you or an agent run.

Folders that aren't jj repos show nothing. If jj fails, the tokens are
cleared and the error goes to the plugin log (`herdr plugin log list --plugin
duncanjsp.herdr-jj-sidebar`).

## Settings

Everything is optional. Create `config.toml` in the directory printed by
`herdr plugin config-dir duncanjsp.herdr-jj-sidebar`:

```toml
bookmark = "nearest"
status = "conflict push files"
remote_icon = false
```

`bookmark` is one of:

- `nearest` (default): the nearest bookmark and its distance, e.g. `main·2`
- `name`: the nearest bookmark without the distance
- `change-id`: bookmarks on `@` itself, otherwise `@`'s change ID

`status` lists which parts to show, from `conflict`, `push` and `files`. The
display order is always the one above. Use `status = ""` to hide the status.

`remote_icon = true` starts the status with a [Nerd Font](https://www.nerdfonts.com)
icon for where the repo is hosted: GitHub, GitLab, Bitbucket, a generic git
icon for any other host, or a crossed-out cloud when the repo has no remotes.
The remote is the one the bookmark is compared with, otherwise `origin`,
otherwise the first remote. With the icon on, a bookmark that's in sync with
nothing else to report shows `✓`, so the status line is never just an icon.

Only flat `key = value` lines are read.

## Colours

Herdr can colour the status by its contents. For example:

```toml
[ui.sidebar.spaces]
rows = [
  ["state_icon", "workspace"],
  [{ token = "$jjs_bookmark", dim = true }],
  [{ token = "$jjs_status", rules = [
    { contains = "!", fg = "#f38ba8", bold = true },
    { contains = "?", fg = "#fab387" },
    { contains = "⇅", fg = "#f5c2e7" },
    { contains = "↓", fg = "#f5c2e7" },
    { contains = "↑", fg = "#74c7ec" },
    { contains = "✓", fg = "#a6e3a1" },
  ] }],
]
```

Dimming the bookmark keeps the workspace name reading as the heading. The
first matching rule colours the whole status. Empty rows are hidden, so the
status row disappears when there's nothing to show.

## Refreshing

The sidebar refreshes when Herdr starts, when you create or switch
workspaces, tabs or panes, and when an agent's status changes, which is
usually right after it has run jj.

To also refresh after every command in your shell, add this to `~/.zshrc`:

```zsh
_herdr_jj_sidebar() {
  [[ -n $HERDR_WORKSPACE_ID ]] || return
  herdr plugin action invoke refresh --plugin duncanjsp.herdr-jj-sidebar &>/dev/null &!
}
autoload -Uz add-zsh-hook
add-zsh-hook precmd _herdr_jj_sidebar
```

You can refresh by hand with the same `herdr plugin action invoke` command.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
