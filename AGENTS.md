Read CLAUDE.md and DECISIONS.md first; the same rules apply here.

## Branches

One task, one short-lived branch, one pull request. Main moves only by a pull request whose CI has passed.

1. Start from the latest main: `git fetch origin main`, then `git switch -c <short-name> origin/main`. Don't start from an older checkout, a long-lived branch or another task's branch.
2. Work and commit on that branch only, in the main checkout or in a worktree made for it (`git worktree add -b <short-name> .worktrees/<short-name> origin/main`). Don't use long-lived branches for new work.
3. When the task's Check passes and pre-commit is clean, push the branch (`git push -u origin <short-name>`) and open a pull request into main with `gh pr create --base main`. Never push to main, never force-push, never use `--no-verify`, and never move or delete a tag (`prereg-real-treasury` and `run-real-treasury` are records).
4. Wait for the pull request's CI: `gh pr checks --watch`. If a check fails, fix it on the branch, push again and wait again. Never merge a pull request whose CI has not passed, and never bypass it (`--admin`).
5. Merge it with `gh pr merge --rebase --delete-branch`. That keeps main a straight line with no merge commit and deletes the branch on GitHub and here. If the branch is checked out in a worktree, remove the worktree first (`git worktree remove <path>`) and run the merge from the main checkout, since a branch in use cannot be deleted.
6. Then update main: `git fetch origin main`, `git switch main`, `git merge --ff-only origin/main`.

A rebase merge gives the commits new hashes on main, so make any tag a record depends on (a pre-registration, a run) on main's commit after the merge, never on the branch's.

If main moved and the pull request now conflicts, don't force-push the branch: start a new branch from the new main, `git cherry-pick` your commits onto it, and open a new pull request.
