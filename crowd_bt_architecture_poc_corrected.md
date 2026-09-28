# Hierarchical Bayesian Crowd-Bradley–Terry Judging Architecture

**Corrected Architecture, Proof of Concept, Results, and Python Implementation**

## 1. System Purpose

The system converts judge evaluations into a common project ordering without requiring judges to use the same absolute scoring scale.

The primary ranking signal is the ordering between projects produced by each judge. A strict judge and a lenient judge may use different numerical scales, but both can provide valid pairwise preference information.

The system uses a Bradley–Terry model to estimate latent project strength. Judge reliability is included as a model parameter. Historical judge performance is used to establish the prior for that reliability.

## 2. Overall Architecture

```text
Weighted Rubric → Pairwise Preferences → Hierarchical Bayesian Crowd-BT
Historical Judge Performance → Reliability Prior → Current Reliability Posterior
```

The complete processing sequence is:

1. Judge evaluates a project using the defined rubric criteria.
2. Rubric weights are applied to produce a weighted score.
3. Projects evaluated by the same judge are compared pairwise.
4. Each non-tied comparison produces a winner and loser.
5. The pairwise observations are supplied to the Bradley–Terry model.
6. Judge reliability modifies the strength of the judge's preference signal.
7. Historical judge performance defines the prior for current reliability.
8. The model estimates project latent strength and current judge reliability.
9. Production inference should also report uncertainty.

## 3. Stage 1 — Judge Evaluation

Each judge evaluates a project using the competition rubric. The fixture contains criteria including functionality, quality, and innovation.

A judge does not need to evaluate every project. The model operates on the comparison graph created by the evaluations that are available.

## 4. Stage 2 — Weighted Rubric

The fixture does not define criterion weights. The proof of concept therefore assumes:

| Criterion | Weight |
|---|---:|
| Functionality | 0.40 |
| Quality | 0.35 |
| Innovation | 0.25 |

The weighted score is:

```text
Sᵢⱼ = 0.40(Functionality) + 0.35(Quality) + 0.25(Innovation)
```

The weighted score is used to establish the ordering between projects evaluated by the same judge.

## 5. Stage 3 — Pairwise Preference

For two projects evaluated by the same judge:

```text
If S(A,j) > S(B,j), record A > B for judge j.
```

Absolute score scales do not need to be aligned across judges.

Example:

- Strict judge: A = 5, B = 3 → A > B.
- Lenient judge: A = 85, B = 70 → A > B.

Both observations express the same directional preference.

## 6. Stage 4 — Scale-Invariant Evidence

The previous proof of concept used:

```text
w = 1 + |S(A,j) − S(B,j)|
```

This has been removed.

A raw score difference reintroduces the exact scale dependence that pairwise conversion was intended to remove.

A strict judge producing 5 versus 3 has a raw margin of 2. A lenient judge producing 85 versus 70 has a raw margin of 15. Weighting by those raw margins would give the second judge greater influence solely because the numerical scale is wider.

The corrected core model therefore assigns equal base weight to every non-tied pairwise comparison:

```text
A > B → weight = 1
```

Judge reliability, rather than score range, determines how strongly a judge's preference pattern is trusted.

### Design Principle

> The numerical scoring scale is local to the judge. The pairwise preference is the cross-judge signal.

## 7. Optional Extension — Relative Margin

Score-margin information may still be useful, but it should be treated as a separate confidence signal rather than as a raw evidence weight.

A possible normalized margin is:

```text
M = |S(A,j) − S(B,j)| / Dⱼ
```

where `Dⱼ` may represent a judge's within-competition score spread.

This normalized margin can later be tested in an ordinal or confidence model.

The three concepts should remain separate:

- **Preference:** Which project did the judge place above the other?
- **Confidence or separation:** How far apart did the judge score the projects relative to that judge's own scale?
- **Reliability:** How consistently does the judge's preference information agree with the model and historical evidence?

## 8. Stage 5 — Bradley–Terry

Each project is assigned an unobserved latent strength `θᵢ`.

The basic Bradley–Terry relationship is:

```text
P(A > B) = sigmoid(θ_A − θ_B)
```

With judge reliability:

```text
Pⱼ(A > B) = sigmoid(rⱼ(θ_A − θ_B))
```

The reliability parameter controls the judge's discriminative contribution.

A higher reliability produces a stronger response to differences in latent project strength.

## 9. Stage 6 — Judge Reliability

Judge reliability is modeled as a positive parameter:

```text
rⱼ = exp(log_reliabilityⱼ)
```

This guarantees:

```text
rⱼ > 0
```

Strictness and reliability are different quantities.

A judge who consistently gives low scores is not automatically unreliable. Pairwise conversion removes much of the effect of an additive scoring offset because the same judge compares projects on the same scale.

## 10. Stage 7 — Hierarchical Bayesian Reliability Prior

Historical judge performance is used to establish the prior for current reliability:

```text
log rⱼ ~ Normal(μᵣ, σᵣ²)
```

The intended production flow is:

```text
Historical performance
        ↓
Historical posterior
        ↓
Current reliability prior
        ↓
Current reliability posterior
```

A new judge may receive a broad neutral prior. A judge with sufficient historical evidence may receive a more informative prior.

The fixture contains no historical competition data. The proof of concept therefore uses a neutral prior:

```text
μᵣ = 0
σᵣ = 0.60
```

The prior is centered at `log(r)=0`, corresponding to `r=1`.

## 11. Project Prior and Identifiability

Project latent strength uses a weak prior:

```text
θᵢ ~ Normal(0, 2²)
```

Bradley–Terry latent strengths have a location ambiguity. Adding a constant to every `θ` produces the same pairwise differences.

One project is therefore fixed to:

```text
θ = 0
```

The reference value is not an absolute quality score. It defines the origin of the latent scale.

## 12. Missing Evaluations and Comparison Graph

A complete judge-by-project matrix is not required.

Each judge contributes comparisons between the projects evaluated by that judge. The combined observations form a comparison graph.

The graph must be sufficiently connected for a common latent ordering to be inferred.

If the graph contains disconnected components, projects in separate components cannot be directly placed on one common latent scale without additional linking observations.

## 13. Corrected Proof of Concept

A six-project connected subset was used:

| Project ID | Project |
|---|---|
| `prj_02` | Small Meadow |
| `prj_03` | Deep Compass |
| `prj_04` | Green Switch |
| `prj_06` | Dry Compass |
| `prj_07` | Dry Harbour |
| `prj_12` | Open Beacon |

The corrected implementation uses the same rubric weights as the previous proof of concept.

Every non-tied pairwise observation has unit weight.

## 14. Corrected Pairwise Evidence

| Judge | Winner | Loser | Weight |
|---|---|---|---:|
| `jdg_21` | Small Meadow | Deep Compass | 1.0 |
| `jdg_21` | Small Meadow | Dry Harbour | 1.0 |
| `jdg_21` | Dry Harbour | Deep Compass | 1.0 |
| `jdg_12` | Dry Harbour | Small Meadow | 1.0 |
| `jdg_26` | Small Meadow | Deep Compass | 1.0 |
| `jdg_26` | Small Meadow | Dry Compass | 1.0 |
| `jdg_26` | Dry Harbour | Small Meadow | 1.0 |
| `jdg_26` | Deep Compass | Dry Compass | 1.0 |
| `jdg_26` | Dry Harbour | Deep Compass | 1.0 |
| `jdg_26` | Dry Harbour | Dry Compass | 1.0 |
| `jdg_19` | Deep Compass | Dry Harbour | 1.0 |
| `jdg_22` | Open Beacon | Green Switch | 1.0 |
| `jdg_24` | Open Beacon | Dry Compass | 1.0 |

## 15. Corrected POC — Project Latent Strength

The following are MAP estimates from the corrected unit-weighted model. Open Beacon is fixed at `θ=0` as the reference project.

| Position | Project | Latent Strength `θ` |
|---:|---|---:|
| 1 | Dry Harbour | `+1.042` |
| 2 | Small Meadow | `+0.596` |
| 3 | Open Beacon | `0.000` |
| 4 | Deep Compass | `-0.512` |
| 5 | Green Switch | `-1.263` |
| 6 | Dry Compass | `-1.911` |

> **Reference note:** `θ=0` for Open Beacon is an identifiability constraint. It does not mean that Open Beacon has zero quality.

## 16. Corrected POC — Judge Reliability

| Judge | Estimated Reliability `r` |
|---|---:|
| `jdg_26` | 1.716 |
| `jdg_21` | 1.241 |
| `jdg_22` | 1.154 |
| `jdg_24` | 1.145 |
| `jdg_12` | 1.144 |
| `jdg_19` | 0.581 |

These estimates are proof-of-concept values only. The sample is small and no historical reliability data is present. They should not be interpreted as stable production estimates.

## 17. Design Correction

The following changes were made from the previous proof of concept:

1. Removed `w = 1 + |score difference|`.
2. All non-tied pairwise observations now have unit weight.
3. The ranking signal is invariant to simple rescaling of a judge's scoring units.
4. Judge reliability, rather than numerical score range, controls the strength of a judge's contribution.
5. Relative score margins are reserved for a possible future confidence model.
6. The POC results are recomputed using the corrected likelihood.

## 18. Production Architecture

The production system can be divided into the following components:

1. **Evaluation Ingestion**  
   Receives judge/project rubric scores.

2. **Rubric Processor**  
   Applies configured criterion weights.

3. **Pairwise Preference Generator**  
   Creates within-judge pairwise observations.

4. **Comparison Store**  
   Stores judge, winner, loser, and source-evaluation metadata.

5. **Reliability Prior Service**  
   Retrieves historical judge-performance information.

6. **Hierarchical Bayesian Crowd-BT Model**  
   Estimates project strength and judge reliability.

7. **Posterior Uncertainty Module**  
   Estimates uncertainty around model parameters.

8. **Ranking Service**  
   Produces the current project ordering.

9. **Judge Analytics**  
   Reports reliability and diagnostics without equating strictness with unreliability.

10. **Audit Store**  
    Retains source evaluations, derived preferences, and model version.

## 19. Recommended Data Flow

```text
Judge Scores
     ↓
Weighted Rubric Scores
     ↓
Within-Judge Pairwise Preferences
     ↓
Unit-Weighted Comparison Graph
     ↓
Hierarchical Bayesian Crowd-BT
     ↙                         ↘
Project Strength θ       Judge Reliability r
     ↓                         ↓
Project Ordering          Judge Analytics
```

Historical judge performance enters through the reliability prior. It does not require absolute score normalization.

## 20. Limitations and Future Extensions

- The fixture does not define criterion weights; the POC assumes `0.40`, `0.35`, and `0.25`.
- The fixture contains no historical judge-performance data; the reliability prior is neutral.
- The POC uses unit-weighted binary preferences as the scale-invariant baseline.
- A future confidence model may use judge-relative score margins, but raw score differences should not be used as cross-judge evidence weights.
- The POC uses MAP estimation rather than full posterior sampling.
- The selected subset is small, so reliability estimates may be unstable.
- Disconnected comparison components cannot be directly placed on one common latent scale.
- Production validation should include posterior uncertainty, held-out preference prediction, sensitivity analysis, and graph-connectivity checks.

## 21. Summary

The corrected architecture keeps pairwise conversion consistent with its purpose.

Absolute score magnitude establishes the ordering within a judge, but raw score differences do not determine evidence weight.

The core model receives pairwise preferences with equal base weight. Judge reliability determines how strongly a judge's preference pattern contributes. Historical performance provides the prior for that reliability.

```text
Weighted Rubric
      ↓
Pairwise Ordering
      ↓
Unit-Weighted Crowd-BT
      ↓
Project Strength + Judge Reliability
```

Optional score-margin information can be modeled separately as a confidence signal after the scale-invariant baseline has been validated.

---

# Appendix A — Corrected Python Proof of Concept

```python
import json
import itertools
import numpy as np
from scipy.optimize import minimize
from pathlib import Path

FIXTURE_PATH = Path("fixtures.json")

PROJECT_IDS = [
    "prj_02", "prj_03", "prj_04",
    "prj_06", "prj_07", "prj_12"
]

WEIGHTS = {
    "functionality": 0.40,
    "quality": 0.35,
    "innovation": 0.25,
}

# Neutral hierarchical prior because fixtures.json
# contains no historical judge-performance data.
MU_R = 0.0
SIGMA_R = 0.60

# Weak project-strength prior.
THETA_SIGMA = 2.0


def sigmoid(x):
    x = np.clip(x, -50, 50)
    return 1.0 / (1.0 + np.exp(-x))


def weighted_score(score):
    return sum(
        WEIGHTS[k] * float(score[k])
        for k in WEIGHTS
    )


with FIXTURE_PATH.open() as f:
    fixtures = json.load(f)

project_names = {
    p["id"]: p["name"]
    for p in fixtures["projects"]
}

selected = set(PROJECT_IDS)

records = [
    s for s in fixtures["scores"]
    if s["project_id"] in selected
]

by_judge = {}

for record in records:
    by_judge.setdefault(
        record["judge_id"], []
    ).append(record)


# Core model:
# pairwise ordering only;
# every non-tied comparison has weight 1.
comparisons = []

for judge_id, judge_records in by_judge.items():

    for a, b in itertools.combinations(
        judge_records, 2
    ):

        sa = weighted_score(a)
        sb = weighted_score(b)

        if sa == sb:
            continue

        if sa > sb:
            winner = a["project_id"]
            loser = b["project_id"]
        else:
            winner = b["project_id"]
            loser = a["project_id"]

        comparisons.append({
            "judge": judge_id,
            "winner": winner,
            "loser": loser,
            "weight": 1.0,
        })


projects = PROJECT_IDS

judges = sorted({
    c["judge"]
    for c in comparisons
})

# Fix Open Beacon as the reference point.
reference_project = "prj_12"

free_projects = [
    p for p in projects
    if p != reference_project
]


def unpack(x):

    theta = {
        reference_project: 0.0
    }

    for i, project_id in enumerate(
        free_projects
    ):
        theta[project_id] = x[i]

    log_r = {
        judge_id: x[
            len(free_projects) + j
        ]
        for j, judge_id
        in enumerate(judges)
    }

    reliability = {
        judge_id: np.exp(value)
        for judge_id, value
        in log_r.items()
    }

    return theta, log_r, reliability


def negative_log_posterior(x):

    theta, log_r, reliability = unpack(x)

    nlp = 0.0

    # Pairwise likelihood.
    for c in comparisons:

        delta = (
            theta[c["winner"]]
            - theta[c["loser"]]
        )

        p = sigmoid(
            reliability[c["judge"]]
            * delta
        )

        p = np.clip(
            p,
            1e-12,
            1.0 - 1e-12
        )

        # Unit weight.
        # No raw score margin is used.
        nlp -= (
            c["weight"]
            * np.log(p)
        )

    # Project-strength prior.
    for project_id in free_projects:

        nlp += 0.5 * (
            theta[project_id]
            / THETA_SIGMA
        ) ** 2

    # Hierarchical reliability prior:
    # log(r_j) ~ Normal(MU_R, SIGMA_R^2)
    for judge_id in judges:

        nlp += 0.5 * (
            (
                log_r[judge_id]
                - MU_R
            )
            / SIGMA_R
        ) ** 2

    return nlp


x0 = np.zeros(
    len(free_projects)
    + len(judges)
)

result = minimize(
    negative_log_posterior,
    x0,
    method="BFGS",
)

theta, log_r, reliability = unpack(
    result.x
)


print("\nPROJECT LATENT STRENGTH")

for project_id, value in sorted(
    theta.items(),
    key=lambda item: item[1],
    reverse=True,
):

    print(
        f"{project_names[project_id]:20s} "
        f"theta={value:+.3f}"
    )


print("\nJUDGE RELIABILITY")

for judge_id, value in sorted(
    reliability.items(),
    key=lambda item: item[1],
    reverse=True,
):

    print(
        f"{judge_id:10s} "
        f"reliability={value:.3f}"
    )


print(
    "\nOptimization success:",
    result.success
)

print(
    "Message:",
    result.message
)
```

# Appendix B — Corrected POC Results

## Project Latent Strength

```text
Dry Harbour         theta=+1.042
Small Meadow        theta=+0.596
Open Beacon         theta=+0.000
Deep Compass        theta=-0.512
Green Switch        theta=-1.263
Dry Compass         theta=-1.911
```

## Judge Reliability

```text
jdg_26              reliability=1.716
jdg_21              reliability=1.241
jdg_22              reliability=1.154
jdg_24              reliability=1.145
jdg_12              reliability=1.144
jdg_19              reliability=0.581
```

## Optimization

```text
Optimization success: True
```

The exact optimizer message is produced by the SciPy installation when the script is executed.
