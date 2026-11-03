## 1. Why do we need a new project documentation system?

### 1.1 Pain points of traditional documentation systems

In traditional software development, documentation systems face the following major challenges:

**Fragmented information**

- Requirements docs, design docs, and test docs are independent of each other
- There is a conceptual gap between business requirements and technical implementation
- Documentation updates lag behind code changes

**Shared difficulties in information retrieval and machine comprehension**

Traditional natural-language documentation creates obstacles for both humans and machines in how information is organized and expressed:

- Traditional natural-language docs are **hard for both humans and AI to locate key information quickly** — manual search takes time, and machines cannot parse them directly
- Lack of structured expression — information is buried in large blocks of text, making **manual review rely on experience to hunt for details while code generation relies on guesswork and patchwork**
- Blurry expression of boundary constraints — key constraints like [MUST]/[SHOULD] are mixed into narrative text, making them **easy to miss in manual reviews and leaving AI without clear rule boundaries during generation**

**Low collaboration efficiency**

- Writing docs takes time; maintenance cost is high
- Docs become outdated quickly; update frequency is low
- Decision-making process is not traceable
- Docs lack cross-references, so descriptions can easily become inconsistent

### 1.2 Value of the new documentation system

**Improved development efficiency (human + AI)**

- Provides structured spec descriptions that both humans and AI can quickly locate (requirements are carried jointly by project goals in `business-context.md` and feature specs in `feature-design.md`; the system does not have a separate "requirements document")
- Clear boundary constraints — human reviewers have a basis to work from; AI generation follows clear rules
- Enables a complete traceable closed loop from requirements (project goals / feature specs) to tests

**Strengthened engineering discipline**

- Built-in test-driven flow
- Ensures decision traceability
- Uses spec-style documents (Spec, i.e., all document types in this system, see §3.6) as the Single Source of Truth; code is a derivative artifact of the Spec and evolves in sync with it (Spec-first), avoiding the "documentation update lags behind code changes" problem

**Improved team collaboration efficiency**

- Unified documentation paradigm reduces communication cost
- Layered structure supports progressive knowledge disclosure
- Template-driven design improves indexing efficiency

### 1.3 Quick look at human usage scenarios

The design features described above are not only for AI-assisted development — they play a critical role in pure manual development scenarios as well:

| Scenario | Documents used | Value |
|----------|---------------|-------|
| New hire onboarding | Project charter (top-level doc collection) + one complete module | Understand the full business picture and technical architecture within 1 hour |
| Code review | `feature-design.md` + `decision-log.md` | Verify that implementation matches design intent; understand selection rationale |
| Architecture review | `architecture.md` + `inter-module-contracts.md` | Check the reasonableness of module boundaries and interface design |
| Change impact assessment | Look up `depends_on` reverse chain | Know who will be affected before modifying a document |
| Test review | `unit-tests.md` + `acceptance-tests.md` | Confirm acceptance scenarios are fully covered |
| Tech debt triage | Look up docs with `status=deprecated` | Identify outdated docs that need updating or cleanup |

> **Design principle**: All design features of this documentation system start from **human-machine co-readability** — clear and readable for humans, structured and parsable for machines. We do not sacrifice human reading experience to accommodate machines, nor do we give up machine processability to serve humans.

### 1.4 Scope of applicability

**Primary audience of this system**: Individuals and organizations that have decided or are seriously evaluating fully embracing AI Coding. If you believe AI will take on an increasing share of development work, this system is designed for that kind of production relationship.

**This system is suitable for:**
- Pure software domains, or software-dominant systems (hardware parts are encapsulated via `integration.md`)
- AI-assisted coding or pure manual development as the primary production method
- Teams of 1-50 people, without multi-level approval stage gates
- Teams that already use Git and Markdown collaboratively, and accept semantic versioning and modular splitting conventions

**This system is NOT suitable for:**
- Hardware-software products that require strict IPD stage review deliverables (e.g. MRD/CDCP/ADCP)
- Organizations that require Word/Excel/PDF as deliverables instead of Markdown
- Teams without version management fundamentals (Git), or where documentation ownership is completely independent of the codebase

## 2. Design philosophy of the documentation system

### 2.1 Longitudinal modular architecture

Traditional documentation systems often use horizontal layered designs, separating requirements, design, implementation, and testing into independent documentation layers. Although this design is logically clear, it presents obvious context-management challenges in practice — **both humans and AI need to switch across multiple layers of docs to piece together complete context**, leading to:

- **Context bloat**: The more layers there are, the more documents need to be read simultaneously, overwhelming the human brain and working memory
- **Information redundancy**: The same piece of information repeats across different layers, **wasting time when humans re-read, and confusing AI about which version is latest**
- **Difficult retrieval**: Humans waste time hunting for specific information across multi-level directories; AI also struggles to quickly locate the minimal set of documents relevant to the current task
- **Inconsistencies across layers**: Different layers of docs are typically owned and maintained independently by different teams, making content updates hard to sync and causing factual contradictions

This system adopts a **longitudinal modular** design approach:

- **Longitudinal division**: Docs are organized by business module; each **module** is self-contained with complete architecture design, domain model, and feature specs
- **Top-level sharing**: Shared information like project background and technical framework is centralized at the top level, loaded once and reused everywhere
- **Progressive disclosure (load on demand)**: Humans can read layer by layer from "top-level → module → feature"; AI can load the minimal context set on demand (see §2.2)
- **Toolchain**: Unified frontmatter and [MUST]/[SHOULD] constraint markers for automated validation and assisted writing via scripts/CLI tools; tools are planned to automatically handle `last_updated` updates and `depends_on` derivation (see §3.5.2 field table)

### 2.2 Core design principles

**Human & AI Readable**

- **Structured expression** — humans quickly locate key content through clear information hierarchy; machines accurately parse through standardized frontmatter and format
- **Clear constraint boundaries** — [MUST]/[SHOULD]/[MAY] **give human reviewers a basis to work from, reducing disputes**, while constraining AI-generated products to stay within scope
- **Clear What / Why / verification descriptions** — the feature layer is organized as What (behavioral spec in `feature-design.md`) + Why (decision rationale in `decision-log.md`) + verification (test cases); HOW (implementation) belongs to the `architecture.md` module layer and is not described at the feature layer. During code review, correctness is judged against design intent; code generated by AI after understanding design premises better matches expectations

**Engineering practice integration**

- Integrates three methodologies: DDD (Domain-Driven), BDD (Behavior-Driven), TDD (Test-Driven), with the correspondence: DDD → `domain-model.md` and module/submodule division; BDD → `acceptance-tests.md` (Gherkin scenarios); TDD → `unit-tests.md` written before implementation, with constraint-first cases
- Left wing (design decisions: `decision-log.md`) → Right wing (test verification: `unit-tests.md` + `acceptance-tests.md`) form a closed loop; `feature-design.md` (What) serves as the behavioral spec hub connecting both wings
- Implements a complete closed loop from strategic design (module boundaries, top-level contracts) to tactical implementation (domain models, feature specs, tests)

**Progressive knowledge disclosure**

- Top-level docs provide global project context; a single reading gives the full picture
- Module-level docs are independent and complete, can be read on demand or used as standalone references
- Humans read layer by layer; AI loads the minimal context set on demand

## 3. Detailed architecture of the documentation system

> **Terminology mapping**: This document uses three sets of terms interchangeably, all with one-to-one correspondence —
>
> | frontmatter `level` value | Common term | Chinese term | Documents included |
> |------|---------|---------|---------|
> | `top` | Level 0 | Top-level (project charter) | 7 top-level doc types including `business_context` |
> | `module` | Level 1 | Module layer | `architecture`, `domain_model`, `module_manifest`, `integration` |
> | `feature` | Level 2 | Feature layer | `feature_design`, `decision_log`, `unit_test`, `acceptance_test` |

### 3.1 Top-level: Project Charter

The project charter is the top level of the entire documentation system, containing global project information shared by all modules.

#### 3.1.1 Document structure

The project charter consists of the following documents. They **lie directly in the document root directory** (at the same level as each `module-*/` directory; the complete directory is shown in §3.4.1); `project-charter` is only a conceptual value in the frontmatter `module` field and does not correspond to a real directory:

```
(document root)
├── business-context.md              # Business context (required)
├── technical-framework.md           # Technical framework (required)
├── non-functional-constraints.md    # Non-functional constraints (required)
├── global-policies.md               # Global policies (required)
├── inter-module-contracts.md        # Inter-module contracts (recommended)
├── stakeholders.md                  # Stakeholder analysis (optional)
└── release-policy.md                # Release policy (recommended, see §3.8)
```

#### 3.1.2 Basic structure of each document

The project charter contains 7 top-level documents (`stakeholders.md` is optional; `inter-module-contracts.md` and `release-policy.md` are recommended; the rest are required), organized following the logic of "business context → technical framework → constraints → policies → contracts → stakeholders"; `release-policy.md` defines the release domain (see §3.8) and is independent of this logic chain. Its basic structure is at the end of this section. Each document's core positioning and recommended section structure are described below.

> **Terminology note**: "Constraints" in the documents below refer to **writing boundaries** (what content should NOT be written in this document); this is different from the content-level constraint markers `[MUST]` / `[SHOULD]` / `[MAY]` in §3.5.5 — do not confuse them.

##### business-context.md — Business context

**Positioning**: Describes the business motivation, goals, and scope of the project. It is the first entry point for readers to understand "why this project exists". New hires and cross-team collaborators should read this document first.

**Constraints**: Do not write technical solutions or implementation details; do not discuss "how to do it" here — only answer "why to do it".

```markdown
## Project motivation

One paragraph: project origin + business problem to solve (≤ 200 words).

## Project goals

- Results at the business value level (measurable); quantifiable technical metrics (latency/throughput thresholds) belong in non-functional-constraints.md

## Target users

| Role | Characteristics | Primary demands |
|------|----------------|-----------------|
| Grid dispatch operator | Familiar with dispatch procedures | Real-time data visibility |

## Business scope

- In scope: this phase covers distributed PV integration and monitoring
- Out of scope: no energy storage dispatch or demand management

## Key terminology

| Term | Definition |
|------|-----------|
| Telemetry | Periodic runtime data reported by devices (voltage, current, power, etc.) |
```

> In-depth analysis of target users (concerns, decision-making power, participation, information needs) belongs in `stakeholders.md` — do not expand here.

##### technical-framework.md — Technical framework

**Positioning**: Describes the project's core technology choices, architectural style, and development toolchain. All module-level technical decisions should be made within this framework.

**Constraints**: Do not list all candidate technologies; only record the final choices and their **rationale**; do not write internal technical details of individual modules here.

```markdown
## Tech stack overview

| Category | Technology | Version | Rationale | Constraint/scale estimate |
|---------|-----------|---------|-----------|--------------------------|
| Language & runtime | Python | 3.11+ | Rich AI ecosystem; unified team stack | — |
| Data storage | PostgreSQL | 16 | Structured data; ACID transaction requirements | Data scale < 10TB |

## Architecture style

One paragraph: style name + rationale (e.g., "Event-driven + modular monolith: clear business module boundaries, event decoupling for cross-module collaboration").

## Key frameworks and middleware

| Framework/Middleware | Version | Purpose | Alternatives |
|---------------------|---------|---------|-------------|
| FastAPI | 0.110 | HTTP interfaces, auto-generates OpenAPI docs | Flask (not chosen: no native async) |

## Deployment model

One paragraph: deployment shape (containerized / edge-cloud two-tier, etc.) + runtime environment.

## Dev environment & toolchain

- IDE: VS Code + Python extension
- CI: GitHub Actions, build on push
```

##### non-functional-constraints.md — Non-functional constraints

**Positioning**: Lists the non-functional metrics and baselines that the project must meet (performance, security, compliance, compatibility, coding standards, etc.). It is the basis for module design and code review. Constraints should use [MUST]/[SHOULD]/[MAY] markers to indicate level.

**Constraints**: Do not write ideal goals or visions (e.g., "hope the system performance is excellent"); each constraint should be **verifiable** — quantifiable metrics give values directly (e.g., order API P99 response time ≤ 300ms); rule-type constraints give determinable criteria (e.g., "follow team coding standards"); do not repeat choices already declared in the technical framework here.

```markdown
## Performance constraints

| Constraint ID | Metric/Requirement | Value | Level | Note |
|--------------|-------------------|-------|-------|------|
| C-101 | Order API P99 response time | ≤ 300ms | [MUST] | Main order placement chain |
| C-102 | Multi-AZ deployment | Any single-AZ failure does not affect ordering | [MUST] | Availability |

## Security constraints

| Constraint ID | Requirement | Level | Note |
|--------------|-------------|-------|------|
| C-201 | Use TLS 1.3 for transmission | [MUST] | Full-link encryption |

## Coding standards

| Constraint ID | Standard | Level | Note |
|--------------|----------|-------|------|
| C-301 | Code follows team coding standards (ESLint ruleset) | [MUST] | Rule content in global-policies.md §Coding Standards |
| C-302 | Unit test coverage ≥ 80% | [MUST] | Threshold value in this doc |

## Platform compatibility

| Constraint ID | Dimension | Level | Target Platform/Version |
|--------------|-----------|-------|------------------------|
| C-401 | OS | [MUST] | Windows 10+ / macOS 12+ |

## Third-party dependency constraints

| Constraint ID | Dependency Constraint | Level | Note |
|--------------|---------------------|-------|------|
| C-501 | Lock dependency versions (lock file committed to repo) | [MUST] | Reproducible builds |
```

> Each section is a **constraint table** (one constraint per row); column names can be adjusted by dimension (e.g., §Platform Compatibility uses "Dimension / Target Platform·Version"). "How to define standards" belongs in `global-policies.md`; "what thresholds must be met" belongs in this document.

##### global-policies.md — Global policies

**Positioning**: Defines globally unified design policies that affect multiple business modules and cannot be attributed to any single module. When the same thing (authentication, logging, error codes) appears in two or more modules, it should be defined here uniformly to avoid modules reinventing the wheel.

**Division of labor with non-functional-constraints.md**:

| Document | What question does it answer | Typical content |
|----------|----------------------------|----------------|
| `non-functional-constraints.md` | "What metrics/thresholds must be met" | Order API P99 ≤ 300ms, multi-AZ deployment required, [MUST] follow team coding standards |
| `global-policies.md` | "What global solution to choose, how to do it" | Unified OAuth2 authentication, unified structured log format, unified error code system |

**Constraints**: Do not replace specific implementation details within each module; module-specific special handling is not defined here.

**How to determine whether a policy should be written here**:
- ✅ The policy affects **2 or more** modules → write here
- ✅ The consequence of not unifying is a **system-level problem** (security vulnerabilities, unmaintainable, data inconsistency) → write here
- ❌ Only affects a single module → write in that module's own documents
- ❌ Is a quantifiable metric or threshold → write in `non-functional-constraints.md`

```markdown
## [Policy name]

### Scope
**Affected modules**: [list at least 2 affected modules]

### Policy definition
[The globally unified approach or standard]

### Rules all modules must follow
- [MUST] C-101 [rule 1]
- [SHOULD] S-101 [rule 2]

### Why unify
[What problems would arise without unification — helps new members understand the tradeoff]
```

**Writing points**:
- Each policy is its own section with a clear, readable name (e.g., "Authentication", "Logging Standards", "Error Code System")
- Use [MUST]/[SHOULD] markers to indicate rule enforcement level
- For each policy, explain "why unify" — helps new members understand the underlying tradeoffs
- Modules should **reference** definitions from global policies in their own designs, avoiding duplication
- Global policies are **living documents**, continuously updated as the project evolves

##### inter-module-contracts.md — Inter-module contracts

**Positioning**: Defines the interface specifications, shared events, and shared data structures that need **precise alignment** between modules. When two modules need to clearly agree on "what the input looks like, what the output looks like, what happens on error", it should be recorded here.

**Division of labor with module-manifest.md**:

| Document | Level | What question does it answer | Level of detail | Example |
|----------|-------|----------------------------|-----------------|---------|
| `module-manifest.md` | One per module (Level 1) | "What capabilities does this module provide, whose capabilities does it consume" | Capability name level (existence) | exports declares `deduct_stock`; imports declares inventory > deduct_stock |
| `inter-module-contracts.md` | One global (Level 0) | "What format are the inputs/outputs during integration" | Field-level + protocol-level | Defines deduct_stock request body format, response structure, and error codes |

> The two are like "directory" vs. "instruction manual": `module-manifest.md` declares whether a capability **exists and who provides it** (each import must pair with the provider's export, see §3.2.2); `inter-module-contracts.md` defines what a capability **looks like and what happens on error**; the same capability name must remain consistent across both documents.

**Constraints**: Do not write single-module internal interfaces; do not create interfaces beyond the capability relationships already declared in module-manifest.

**How to determine whether an interface should be written here**:
- ✅ The interface input/output structure is complex (3+ fields or nested structures) → write here
- ✅ The interface has error semantics that need agreement (exception codes, retry strategy) → write here
- ✅ The interface has version negotiation or compatibility requirements → write here
- ✅ An event is consumed by 3+ modules and needs a unified payload schema definition → write here
- ❌ The interface only has simple parameters (like a single ID or boolean) → just note it in the module-manifest description column
- ❌ This is a call between internal components of one module → do not write here

```markdown
## Inter-module interface definitions

### [Interface name]
**Provider**: [module name]  **Consumers**: [list of module names]
**Communication**: sync RPC / async message / event broadcast
**Data format**: JSON / Protobuf / custom binary

**Request structure**:
```json
{
  "order_id": "string (required, unique order identifier)",
  "items": ["array (deduction entries, each containing sku_id and quantity)"]
}
```

**Response structure**:
```json
{
  "success": "boolean",
  "error_code": "int (0=success, 1=timeout, 2=format error)",
  "error_msg": "string"
}
```

**Constraints**:
- [MUST] C-601 timeout ≤ 500ms
- [SHOULD] S-601 implement exponential backoff retry, up to 3 times

## Shared event definitions

### [Event name]
**Publisher**: [module name]
**Subscribers**: [list of module names]
**Trigger condition**: [what scenario fires this event]

**Payload**:
```json
{
  "event_id": "string (UUID)",
  "timestamp": "uint64",
  "payload": { ... }
}
```

## Shared data structures

### [Structure name]
**Owned by**: [module responsible for maintaining this structure]
**Used by**: [which modules use it]

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id    | string | ✅ | Globally unique identifier |
| name  | string | ✅ | Display name |
| status | enum | ✅ | active / inactive / archived |
```

**Writing points**:
- Interface definitions must be **field-level precise** — this is the only factual basis for AI-generated code and human reviews
- Shared data structures should clearly indicate **ownership** (which module is responsible for version updates) to avoid conflicts from multiple people modifying
- Event definitions should mark the **publisher and all subscribers** — the toolchain can generate publish/subscribe topology diagrams from this
- Constraint markers differ from global-policies: constraints here are **interface-level** (e.g., "timeout ≤ 500ms"), while constraints in global-policies are **system-level** (e.g., "full-link encryption")

##### stakeholders.md — Stakeholder analysis

**Positioning**: Identifies key project stakeholders and their interests, guiding requirement prioritization and communication strategy. This document is **optional**; smaller projects can omit it.

**Constraints**: Stakeholders with vague or no direct definition should not be recorded.

```markdown
## Role definitions
| Role | Responsibilities | Concerns | Decision authority | Expected participation |
|------|-----------------|----------|--------------------|-----------------------|
| Grid dispatch operator | Issue dispatch instructions and monitor execution | Data real-time nature and accuracy | Has operational permissions | Participate in requirement review and acceptance |

## Information needs matrix
| Role | Required Info | Frequency | Channel/Format |
|------|---------------|-----------|----------------|
| Grid dispatch operator | Real-time telemetry data | Second-level | Monitoring dashboard |
| Operations staff | Device alert notifications | Real-time | IM push |
```

> Section notes: "Concerns / Participation" are merged into columns of the §Role Definitions table; "Information needs" is carried by §Information Needs Matrix (role | required info | frequency | channel/format).

##### release-policy.md — Release policy

**Positioning**: Defines authoritative rules for the release domain — release state machine, release unit division, release gates, release pipeline, release number rules, and rollback strategy. It is the policy carrier for the release domain (§3.8): default definitions for state machine, gates, and flow are in §3.8; the project can customize them in this document. This document is **recommended**.

**Constraints**: Do not write deployment operation details — deployment model belongs in `technical-framework.md`; do not write content of a specific release — release records are derived artifacts generated by the toolchain and do not belong in Spec documents.

```markdown
## Release states

| State | Meaning | Entry condition |
|-------|---------|-----------------|
| draft | Draft | Spec change committed |
| in-review | In review | Submitted for review |
| ready | Gates passed | P1 static gates + P2 dynamic gates all green |
| released | Released | P4 release validation passed and P5固化 complete |
| superseded | Replaced by new release | A newer released release unit appears |

## Release unit division

Default: one feature (4 documents under `features/<feature-name>/`) + its `depends_on` dependency chain (see §3.8.2).

## Release gates

| Gate | What to check | Mechanism |
|------|--------------|-----------|
| G1 Doc health | All docs in release unit are active, no deprecated blockers | §3.7 |
| G2 Dependency consistency | `depends_on` exact version, no drift/cycle/reverse dependencies | §3.5.7 |
| G3 Contract closure | imports ↔ exports paired, no dangling contract interfaces | §3.2.2 |
| G4 Constraint coverage | Each numbered [MUST] constraint in `feature-design.md` §Boundary Constraints within the release unit is referenced by unit-tests | §3.5.5, §3.5.6 |
| G5 Tests green | unit-tests + acceptance-tests execute successfully | §3.3.3 |
| G6 Implementation mapping | Paths declared in `implemented_in` actually exist | §3.5.9 |

## Release pipeline

P0 change detection → P1 static gates → P2 dynamic gates → P3 artifact generation → P4 release validation → P5固化 (see §3.8.4).

## Release number rules

`YYYY.MM.n`, independent from Spec version (§3.5.7).

## Rollback strategy

- Trigger condition: [when to roll back]
- Rollback action: [which version/artifact to roll back to]
- Record requirements: [records to append after rollback]
```

**Writing points**:
- §Release States defaults to `draft → in-review → ready → released → superseded` from §3.8.1; adding or removing states must also explain their correspondence with gates
- Gates should be added/removed on top of G1~G6 from §3.8.3 as needed; deleting or adding must state reasons (G4 coverage scope see §3.8.3)
- Release numbers recommended to use `YYYY.MM.n` format, independent from Spec version (§3.5.7)

#### 3.1.3 Common metadata structure

The 7 documents under the project charter follow a unified metadata format, ensuring that both humans and tools can quickly parse a document's identity, level, and dependency relationships. The YAML frontmatter of top-level documents uses the following structure:

```yaml
---
doc_type: business_context       # Document type, from type registry (see §3.6)
module: project-charter          # Owning module; top-level docs are fixed as project-charter
level: top                       # Level: top | module | feature
version: 0.1.0                   # Semantic version, manually incremented by user
last_updated: 2026-03-10         # Auto-updated by tool
author: team-architecture        # Document owner
status: active                   # active | deprecated | archived
---
```

**Positioning of key fields**:

- `doc_type` identifies the document role, determines what sections the document should contain; values include `business_context`, `technical_framework`, `non_functional_constraints`, `global_policies`, `inter_module_contract`, `stakeholders`, etc.
- `level: top` marks it as a top-level document; reverse dependencies to lower levels are prohibited
- `version` works with `depends_on` to implement version consistency management (see §3.5.7)
- `status` manages the document lifecycle; `deprecated` identifies outdated docs, `archived` identifies archived docs, preventing zombie document accumulation

> Complete field definitions, required rules, and the full list of doc_type values are in §3.5.2 Metadata Block Specification.

**Relationship between doc_type and filename**: `doc_type` is a type identifier in the registry (§3.6), named with underscores (e.g., `business_context`); filenames are standard agreed filenames, named with hyphens (e.g., `business-context.md`). They correspond one-to-one, and only `doc_type` is written in frontmatter.

### 3.2 Module Layer: Module Architecture Design

Each business module contains independent architecture design, domain model, and feature specs. Modules can recursively nest submodules.

#### 3.2.1 Document structure

```
module-name/
├── module-manifest.md        # Module manifest: exports/imports
├── architecture.md           # Module architecture design
├── domain-model.md           # Domain model
├── integration.md            # External integration (optional)
├── features/                 # Feature set
│   ├── feature-a/
│   │   ├── feature-design.md       # Feature design (What)
│   │   ├── decision-log.md         # Decision trace (Why, left wing)
│   │   ├── unit-tests.md           # Unit tests (right wing)
│   │   └── acceptance-tests.md     # Acceptance tests (BDD)
│   └── feature-b/
│       └── ...
└── sub-modules/              # Submodules (optional)
    └── sub-module-a/
        └── ...
```

#### 3.2.2 Basic structure of each document

The module layer contains 3 core documents plus the `features/` directory. Each document's core positioning and recommended section structure are described below.

##### architecture.md — Module architecture design

**Positioning**: Describes the module's overall architecture, core capabilities, and interface boundaries. It is the blueprint for module development. Readers use this document to understand what the module is responsible for, what it is NOT responsible for, and how it interacts with other modules.

**Constraints**: Do not write line-by-line code implementation; do not define domain entities here — domain model belongs in domain-model.md.

```markdown
## Module overview
Order module, responsible for order creation, query, and state transition.

## Core capabilities
- Order creation and validation
- Order state transition (pending_payment / paid / cancelled)
- Order query

## Component division
| Component | Responsibility | Dependencies on internal components |
|-----------|----------------|-------------------------------------|
| Order application service | Orchestrate order placement / cancel flow | Order domain service, Order repository |
| Order domain service | Order creation, state transition, timeout cancellation | Order repository |
| Order repository | Order persistence | — |

## Module interfaces

This section is split into two tables: **external interfaces** (what this module provides to other modules) and **internal interfaces** (between components within the module), without repeating field details.

### External interfaces

Interfaces only list **capability name + purpose + constraints**; **signatures** belong in `module-manifest.md` §Exports; field-level request/response and error codes belong in `inter-module-contracts.md`.

| Capability name | Purpose | Constraints |
|-----------------|---------|-------------|
| create_order | Create order | [MUST] C-701 latency ≤ 1ms |
| cancel_order | Cancel order | — |

### Internal interfaces

Call conventions between internal components of the module (signatures given in this document).

| Caller | Callee | Signature | Note |
|--------|--------|-----------|------|
| Order application service | Order domain service | `createOrder(userID string) (Order, error)` | Orchestrate order placement |
| Order domain service | Order repository | `save(order Order) error` | Persist order |

> Interactions with other modules are NOT defined here: capability-level dependencies are declared in `module-manifest.md` imports; field-level contracts are defined in `inter-module-contracts.md`.

## Key flows
Flows in this section are **module/component-level** orchestration; **behavior chains of individual features from trigger to completion** belong in `feature-design.md` §Processing Flow.

1. Order placement: validate product and stock → create order (pending_payment) → pre-occupy stock → return order number
2. Timeout cancellation: periodic scan of expired orders → mark as cancelled → release stock → notify user
```

##### domain-model.md — Domain model

**Positioning**: Defines internal domain entities, value objects, their relationships, and constraints. It is the outcome artifact of DDD tactical design. Each aggregate root, entity, and value object should have a clear responsibility boundary.

**Constraints**: Do not write database table structures or ORM mappings — those are implementation details, not domain models; do not describe module interfaces here — interfaces belong in architecture.md.

The body is the "domain model definition" section defined here, divided into 4 fixed sections by type, with a unified template for each domain object (**Type** / **Properties** / **Behavior** / **Constraints**).

```markdown
## Aggregate roots

### Order - Order
**Type**: Aggregate root
**Properties**:

| Field name | Type | Constraint | Description |
|------------|------|------------|-------------|
| order_id | string | Required | Order ID |
| user_id | string | Required | Ordering user |
| total_amount | decimal | Required, ≥ 0 | Order amount |
| status | enum | Required | pending_payment / paid / cancelled |

**Behavior**:
- Create order: validate product stock and price
- Timeout cancellation: auto-cancel and release stock after payment deadline

**Constraints**:
- [MUST] C-801 Order amount cannot be negative

## Entities

### Payment - Payment
**Type**: Entity
**Properties**:

| Field name | Type | Constraint | Description |
|------------|------|------------|-------------|
| payment_id | string | Required | Payment transaction ID |
| amount | decimal | Required | Payment amount |
| status | enum | Required | pending / success / failed |

**Behavior**:
- Payment callback handling: validate callback signature and update payment status

**Constraints**:
- [MUST] C-802 Payment callbacks handled idempotently; duplicate callbacks must not result in duplicate deductions

## Value objects

### Money - Amount
**Type**: Value object
**Properties**:

| Field name | Type | Constraint | Description |
|------------|------|------------|-------------|
| amount | decimal | Required | Numeric value |
| currency | enum | Required | CNY / USD |

**Behavior**:
- Same-currency addition; instance is immutable, operations return new instance

**Constraints**:
- [MUST] C-803 Money operation result must maintain currency consistency

## Domain constraints

Table of global business rules across entities (format: constraint ID | rule | level | affected entities).

| Constraint ID | Rule | Level | Affected entities |
|--------------|------|-------|-------------------|
| C-801 | Order payment amount must equal order amount | [MUST] | Order / Payment |
| C-802 | Cancelled orders must not initiate payment | [MUST] | Order / Payment |
```

**Writing points**:
- Each domain object should mark its **type** (aggregate root / entity / value object)
- **Properties** list key fields and types; no need to enumerate all implementation details
- **Behavior** describes the business logic the object is responsible for, not technical implementation
- **Constraints** only mark **single-entity / single-value-object** business rules and invariants, using [MUST]/[SHOULD] markers; **cross-entity** rules go into §Domain Constraints

##### integration.md — External integration (optional)

**Positioning**: Describes how the module integrates with external systems (third-party services, legacy systems, hardware devices, etc.). This document can be omitted when the module does not involve external integration.

**Constraints**: Do not write interface conventions between internal project modules — internal interfaces belong in module-manifest.md and inter-module-contracts.md; do not repeat internal component relationships already defined in architecture.md here.

```markdown
## External systems overview

| External system | Purpose | Communication direction | Key constraint |
|----------------|---------|------------------------|----------------|
| SCADA dispatch system | Dispatch instructions and status feedback | Bidirectional | [MUST] C-901 Communication latency ≤ 100ms |

## Integration methods and protocols

| External system | Protocol | Connection | Data format | Authentication |
|----------------|----------|-----------|-------------|----------------|
| SCADA dispatch system | IEC 104 | Long connection | Custom binary | Certificate |

## Data flow and sync strategy

| Data flow | Direction | Trigger | Sync strategy | Max latency |
|-----------|-----------|---------|---------------|-------------|
| Telemetry data | Inverter → this module → storage module | Periodic poll | Incremental | 1s |

## Error handling and degradation

This document only writes about **specific external system integration** failure detection, degradation, and recovery; **system-level error code standards and unified degradation/recovery strategies belong in `global-policies.md` §Exception Handling**.

| Failure scenario | Detection method | Handling strategy | Recovery method |
|-----------------|-----------------|------------------|----------------|
| Communication timeout | Heartbeat timeout | Retry 3 times then write to error queue | Manual intervention |
```

**Writing points**:
- Division of labor between external integration and inter-module contracts: external integration is **one-way or two-way calls between a module and an external system**; inter-module contracts are **interface conventions between internal project modules**
- Should describe degradation and retry mechanisms when integration fails

##### module-manifest.md — Module manifest

**Positioning**: Declares capabilities provided externally by the module (exports) and capabilities of other modules that this module depends on (imports). The toolchain can automatically derive inter-module dependency graphs from this file, detect circular dependencies, and analyze call chain anomalies.

> The module manifest introduces the `import` / `export` dependency expression paradigm, validated over decades in programming module systems (ES Modules, Java packages, Go packages, etc.), directly into the documentation system. Traditional software design documents (interface docs, architecture docs) only describe "what the interface looks like" (fields, protocols, sequences) but never mechanically declare "who provides this capability and who consumes it." `module-manifest.md` extracts "who depends on whom" from scattered narrative text across architecture docs into **mechanically verifiable tables**: when all module manifests in the project are combined, they form the system's **capability map** — equivalent to aggregating each module's `package.json` / `go.mod` into a single dependency topology.

**Core invariant: imports must pair with exports**

The single most important rule of module manifests, equivalent to symbol resolution in programming: **each import declared by a consumer (`source module` + `capability name`) must find a corresponding entry in the provider's exports** — just as `import`-ing a non-existent export causes a compile failure, importing a non-existent module capability is equally illegal.

```markdown
# Provider: inventory/module-manifest.md
## Exports
| Capability name | Type | Signature | Description | Stability |
|----------------|------|-----------|-------------|-----------|
| deduct_stock | interface | (sku_id string, qty int) → error | Deduct stock | stable |
| query_stock  | interface | (sku_id string) → (Stock, error) | Query stock | stable |

# Consumer: order/module-manifest.md
## Imports
| Source module | Capability name | Purpose |
|--------------|----------------|---------|
| inventory | deduct_stock | Deduct stock |
```

- `order`'s `imports.inventory.deduct_stock` ↔ `inventory`'s `exports.deduct_stock` one-to-one correspondence → ✅ pair closed
- `inventory` deletes or renames `deduct_stock` while `order` does not sync → ❌ pair broken; the toolchain should mark all importers immediately
- `order` spells the capability as `deduct_stock2` → ❌ cannot pair, treated as illegal dependency, must be corrected

**Three pairing results and their meanings**:

| import ↔ export pairing | Judgement | Meaning |
|------------------------|-----------|---------|
| import exists, export exists | ✅ Legal | Dependency closed, call chain traceable |
| import exists, export does NOT exist | ❌ Illegal | Consuming non-existent capability: typo, or provider deleted/modified without sync |
| export exists, nobody imports | ⚠️ Review | Capability not consumed: possibly redundant, or for external systems / future features |

**Constraints**: Do not write internal implementation details or non-public capabilities only used within the module; exports only list capabilities on the **module contract boundary**, and capability names should correspond one-to-one with interfaces in `inter-module-contracts.md` — the module manifest declares "whether a capability exists and who provides it"; the inter-module contract defines "what a capability looks like and what happens on error"; the two complement each other (see §3.1.2).

```markdown
## Exports

Capabilities this module provides externally. **Signatures are the single authoritative source for capability signatures**; `architecture.md` §Module Interfaces only lists capability names and purposes, without repeating signatures; `inter-module-contracts.md` defines field-level request/response and error codes for the same capability.

"Type" values are fixed as `interface | event | data_structure | capability`.

| Capability name | Type | Signature | Description | Stability |
|----------------|------|-----------|-------------|-----------|
| create_order | interface | (user_id string, items []Item) → (Order, error) | Create order | stable |
| cancel_order | interface | (order_id string) → error | Cancel order | stable |
| order_created | event | (order_id string, created_at time) | Order created event | stable |

## Imports

Capabilities of other modules that this module depends on; each entry points to a specific export item in the target module. Interface-level constraints (timeout / retry, etc.) belong in `inter-module-contracts.md`; not repeated here.

| Source module | Capability name | Purpose |
|--------------|----------------|---------|
| inventory | deduct_stock | Deduct stock |
| payment | create_payment | Initiate payment |
| notification | notify_user | Send order status notification |
```

**Usage scenarios**:
- **Architecture review**: Read all module manifests to master the system's capability topology without flipping through each architecture doc
- **Change impact assessment**: Before deleting or modifying an export, first reverse-query who imports it
- **AI cross-module development**: Before generating cross-module calls, first check consumer imports to confirm the capability exists, then check `inter-module-contracts.md` for field-level contracts
- **New member onboarding**: Module manifests + `inter-module-contracts.md` form the system's "capability map + interface manual" — the fastest entry point to understanding the system

**Toolchain capabilities**:
- Automatically collect exports → imports from all modules, generating a global dependency graph
- Validate import/export pairing (core invariant), detect circular dependencies, fan-in/fan-out anomalies, and level boundary violations
- When a dependent module deletes or modifies an export entry, mark all importers immediately
- `imports` (capability dependencies) and `depends_on` (document dependencies) are two independent dimensions, not substitutes for each other; cross-module **document references** (e.g., `architecture.md` referencing `global-policies.md`) still need to be declared in `depends_on`

#### 3.2.3 Submodule mechanism

When internal business logic of a module becomes too complex, it can be recursively split via **submodules**, keeping each granularity of module documentation readable.

##### When to use submodules

Consider splitting submodules in the following situations:
- Module contains multiple relatively independent business subdomains
- A single module has too many features and too long documentation
- Subdomain responsibilities and boundaries can be clearly defined
- Team members can divide work by submodule

##### Submodule document structure

Submodule documentation structure stays consistent with the parent module: `architecture.md` + `domain-model.md` + `features/` feature set.

```
module-name/
├── architecture.md               # Parent module architecture
├── domain-model.md               # Parent module domain model
├── features/                     # Parent module feature set
└── sub-modules/
    └── order-core/               # Submodule: order state machine core
        ├── architecture.md       # Submodule architecture
        ├── domain-model.md       # Submodule domain model
        └── features/
            └── ...
```

##### Contract relationships

- Submodules **inherit** the parent module's inter-module contracts: a submodule's imports/exports are treated as part of the parent module's capabilities, following contracts declared by the parent
- Interface conventions between submodules are recorded in the **parent module's** architecture document
- Capabilities exposed externally by submodules are presented through parent module interfaces, avoiding external modules directly depending on submodule details; if independent capability exposure is needed, a submodule can maintain its own `module-manifest.md` (optional)
- The `module` field in submodule docs is `<parent-module>.<submodule>` (dot-separated, e.g., `order.core`), with directory at `module-<parent-module>/sub-modules/<submodule>/` (e.g., `module-order/sub-modules/core/`)
- Submodules can continue nesting submodules, forming a recursive structure (usually 2~3 layers is appropriate)

### 3.3 Feature Layer: Feature Spec Design

Each feature contains 4 documents, organized by the logic of "What → Why → Test", forming a complete closed loop from design decision to verification.

#### 3.3.1 Document structure

```
features/order-timeout-cancel/
├── feature-design.md       # Feature design (What)
├── decision-log.md         # Decision trace (Why, left wing)
├── unit-tests.md           # Unit tests (right wing — code correctness)
└── acceptance-tests.md     # Acceptance tests (right wing — business behavior verification)
```

#### 3.3.2 Basic structure of each document

Each document's core positioning and recommended section structure are described below. Templates omit the opening `#` document title line for brevity — actual documents should start with a `#` title (see §3.5.1), and the heading levels in the template represent the levels the body should maintain.

##### feature-design.md — Feature design (What)

**Positioning**: Describes the complete behavioral spec of a feature, including prerequisites, trigger conditions, processing flow, exception paths, boundary constraints, and function call relationships. Developers use this as the blueprint to implement features; testers use it as the basis to write tests.

**Constraints**: Do not write implementation code here; do not record design decision rationale here — rationale belongs in decision-log.md.

```markdown
## Feature: Order automatic timeout cancellation

### Feature description
When an order remains unpaid for more than 30 minutes after creation, the system automatically cancels the order and releases the reserved stock.

### Trigger conditions

| Condition | Threshold | Duration requirement |
|-----------|-----------|----------------------|
| Order status is "pending_payment" | More than 30 minutes after creation | — |
| User initiates manual cancellation | Status is "pending_payment" | — |

### Applicable prerequisites
("Prerequisites" on the design side = states the system must already be in for the feature to be executable; not the same level as test case Given / Gherkin assumptions)
- Order module and inventory module are communicating normally
- Scheduled task scheduler is running

### Processing flow
1. Scheduled task scans expired orders
2. Validate order status is still "pending_payment"
3. Mark order as "cancelled"
4. Call inventory service to release stock
5. Notify user that order has been cancelled

### Exception paths

| Exception scenario | Handling method | Notification method |
|-------------------|----------------|--------------------|
| Stock release failure | Retry 3 times then mark order as pending compensation | Alert notification to operations |
| User notification failure | Put message in retry queue, do not block order cancellation | Log recording |

### Boundary constraints

| Constraint ID | Constraint | Level | Target value | Note |
|--------------|-----------|-------|--------------|------|
| C-101 | Scan cycle | [MUST] | ≤ 5 minutes | Timeout judgment precision |
| C-102 | Cancellation and stock release atomic | [MUST] | Same transaction | Avoid stock leakage |

### Function call relationships

| Function | Signature | Responsibility | Calls |
|----------|-----------|----------------|-------|
| cancelExpiredOrders | (ctx context.Context) error | Scan and cancel expired orders (entry) | findExpiredOrders, cancelOrder, releaseStock |
| findExpiredOrders | (ctx context.Context) ([]Order, error) | Query expired unpaid orders | — |
| cancelOrder | (order Order) error | Mark order as cancelled | — |
| releaseStock | (order Order) error | Release stock reserved by order | — |
```

##### decision-log.md — Decision trace (Why, left wing)

**Positioning**: Records the background, rationale, and alternative analysis of key design decisions, providing a traceable basis for future reviews and changes.

**Constraints**: Do not write meeting minutes or discussion process here; only record conclusions and rationale; do not define feature behavior here — feature behavior belongs in feature-design.md.

```markdown
## Decision: Use async messaging instead of sync RPC for payment callbacks

**Date**: 2026-03-10  **Decision maker**: team-architecture  **Status**: Approved

### Problem description
Should payment callbacks use sync RPC or async messaging?

### Business Why
- Payment gateway responses are slow and unstable; sync waiting would block the main order placement chain
- Asynchronous processing ensures the order API P99 response time meets the target (≤ 300ms)

### Technical Why
- Message queues can absorb peaks; callback spikes do not overwhelm the order service
- Failed callbacks auto-retry without human intervention
- Messages are persisted; service restart does not lose callbacks

### Alternative analysis
| Option | Pros | Cons | Evaluation |
|--------|------|------|-----------|
| Sync RPC | Simple to implement, results immediately known | Blocks order placement when payment gateway fails | Not recommended |
| Periodic polling | No additional dependencies | High latency, poor real-time | Not recommended |
| Async messaging | Decoupled, retryable, peak-absorbing | Introduces middleware, higher complexity | Recommended |

### Final decision
Use async messaging (message queue) for payment callback processing.
```

> One `## Decision: <Title>` record per decision; existing records **cannot be modified** — when conclusions change, append a new record (see §3.3.3).

##### unit-tests.md — Unit tests (right wing — code correctness)

**Positioning**: Defines the inputs, operations, and expected outputs of each test scenario. Each GWT (Given-When-Then) triple describes an independent, language-agnostic test case. Developers write actual test code (`xxx_test.go` / `xxxTest.java`, etc.) based on this; reviewers judge implementation correctness based on this.

**Difference between this document and source test files**:
- `unit-tests.md` describes **what to test and what is expected** — language-agnostic, not tied to implementation
- Source test files are **specific implementations** — contain mock setup, framework calls, assertion APIs, etc.

**Constraints**: Do not write integration or end-to-end tests — those belong in acceptance-tests.md; do not describe business scenarios here — scenarios belong in acceptance-tests.md; do not write mock details or framework calls — those belong in source test files.

```markdown
### Test case: <case name>

#### Given prerequisites
[Describe input state, prerequisite data (can include mock behavior agreements, but do not write specific mock configuration or framework calls)]

#### When trigger action
[Which function to call, with what parameters]

#### Then expected result
- [Expected return value or state change 1]
- [Expected return value or state change 2]
```

##### acceptance-tests.md — Acceptance tests (right wing — business behavior verification)

**Positioning**: Describes complete business scenarios in BDD-style Gherkin syntax, verifying whether features meet business expectations.

**Constraints**: Do not write technical implementation details or code-level verification here — code correctness verification belongs in unit-tests.md; do not define feature constraints here — constraints belong in feature-design.md.

```gherkin
# language: zh-CN
功能: 订单超时自动取消
  作为 用户
  我希望 超时未支付的订单自动取消
  以便 释放库存、避免占用

  场景: 超时订单被自动取消
    假设 订单创建已超过 30 分钟且状态为「待支付」
    当 定时任务执行
    那么 订单状态变为「已取消」且库存恢复
```

> Complete Gherkin syntax specification and file organization see §3.5.8 Acceptance Test Specification.

#### 3.3.3 Feature spec closed loop (left wing → right wing)

The 4 documents in the feature layer form a "decision-driven verification" closed loop:

```
feature-design.md (What) ──→ Defines the feature's behavioral spec
         │
         ├──→ decision-log.md (Why) ──→ Records design decisions and selection rationale
         │
         ├──→ unit-tests.md (code correctness) ──→ Verifies implementation is correct
         │
         └──→ acceptance-tests.md (business verification) ──→ Verifies behavior meets expectations
```

> Note: The arrows in the diagram represent **logical association direction** (decisions and tests both revolve around feature design), not dependency declarations; document dependencies follow the registry in §3.6.3.

> Terminology convention: "Spec" in the following text and conclusion refers to the spec-style documents in this system (all document types including `feature-design.md`, `unit-tests.md`, etc., see §3.6).

**Left wing drives right wing**:
- Boundary constraints in feature design (e.g., "[MUST] C-101 scan cycle ≤ 5 minutes") should be directly reflected in unit test cases
- Business rules in feature design should be completely covered by acceptance test scenarios
- When right-wing tests fail, trace decision basis back to the left wing: when tests don't match the Spec, it's mostly an implementation defect — fix the code; if the Spec constraint itself doesn't hold, modify the Spec, and if necessary, **append** a new decision record to the decision log — existing decision records cannot be modified to maintain decision traceability

**Dual-track verification**:
- Unit tests focus on **code correctness** ("Was the code written correctly?")
- Acceptance tests focus on **business conformance** ("Is this what the user wanted?")
- The two complement each other and cannot replace each other

### 3.4 Document directory structure design

#### 3.4.1 Overall structure

```
project-docs/
├── business-context.md               # Level 0: Business context
├── technical-framework.md            # Level 0: Technical framework
├── non-functional-constraints.md     # Level 0: Non-functional constraints
├── global-policies.md                # Level 0: Global policies
├── inter-module-contracts.md         # Level 0: Inter-module contracts
├── stakeholders.md                   # Level 0: Stakeholder analysis (optional)
├── release-policy.md                 # Level 0: Release policy (recommended, see §3.8)
├── module-order/                     # Level 1: Module 1 — Order
│   ├── module-manifest.md            # Module manifest: exports/imports
│   ├── architecture.md               # Module architecture design
│   ├── domain-model.md               # Domain model
│   ├── integration.md                # External integration (optional)
│   ├── features/                     # Level 2: Feature set
│   │   ├── order-timeout-cancel/
│   │   │   ├── feature-design.md     # Feature design (What)
│   │   │   ├── decision-log.md       # Decision trace (Why, left wing)
│   │   │   ├── unit-tests.md         # Unit tests (right wing)
│   │   │   └── acceptance-tests.md   # Acceptance tests (BDD)
│   │   └── order-refund/
│   │       └── ...
│   └── sub-modules/
│       └── order-core/
│           ├── module-manifest.md    # Submodule manifest (optional)
│           ├── architecture.md
│           ├── domain-model.md
│           └── features/
│               └── ...
├── module-data-storage/              # Module 2: Data storage
│   ├── module-manifest.md
│   ├── architecture.md
│   ├── domain-model.md
│   ├── integration.md
│   └── features/
│       └── ...
└── README.md                         # Usage instructions
```

**Directory naming rules**: Module directories are uniformly `module-<module-name>/` (module name in kebab-case, e.g., `module-order`); submodules are at the parent module's `sub-modules/<submodule-name>/`; top-level documents lie flat directly in the document root directory.

#### 3.4.2 Progressive disclosure principle (providing progressive loading path for AI)

**Top-level loading**:
- When starting project work, first read the project charter to get global context
- Obtain project background, technical framework, global constraints

**Module-level loading**:
- Load the corresponding module's architecture design on demand
- When developing features within a module, load specific feature documents

**Feature-level loading**:
- Load feature design (What)
- Load decision trace (Why, left wing)
- Load unit tests (right wing)
- Load acceptance tests (BDD scenario verification)

### 3.5 Markdown format specification

For convenient parsing by subsequent MCP and Skills programs, documents must follow a unified format specification.

#### 3.5.1 Heading level specification

```markdown
# Level 1 heading: Document title (only at document start)
## Level 2 heading: Section title
### Level 3 heading: Subsection title
#### Level 4 heading: Content block title
##### Level 5 heading: Sub-item title (available when content hierarchy is deep)
```

#### 3.5.2 Metadata block specification

Each document file consists of two layers, stored in a single `.md` file:

```
---
# Metadata layer (frontmatter) — structured fields, parsed by both humans and tools; field maintainers see field table below
doc_type: feature_design         # Document type, see §3.6 document type registry
module: order                     # Owning module name (submodules fill parent-module.submodule, dot-separated, e.g., order.core)
feature: order-timeout-cancel    # Owning feature name (Level 2 only)
level: feature                   # Level: top | module | feature
version: 1.0.0                   # Semantic version, manually incremented by user
last_updated: 2024-03-10         # Auto-updated by tool
author: team-architecture        # Document owner
status: active                   # active | deprecated | archived (default active)
deprecated_at:                   # Deprecation date (required when status=deprecated)
deprecated_reason:               # Deprecation reason (required when status=deprecated)
superseded_by:                   # Superseded document (required when deprecated with replacement; can be omitted when no replacement)
  - doc: feature-design-v2.md
    module: order
archived_at:                     # Archive date (required when status=archived)
# implemented_in only needed for Level 2 feature/test docs (see §3.5.9)
implemented_in:                  # Implementation location; tool validates path existence
  - path: src/order/features/timeout_cancel/
    lang: go
depends_on:                      # Dependency declaration with precise version locking
  - doc: domain-model.md
    module: order
    version: "1.0.0"
  - doc: architecture.md
    module: order
    version: "1.2.0"
---

# Variable layer — Markdown content edited freely by users
## Feature description
...
```

**Field descriptions**:

| Field | Required | Maintainer | Description |
|-------|----------|-----------|-------------|
| `doc_type` | ✅ | Set at creation | Document type identifier, from document type registry (see §3.6) |
| `module` | ✅ | Set at creation | Owning module name; top-level docs fill `project-charter` |
| `feature` | Conditional | Set at creation | Only needed for Level 2 docs, fill feature directory name |
| `level` | ✅ | Set at creation | Level identifier: `top` / `module` / `feature`, used for dependency direction validation |
| `version` | ✅ | Manual user | Semantic version `major.minor.patch`, initial value `0.1.0`, user increments via `[+1]` button |
| `last_updated` | ✅ | Auto tool | ISO 8601 date `YYYY-MM-DD`, tool auto-updates on save |
| `author` | ✅ | Set at creation | Document owner (team role or person name), used for change notification routing |
| `status` | ✅ | Manual user | `active` (default), `deprecated`, `archived` |
| `deprecated_at` | Conditional | Manual user | Only needed when `status=deprecated`, fill ISO 8601 date |
| `deprecated_reason` | Conditional | Manual user | Only needed when `status=deprecated`, briefly describe deprecation reason |
| `superseded_by` | Conditional | Manual user | Reference list for replacement documents (required when deprecated with replacement; can be omitted when no replacement) |
| `archived_at` | Conditional | Manual user | Only needed when `status=archived`, fill ISO 8601 date |
| `implemented_in` | Conditional | User+Tool | Only needed for Level 2 feature/test docs (see §3.5.9), declares implementation location; tool validates path existence |
| `depends_on` | Conditional | User+Tool | Declares other documents this one depends on (see §3.5.7); tool re-derives structure on save, user confirms version numbers |

**Maintenance division**: Not all frontmatter fields are automatically managed by tools — `last_updated` is updated by the tool on save, `depends_on` structure is derived by the tool (version numbers confirmed by the user), and all other fields (`version`, `status`, and deprecation/archive related fields) are manually maintained by users. The "Maintainer" column in the field table is the authoritative statement of this division.

#### 3.5.3 Content reference specification

The following reference format is designed to ensure both humans and AI can accurately understand. All references uniformly use the format "filename + section", distinguished by whether the reference target is in the same module:

**Same-module reference** (docs within this module: same directory directly write filename, when in subdirectory write relative path):
```markdown
Module interface description see `module-manifest.md` §"Imports".
Feature behavior definition see `features/order-timeout-cancel/feature-design.md` §"Boundary Constraints".
```

**Cross-module reference** (referencing other modules or top-level docs: path base is the **document root directory** — top-level docs in root directly write filename, module docs write `module-<module-name>/...` relative path; same-module references use **module root directory** as base):
```markdown
Exception scenario handling strategy see `global-policies.md` §"Degradation and Fault Tolerance".
External data format see `module-order/architecture.md` §"Module Interfaces".
```

**Pure filename reference** (not pointing to specific section, used to indicate the document as a whole):
```markdown
Detailed interface constraints see `inter-module-contracts.md`.
```

> Unified reference format allows AI to quickly locate referenced context, forming the basis for building traceable links between documents; body references should stay consistent with dependency declarations in `depends_on`.

#### 3.5.4 Charts and code blocks specification

**Code blocks**: For interface examples, config examples, etc., **structured data uniformly use JSON code blocks** to ensure consistent cross-model parsing:

```json
{
  "order_id": "20240310-0001",
  "status": "pending_payment",
  "expires_at": "2024-03-10T12:30:00Z"
}
```

> JSON is the most stable code block format for mainstream model parsing; all models can parse it correctly.

**Mermaid flowcharts (optional)**: Allowed for complex flows; but different models have different rendering support for Mermaid, so when using them, **also include a simplified text flow description as a fallback**, ensuring readers/models that don't support Mermaid can still understand.

#### 3.5.5 Constraint marker specification

Constraint markers use a three-level system: [MUST] / [SHOULD] / [MAY]:

- `[MUST]`: Absolutely must-obey rules; violation leads to unacceptable system state or feature failure
- `[SHOULD]`: Strongly recommended to obey; can be exempted after evaluation in specific scenarios
- `[MAY]`: Allowed but not mandatory; whether to use is decided by module or feature team

```markdown
- [MUST] C-100 Order API P99 response time ≤ 300ms
- [SHOULD] S-100 Implement exponential backoff retry
- Developers [MAY] choose to use sync or async implementation
```

**Constraint IDs (tracking mechanism)**: To support mechanical coverage verification of "[MUST] constraints → test cases" (see §3.8.3 gate G4), constraints need unique identifiers:

- ID prefix corresponds one-to-one with constraint level: `C-` (Constraint, must level) for `[MUST]`, `S-` (Should, suggestion level) for `[SHOULD]`, `[MAY]` not numbered; `[MUST]` **must be** numbered (e.g., `C-101`), `[SHOULD]` optional (recommended, e.g., `S-101`)
- IDs are unique within the owning document; cross-document references use complete form, written by introducing level: top-level `<doc_type>@project-charter:C-101`, module-level `<doc_type>@<module-name>:C-101`, feature-level `<doc_type>@<module-name>.<feature-name>:C-101` (e.g., `feature-design@order.order-timeout-cancel:C-101`)
- **Numbering is only unique within the owning document, not globally**: the same number in different documents (both called `C-101`) is legal; cross-document references **must** carry the document prefix or they cannot be located
- **Recommend each document use a fixed number range**, for humans and tools to identify source at a glance (numbering still unique only within document): `non_functional_constraints` C-1xx~C-5xx (divided by §Performance / §Security / §Coding Standards / §Platform Compatibility / §Third-Party Dependency), `inter_module_contract` C-6xx, `architecture` C-7xx, `domain_model` C-8xx, `integration` C-9xx, `global_policies` and `feature_design` C-1xx (policy level and feature level each start from 101)
- IDs bind to constraint entries not content: modifying constraint content preserves the ID (with version increment); deleting a constraint invalidates its ID and it is not reused

```markdown
- [MUST] C-101 Scan cycle ≤ 5 minutes
- [MUST] C-102 Cancellation and stock release atomic execution (same transaction)
- [SHOULD] S-101 Timeout notification completed within 1 minute
```

**Meaning of constraint levels**:
- **For developers**: [MUST] is the red line in code review — direct rejection on violation; [SHOULD] is a rule where deviation must be explained
- **For AI**: Constraint markers are hard boundary conditions when generating code; AI should translate them into assertions/configurations/validation logic in code
- **For reviewers**: Constraint markers give reviewers a basis, reducing disputes like "is this required or optional"
- **For tests**: [MUST] constraints should have corresponding case coverage in unit tests (language-agnostic GWT cases suffice, no specific code assertions required)

#### 3.5.6 Unit test specification

Each test case uses GWT (Given-When-Then) structure, language-agnostic and purely descriptive:

```markdown
### Test case: <case name>

Covers constraints: [referenced constraint IDs, e.g., C-101; omit if none]

#### Given prerequisites
[Describe input state, prerequisite data]

#### When trigger action
[Which function to call, with what parameters; function names reference §"Function Call Relationships" of feature-design.md (§3.5.10)]

#### Then expected result
- [Expected return value / state change / exception]
```

> Scenarios declare their validated constraint IDs via the "Covers constraints" line (syntax see §3.5.5); tools mechanically verify that "each numbered [MUST] constraint is referenced by at least one scenario" (gate G4, see §3.8.3).

#### 3.5.7 Version dependency management

**depends_on declaration format** (below using `architecture.md` depending on top-level docs as example):

```yaml
depends_on:
  - doc: global-policies.md
    module: project-charter
    version: "2.0.0"
  - doc: non-functional-constraints.md
    module: project-charter
    version: "1.3.0"
```

**Version consistency rules**:

- Execute version number increment each time a document is **modified**; increment level judgment criteria:
  - `patch`: fix typos, clarify wording, content meaning unchanged
  - `minor`: add/remove sections, supplement constraints or test scenarios, backward compatible
  - `major`: rewrite main body, change core definitions or constraints, not backward compatible
- When a depended-on document has a `minor` or above version change, dependents should evaluate whether to update their own `depends_on` and increment version; only `patch` changes are not mandatory
- Use exact version numbers when referencing depended-on documents in `depends_on`

**Validation rules**:

| Scenario | Allowed? | Description |
|----------|----------|-------------|
| Dependency on non-existent doc (combination of `doc` + `module` does not exist) | ❌ Prohibited | Tool should validate whether doc + module combination exists on save |
| Dependency version number does not follow semantic versioning convention | ⚠️ Warning | Recommended to follow major.minor.patch format |
| Lower-level doc depends on higher-level doc | ✅ Allowed | feature depends on module, module depends on top |
| Higher-level doc reverse-depends on lower-level doc | ❌ Prohibited | top should not depend on module or feature |
| Dependency direction forms a cycle | ❌ Prohibited | Tool should detect circular dependency on update |

#### 3.5.8 Acceptance test specification

Acceptance test documents are written in Gherkin format.

**File organization**: **One** `acceptance-tests.md` per feature directory, all scenarios written into the same file (filename corresponds one-to-one with `doc_type`, see §3.6.3); when there are too many scenarios, appropriately reduce scenario description granularity rather than splitting filenames.

```gherkin
# language: zh-CN
功能: 订单超时自动取消
  作为 <角色>
  我希望 <功能目标>
  以便 <业务价值>

  场景: <场景名>
    假设 <前置条件>
    当 <触发事件>
    那么 <预期结果>
    并且 <预期结果2>
```

**Keyword set**: `功能 / 作为 / 我希望 / 以便 / 场景 / 假设 / 当 / 那么 / 并且`; when a scenario has multiple expected results, use "并且" to list them one by one (do not open a new scenario).

#### 3.5.9 Implementation mapping specification (Spec → code)

Implementation mapping declares the implementation location corresponding to Spec documents (`implemented_in`), for AI to locate implementations and verify consistency between docs and implementation. Mapping direction is one-way: docs point to code; code side does not do any reverse annotation.

**Mapping carrier**:

- Doc side: feature-level doc frontmatter declares `implemented_in` (conditional field, see §3.5.2):

```yaml
implemented_in:
  - path: src/order/features/timeout_cancel/
    lang: go
```

- Test side: test functions are named by scenario (`TestCancelExpiredOrders` ↔ scenario "expired orders are scanned"), relying on naming convention + AI cross-reference, no mechanical annotation required

**Mapping granularity**:

| Granularity | Doc side | Code side | Purpose | Level |
|-------------|----------|-----------|---------|-------|
| Feature-level | `implemented_in` of `feature-design.md` | Feature implementation source directory/file | AI locates implementation, change impact analysis | [MUST] |
| Case-level | Test scenario name in `unit-tests.md` | Test function/method (naming convention) | Constraint coverage tracking (see §3.8.3 gate G4) | [SHOULD] |
| Contract-level | Interface name in `inter-module-contracts.md` | RPC method / API endpoint | Contract implementation verification | [MAY] |

**Validation rules**:

- Path declared in `implemented_in` must actually exist, otherwise alert (Spec declares implementation but code is missing)
- Optional: based on git history, remind review of corresponding Spec version when path pointed to by `implemented_in` changes

> Division of labor with `depends_on`: `depends_on` is dependency within the doc domain (doc ↔ doc); implementation mapping is cross-domain linking (doc → code); the two dimensions are orthogonal and both indispensable — the former ensures docs are self-consistent, the latter ensures docs match implementation.

#### 3.5.10 Function call relationship specification (bridge from design to coding)

Function call relationship is an inherent section of `feature-design.md` (§3.3.2), describing the **function-level static structure** of a single feature — function signatures and call relationships, complementing the last step between behavioral spec and code implementation: `implemented_in` locates where the code lands (Where); function call relationship designs how the code is organized (static skeleton of How).

**Positioning and boundaries**:

- Only design **function boundaries** (function name + input/output + responsibility + call chain); do not write function bodies, branches, loops, or pseudocode — implementation code belongs in source files declared by `implemented_in` (§3.5.9).
- Only describe **internal** function calls of this feature; cross-component/cross-module calls belong in `architecture.md` (component relationships) and `inter-module-contracts.md` (interface contracts).
- Link with `unit-tests.md`: `When trigger action` in unit tests should reference function names from this section, giving an authoritative source for "which function to test" (§3.5.6).

**Signature expression**:

- Signatures are expressed in the language declared by `implemented_in`; when no language is declared, use language-agnostic pseudosignatures (e.g., `(samples []Sample, threshold float64) → TripCmd`).
- Mark entry functions as "entry"; the "Calls" column lists called function names, or `—` if none.

**Format**:

```markdown
### Function call relationships

| Function | Signature | Responsibility | Calls |
|----------|-----------|----------------|-------|
| detectOverVoltage | (samples []Sample, threshold float64) → TripCmd | Voltage over-limit detection (entry) | evaluateThreshold, issueTrip |
| evaluateThreshold | (samples []Sample, threshold float64) → bool | Determine if sample value exceeds limit | — |
| issueTrip | (cmd TripCmd) → error | Generate and send trip message | — |
```

> Complex call chains can be supplemented with mermaid `flowchart` code blocks; each step in "Processing Flow" should map to one or more functions in the table.

### 3.6 Document Type Registry

This section completely enumerates the 15 document types defined in this system, clarifying the responsibility, level ownership, version strategy, and dependency rules for each type.

#### 3.6.1 Level 0: Project Charter

| ID | doc_type | Filename | Required? | Responsibility | Version strategy | Dependable targets | Writing order |
|----|----------|----------|-----------|----------------|------------------|--------------------|---------------|
| T-01 | `business_context` | business-context.md | ✅ Required | Why the project exists: business context, motivation, target users | Increment when business direction adjusts | (None, top-level entry) | 1st |
| T-02 | `technical_framework` | technical-framework.md | ✅ Required | Global tech stack convention: language, frameworks, middleware | Increment when tech stack changes | T-01 | 2nd |
| T-03 | `non_functional_constraints` | non-functional-constraints.md | ✅ Required | Non-breakable baselines: performance metrics, compliance requirements, hardware limits | Increment when constraints added/modified | T-01, T-02 | 3rd |
| T-04 | `global_policies` | global-policies.md | ✅ Required | Cross-module global policies: authentication, observability, data consistency | Increment when global policies change | T-01, T-02, T-03 | 4th |
| T-05 | `inter_module_contract` | inter-module-contracts.md | Recommended | Inter-module interface specs: request/response format, shared events, data structures | Increment when interfaces change | T-04, T-02 | 5th |
| T-06 | `stakeholders` | stakeholders.md | Optional | Stakeholder analysis: roles, concerns, decision authority | Increment when stakeholders change | T-01 | 6th |
| T-15 | `release_policy` | release-policy.md | Recommended | Release domain authoritative definition: release state, release unit, gates, pipeline, release number, rollback strategy (see §3.8) | Increment when gates/process change | T-01, T-02, T-03, T-05 | 15th |

#### 3.6.2 Level 1: Module Layer

| ID | doc_type | Filename | Required? | Responsibility | Version strategy | Dependable targets | Writing order |
|----|----------|----------|-----------|----------------|------------------|--------------------|---------------|
| T-07 | `architecture` | architecture.md | ✅ Required | Module component division, responsibilities, inter-component relationships, key flows | Increment when architecture adjusts | T-01~T-06 | 7th |
| T-08 | `domain_model` | domain-model.md | ✅ Required | Domain entities, value objects, aggregate roots, their relationship constraints | Increment when domain model changes | T-07 | 8th |
| T-09 | `integration` | integration.md | Optional | External system dependencies: protocols, data flows, degradation strategies | Increment when external integration changes | T-07 | 9th |
| T-10 | `module_manifest` | module-manifest.md | ✅ Required | Declaration of module's external capabilities (exports) and capability dependencies (imports); import/export must pair | Increment when exports/imports change | T-07, T-08 | 10th |

#### 3.6.3 Level 2: Feature Layer

| ID | doc_type | Filename | Required? | Responsibility | Version strategy | Dependable targets | Writing order |
|----|----------|----------|-----------|----------------|------------------|--------------------|---------------|
| T-11 | `feature_design` | feature-design.md | ✅ Required | Feature behavioral spec: prerequisites, trigger conditions, processing flow, exception paths, boundary constraints, function call relationships | Increment when feature spec changes | T-07, T-08 | 11th |
| T-12 | `decision_log` | decision-log.md | ✅ Required | Key design decisions: problem, background, option comparison, selection rationale (append, never overwrite) | Increment when decisions change | T-11 | 12th |
| T-13 | `unit_test` | unit-tests.md | ✅ Required | Unit-level code correctness verification | Increment when test cases change | T-11 | 13th |
| T-14 | `acceptance_test` | acceptance-tests.md | ✅ Required | BDD acceptance scenarios: business behavior verification | Increment when acceptance scenarios change | T-11, T-12 | 14th |

#### 3.6.4 Dependency relationship illustration

```
Dependency direction (top-down = forward dependency):
business context → technical framework → non-functional constraints → global policies → inter-module contracts → architecture design → domain model → feature design
                                                                          ├─→ decision log
                                                                          └─→ unit tests / acceptance tests
```

**Constraint relationships** (not dependency chain, cross-layer guidance relationship):

- Non-functional constraints **guide** global policies: global policies must not break constraint baselines from `non-functional-constraints.md`
- Global policies **constrain** module design: `architecture.md` / `domain-model.md` must follow global conventions from `global-policies.md`
- Feature design **defines** constraints, decision log **records** rationale, unit tests / acceptance tests **verify** implementation

> Note: This diagram represents the **primary dependency chain** (adjacent items are direct dependencies); each document type's complete "dependable targets" follow the registries in §3.6.1~§3.6.3 (e.g., `unit_test` only depends on `feature_design`, `acceptance_test` depends on `feature_design` and `decision_log`).

### 3.7 Lifecycle Management Specification

Documents evolve with the project; some gradually become obsolete. This system defines a three-state lifecycle to prevent zombie document accumulation.

#### 3.7.1 Three-state definitions

```
State machine:
══════════════════════════════════════════════════

              Deprecate                Archive
  ┌─────────┐  ──────────→ ┌─────────┐  ──────────→ ┌─────────┐
  │  Active │              │ Deprec. │              │  Arch.  │
  │ Active  │              │ Deprecated│             │ Archived│
  └─────────┘              └─────────┘              └─────────┘

Rollback paths (arrows not shown in diagram; both rollbacks are manual operations, change back to `active` then clean up deprecation/archive related fields per §3.5.2):
- Deprec. → Active: Undo deprecation (re-evaluate and confirm still applicable)
- Arch. → Active: Restore to active (must review content for needed updates before restoring)
```

| State | frontmatter value | Meaning | Trigger condition |
|-------|-------------------|---------|-------------------|
| Active | `active` | Document is currently valid, participates in all checks | Default for new docs |
| Deprecated | `deprecated` | Document no longer recommended for use, but historical references still need maintenance | Replaced by new version, design is outdated |
| Archived | `archived` | Document removed from dynamic index, for historical reference only | Exceeded cleanup period after deprecation, confirmed no longer needed |

#### 3.7.2 Meaning of each state

**active**
- Document content is consistent with the project's current design; it is a trusted source
- All readers (humans / AI) should treat this as authoritative
- Dependents can safely reference it; handle version changes per version management process

**deprecated**
- Document content is outdated and no longer represents the project's current design
- New readers should avoid directly referencing this document; existing dependents should evaluate whether to migrate
- When setting deprecated status, the deprecation reason (`deprecated_reason`) must be declared; **when there is a replacement document, `superseded_by` must be filled**; can be omitted when there is no replacement

**archived**
- Document is for historical tracing only, no longer participates in daily dependency checks and version notifications
- Before archiving, confirm all dependents have completed migration
- Can be restored to active when needed, but content should be reviewed for needed updates after restoration

#### 3.7.3 Deprecation operation guide

Deprecating a document should follow these steps:

1. **Confirm deprecation** — Confirm the document content truly no longer applies, and determine replacement doc (if any)
2. **Update frontmatter** — Change `status` to `deprecated`, fill in `deprecated_at`, `deprecated_reason` (fill in `superseded_by` when there is a replacement document)
3. **Notify dependents** — Contact all teams or module leads that directly reference this document, inform of deprecation reason and alternative
4. **Dependent response** — After dependents review changes, they can choose:
   a) Update their own `depends_on` to point to the replacement document
   b) Their own content is simultaneously marked as `deprecated`
   c) After evaluation, confirm they are not affected and do nothing

#### 3.7.4 Archive and deletion strategy

**Archive (recommended)**
- File stays on disk, status marked as `archived`, content available for historical audit or retrospective reference
- Can be restored to `active` at any time, but content should be reviewed for needed updates after restoration
- Applicable scenario: design is outdated but has historical reference value

**Delete (with caution)**
- File completely removed, information needs to be traced back through version control
- Only applicable for creation errors or completely invalid content scenarios
- Recommend using archive first; deletion should be the last resort

**Cleanup cadence**
- Periodically review the validity of all `active` documents
- Documents that no longer apply are preferentially marked as `deprecated`
- Those with `deprecated` status for a certain period (e.g., 6 months) and confirmed to have no dependents can transition to `archived`

### 3.8 Release Domain (AICoding CI/CD)

§3.7 manages the **content dimension** of documents — whether a document is credible (active / deprecated / archived). Beyond content credibility there is a **go-live dimension** — whether a credible document can enter production environment; this section answers the latter. Traditional CI/CD pipeline objects are code (build → test → deploy); this system's release pipeline objects are **Spec** — release is not "deploy code once" but "advance a set of Specs to released status"; code, tests, deploy configs, change logs are all generated as **derivative artifacts** at that status. This is consistent with the conclusion "Spec is asset": Spec is the sole authority, release is the solidification of Spec status.

#### 3.8.1 Release state machine

Release state measures **go-live readiness**, orthogonal to the content lifecycle in §3.7 — a document can be active but not yet pass release gates:

```
draft → in-review → ready → released → superseded
```

#### 3.8.2 Release unit

Minimum release unit = **one feature (4 documents under `features/<feature-name>/`) + its `depends_on` dependency chain**. Modifying one feature only releases the version of that feature and its dependency documents, not the entire repo — analogous to "changing one module only triggers that module's CI".

#### 3.8.3 Release gates

| Gate | What to check | Mechanism |
|------|--------------|-----------|
| G1 Doc health | All docs in release unit are `active`, no deprecated blockers | §3.7 |
| G2 Dependency consistency | `depends_on` exact version, no drift/cycle/reverse dependencies | §3.5.7 |
| G3 Contract closure | imports ↔ exports paired, no dangling contract interfaces | §3.2.2 |
| G4 Constraint coverage | Each numbered [MUST] constraint in `feature-design.md` §Boundary Constraints **within the release unit** (e.g., `C-101`) has a corresponding scenario reference in unit-tests.md; numbered constraints in top-level/module-level docs are not included in G4 | §3.5.5, §3.5.6 |
| G5 Tests green | unit-tests + acceptance-tests execute successfully | §3.3.3 |
| G6 Implementation mapping | Implementation path declared in `implemented_in` actually exists | §3.5.9 |

#### 3.8.4 Release pipeline

```
Spec change committed
  → P0 Change detection: diff locates changed docs, auto-suggests version increment, identifies release unit
  → P1 Static gates: G1 / G2 / G3 / G4 / G6 (no code execution)
  → P2 Dynamic gates: G5 (execute tests; AI generates/fixes tests)
  → P3 Artifact generation: generate release-manifest, change log, deploy config snapshot
  → P4 Release validation: acceptance tests run on deploy environment (smoke test)
  → P5 Solidification: document status set to released, release-manifest archived
Any step failure → revert to corresponding phase for repair (AI repair, exception decisions go to human)
```

#### 3.8.5 Tiered applicability

- **Small projects / startup phase**: use default gate values, release = pass G1/G2/G3/G5 minimum gates
- **Formal projects**: enable all G4/G6 gates, document `release-policy.md`

## Conclusion: Toward an Era Where Spec Is Asset

The birth of this documentation system stems from one judgment: **with the large-scale application of AI Coding, the production relations of software development are undergoing fundamental transformation.**

### Spec is asset

In the traditional view, source code is the core asset of an enterprise, and documentation is auxiliary explanation. But today, when AI can understand structured specs and directly generate high-quality code, this relationship is reversing — **spec-style documents (Spec) will become the mainstream carrier of project delivery, and source code will retreat to being one of the derivative artifacts from Spec.**

This is fundamentally different from traditional "document-driven development": document-driven development treats writing docs as preparation before coding; code is still the final deliverable. The design premise of this system is that **Spec itself is the deliverable** — it is structured, versioned, verifiable, and can be accurately parsed by AI to generate code, test cases, deploy configs. When business logic changes, modify the Spec rather than the code, and AI automatically syncs derivatives.

This means the team's knowledge assets will settle at the Spec layer rather than scatter in each person's coding habits. The documentation system no longer serves the purpose of "writing knowledge down for people to read" — it becomes the **Single Source of Truth for project facts**.

### From specification to discipline

In the current system, version number increment, dependency declaration, and status management still require manual completion. The real challenge lies in embedding these operations into daily engineering workflows — validating version consistency in PR reviews, detecting dependency drift in CI, automatically analyzing impact scope before changes. When documentation maintenance becomes engineering discipline rather than an extra burden, the system's value can be fully unleashed.

### From passive reference to active assistance

depends_on, level dependencies, and exact version locking give the documentation system structured semantics. This is not just a directory for humans to read — it is a **knowledge graph** that AI can understand. On this basis, the documentation system's capability boundary will extend from "storing knowledge for query" to "actively prompting inconsistencies", "analyzing change impact", "auto-generating test scenarios" — evolving from static reference to dynamic engineering partner.

### From single project to organizational asset

When multiple projects adopt the same set of specifications, the technical frameworks, cross-cutting concerns, and inter-module contracts in top-level documents become reusable organizational-level knowledge assets. New projects can inherit existing specs, new members can quickly integrate under a unified framework, and team experience no longer dissipates with personnel turnover.

---

This system is not the end — it is the starting point. Its value does not depend on how perfectly it is designed, but on whether the team can persist in using it to build, deliver, and evolve real projects. **The era where Spec is asset is coming, and this system provides an actionable roadmap for embracing that era.**
