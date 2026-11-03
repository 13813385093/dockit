# doc-kit

> A documentation toolchain for the AI era: a desktop App + a project-bundled CLI + 8 AI skills, jointly maintaining the `ProjectSpec/` layered documentation and the topic / dev-loop workflow.

- [中文](README.md)

---

## Table of Contents

1. [How to Build](#1-how-to-build)
2. [Initialize a New Project with init](#2-initialize-a-new-project-with-init)
3. [Upgrade an Initialized Project to a New Version](#3-upgrade-an-initialized-project-to-a-new-version)
4. [Skills Overview](#4-skills-overview)
5. [App Overview](#5-app-overview)

---

## 1. How to Build

### 1.1 Prerequisites

```bash
pip install -r requirements.txt        # runtime deps (PySide6 / qt-material / PyYAML / Markdown)
pip install -r requirements-dev.txt    # build deps (pyinstaller)
```

### 1.2 Package

The build spec is at `src/app/doc_kit.spec`; it bundles `templates/`, `resources/`, and `skills/` into the release:

```bash
pyinstaller src/app/doc_kit.spec
```

The output is under `dist/doc_kit/`, with the executable named `doc_kit` (`doc_kit.exe` on Windows).

---

## 2. Initialize a New Project with init

`init` generates the full documentation skeleton and toolchain copy at the target project root.

### 2.1 Command

```bash
doc-kit init <project-root> [--name <project-name>]
```

### 2.2 What gets created

| Path | Purpose |
|---|---|
| `ProjectSpec/` | 7 top-level document skeletons (business-context, technical-framework, non-functional-constraints, global-policies, inter-module-contracts, stakeholders, release-policy) |
| `.doc-kit/config.yaml` | project name and creation time |
| `.doc-kit/registry.yaml` | registry of 15 document types (three levels: top / module / feature) |
| `.doc-kit/templates/` | Markdown templates for each document type |
| `.doc-kit/cli/` | toolchain CLI (`cli.py` + helper modules), the unified execution backend for skills |
| `.doc-kit/skills/` | copies of the 8 skills' `SKILL.md` + the `guidance/` capability library (to be linked into the agent's skills directory) |
| `.doc-kit/index.json` | document index (path, type, dependencies) |
| `.doc-kit/toolchain.json` | toolchain version and sha256 manifest of each copy, used for consistency checks |

### 2.3 Make the skills available to your AI agent

`init` places skill copies in the project's `.doc-kit/skills/`, but most agents only scan their own fixed skills directory. **Symlinks are recommended over copies**: link each skill directory under `.doc-kit/skills/` into the agent's skills directory, so that after a project upgrade the links automatically point to the new versions—no reinstall needed.

#### Option 1 (recommended): let the agent create the symlinks itself

Just tell the AI:

> Please install all `spec-*` directories under the current project's `.doc-kit/skills/` into your own skills directory using symlinks.

The agent will:
1. locate its own skills directory (e.g. `~/.trae-cn/skills/`, `~/.claude/skills/`, `~/.reasonix/skills/`, etc.);
2. create symlinks (not copies) for each `.doc-kit/skills/spec-*`;
3. skip any existing entry with the same name to avoid overwriting custom skills.

The benefit of symlinks is that after a project-side `doc-kit init` upgrade, the agent automatically gets the new skills without running the install again.

#### Option 2: manual symlinks (TRAE example)

```bash
AGENT_SKILLS_DIR=~/.trae-cn/skills          # replace with your agent's skills dir
mkdir -p "$AGENT_SKILLS_DIR"
for skill in <project-root>/.doc-kit/skills/spec-*; do
  name=$(basename "$skill")
  ln -sfn "$skill" "$AGENT_SKILLS_DIR/$name"
done
```

> The `-n` in `ln -sfn` prevents the link from being created inside an existing directory. If your agent does not support symlinks (some Windows scenarios), fall back to the copy method via `doc-kit install-skills`.

#### Option 3: copy install (not recommended, must be redone on every upgrade)

```bash
doc-kit install-skills <agent-skills-dir>
```

The copy method must be re-run on every upgrade and can lead to a mismatch where the project side is upgraded but the agent side still uses the old version. Use it only when symlinks are not available.

---

## 3. Upgrade an Initialized Project to a New Version

The toolchain uses a "snapshot copy" model: `init` copies the CLI / skills / templates of the current version into the project, after which the repository and the project evolve independently. To upgrade, **delete the project's `.doc-kit/` first, then re-run init**, so the CLI rebuilds all resources from the existing `ProjectSpec/`.

### 3.1 Check whether an upgrade is needed

```bash
python .doc-kit/cli/cli.py tool status
```

The output tells you the current CLI version vs. the recorded project version, how many versions behind you are, what changed in between, and whether any copies were modified or are missing.

### 3.2 Perform the upgrade

```bash
# 1. delete the old toolchain copies
rm -rf <project-root>/.doc-kit

# 2. re-initialize (rebuilds .doc-kit/ from the existing ProjectSpec/, does not touch ProjectSpec/)
doc-kit init <project-root>

# 3. rebuild the document index from ProjectSpec/
#    (init only indexes newly created docs; existing docs need a reindex)
python <project-root>/.doc-kit/cli/cli.py doc reindex

# 4. refresh the agent-side skills
doc-kit install-skills <agent-skills-dir>
```

After that, restart the current topic / dev-loop workflow.

---

## 4. Skills Overview

There are 8 skills in total, split into a "topic side" and a "dev-execution side". All operate on project state through `.doc-kit/cli/cli.py`.

### Topic side (discussion → decisions → persistence)

| Skill | Purpose |
|---|---|
| **spec-start** | The single entry point for topics. On a new conversation, resume the last topic (restate pending agenda items), or create one after confirming the agenda when there is no active topic. |
| **spec-pause** | Temporary checkpoint: persist the current discussion as meeting notes (writes `SessionSpec/` only; does not write `ProjectSpec/` and does not change status). |
| **spec-close** | Wrap-up. Keep results → persist notes → map decisions to their document homes → write into `ProjectSpec/` after review → archive; or abandon (record the reason and archive directly, no docs written). |
| **spec-archive** | Archive fallback: clean up leftovers that were closed/abandoned but not archived (the normal flow is already inlined at the end of spec-close). |

### Dev-execution side (implementation → verification → commit)

| Skill | Purpose |
|---|---|
| **spec-dev-loop** | Faithfully implement a feature from the design in `ProjectSpec/`: read design → skeletonize (user confirms signatures) → delegate implementation and verify → unit & acceptance tests → align and wrap up. `ProjectSpec/` is read-only throughout. |
| **spec-code-review** | Pre-PR design-document consistency check: from the git review-anchor scope, compare code and docs side by side, judge each difference, and write a review report. |
| **spec-code-smell** | Code-smell scanning (duplicated code, long parameter lists, mysterious names, etc.), with quick / deep modes and evidence plus false-positive rationale. |
| **spec-smart-git** | Smart commits: split working-tree changes into semantically independent commits by feat/fix/docs/refactor/chore labels and execute them one by one. |

---

## 5. App Overview

The doc-kit desktop App (PySide6) is the **visual management interface** for the project documentation system, sharing the same `ProjectSpec/` data with the CLI and skills.

### Main areas (document tree on the left + tabs on the right)

| Tab | Function |
|---|---|
| **Dashboard** | project document overview, module/feature distribution, quick entry |
| **md Editor** | WYSIWYG Markdown editing, with frontmatter (doc_type / version / status / depends_on) and body maintained in separate panes |
| **JSON Editor** | directly edit a document's frontmatter fields, useful for bulk metadata changes |
| **Dependency Graph** | draws inter-document dependencies based on `depends_on`, supports reverse-dependency queries |
| **Lifecycle** | manage the active → deprecated → archived state transition of documents, batch archive |
| **Settings** | project configuration, toolchain version info |

### Launch

```bash
doc-kit [project-root]      # optional: load a specific project directly
```

The App and the CLI share core engines such as `IndexManager` and `FrontmatterParser` (`src/app/engine/`); changes on either side are synchronized to the other through `index.json`.
