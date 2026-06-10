---
agent:
  default_effort: medium
  max_turns: 20
hooks:
  after_create: |
    if [ -f package.json ]; then
      npm install
    elif [ -f pyproject.toml ]; then
      if command -v pdm &>/dev/null; then
        pdm install
      elif command -v pip &>/dev/null; then
        pip install -e .
      fi
    fi
---

# Development Workflow — mandate-finder

**Repo:** github.com/Aimino-Tech/mandate-finder
**Framework:** Aimino orchestration project
**Standards:** Conventional Commits, GitHub Flow, CI/CD via GitHub Actions

---

## Getting Started

```bash
# Clone the repository
git clone git@github.com:Aimino-Tech/mandate-finder.git
cd mandate-finder
```

---

## Development Workflow

### 1. Branch Naming

Use **kebab-case** with category prefixes:

| Prefix     | Purpose          | Branch From | Merge To |
|------------|------------------|-------------|----------|
| `feature/` | New features     | `main`      | `main`   |
| `fix/`     | Bug fixes        | `main`      | `main`   |
| `hotfix/`  | Critical fixes   | `main`      | `main`   |
| `chore/`   | Maintenance      | `main`      | `main`   |
| `docs/`    | Documentation    | `main`      | `main`   |

Examples:
```
feature/mandate-scraping
fix/parsing-timeout
hotfix/security-patch
docs/api-endpoints
```

### 2. Development Cycle

1. **Create** a branch from `main` with an appropriate prefix
2. **Develop** with regular, atomic commits
3. **Rebase** on latest `main` before opening a PR
4. **Open PR** targeting `main`
5. **Address review** feedback
6. **Merge** via squash merge
7. **Delete** the branch after merge

### 3. Commit Conventions

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short description>

<optional body>
<optional footer>
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `style`, `perf`

Examples:
```
feat: add mandate search by CPV code
fix: resolve timeout on large result sets
docs: update API endpoint documentation
```

---

## Build & Test

```bash
# Install dependencies
npm install                       # Node/TypeScript
# or
pip install -e .[dev]             # Python

# Run linting
npm run lint                      # Node/TypeScript (biome)
# or
ruff check .                      # Python

# Run type checking
npm run typecheck                 # Node/TypeScript (tsc --noEmit)
# or
mypy .                            # Python

# Run tests
npm test                          # Node/TypeScript (vitest/jest)
# or
python -m pytest                  # Python

# Build
npm run build                     # Node/TypeScript
# or
pip install -e .                  # Python
```

> **Note:** These commands are the convention. Update this section with the actual toolchain once the project is scaffolded.

---

## Linting & Formatting

This project enforces code quality through automated linting and formatting.

- **Linting rules** are defined in the project's linter configuration
- **Formatting** is automatically checked in CI
- Run linting locally before committing to avoid CI failures

Recommended toolchain:

| Language     | Linter          | Formatter       | Type Checker |
|--------------|-----------------|-----------------|--------------|
| TypeScript   | `biome check`   | `biome format`  | `tsc`        |
| Python       | `ruff check`    | `ruff format`   | `mypy`       |

---

## Pull Request Process

1. Ensure all CI checks pass (lint → typecheck → test → build)
2. Request review from at least one maintainer
3. Address all reviewer comments
4. Keep PRs focused — one feature/fix per PR
5. Update PR description with context and testing evidence
6. Squash-merge into `main` once approved
7. Delete the feature branch after merge

---

## CI/CD

- **CI** runs on every PR: lint → typecheck → test → build
- **Merge requirements**: all CI checks must pass, at least one review approval required
- **Branch protection**: direct pushes to `main` are blocked — all changes must go through PRs
- **CI Provider**: GitHub Actions (`.github/workflows/`)
- **Artifacts**: Built packages are published on tagged releases

---

## Project Structure (convention)

```
mandate-finder/
├── src/                  # Source code
├── tests/                # Test files
├── .github/workflows/    # CI/CD pipelines
├── package.json          # Node/TypeScript (if applicable)
├── pyproject.toml        # Python (if applicable)
└── README.md
```

> Update this section once the project tech stack and structure are finalized.
