# prompt_T2 — Competition Judging, Balanced Assignment, and Hierarchical Crowd-BT

crowd_bt_architecture_poc_corrected.md — the mathematical/model reference

## Objective

Implement the competition judging workflow end-to-end in the existing application.

This task has two major parts:

1. **Judging operations**
   - Organizer/admin rubric creation.
   - Judge assignment and removal.
   - Balanced project-to-judge assignment.
   - Rolling or batch assignment.
   - Judging deadlines and judging lifecycle.
   - Judge scoring against weighted rubrics.

2. **Final ranking**
   - Collapse each judge's rubric evaluation for a project into one weighted score.
   - Convert each judge's evaluated projects into within-judge pairwise preferences.
   - Feed the pairwise preferences into a hierarchical Bayesian Crowd-Bradley–Terry model.
   - Estimate project latent strength and judge reliability.
   - Produce the final project ranking.

The architecture described below is the source of truth for the ranking model. The important correction is that **raw score differences must NOT be used as cross-judge evidence weights**.

The existing architecture document establishes that the core signal is pairwise ordering, with unit-weighted non-tied comparisons, while judge reliability is modeled separately. It also defines the reliability prior flow as historical performance → historical posterior → current prior → current posterior. See the corrected architecture and POC for the detailed formulation. fileciteturn2file0L47-L68 fileciteturn2file0L71-L97

---

# 1. First: Inspect the Existing Codebase

Before changing code:

1. Inspect the repository structure.
2. Identify:
   - competition/event models
   - project/submission models
   - organizer/admin authorization
   - judge models
   - existing judge assignment logic
   - registration/submission deadlines
   - existing scoring/rubric code
   - database migrations
   - API routes/controllers
   - frontend pages/components
   - background jobs/tasks, if any
3. Reuse existing architecture and conventions.
4. Do not introduce a new framework or duplicate an existing service.
5. Do not rewrite unrelated functionality.
6. Determine whether equivalent fields already exist before adding new database fields.
7. Follow the existing project's naming, validation, error handling, authentication, and API conventions.
8. Run the existing test suite before making changes if one exists.

Do not start by blindly creating new models. First understand how the current competition workflow is represented.

---

# 2. Competition Rubrics / Criteria

Organizers and admins must be able to define the rubric used by judges for a competition.

A competition may contain multiple rubric criteria.

Each criterion should have at least:

- id
- competition id
- name
- description/instructions for the judge
- weight
- display/order position
- active/deleted state if the existing application uses soft deletion

Example:

```text
Functionality     40%
Quality            35%
Innovation        25%
```

## Weight rules

- A criterion weight is represented as a percentage from `0` to `100`.
- If no explicit weights are configured, all criteria are equally weighted.
- Do not assume the hard-coded example weights above are universal. They are only the POC configuration.
- The actual competition rubric must come from the organizer/admin configuration.

If the current application already has a rubric/criteria abstraction, extend it rather than creating a parallel one.

If explicit weights are used, validate them consistently. If the existing product semantics require weights to total 100%, enforce that. If the existing design allows arbitrary nonzero weights, normalize them internally before calculating the weighted score.

Do not silently assign arbitrary weights.

## Permissions

Only authorized organizers/admins may:

- create criteria
- edit criteria before judging begins
- remove/deactivate criteria
- configure weights

Judges must only be able to view the rubric and submit scores against it.

Participants must not be able to modify judging criteria.

---

# 3. Judge Management

Organizers/admins can:

- assign judges to a competition
- remove judges from a competition
- view judges assigned to the competition
- view current assignment/load information

A judge can only judge competitions to which they are assigned.

## Removing a Judge

When a judge is removed:

1. Find all projects currently assigned to that judge.
2. Determine which assignments are incomplete.
3. Reassign those projects to eligible remaining judges.
4. Preserve the target number of judges per project.
5. Do not create duplicate assignments for the same judge/project.
6. Do not assign a project to an ineligible/inactive judge.
7. Preserve an audit trail of the old assignment and the reassignment.

Do not silently delete historical records.

If a removed judge already submitted scores, preserve those records according to the application's audit/data-retention rules. Do not silently overwrite or destroy submitted judging data.

The implementation must distinguish at least:

```text
ASSIGNED
IN_PROGRESS
COMPLETED
REVOKED/REMOVED
```

Use the existing status system if one already exists.

---

# 4. Balanced Judge Assignment

The system must distribute projects among judges in a balanced manner.

The goal is not simply random assignment.

The assignment system should account for **current utilization/load**.

The basic principle is:

> Judges with lower current utilization should receive new assignments before judges with higher utilization.

This should operate continuously when rolling assignment is enabled.

## What counts as utilization

Use the application's actual assignment state rather than only counting completed scores.

At minimum, track:

```text
active assigned projects
completed judging assignments
total assignment load
```

The exact utilization metric should be implemented in a way that makes sense with the existing schema.

A useful baseline is:

```text
current_load_j = number of active/incomplete projects assigned to judge j
```

Then prefer judges with lower current load.

Do not simply alternate judges in a fixed round-robin sequence because that can become unbalanced when submissions arrive unevenly or judges are removed.

## Assignment constraints

When assigning a project:

- only active competition judges are eligible
- do not assign the same project twice to the same judge
- respect the configured target number of judges per project
- prefer judges with lower current load
- preserve already-completed judging work
- avoid assigning new work to a judge who has been removed/inactivated
- handle ties deterministically or with a stable secondary rule

If the existing system already has a configured number of judges per project, reuse it.

If it does not, identify the correct place to introduce a competition-level configuration rather than hard-coding a number inside the assignment algorithm.

---

# 5. Rolling Assignment vs Batch Assignment

The organizer/admin must be able to choose whether judging assignments happen continuously while submissions are arriving.

Add/use a competition-level setting equivalent to:

```text
rolling_judging = true | false
```

Use the project's existing naming conventions if an equivalent field already exists.

## Rolling = ON

When a valid project submission arrives:

1. The submission becomes eligible for judging.
2. The assignment service evaluates current judge utilization.
3. The project is assigned to the required number of judges.
4. Multiple judges may receive the same project.
5. Assignment should happen without waiting for the submission deadline.
6. As additional submissions arrive, repeat the same balanced assignment process.

Example:

```text
Project A submitted
    ↓
Judge 1 + Judge 4 assigned

Project B submitted
    ↓
Judge 2 + Judge 5 assigned

Project C submitted
    ↓
Judge 1 + Judge 3 assigned
```

The exact number of judges per project must come from competition configuration.

## Rolling = OFF

Do not assign projects immediately after submission.

When the submission deadline closes:

1. collect all eligible submissions
2. calculate the assignment plan
3. balance the load across eligible judges
4. assign the projects in one batch

This is the "one big assignment" mode.

---

# 6. Assignment Algorithm

Implement the assignment logic as a dedicated service/module rather than embedding it inside an API route.

The service should support:

```text
assign_project(project_id)
assign_all_pending_projects(competition_id)
reassign_removed_judge_projects(competition_id, removed_judge_id)
rebalance_assignments(competition_id)
```

Use transactions/locking where necessary so simultaneous submissions cannot produce duplicate or over-capacity assignments.

## Baseline selection logic

For every required judge slot:

1. Build the eligible judge set.
2. Remove judges already assigned to the project.
3. Remove inactive/removed judges.
4. Calculate each judge's current load.
5. Sort/select judges by lowest current load.
6. Use a stable secondary tie-breaker.
7. Assign the project.
8. Update the effective load before selecting the next slot.

The algorithm must account for the assignment being created during the same operation.

Do not calculate all slots from a stale load snapshot.

---

# 7. Submission and Judging Deadlines

The competition has two important stages:

```text
Submission Deadline
        ↓
Judging Period
        ↓
Judging Deadline
        ↓
Final Calculation
```

The submission deadline controls when projects stop entering the competition.

The judging deadline controls when judges must finish scoring.

## Important rule

The final Crowd-BT calculation must not run before the judging period closes.

After the judging deadline:

1. stop accepting judge scores
2. finalize eligible judging records
3. collect completed rubric evaluations
4. calculate weighted project scores
5. generate pairwise preferences
6. run the hierarchical Bayesian Crowd-BT model
7. calculate the final project latent strengths
8. generate the final ranking
9. store the model run/results for auditability

If the existing competition state machine already handles deadlines, extend it rather than creating a second independent lifecycle.

---

# 8. Judge Scoring

A judge sees only projects assigned to them.

For every assigned project:

1. display the project/PPT
2. display the competition rubric
3. allow the judge to enter a score for every criterion
4. validate criterion scores
5. calculate/display the weighted total
6. allow submission/finalization of the judging result

Do not allow the judge to alter the criterion weights.

The weighted project score for judge `j` and project `i` is:

```text
Sᵢⱼ = Σₖ wₖ × scoreᵢⱼₖ
```

where:

- `wₖ` is the normalized rubric weight
- `scoreᵢⱼₖ` is judge `j`'s score for project `i` on criterion `k`

The resulting weighted score is local to that judge.

Do not compare raw weighted scores across different judges as though they were directly calibrated absolute measurements.

---

# 9. Pairwise Preference Generation

After the judging deadline closes, generate pairwise comparisons separately for each judge.

For every judge:

```text
Judge J evaluated:
Project A
Project B
Project C
Project D
```

Generate:

```text
A vs B
A vs C
A vs D
B vs C
B vs D
C vs D
```

For each pair:

```text
if S(A,J) > S(B,J):
    A wins
elif S(B,J) > S(A,J):
    B wins
else:
    tie / no preference
```

Ties must not be forced into an arbitrary winner.

For the corrected core model, every non-tied pairwise observation has:

```text
weight = 1
```

Do **NOT** use:

```text
1 + abs(S(A,J) - S(B,J))
```

Do **NOT** weight judges more heavily because they use a wider numerical scale.

This is a central architectural requirement.

The corrected architecture explicitly removes raw score-difference weighting because it would reintroduce cross-judge scale dependence. fileciteturn2file1L73-L97

---

# 10. Hierarchical Bayesian Crowd-Bradley–Terry

The ranking model uses project latent strength and judge reliability.

Each project has:

```text
θᵢ = latent project strength
```

For a pairwise comparison:

```text
P(A > B) = sigmoid(θ_A - θ_B)
```

With judge reliability:

```text
Pⱼ(A > B) = sigmoid(rⱼ(θ_A - θ_B))
```

where:

```text
rⱼ > 0
```

Use:

```text
rⱼ = exp(log_reliabilityⱼ)
```

The architecture treats reliability as discriminative trust.

Do not equate:

```text
strict judge = unreliable judge
lenient judge = reliable judge
```

Strictness and reliability are separate concepts.

The corrected architecture explicitly defines this distinction. fileciteturn2file0L71-L89

---

# 11. Historical Judge Reliability

New judges need a default reliability prior.

A judge who has participated in previous competitions should have historical evidence associated with them.

The Bayesian flow is:

```text
Historical Judge Performance
          ↓
Historical Reliability Posterior
          ↓
Current Competition Reliability Prior
          ↓
Current Competition Reliability Posterior
```

The hierarchical prior is:

```text
log rⱼ ~ Normal(μᵣ, σᵣ²)
```

For a completely new judge, use the system's configured neutral prior.

The POC used:

```text
μᵣ = 0
σᵣ = 0.60
```

which is equivalent to a prior centered at:

```text
r = 1
```

For an experienced judge, the previous competition's posterior should inform the current prior.

Do not simply store one hard-coded "reliability score" and treat it as truth. Store enough information to represent the Bayesian prior/posterior correctly.

If the existing database has no historical reliability storage, introduce an appropriate model/table rather than hiding historical reliability inside the current competition record.

---

# 12. Model Execution

The main model calculation occurs only after judging closes.

The calculation pipeline is:

```text
Completed Judge Rubric Scores
            ↓
Weighted Scores
            ↓
Within-Judge Pairwise Preferences
            ↓
Unit-Weighted Comparison Graph
            ↓
Hierarchical Bayesian Crowd-BT
            ↓
Project Latent Strength θ
            +
Judge Reliability r
            ↓
Final Project Ranking
```

The architecture requires the model to handle incomplete judge/project coverage.

A judge does not need to evaluate every project.

The combined pairwise graph must be sufficiently connected to infer a common latent ordering. Disconnected components cannot be directly placed on one common latent scale without additional linking comparisons. fileciteturn2file0L94-L97

---

# 13. Identifiability

Bradley–Terry latent strengths have a location ambiguity.

Adding the same constant to every `θ` does not change pairwise differences.

Therefore the implementation must use an identifiability constraint.

The POC fixes one project to:

```text
θ = 0
```

This does NOT mean that project has zero quality.

It is only the origin of the latent scale. fileciteturn2file0L90-L93

---

# 14. Result Storage

Do not calculate the ranking and then discard the intermediate data.

Persist enough information to reproduce and audit a model run.

At minimum, store:

## Model Run

- competition id
- model version
- execution timestamp
- model status
- prior configuration
- rubric configuration/version
- number of projects
- number of judges
- number of pairwise comparisons
- optimizer/inference status

## Project Result

- model run id
- project id
- latent strength `θ`
- final rank
- uncertainty fields when implemented

## Judge Result

- model run id
- judge id
- estimated reliability `r`
- posterior/prior information when applicable

## Pairwise Observation

- model run id
- judge id
- winner project id
- loser project id
- source evaluation ids
- observation weight
- tie status if applicable

The audit data should make it possible to trace:

```text
Final Rank
    ↓
Latent Strength
    ↓
Pairwise Preferences
    ↓
Judge Weighted Scores
    ↓
Original Rubric Scores
```

---

# 15. API Requirements

Inspect the existing API conventions first.

Implement the equivalent endpoints/services needed for:

### Organizer/Admin

- create competition rubric
- update rubric
- remove/deactivate rubric criterion
- configure criterion weights
- configure rolling judging
- view assigned judges
- assign judge
- remove judge
- trigger/retrigger assignment where appropriate
- view assignment utilization
- view judging status
- view final ranking
- view model run information

### Judge

- view assigned projects
- view rubric
- submit criterion scores
- finalize judging for a project
- view judging completion status

### System/Admin

- finalize judging after deadline
- generate pairwise comparisons
- execute Crowd-BT calculation
- persist model results

Do not expose internal model-calculation controls to participants.

---

# 16. Frontend Requirements

Reuse the existing UI patterns.

Organizer/admin UI should provide:

### Rubric Builder

```text
Criterion Name
Description
Weight
Order
Add Criterion
Edit
Remove
```

Show the resulting weight configuration clearly.

### Judge Assignment

Show:

```text
Judge
Active Load
Completed
Total Assigned
Utilization
Status
```

Provide:

```text
Assign
Remove
Reassign
```

### Rolling Judging

Provide a clear competition-level setting:

```text
Rolling Judging: ON / OFF
```

Explain the behavior in the UI:

- ON → submissions are assigned as they arrive.
- OFF → submissions are assigned in batch after the submission deadline.

### Judge View

Show:

```text
Assigned Projects
↓
Open Project
↓
Rubric
↓
Criterion Scores
↓
Weighted Total
↓
Submit
```

### Results

After judging closes, show:

```text
Rank
Project
Latent Strength
```

and, where appropriate:

```text
Judge Reliability
Model Run
Uncertainty
```

Do not expose raw internal Bayesian parameters to participants unless the existing product requirements call for it.

---

# 17. State and Lifecycle Requirements

Use the existing competition state model if possible.

The intended lifecycle is:

```text
DRAFT
  ↓
REGISTRATION/SUBMISSION OPEN
  ↓
SUBMISSION CLOSED
  ↓
JUDGING OPEN
  ↓
JUDGING CLOSED
  ↓
CALCULATING
  ↓
RESULTS READY
```

Rolling assignment affects when assignments are created. It does not change the requirement that final model calculation occurs after judging closes.

Ensure invalid state transitions are rejected.

Examples:

- cannot edit rubric after judging has started unless explicitly supported
- cannot submit a judge score after judging closes
- cannot assign removed judges
- cannot modify final model results without creating a new model run/version

---

# 18. Concurrency and Consistency

This workflow will have concurrent operations.

Examples:

- multiple projects submitted at the same time
- multiple admins assigning/removing judges
- a judge being removed while assignments are being processed
- judging submissions occurring near the judging deadline
- model calculation starting while a final judging submission is being processed

Use database transactions and appropriate locking/idempotency where required.

Assignment operations must be idempotent.

Calling:

```text
assign_project(project_id)
```

twice must not create duplicate judge/project assignments.

The same applies to batch assignment and reassignment.

---

# 19. Testing Requirements

Add tests for the important business rules.

## Rubrics

- create criterion
- edit criterion
- remove criterion
- zero weight validation
- invalid weight validation
- equal-weight fallback
- explicit weighted calculation

## Assignment

- balanced assignment
- no duplicate judge/project assignment
- required judges per project
- judge removal and reassignment
- inactive judge exclusion
- rolling assignment
- batch assignment
- concurrent assignment/idempotency

## Judging

- judge sees only assigned projects
- judge can score every criterion
- invalid scores rejected
- weighted total calculated correctly
- judging blocked after deadline
- judge cannot alter rubric weights

## Pairwise

- correct winner generation
- correct loser generation
- ties are not forced
- unit weight always equals `1`
- raw score margin does not affect pairwise weight
- judges with different score scales produce the same directional preference when ordering is the same

## Bayesian Model

At minimum test:

- project latent strengths are produced
- judge reliability is positive
- new judge receives neutral prior
- historical judge receives historical prior
- reference constraint is applied
- disconnected comparison graph is detected
- model run is persisted
- final ranking is reproducible from stored observations

---

# 20. Important Non-Goals

Do NOT:

- normalize every judge's absolute scores into a common scale as the primary ranking mechanism
- weight pairwise comparisons using raw score differences
- assume strict judges are unreliable
- assume lenient judges are reliable
- force tied scores into a winner
- require every judge to evaluate every project
- assign the same judge to the same project more than once
- silently delete judging history when a judge is removed
- calculate final results before judging closes
- hard-code the POC rubric weights as the production competition rubric
- hard-code a judge reliability value for every competition
- discard the intermediate pairwise/model data needed for auditability

The corrected architecture specifically removes raw score-difference weighting because it would reintroduce judge-scale dependence. fileciteturn2file0L47-L56

---

# 21. Reference POC

The corrected architecture was validated on a six-project subset:

```text
prj_02  Small Meadow
prj_03  Deep Compass
prj_04  Green Switch
prj_06  Dry Compass
prj_07  Dry Harbour
prj_12  Open Beacon
```

The corrected POC uses unit-weighted pairwise observations. The documented pairwise evidence and example MAP outputs are included in the architecture document. fileciteturn2file0L98-L145

The reference Python implementation follows this structure:

```text
fixtures.json
    ↓
weighted rubric scores
    ↓
within-judge pairwise comparisons
    ↓
weight = 1
    ↓
hierarchical Bayesian Crowd-BT
    ↓
project latent strength
+
judge reliability
```

The complete corrected implementation is included in the supplied architecture Markdown document, including the unit-weight comparison logic and model equations. fileciteturn2file1L377-L377 fileciteturn2file1L443-L471 fileciteturn2file1L519-L571

---

# 22. Implementation Order

Implement in this order so the feature can be tested incrementally:

### Phase 1 — Data Model

1. Inspect existing schema.
2. Add/extend rubric models.
3. Add/extend judge assignment models.
4. Add rolling judging configuration if missing.
5. Add assignment status/state if missing.
6. Add model-run/result persistence.
7. Add migrations.

### Phase 2 — Rubric Management

1. Organizer/admin rubric CRUD.
2. Weight validation.
3. Equal-weight fallback.
4. Rubric locking once judging starts, unless existing rules explicitly allow editing.

### Phase 3 — Judge Assignment

1. Eligible judge selection.
2. Load/utilization calculation.
3. Balanced assignment service.
4. Rolling assignment.
5. Batch assignment.
6. Judge removal/reassignment.
7. Transaction/idempotency handling.

### Phase 4 — Judge UI/API

1. Assigned project list.
2. Project judging screen.
3. Rubric display.
4. Criterion scoring.
5. Weighted total.
6. Score submission/finalization.

### Phase 5 — Judging Lifecycle

1. Submission deadline handling.
2. Judging deadline handling.
3. Prevent late scoring.
4. Trigger final calculation only after judging closes.

### Phase 6 — Pairwise Generator

1. Collect finalized scores.
2. Calculate weighted score per judge/project.
3. Generate all within-judge pairs.
4. Skip ties.
5. Assign unit weight `1`.
6. Persist pairwise observations.

### Phase 7 — Historical Reliability

1. Define historical reliability persistence.
2. Load prior for each judge.
3. Use neutral prior for new judges.
4. Convert historical posterior into current prior where historical data exists.

### Phase 8 — Crowd-BT

1. Implement latent project strengths.
2. Implement positive judge reliability.
3. Implement hierarchical prior.
4. Apply identifiability constraint.
5. Fit the model.
6. Persist model run.
7. Persist project results.
8. Persist judge reliability results.

### Phase 9 — Results

1. Generate final ranking.
2. Expose ranking API.
3. Build organizer/admin result view.
4. Add audit/debug information.
5. Add uncertainty fields when the inference implementation supports them.

### Phase 10 — Tests

Run the full existing test suite and add targeted tests for all requirements above.

---

# 23. Final Instruction to the Coding Agent

Do not treat this as a request to merely create a prototype disconnected from the existing application.

Integrate the workflow into the existing competition system.

Before coding, inspect the repository and identify the current architecture.

Then implement incrementally.

For every major change:

1. explain which existing files/models/routes are being reused
2. make the smallest coherent change
3. run relevant tests
4. fix regressions before moving on
5. keep database migrations reversible where practical
6. do not modify unrelated functionality

When the implementation is complete, report:

```text
Files changed
Database migrations
New API endpoints
New frontend components/pages
Assignment algorithm
Judging lifecycle changes
Pairwise generation logic
Bayesian model implementation
Historical reliability handling
Tests added
Tests passed
Known limitations
```

The critical mathematical invariant is:

```text
Judge Scores
    ↓
Judge-local weighted score
    ↓
Pairwise ordering
    ↓
UNIT-WEIGHTED pairwise observation
    ↓
Hierarchical Bayesian Crowd-BT
```

Do not reintroduce raw cross-judge score differences into the pairwise evidence weight.
