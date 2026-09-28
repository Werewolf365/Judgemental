#!/usr/bin/env python3
"""Ranking-correctness validation: does the pipeline produce SENSIBLE
rankings, not just green tests? Runs INSIDE the api container:

    docker compose exec -T api python - < scripts/validate_ranking.py

Uses the REAL pipeline modules (pairwise.generate_pairs, crowd_bt.fit)
on synthetic ground truth — no database, no server. All randomness is
seeded, so every run is identical.

Experiments:
 1. unanimous      — every judge ranks A>B>C>D>E: must recover exactly that.
 2. scale_invariance — strict (1-5) vs lenient (0-100) judges, same ordering:
    identical pairs, and reliabilities must not reward the wider scale.
 3. ground_truth    — 5 projects with known true strengths; strict, lenient,
    noisy and ADVERSARIAL (inverted) judges: ranking must recover truth and
    the adversary's reliability must collapse vs consistent judges.
 4. optimum_check   — numerical gradient of the MAP objective at the fitted
    point must be ~zero (independent proof the optimizer found a minimum,
    not just returned success=True).
"""
import math
import random
import sys

sys.path.insert(0, "/app")

from app.modules.judging import crowd_bt
from app.modules.judging.pairwise import generate_pairs

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f" -- {detail}"))


def order_of(thetas):
    return [p for p, _ in sorted(thetas.items(), key=lambda kv: kv[1], reverse=True)]


def fit_of(rows, ref):
    pairs = generate_pairs(rows)
    judges = sorted({p["judge_user_id"] for p in pairs})
    projs = sorted({p["winner_project_id"] for p in pairs}
                   | {p["loser_project_id"] for p in pairs})
    out = crowd_bt.fit(pairs, projs, judges, reference_project=ref,
                       priors={j: (0.0, 0.60) for j in judges})
    return out, pairs


print("[1] unanimous ordering")
rows = []
for j in ("j1", "j2", "j3"):
    for i, p in enumerate(["A", "B", "C", "D", "E"]):
        rows.append({"judge_user_id": j, "project_id": p,
                     "weighted_score": float(10 - 2 * i),
                     "evaluation_id": f"{j}{p}"})
out, pairs = fit_of(rows, "E")
check("recovers A>B>C>D>E", order_of(out["thetas"]) == ["A", "B", "C", "D", "E"],
      f"{order_of(out['thetas'])}")
th = out["thetas"]
check("thetas strictly decreasing",
      all(th[a] > th[b] for a, b in zip("ABCD", "BCDE")), f"{th}")

print("[2] scale invariance (strict 1-5 vs lenient 0-100, same order)")
strict = [{"judge_user_id": "s", "project_id": p, "weighted_score": float(v),
           "evaluation_id": f"s{p}"} for p, v in zip("ABCDE", [5, 4, 3, 2, 1])]
lenient = [{"judge_user_id": "l", "project_id": p, "weighted_score": float(v),
            "evaluation_id": f"l{p}"} for p, v in zip("ABCDE", [95, 80, 62, 41, 20])]
ps = generate_pairs(strict)
pl = generate_pairs(lenient)
check("identical pairwise evidence",
      sorted((x["winner_project_id"], x["loser_project_id"]) for x in ps)
      == sorted((x["winner_project_id"], x["loser_project_id"]) for x in pl))
outs, _ = fit_of(strict, "E")
outl, _ = fit_of(lenient, "E")
rs, rl = outs["reliabilities"]["s"], outl["reliabilities"]["l"]
check("wider scale buys no extra reliability",
      abs(rs - rl) < 0.05, f"strict r={rs:.3f} lenient r={rl:.3f}")
check("same thetas up to optimizer dust",
      all(abs(outs["thetas"][p] - outl["thetas"][p]) < 1e-6 for p in "ABCDE"))

print("[3] ground truth + noisy + adversarial judges")
rng = random.Random(0)
truth = {"P1": 2.0, "P2": 1.0, "P3": 0.0, "P4": -1.0, "P5": -2.0}
# (scale_lo, scale_hi, noise_sd, invert?) — maps truth range [-2,2] to a scale
styles = {"strict": (1, 5, 0.15, False), "lenient": (55, 100, 2.0, False),
          "noisy": (0, 10, 1.2, False), "adversarial": (0, 10, 0.4, True)}
rows = []
for j, (lo, hi, sd, inv) in styles.items():
    for p, t in truth.items():
        v = (lo + (t + 2) / 4 * (hi - lo))
        if inv:
            v = lo + hi - v
        v += rng.gauss(0, sd)
        rows.append({"judge_user_id": j, "project_id": p,
                     "weighted_score": v, "evaluation_id": f"{j}{p}"})
out, pairs = fit_of(rows, "P5")
got = order_of(out["thetas"])
check("recovers true order P1>...>P5", got == ["P1", "P2", "P3", "P4", "P5"], f"{got}")
r = out["reliabilities"]
cons = [r[j] for j in ("strict", "lenient", "noisy")]
check("adversary reliability collapses",
      r["adversarial"] < 0.5 * min(cons),
      f"adversarial={r['adversarial']:.3f} vs consistent={[f'{v:.3f}' for v in cons]}")
check("consistent judges stay near neutral prior",
      all(0.5 < v < 2.5 for v in cons), f"{cons}")

print("[4] optimizer actually at a minimum (finite-difference gradient)")
import numpy as np  # noqa: E402
pairs = generate_pairs(rows)
judges = sorted({p["judge_user_id"] for p in pairs})
projs = sorted({p["winner_project_id"] for p in pairs}
               | {p["loser_project_id"] for p in pairs})
free = [p for p in projs if p != "P5"]
# Rebuild the objective in terms of the flat vector, evaluate grad numerically.
wd = {p["winner_project_id"]: 1 for p in pairs}  # placeholder, rebuilt below
widx = [(free.index(p["winner_project_id"]) if p["winner_project_id"] != "P5" else -1,
         free.index(p["loser_project_id"]) if p["loser_project_id"] != "P5" else -1,
         judges.index(p["judge_user_id"])) for p in pairs]


def nlp(x):
    th = x[:len(free)]
    lr = x[len(free):]
    rr = np.exp(lr)
    total = 0.0
    for wi, li, ji in widx:
        tw = 0.0 if wi == -1 else th[wi]
        tl = 0.0 if li == -1 else th[li]
        z = min(50, max(-50, rr[ji] * (tw - tl)))
        total -= math.log(1.0 / (1.0 + math.exp(-z)))
    total += 0.5 * float(np.sum((np.asarray(th) / 2.0) ** 2))
    total += 0.5 * float(np.sum((np.asarray(lr) / 0.60) ** 2))
    return total


x = np.array([out["thetas"][p] for p in free]
             + [out["log_reliabilities"][j] for j in judges])
h = 1e-6
grad = [(nlp(x + h * np.eye(len(x))[i]) - nlp(x - h * np.eye(len(x))[i])) / (2 * h)
        for i in range(len(x))]
gnorm = math.sqrt(sum(g * g for g in grad))
check("gradient norm ~ 0 at fitted point", gnorm < 1e-4, f"|grad|={gnorm:.2e}")

print("RANKING " + ("ALL PASS" if all(results) else "FAILURES PRESENT"))
raise SystemExit(0 if all(results) else 1)
