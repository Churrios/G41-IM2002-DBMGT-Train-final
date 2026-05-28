# IM2002 Database Management — Assessment Overview

## Project: TransitFlow

You will implement three databases that power a pre-built LLM+RAG transit assistant. **Team size:** 3-4 students. **Deliverables:** Four separate submissions.

| Deliverable | Who submits | What to submit |
|-------------|-------------|----------------|
| **Code Repository** | Team | GitHub repo link |
| **Design Document** | Team | Markdown via EEClass |
| **Work Allocation Report** | Team | Completed `WORK_ALLOCATION_TEMPLATE.md` via EEClass |
| **Peer Review Report** | Each member individually | Completed `PEER_REVIEW_TEMPLATE.md` via EEClass (confidential) |

---

## Three Separate Marking Schemes — Each /100

Your submission is graded across three independent components. Each is scored out of 100
and tallied separately. The weighting between components is set by the instructor.

| Component | Guide | What is assessed |
|-----------|-------|-----------------|
| **Static Code** | [STUDENT_GUIDE_CODE.md](STUDENT_GUIDE_CODE.md) | Schema design, query functions, seeding, graph design, code quality |
| **Design Document** | [STUDENT_GUIDE_DOC.md](STUDENT_GUIDE_DOC.md) | ER diagram, normalisation, graph rationale, RAG design, AI usage, reflection |
| **Live Testing** | [STUDENT_GUIDE_LIVE.md](STUDENT_GUIDE_LIVE.md) | Seeding runtime, PostgreSQL query outputs, Neo4j routing outputs |

Read each guide carefully — it explains exactly what is assessed and what earns full marks
for that component.

---

## Task 6 — Optional Extension Bonus · up to +15 per component

Each of the three components has its own independent +15 bonus. You can earn up to +45
across all three if all components are satisfied.

| Component | Bonus | What is graded |
|-----------|-------|----------------|
| Static Code | up to +15 | Code implementation quality, end-to-end functionality, comments |
| Design Document | up to +15 | Section 7: motivation, schema changes, example queries, testing evidence |
| Live Testing | up to +15 | Live demo, database correctness, regression-free integration |

To be eligible for the bonus in **any** component, all four of the following must be present:

1. The extension touches database code — new schema, queries, or seed data. UI-only changes do not count.
2. Detailed inline comments explain every new database operation.
3. A **Section 7** in your design document covering motivation, changes, example queries, and testing evidence.
4. A **`TASK6.md`** file at the repo root listing every file modified or added, with specific function and table names. Each modified file must also have a `# TASK 6 EXTENSION:` comment near the top.

---

## Individual Contribution Adjustment

The Static Code score is a team score by default, but each member's individual mark may be
adjusted up or down based on their actual contribution. TAs assess contribution using three
sources of evidence:

- **Work Allocation Report** — your team's self-reported breakdown of who did what
- **Peer Review Reports** — confidential assessments submitted individually by each member
- **GitHub commit history** — commit frequency, volume, and scope per author

If the evidence consistently shows that a member contributed significantly less than their
allocation, their Static Code mark is reduced. If the evidence shows a member consistently
exceeded their allocation, a small upward adjustment is possible.

The Design Document and Live Testing scores are not individually adjusted — they are shared
equally across all team members.
