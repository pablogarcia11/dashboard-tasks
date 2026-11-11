# Contributing

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org/), the same convention as the other 1MillionBot repos (`airisk-api`, `airiskmanagement`, `migration-boilerplate-api`…).

```
<type>(<optional scope>): <description>
```

- **English**, lowercase, imperative mood ("add", "fix", "show"), no trailing period.
- One line describing the change from the user's point of view. Add a body only when the *why* is not obvious.
- Types: `feat` (new behaviour), `fix` (bug fix), `refactor` (no behaviour change), `perf`, `style` (formatting or visual tweaks), `docs`, `test`, `chore` (tooling, config, dependencies).
- Optional scope for the area touched, e.g. `feat(notion): …`, `fix(git): …`.
- When Claude co-authors a commit, end the message with its `Co-Authored-By:` trailer.

Examples:

```
feat: collect local git commits and uncommitted work into sqlite
fix(git): keep worktree commits from being counted twice
docs: add commit message conventions
```

## Secrets

Never commit `.env`, `secrets/` or `db/*.db` (already in `.gitignore`). Check `git status` before committing.
