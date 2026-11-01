Read CLAUDE.md and DECISIONS.md first; the same rules apply here.

## Branches

One task, one short-lived branch, and main moves only by fast-forward.

1. Start from the latest main: `git fetch origin main`, then `git switch -c <short-name> origin/main`. Don't start from an older checkout, a long-lived branch or another task's branch.
2. Work and commit on that branch only. Don't use worktrees or long-lived branches for new work.
3. When the task's Check passes and pre-commit is clean, fast-forward main: `git push origin <short-name>:main`. The push must be a fast-forward. Never force-push, never make a merge commit on main, never use `--no-verify`, and never move or delete a tag (`prereg-real-treasury` and `run-real-treasury` are records).
4. If the push is refused because main moved, run `git fetch origin main` and `git rebase origin/main`. That moves only your own unpushed commits, so no published history is rewritten. Run the Check again, then push.
5. Then delete the branch: `git switch main`, `git merge --ff-only origin/main`, `git branch -d <short-name>`, and `git push origin --delete <short-name>` if it was ever pushed.
