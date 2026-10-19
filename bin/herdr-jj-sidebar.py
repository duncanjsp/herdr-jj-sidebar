#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERDR = os.environ.get("HERDR_BIN_PATH") or "herdr"
SOURCE = os.environ.get("HERDR_PLUGIN_ID") or "duncanjsp.herdr-jj-sidebar"
SEP = "\x1f"
BOOKMARK_PRESETS = ("nearest", "name", "change-id")
STATUS_PARTS = ("conflict", "push", "files")
HOST_ICONS = (
    ("github.com", ""),
    ("gitlab", ""),
    ("bitbucket.org", ""),
)
ICON_GIT = ""
ICON_LOCAL = "\U000f0164"


def log(message):
    print(f"herdr-jj-sidebar: {message}", file=sys.stderr)


class JJError(Exception):
    pass


def run(args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=False, stdin=subprocess.DEVNULL, capture_output=True, text=True)


class Config:
    def __init__(self, values):
        self.bookmark = values.get("bookmark", "nearest")
        if self.bookmark not in BOOKMARK_PRESETS:
            log(f"unknown bookmark preset '{self.bookmark}'; using 'nearest'")
            self.bookmark = "nearest"

        self.status = []
        for part in values.get("status", " ".join(STATUS_PARTS)).split():
            if part in STATUS_PARTS:
                self.status.append(part)
            else:
                log(f"unknown status part '{part}'; ignoring it")

        remote_icon = values.get("remote_icon", "false")
        if remote_icon not in ("true", "false"):
            log(f"remote_icon must be true or false, not '{remote_icon}'; using false")
            remote_icon = "false"
        self.remote_icon = remote_icon == "true"

    @classmethod
    def load(cls):
        values = {}
        config_dir = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
        path = Path(config_dir, "config.toml") if config_dir else None
        if path and path.is_file():
            for line in path.read_text().splitlines():
                match = re.match(r'\s*([\w-]+)\s*=\s*(?:"([^"]*)"|([^"\s#]*))', line)
                if match:
                    key, quoted, bare = match.groups()
                    values[key] = quoted if quoted is not None else bare
        return cls(values)


class Repo:
    def __init__(self, root):
        self.root = root

    def jj(self, *args):
        result = run(["jj", "--no-pager", "--ignore-working-copy", "--color=never", "-R", self.root, *args])
        if result.returncode != 0:
            raise JJError(result.stderr.strip())
        return result.stdout

    def rows(self, *args):
        return [line.split(SEP) for line in self.jj(*args).splitlines() if line]

    def log(self, revset, template):
        return self.rows("log", "--no-graph", "-r", revset, "-T", template)

    def count(self, revset):
        return len(self.log(revset, '"x\\n"'))


def find_root(cwd):
    if not cwd or not os.path.isdir(cwd):
        return None
    result = run(["jj", "--no-pager", "--ignore-working-copy", "root"], cwd=cwd)
    return result.stdout.strip() if result.returncode == 0 else None


def nearest_bookmark(repo):
    nearest_names, nearest_distance = "", None
    heads = repo.log(
        "heads(::@ & bookmarks())",
        f'commit_id ++ "{SEP}" ++ local_bookmarks.map(|b| b.name()).join(" ") ++ "\\n"',
    )
    for commit_id, names in heads:
        distance = repo.count(f"{commit_id}..@ ~ (@ & empty())")
        if nearest_distance is None or distance < nearest_distance:
            nearest_names, nearest_distance = names, distance
    return nearest_names, nearest_distance


def push_state(repo, name):
    refs = repo.rows(
        "bookmark",
        "list",
        "--all-remotes",
        f"exact:{name}",
        "-T",
        f'remote ++ "{SEP}" ++ if(self.tracked(), "1") ++ "{SEP}" ++ if(self.present(), "1") ++ "\\n"',
    )
    remote, present = "", ""
    for ref_remote, tracked, ref_present in refs:
        if not ref_remote or ref_remote == "git" or tracked != "1":
            continue
        if not remote or ref_remote == "origin":
            remote, present = ref_remote, ref_present
    if not remote or present != "1":
        return remote, "?"

    local_ref = f"bookmarks(exact:{json.dumps(name)})"
    remote_ref = f"remote_bookmarks(exact:{json.dumps(name)}, exact:{json.dumps(remote)})"
    ahead = repo.count(f"({remote_ref}..{local_ref}) ~ ::trunk()")
    behind = repo.count(f"({local_ref}..{remote_ref}) ~ (::trunk() ~ ::{remote_ref})")
    if ahead and behind:
        return remote, f"⇅{ahead}"
    if ahead:
        return remote, f"↑{ahead}"
    if behind:
        return remote, f"↓{behind}"
    return remote, ""


def remote_icon(repo, push_remote):
    urls = dict(line.split(None, 1) for line in repo.jj("git", "remote", "list").splitlines() if line.strip())
    if push_remote:
        url = urls.get(push_remote, "")
    else:
        url = urls.get("origin") or next(iter(urls.values()), "")
    url = url.strip().lower()
    if not url:
        return ICON_LOCAL
    return next((icon for host, icon in HOST_ICONS if host in url), ICON_GIT)


def compute_tokens(repo, config):
    [[conflict, empty, change_id, files, at_names]] = repo.log(
        "@",
        f'if(conflict, "1") ++ "{SEP}" ++ if(empty, "1") ++ "{SEP}" ++ change_id.shortest(8)'
        f' ++ "{SEP}" ++ self.diff().files().len() ++ "{SEP}" ++ local_bookmarks.map(|b| b.name()).join(" ")',
    )
    names, distance = nearest_bookmark(repo)

    if config.bookmark == "change-id":
        bookmark = at_names or f"@{change_id}"
    elif not names:
        bookmark = f"@{change_id}"
    elif config.bookmark == "name" or distance == 0:
        bookmark = names
    else:
        bookmark = f"{names}·{distance}"

    push_remote, push_text = "", ""
    if names and ("push" in config.status or config.remote_icon):
        push_remote, push_text = push_state(repo, names.split()[0])

    parts = []
    if "conflict" in config.status and conflict == "1":
        parts.append("!")
    if "push" in config.status and push_text:
        parts.append(push_text)
    if "files" in config.status and empty != "1":
        parts.append(f"*{files}")

    if config.remote_icon:
        if not parts and "push" in config.status and push_remote and not push_text:
            parts = ["✓"]
        parts.insert(0, remote_icon(repo, push_remote))

    return bookmark, " ".join(parts)


def report(workspace_id, bookmark, status):
    args = [HERDR, "workspace", "report-metadata", workspace_id, "--source", SOURCE]
    for name, value in (("jjs_bookmark", bookmark), ("jjs_status", status)):
        args += ["--token", f"{name}={value}"] if value else ["--clear-token", name]
    run(args)


def refresh_workspace(workspace_id, cwd, config):
    bookmark, status = "", ""
    root = find_root(cwd)
    if root:
        try:
            bookmark, status = compute_tokens(Repo(root), config)
        except (JJError, ValueError) as error:
            log(f"{workspace_id} ({root}): {error}")
    report(workspace_id, bookmark, status)


def find_workspace_id(value):
    if isinstance(value, dict):
        if isinstance(value.get("workspace_id"), str):
            return value["workspace_id"]
        value = list(value.values())
    if isinstance(value, list):
        return next(filter(None, map(find_workspace_id, value)), None)
    return None


def env_json(name):
    try:
        return json.loads(os.environ.get(name) or "null")
    except json.JSONDecodeError:
        return None


def target_workspace():
    if os.environ.get("HERDR_PLUGIN_EVENT") == "startup":
        return None
    context = env_json("HERDR_PLUGIN_CONTEXT_JSON")
    return (
        find_workspace_id(env_json("HERDR_PLUGIN_EVENT_JSON"))
        or (context.get("workspace_id") if isinstance(context, dict) else None)
        or os.environ.get("HERDR_WORKSPACE_ID")
        or None
    )


def workspace_cwd(workspace, panes):
    tab_panes = [
        pane
        for pane in panes
        if pane.get("workspace_id") == workspace["workspace_id"]
        and pane.get("tab_id") == workspace.get("active_tab_id")
    ]
    focused = [pane for pane in tab_panes if pane.get("focused")]
    return next((pane["cwd"] for pane in focused + tab_panes if pane.get("cwd")), "")


def refresh():
    config = Config.load()
    target = target_workspace()
    result = run([HERDR, "api", "snapshot"])
    if result.returncode != 0:
        log("could not read the herdr snapshot")
        return 1
    try:
        snapshot = json.loads(result.stdout)["result"]["snapshot"]
        workspaces, panes = snapshot["workspaces"], snapshot["panes"]
    except (json.JSONDecodeError, KeyError, TypeError):
        log("could not parse the herdr snapshot")
        return 1

    for workspace in workspaces:
        if target is None or workspace["workspace_id"] == target:
            refresh_workspace(workspace["workspace_id"], workspace_cwd(workspace, panes), config)
    return 0


def main(argv):
    if argv[1:] != ["refresh"]:
        print(f"usage: {Path(argv[0]).name} refresh", file=sys.stderr)
        return 2
    return refresh()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
