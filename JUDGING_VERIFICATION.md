# Judging Logic — Verification with Dummy Data

Read-only verification. No model code was changed. All tests ran against the live
stack (`docker compose up`) using freshly created probe events, or directly against
the shipped modules inside the `api` container.

Ground truth was known in advance: 6 projects with a fixed quality order
`p1 > p2 > p3 > p4 > p5 > p6`, scored by 6 judges.

---

## Verdict summary

| Component | Verdict | Evidence |
|---|---|---|
| `assign.py` (balanced assignment) | **WORKS** | spread = 0, every judge gets exactly `jpp` projects, no duplicates |
| `pairwise.py` (preferences) | **WORKS** | correct winners, ties dropped, unit weights, connectivity correct |
| `crowd_bt.py` (MAP fit) | **WORKS when connected** | exactly recovers the true ranking; theta monotonic |
| `judge.py` (scoring) | **WORKS** | weighted score math exact, draft→submit correct, peer isolation correct |
| `results.py` (end-to-end pipeline) | **BROKEN BY DEFAULT** | default `judges_per_project=2` → disconnected graph → 422 → **no ranking** |
| `crowd_bt.py` at event scale | **FAILS** | optimizer returns `success=False` at ≥40 projects → 500; 100 projects takes 25 min |

The four building blocks are individually correct. The **pipeline as configured
does not produce a final ranking**, because two design goals contradict each other —
and even when they are reconciled, the fitter does not converge at the event size the
spec itself defines.

---

## 1. `assign.py` — balanced assignment works

6 projects, 6 judges, `judges_per_project=2`, rolling ON:

```
amara.silva=2  anya.sokolova=2  bruno.costa=2
diego.herrera=2  dilan.yilmaz=2  emeka.adeyemi=2
spread = 0   (ideal is <= 1)
```

Every project got exactly 2 distinct judges, every judge got exactly 2 projects,
no duplicate `(judge, project)` pairs, deterministic tie-break by `user_id`.
Load balancing is correct.

## 2. `pairwise.py` — preference generation works

Scores `A=7, B=4, C=7, D=9` for one judge:

```
6 possible pairs -> 5 observations (A/C tied -> dropped)
D>A, D>B, D>C, A>B
all weights == 1.0, each pair carries 2 source evaluation ids
```

Ties produce no observation (never a forced winner). Weights are always 1.
Connectivity detection is correct: a chain `A-B, B-C, C-D` is one component;
`A|B` and `C|D` are two.

## 3. `crowd_bt.py` — the model recovers ground truth

Simulated judges with known `theta` and known reliability `r`, then fitted:

```
4 judges x 8 projects, full coverage:
  exact_order=True   top1_ok=True   tau=+1.000   r_order_ok=True
```

The model **exactly recovers** the true ranking and the true reliability ordering
when coverage is rich. Theta is monotonic in true quality.

Reliability estimates degrade as coverage thins — and become **anti-correlated**
with truth at the default configuration:

| Configuration | Kendall tau | r vs truth |
|---|---|---|
| 4 judges, 8 projects each | +1.000 | correlated |
| 4 judges, 4 projects each | +0.524 | **anti-correlated (-0.50)** |
| 4 judges, 2 projects each | +1.000 | **anti-correlated (-0.94)** |

At 2 projects per judge each judge contributes a single comparison, so `r` is
essentially the prior re-displayed — and points the wrong way.

## 4. `judge.py` — scoring works

Weighted score `S = 0.40*func + 0.35*qual + 0.25*innov` matches hand calculation
to 1e-12. Draft → submit is one-way and transactional. Peer isolation returns 403
for any id that is not the caller, with no oracle for unknown ids.

## 5. `results.py` — the pipeline is broken by default

This is the finding that matters. `assign.py` is explicitly designed to **spread**
judges evenly ("lowest active load first", "no stealing"). `crowd_bt.py` requires
projects to **share** judges to form a connected comparison graph. Balanced
assignment actively prevents connectivity.

Measured on the live stack, 6 projects / 6 judges:

| `judges_per_project` | evals | pairs | components | outcome |
|---:|---:|---:|---:|---|
| 2 (default) | 12 | 6 | 3 | **422 REFUSED** |
| 3 | 18 | 18 | 2 | **422 REFUSED** |
| 4 | 24 | 36 | 1 | RAN |
| 5 | 30 | 60 | 1 | RAN |
| 6 | 36 | 90 | 1 | RAN |

At `jpp=3` the balanced assignment splits the judges into two disjoint groups:

```
p1,p3,p5 <- amara.silva, diego.herrera, dilan.yilmaz
p2,p4,p6 <- anya.sokolova, bruno.costa, emeka.adeyemi
```

Zero overlap between the groups → two disconnected components → `results.py`
returns `422 "Comparison graph is disconnected"` and the event gets **no final
ranking at all**.

The default `judges_per_project=2` is the worst case: 3 components, 6 pairs.

### Proof the model itself is sound

At `jpp=6` (every judge sees every project, so the graph connects) the full
pipeline runs end to end and **exactly recovers the ground truth**:

```
TRUE order    : p1 p2 p3 p4 p5 p6
model ranking : p1 p2 p3 p4 p5 p6      <- exact match
theta         : +3.03 +1.44 0.00 -1.10 -2.34 -3.81   (monotonic)
run           : SUCCEEDED, 6 projects, 6 judges, 90 comparisons
```

All 6 judges scored near-identically and the model correctly assigned them all
the **same** reliability `r = 1.6273` — the reliability mechanism works as intended.

So the model is correct; the **default configuration makes it unreachable**.

---

## 6. Realistic event scale — 40 projects / 30 judges

The spec ships 40 projects and 30 judges. Two independent failures appear at exactly
that scale.

### 6a. Connectivity is not monotone in `judges_per_project`

40 projects, 30 judges, balanced assignment:

| jpp | evals | pairs | components | outcome |
|---:|---:|---:|---:|---|
| **2 (default)** | 60 | 65 | **15** | 422 DISCONNECTED |
| 3 | 90 | 167 | **10** | 422 DISCONNECTED |
| 4 | 120 | 310 | 1 | RAN |
| 6 | 180 | 743 | **5** | 422 DISCONNECTED |
| 10 | 300 | 2407 | **3** | 422 DISCONNECTED |
| 20 | 600 | 9685 | 1 | 500 optimizer failed |
| 40 | 1200 | 20526 | 1 | 500 optimizer failed |

`jpp=4` connects, but `jpp=6` and `jpp=10` fragment again. Because the assignment is
lowest-load-first, connectivity is an **accident of interleaving**, not a property the
system controls. Raising the setting is therefore not a fix.

### 6b. The optimizer does not converge at this scale

Every judge sees every project (the best possible case for connectivity):

| projects | judges | pairs | `success` | seconds |
|---:|---:|---:|:---:|---:|
| 6 | 6 | 83 | True | 0.07 |
| 8 | 4 | 104 | True | 0.07 |
| 20 | 10 | 1765 | True | 0.74 |
| **40** | **30** | **20863** | **False** | 28.6 |
| 40 | 30 | 21271 | False | 35.6 |
| 60 | 30 | 49737 | False | 120.5 |
| 100 | 50 | 231101 | False | **1497.8** |

`results.py` line 103 does `if not out["success"]: raise RuntimeError("optimizer did
not converge")`, which becomes a 500 and a FAILED run row. The spec's own event size
(40 / 30) is squarely in the failing regime, and a 100-project event would occupy a
request thread for ~25 minutes first.

Causes: BFGS from an all-zeros start with **numerical gradients** (no analytic
Jacobian), default tolerances, and a single free log-reliability per judge adding
`J` more non-convex directions. The all-pairs likelihood is also near-separating at
this density, so |theta| wants to run to infinity and only `THETA_SIGMA=2` brakes it.

---

## Conclusion

- `assign`, `pairwise`, `crowd_bt`, `judge` each work correctly in isolation.
- The end-to-end pipeline fails at the shipped default because balanced
  assignment and a connected comparison graph are opposing requirements.
- The fix is a configuration/contract change, not a math change. Raising
  `judges_per_project` is **not sufficient** — connectivity is non-monotone in it
  (4 connects, 6 and 10 fragment). The assignment strategy itself must guarantee
  overlap, e.g. a shared "anchor" judge per project, or a forced common comparison
  backbone, or per-event stratified assignment.
- The fitter needs an analytic Jacobian, multi-start, and a convergence criterion
  that reports a usable answer instead of raising. At 40 projects / 30 judges it
  currently returns `success=False` after ~30s and `results.py` converts that to a
  500.
- The system should refuse loudly at **assignment** time if the requested
  `judges_per_project` cannot yield a connected graph, rather than failing at
  calculation time after all judging is done.
