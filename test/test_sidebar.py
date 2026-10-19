import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PLUGIN = TEST_DIR.parent / "bin" / "herdr-jj-sidebar.py"

ICON_GITHUB = ""
ICON_GITLAB = ""
ICON_BITBUCKET = ""
ICON_GIT = ""
ICON_LOCAL = "\U000f0164"


class SidebarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cwd = self.tmp
        self.config_dir = self.tmp / "config"
        self.config_dir.mkdir()
        self.log = self.tmp / "herdr.log"
        self.log.touch()
        jj_config = self.tmp / "jj-config.toml"
        jj_config.write_text('[user]\nname = "Test"\nemail = "test@example.com"\n')

        self.env = {
            key: value
            for key, value in os.environ.items()
            if key
            not in ("HERDR_WORKSPACE_ID", "HERDR_PLUGIN_EVENT", "HERDR_PLUGIN_EVENT_JSON", "HERDR_PLUGIN_CONTEXT_JSON")
        }
        self.env.update(
            JJ_CONFIG=str(jj_config),
            HERDR_BIN_PATH=str(TEST_DIR / "fake_herdr.py"),
            HERDR_PLUGIN_ID="test.sidebar",
            HERDR_PLUGIN_CONFIG_DIR=str(self.config_dir),
            FAKE_HERDR_LOG=str(self.log),
            FAKE_HERDR_SNAPSHOT=str(self.tmp / "snapshot.json"),
        )

    def run_command(self, *args):
        return subprocess.run(args, cwd=self.cwd, env=self.env, capture_output=True, text=True, check=True).stdout

    def jj(self, *args):
        return self.run_command("jj", "--quiet", *args)

    def change_id(self):
        return self.jj("log", "--no-graph", "-r", "@", "-T", "change_id.shortest(8)")

    def new_repo(self, name="repo"):
        self.jj("git", "init", name)
        self.cwd = self.tmp / name

    def bare_remote(self, name):
        path = self.tmp / f"{name}.git"
        self.run_command("git", "init", "--quiet", "--bare", str(path))
        return str(path)

    def add_remote(self, name="origin"):
        self.jj("git", "remote", "add", name, self.bare_remote(name))

    def write(self, name, content=None):
        (self.cwd / name).write_text(f"{content or name}\n")

    def commit_file(self, name, content=None):
        self.write(name, content)
        self.jj("commit", "-m", f"edit {name}")

    def config(self, text):
        (self.config_dir / "config.toml").write_text(text)

    def snapshot(self, **cwds):
        workspaces = [{"workspace_id": id, "active_tab_id": f"{id}:t1"} for id in cwds]
        panes = [
            {"workspace_id": id, "tab_id": f"{id}:t1", "focused": True, "cwd": str(cwd)} for id, cwd in cwds.items()
        ]
        Path(self.env["FAKE_HERDR_SNAPSHOT"]).write_text(
            json.dumps({"result": {"snapshot": {"workspaces": workspaces, "panes": panes}}})
        )

    def refresh(self, **env):
        self.log.write_text("")
        result = subprocess.run(
            [str(PLUGIN), "refresh"], cwd=self.cwd, env={**self.env, **env}, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stderr

    def reported(self):
        return self.log.read_text().splitlines()

    def assert_tokens(self, workspace, bookmark, status):
        expected = f"workspace report-metadata {workspace} --source test.sidebar"
        expected += f" --token jjs_bookmark={bookmark}" if bookmark else " --clear-token jjs_bookmark"
        expected += f" --token jjs_status={status}" if status else " --clear-token jjs_status"
        self.assertIn(expected, self.reported())

    def test_clears_both_tokens_outside_a_jj_repo(self):
        (self.tmp / "plain").mkdir()
        self.snapshot(w1=self.tmp / "plain")
        self.refresh()
        self.assert_tokens("w1", "", "")

    def test_shows_the_change_id_when_no_bookmark_is_reachable(self):
        self.new_repo()
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", f"@{self.change_id()}", "")

    def test_shows_the_bookmark_alone_when_at_is_an_empty_change_on_top_of_it(self):
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main", "?")

    def test_counts_non_empty_changes_above_the_bookmark_and_files_changed_in_at(self):
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.commit_file("b")
        self.write("c")
        self.write("d")
        self.jj("status")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main·2", "? *2")

    def test_shows_the_bookmark_alone_when_it_points_at_at(self):
        self.new_repo()
        self.write("a")
        self.jj("bookmark", "create", "feat", "-r", "@")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "feat", "? *1")

    def test_picks_the_closest_of_several_bookmarked_heads(self):
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "far", "-r", "@-")
        self.commit_file("b")
        self.commit_file("c")
        self.jj("bookmark", "create", "near", "-r", "@-")
        self.jj("new", "far", "near")
        self.commit_file("d")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "near·1", "?")

    def test_lists_every_bookmark_on_the_nearest_change(self):
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "alpha", "beta", "-r", "@-")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "alpha beta", "?")

    def test_shows_nothing_for_a_bookmark_in_sync_with_origin(self):
        self.new_repo()
        self.add_remote()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.jj("git", "push", "--bookmark", "main")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main", "")

    def test_shows_a_question_mark_for_a_bookmark_tracked_on_origin_but_never_pushed(self):
        self.new_repo()
        self.add_remote()
        self.commit_file("a")
        self.jj("bookmark", "create", "feat", "-r", "@-")
        self.jj("bookmark", "track", "feat", "--remote", "origin")
        self.assertIn("not created yet", self.jj("bookmark", "list", "--all-remotes", "feat"))
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "feat", "?")

    def test_shows_changes_ahead_of_origin(self):
        self.new_repo()
        self.add_remote()
        self.commit_file("a")
        self.jj("bookmark", "create", "feat", "-r", "@-")
        self.jj("git", "push", "--bookmark", "feat")
        self.commit_file("b")
        self.commit_file("c")
        self.jj("bookmark", "set", "feat", "-r", "@-")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "feat", "↑2")

    def test_shows_changes_behind_origin(self):
        self.new_repo()
        self.add_remote()
        self.commit_file("a")
        self.commit_file("b")
        self.jj("bookmark", "create", "feat", "-r", "@-")
        self.jj("git", "push", "--bookmark", "feat")
        self.jj("bookmark", "set", "feat", "-r", "@--", "--allow-backwards")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "feat·1", "↓1")

    def test_shows_a_trunk_bookmark_behind_origin(self):
        self.new_repo()
        self.add_remote()
        self.commit_file("a")
        self.commit_file("b")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.jj("git", "push", "--bookmark", "main")
        self.jj("bookmark", "set", "main", "-r", "@--", "--allow-backwards")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main·1", "↓1")

    def test_shows_a_rebased_bookmark_as_needing_a_force_push(self):
        self.new_repo()
        self.add_remote()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.jj("git", "push", "--bookmark", "main")
        self.commit_file("b")
        self.commit_file("c")
        self.jj("bookmark", "create", "feat", "-r", "@-")
        self.jj("git", "push", "--bookmark", "feat")
        self.jj("new", "main")
        self.commit_file("d")
        self.commit_file("e")
        self.jj("bookmark", "set", "main", "-r", "@-")
        self.jj("git", "push", "--bookmark", "main")
        self.jj("rebase", "-b", "feat", "-d", "main")
        self.jj("new", "feat")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "feat", "⇅2")

    def test_prefers_origin_over_other_remotes(self):
        self.new_repo()
        self.add_remote()
        self.add_remote("upstream")
        self.commit_file("a")
        self.jj("bookmark", "create", "feat", "-r", "@-")
        self.jj("git", "push", "--bookmark", "feat", "--remote", "upstream")
        self.jj("bookmark", "track", "feat", "--remote", "origin")
        self.jj("git", "push", "--bookmark", "feat", "--remote", "origin")
        self.commit_file("b")
        self.jj("bookmark", "set", "feat", "-r", "@-")
        self.jj("git", "push", "--bookmark", "feat", "--remote", "upstream")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "feat", "↑1")

    def test_flags_conflicts_in_at(self):
        self.new_repo()
        self.commit_file("a", "base")
        self.jj("new", 'description(substring:"edit a")', "-m", "left")
        self.write("a", "left")
        self.jj("new", 'description(substring:"edit a")', "-m", "right")
        self.write("a", "right")
        self.jj("new", "description(substring:left)", "description(substring:right)")
        self.jj("bookmark", "create", "main", "-r", "root()+")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main·2", "! ?")

    def test_name_preset_drops_the_distance(self):
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.commit_file("b")
        self.config('bookmark = "name"\n')
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main", "?")

    def test_change_id_preset_only_names_bookmarks_on_at(self):
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.config('bookmark = "change-id"\n')
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", f"@{self.change_id()}", "?")

    def test_status_setting_picks_which_parts_to_show(self):
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.write("b")
        self.jj("status")
        self.config('status = "files"\n')
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main·1", "*1")

    def test_an_empty_status_setting_hides_the_status(self):
        self.new_repo()
        self.write("a")
        self.jj("bookmark", "create", "main", "-r", "@")
        self.config('status = ""\n')
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main", "")

    def test_falls_back_to_defaults_for_unknown_settings(self):
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.commit_file("b")
        self.config('bookmark = "bogus"\nstatus = "push nonsense"\n')
        self.snapshot(w1=self.cwd)
        output = self.refresh()
        self.assert_tokens("w1", "main·1", "?")
        self.assertIn("unknown bookmark preset 'bogus'", output)
        self.assertIn("unknown status part 'nonsense'", output)

    def test_refreshes_every_workspace_on_startup(self):
        (self.tmp / "plain").mkdir()
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.snapshot(w1=self.tmp / "plain", w2=self.cwd)
        self.refresh(HERDR_PLUGIN_EVENT="startup", HERDR_WORKSPACE_ID="w1")
        self.assert_tokens("w1", "", "")
        self.assert_tokens("w2", "main", "?")

    def test_refreshes_only_the_workspace_named_by_the_event(self):
        (self.tmp / "plain").mkdir()
        self.new_repo()
        self.snapshot(w1=self.tmp / "plain", w2=self.cwd)
        self.refresh(
            HERDR_PLUGIN_EVENT="pane.agent_status_changed",
            HERDR_PLUGIN_EVENT_JSON='{"pane":{"pane_id":"w2:p1","workspace_id":"w2"}}',
            HERDR_PLUGIN_CONTEXT_JSON='{"workspace_id":"w1"}',
        )
        [line] = self.reported()
        self.assertIn("report-metadata w2 ", line)

    def test_refreshes_the_context_workspace_for_an_action(self):
        (self.tmp / "plain").mkdir()
        self.new_repo()
        self.snapshot(w1=self.tmp / "plain", w2=self.cwd)
        self.refresh(HERDR_PLUGIN_CONTEXT_JSON='{"workspace_id":"w1"}')
        self.assertEqual(len(self.reported()), 1)
        self.assert_tokens("w1", "", "")

    def test_logs_jj_failures_and_clears_the_tokens(self):
        self.new_repo()
        self.snapshot(w1=self.cwd)
        shutil.rmtree(self.cwd / ".jj" / "repo" / "op_heads")
        output = self.refresh()
        self.assert_tokens("w1", "", "")
        self.assertIn("w1 (", output)

    def test_remote_icon_is_off_by_default(self):
        self.new_repo()
        self.jj("git", "remote", "add", "origin", "https://github.com/example/repo.git")
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main", "?")

    def test_remote_icon_shows_the_origin_host(self):
        self.new_repo()
        self.jj("git", "remote", "add", "origin", "git@github.com:example/repo.git")
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.config("remote_icon = true\n")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main", f"{ICON_GITHUB} ?")

    def test_remote_icon_recognises_gitlab_bitbucket_and_other_hosts(self):
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.config('remote_icon = "true"\n')
        self.snapshot(w1=self.cwd)
        self.jj("git", "remote", "add", "origin", "https://gitlab.example.com/team/repo.git")
        for url, icon in (
            ("https://gitlab.example.com/team/repo.git", ICON_GITLAB),
            ("https://bitbucket.org/team/repo.git", ICON_BITBUCKET),
            ("https://git.example.com/repo.git", ICON_GIT),
        ):
            with self.subTest(url=url):
                self.jj("git", "remote", "set-url", "origin", url)
                self.refresh()
                self.assert_tokens("w1", "main", f"{icon} ?")

    def test_remote_icon_shows_local_only_without_remotes(self):
        self.new_repo()
        self.config("remote_icon = true\n")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", f"@{self.change_id()}", ICON_LOCAL)

    def test_remote_icon_follows_the_remote_the_bookmark_is_tracked_on(self):
        self.new_repo()
        self.add_remote("upstream")
        self.jj("git", "remote", "add", "origin", "https://github.com/example/repo.git")
        self.commit_file("a")
        self.jj("bookmark", "create", "feat", "-r", "@-")
        self.jj("git", "push", "--bookmark", "feat", "--remote", "upstream")
        self.config("remote_icon = true\n")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "feat", f"{ICON_GIT} ✓")

    def test_rejects_a_remote_icon_value_that_isnt_a_boolean(self):
        self.new_repo()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.config('remote_icon = "yes"\n')
        self.snapshot(w1=self.cwd)
        output = self.refresh()
        self.assert_tokens("w1", "main", "?")
        self.assertIn("remote_icon must be true or false", output)

    def test_remote_icon_leads_the_other_status_parts(self):
        self.new_repo()
        self.add_remote()
        self.commit_file("a")
        self.jj("bookmark", "create", "feat", "-r", "@-")
        self.jj("git", "push", "--bookmark", "feat")
        self.commit_file("b")
        self.jj("bookmark", "set", "feat", "-r", "@-")
        self.write("c")
        self.jj("status")
        self.config("remote_icon = true\n")
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "feat·1", f"{ICON_GIT} ↑1 *1")

    def test_no_tick_when_push_state_is_hidden(self):
        self.new_repo()
        self.add_remote()
        self.commit_file("a")
        self.jj("bookmark", "create", "main", "-r", "@-")
        self.jj("git", "push", "--bookmark", "main")
        self.config('remote_icon = true\nstatus = "conflict files"\n')
        self.snapshot(w1=self.cwd)
        self.refresh()
        self.assert_tokens("w1", "main", ICON_GIT)


if __name__ == "__main__":
    unittest.main()
