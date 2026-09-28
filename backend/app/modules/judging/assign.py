"""Balanced judge assignment service (prompt_T2 §4/§6).

Not embedded in routes: routes validate authZ and commit; everything about
*who* gets *what* lives here.

Assignment is a constrained optimization over three goals, in this priority:

1. Coverage — every SUBMITTED project reaches min(judges_per_project,
   eligible judges). Bounds hold by construction: fills only ever top up
   toward the target, never past it.
2. Workload — W_j is the judge's LIVE project count (non-REVOKED rows,
   finished work included: a completed evaluation is still effort spent).
   Balancing project counts also balances pairwise voice, since C(k,2) is
   monotone in k. Picks use *active* loads (ASSIGNED + IN_PROGRESS) as the
   capacity-now signal. Within load ties, the first slot attaches (prefers
   judges already serving projects, linking the newcomer into the graph)
   while later slots bridge (prefer judges serving components not yet
   represented among this project's picks, so multi-judge projects stitch
   islands together instead of deepening them); user_id breaks what remains
   so concurrent runs choose identically. Load always outranks linkage:
   bridging acts only among equals, never at a balance cost.
3. Connectivity — projects sharing a judge belong to one component; the
   batch pass verifies this and rewires (revoke one movable row, create
   one elsewhere) until connected or no improving swap exists. Coverage-1
   projects can never link — that case stays the calculate gate's refusal,
   reported honestly by health instead of papered over.
    Redundancy - pairs sharing exactly one judge rest on one verdict alone, so later fill slots prefer completing such pairs to 2 shared (after load and bridging), the batch pass upgrades them where a verified swap exists, and health reports the remaining weak-pair count with min_bridge. Full pairwise redundancy is unachievable at uniform coverage 2 without destroying balance (it would force all projects onto one judge pair), so redundancy is opportunistic; jpp 3+ is where it has room to work.

Concurrency: callers run inside a transaction; assign_* takes a
SELECT … FOR UPDATE lock on the event row first, serializing assignment
decisions per event. The partial unique index on judge_assignments is the
second line of defence — duplicate pairs are impossible even if two
transactions interleave, and inserts use ON CONFLICT DO NOTHING so a retry
is always safe (idempotent).

Deliberately NOT done: stealing. Rebalance and repair only *fill* or
*replace* (same coverage count); an ASSIGNED row is a commitment to that
judge and is never moved to even out loads. Evening out happens through
future picks preferring the idled judge.
"""
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import (AssignmentStatus, EvaluationStatus, Event, EventJudge,
                        Evaluation, JudgeAssignment, Project, ProjectStatus, User)
from app.modules.judging import service as _svc
from app.shared.errors import err
import uuid

ACTIVE = (AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS)


async def _lock_event(db: AsyncSession, event_id: str) -> Event:
    e = (await db.execute(
        select(Event).where(Event.id == event_id).with_for_update())).scalar_one_or_none()
    if not e:
        err(404, "not_found", "Event not found")
    return e


def _role_of(u) -> str:
    return u.role.value if hasattr(u.role, "value") else str(u.role)


async def eligible_judges(db: AsyncSession, event_id: str) -> list:
    """Active roster rows whose account still holds the JUDGE role.

    A demoted account is skipped rather than erroring: the roster row stays
    for history, but no new work flows to someone who is no longer a judge.
    """
    res = await db.execute(
        select(User).join(EventJudge, EventJudge.user_id == User.id).where(
            EventJudge.event_id == event_id, EventJudge.is_active == True))  # noqa
    return [u for u in res.scalars().all() if _role_of(u) == "JUDGE"]


async def judge_loads(db: AsyncSession, event_id: str) -> dict:
    """{user_id: active assignment count} for the whole event, one query."""
    res = await db.execute(
        select(JudgeAssignment.judge_user_id, func.count()).where(
            JudgeAssignment.event_id == event_id,
            JudgeAssignment.status.in_(ACTIVE)).group_by(JudgeAssignment.judge_user_id))
    return {uid: n for uid, n in res.all()}


async def project_active_count(db: AsyncSession, project_id: str) -> int:
    res = await db.execute(select(func.count()).select_from(JudgeAssignment).where(
        JudgeAssignment.project_id == project_id,
        JudgeAssignment.status.in_(ACTIVE)))
    return res.scalar() or 0


def _rank_candidates(loads: dict, live: dict, eligible_ids: set, exclude_ids: set) -> list:
    """Pure pick order: lowest active load first, then most already-serving
    (overlap links the project into the comparison graph), then user_id so
    concurrent runs choose identically. `live` maps judge -> set of live
    project ids; `loads` maps judge -> active count."""
    ranked = [(loads.get(uid, 0), -len(live.get(uid, ())), uid)
              for uid in eligible_ids if uid not in exclude_ids]
    return [uid for _, _, uid in sorted(ranked)]


def _slot_ranking(state: dict, project_id: str, picked: list) -> list:
    """Pure per-slot pick order. First slot attaches (same as
    _rank_candidates); later slots BRIDGE — preferring candidates that serve
    components not yet represented among this project's picks — then REDUND
    (complete thin bridges): prefer candidates that lift an exactly-1-shared
    pair involving this project to 2 shared judges. Load stays primary
    throughout, so linkage only ever acts among load ties: balance first,
    new components second, redundancy third. With one slot the key collapses
    exactly to _rank_candidates, keeping single-slot fills byte-identical
    in behavior.
    """
    live, loads = state["live"], state["loads"]
    coverage = state["coverage"]
    exclude = set(coverage.get(project_id, ())) | set(picked)
    if not picked:
        return _rank_candidates(loads, live, state["eligible_ids"], exclude)
    comp_of = {}
    for idx, comp in enumerate(components_of(live)):
        for p in comp:
            comp_of[p] = idx
    picked_comps = {comp_of[p] for q in picked for p in live.get(q, ()) if p in comp_of}
    have_now = set(coverage.get(project_id, ())) | set(picked)

    def redundancy_gain(uid):
        """Projects q (≠ this one) with which this project currently shares
        exactly one judge, and uid serves q: adding uid completes the pair
        to a redundant (≥2 shared) bridge."""
        gain = 0
        served = live.get(uid, ())
        if project_id in served:
            return 0
        for q, judges_q in coverage.items():
            if q == project_id or q not in live.get(uid, ()):
                continue
            shared_now = len(set(judges_q) & have_now)
            if shared_now == 1 and uid not in have_now:
                gain += 1
        return gain

    def key(uid):
        served = live.get(uid, ())
        new = {comp_of[p] for p in served if p in comp_of} - picked_comps
        return (loads.get(uid, 0), -len(new), -redundancy_gain(uid),
                -len(served), uid)

    return sorted((uid for uid in state["eligible_ids"] if uid not in exclude), key=key)


def _fill_project_slots(state: dict, project_id: str, need: int) -> list:
    """Pick up to `need` judges for one project, slot by slot, updating the
    shared maps after each pick so later slots see earlier ones."""
    picked = []
    for _ in range(max(0, need)):
        ranked = _slot_ranking(state, project_id, picked)
        if not ranked:
            break
        picked.append(ranked[0])
        _apply_pick(state, project_id, [ranked[0]])
    return picked


def shared_judge_count(coverage: dict, p1: str, p2: str) -> int:
    """Pure: number of judges serving both projects (|judges(p1) ∩ judges(p2)|)."""
    return len(coverage.get(p1, set()) & coverage.get(p2, set()))


def single_shared_pairs(coverage: dict) -> list:
    """Pure: sorted [(p1, p2)] over project pairs sharing exactly one judge.

    These are the thin bridges — one departure (or one noisy judge) from a
    flat likelihood direction. The strengthen pass targets exactly these.
    """
    pids = sorted(coverage.keys())
    out = []
    for i, p1 in enumerate(pids):
        for p2 in pids[i + 1:]:
            if shared_judge_count(coverage, p1, p2) == 1:
                out.append((p1, p2))
    return out


def min_bridge(coverage: dict) -> int | None:
    """Pure: minimum shared-judge count over directly-linked project pairs.

    None when no pair shares a judge at all. The batch response reports this
    so organizers can see bridge redundancy, not just connectivity.
    """
    pids = sorted(coverage.keys())
    best = None
    for i, p1 in enumerate(pids):
        for p2 in pids[i + 1:]:
            shared = shared_judge_count(coverage, p1, p2)
            if shared == 0:
                continue
            if best is None or shared < best:
                best = shared
    return best


def components_of(live: dict) -> list:
    """Pure: connected components of projects over shared judges.

    Structural linkage (a judge serving both projects) is necessary but not
    sufficient for comparison linkage (which additionally needs ≥2 evaluated
    projects per judge) — so this is the assignment-level projection of the
    connectivity the calculate gate checks on real pairs. Sorted
    deterministically by (size, smallest project id).
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    projs = set()
    for ps in live.values():
        projs.update(ps)
    for p in projs:
        parent.setdefault(p, p)
    for ps in live.values():
        ordered = sorted(ps)
        for a, b in zip(ordered, ordered[1:]):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    groups = {}
    for p in projs:
        groups.setdefault(find(p), set()).add(p)
    return sorted(groups.values(), key=lambda s: (len(s), sorted(s)[0] if s else ""))


async def _load_state(db: AsyncSession, event: Event, with_projects: bool = False) -> dict:
    """One-shot read of everything pick/repair/health decisions need."""
    eligible = await eligible_judges(db, event.id)
    eligible_ids = {u.id for u in eligible}
    loads = await judge_loads(db, event.id)
    res = await db.execute(select(
        JudgeAssignment.id, JudgeAssignment.project_id,
        JudgeAssignment.judge_user_id, JudgeAssignment.status).where(
        JudgeAssignment.event_id == event.id,
        JudgeAssignment.status != AssignmentStatus.REVOKED))
    live, coverage, rows = {}, {}, {}
    for rid, pid, uid, st in res.all():
        live.setdefault(uid, set()).add(pid)
        coverage.setdefault(pid, set()).add(uid)
        rows[(pid, uid)] = {"id": rid, "status": st}
    pids = []
    if with_projects:
        res = await db.execute(select(Project.id).where(
            Project.event_id == event.id, Project.status == ProjectStatus.SUBMITTED
        ).order_by(Project.submitted_at, Project.id))
        pids = [r[0] for r in res.all()]
    return {"eligible": eligible, "eligible_ids": eligible_ids, "loads": loads,
            "live": live, "coverage": coverage, "rows": rows, "pids": pids}


async def _insert_slots(db: AsyncSession, event_id: str, project_id: str,
                        judge_ids: list[str]) -> int:
    """Insert ASSIGNED rows, ignoring pairs that appeared concurrently."""
    if not judge_ids:
        return 0
    stmt = pg_insert(JudgeAssignment).values([{
        "id": f"asg_{uuid.uuid4().hex[:8]}",
        "event_id": event_id, "project_id": project_id,
        "judge_user_id": j, "status": AssignmentStatus.ASSIGNED,
    } for j in judge_ids])
    # Arbiter matches uq_assignment_project_judge_active exactly (columns
    # AND predicate): without the predicate Postgres cannot infer the
    # partial index and a concurrent duplicate would raise instead of
    # being ignored. Retry-safe idempotency.
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["project_id", "judge_user_id"],
        index_where=text("status <> 'REVOKED'"))
    res = await db.execute(stmt)
    return res.rowcount or 0


def _apply_pick(state: dict, project_id: str, picked: list) -> None:
    """Bump the in-memory maps so later slots in the same pass never use a
    stale snapshot."""
    for uid in picked:
        state["live"].setdefault(uid, set()).add(project_id)
        state["coverage"].setdefault(project_id, set()).add(uid)
        state["loads"][uid] = state["loads"].get(uid, 0) + 1


async def assign_project(db: AsyncSession, project_id: str,
                         allow_closed: bool = False) -> dict:
    """Fill one SUBMITTED project up to its event's judges_per_project.

    Returns {"assigned": [...user_ids newly picked...], "needed": n, "ok": bool}.
    No-op (ok=True, empty) when already covered or when no judge is eligible.
    Refused (ok=False + reason) once judging has closed: post-deadline work
    could never be scored, so it is never created — except for refills
    (allow_closed), which preserve coverage granted before the close rather
    than creating anything new.
    """
    p = await db.get(Project, project_id)
    if not p:
        err(404, "not_found", "Project not found")
    if (p.status.value if hasattr(p.status, "value") else str(p.status)) != "SUBMITTED":
        err(422, "validation_error", "Only submitted projects can be assigned for judging")
    event = await _lock_event(db, p.event_id)
    if not allow_closed and await _svc.judging_stage(db, event) in ("CLOSED", "RESULTS_READY"):
        return {"assigned": [], "needed": event.judges_per_project,
                "ok": False, "reason": "judging is closed for this event"}
    state = await _load_state(db, event)
    if not state["eligible"]:
        return {"assigned": [], "needed": event.judges_per_project, "ok": False,
                "reason": "no eligible judges assigned to this event"}
    # Coverage counts every live row — active AND completed. A finished
    # evaluation is still a judgment by that judge; ignoring it would both
    # over-assign finished projects and re-pick their judges, hitting the
    # partial unique index as an unhandled 500. Only REVOKED rows free a slot.
    live_here = state["coverage"].get(project_id, set())
    need = max(0, event.judges_per_project - len(live_here))
    if need <= 0:
        return {"assigned": [], "needed": 0, "ok": True}
    picked = _fill_project_slots(state, project_id, need)
    created = await _insert_slots(db, event.id, project_id, picked)
    return {"assigned": picked, "needed": need, "ok": True, "created": created}


async def _repair_connectivity(db: AsyncSession, event_id: str, state: dict) -> list:
    """Merge split components with minimal swaps. Each swap revokes one
    movable (never COMPLETED) row and creates its replacement, keeping the
    project's coverage count identical. Prefers rows with no saved evaluation
    (revoking those orphans nothing) and relieves the highest-load donor.
    Returns repair records; empty means already connected or unrepairable
    (e.g. every project at coverage 1 — nothing movable without breaking
    coverage, correctly left for the calculate gate to refuse).
    """
    repairs = []
    res = await db.execute(select(Evaluation.assignment_id).where(
        Evaluation.event_id == event_id))
    with_eval = set(r[0] for r in res.all())
    # Absolute cap: swaps are bounded, termination never depends on progress.
    for _ in range(max(1, len(state["eligible_ids"]) + 1)):
        comps = components_of(state["live"])
        if len(comps) <= 1:
            break
        done = await _merge_one(db, event_id, state, comps, with_eval)
        if done is None:
            break
        repairs.append(done)
    return repairs


async def _merge_one(db: AsyncSession, event_id: str, state: dict,
                     comps: list, with_eval: set):
    small, large = comps[0], comps[-1]
    large_judges = {j for j, ps in state["live"].items() if ps & large}
    res = await db.execute(select(JudgeAssignment).where(
        JudgeAssignment.event_id == event_id,
        JudgeAssignment.status != AssignmentStatus.REVOKED))
    by_pid = {}
    for r in res.scalars().all():
        by_pid.setdefault(r.project_id, []).append(r)
    # Candidates across EVERY project in the small component: the cheapest
    # merge may live on a later project, and stopping at the first pid
    # with any success locks in avoidable spread damage.
    base = {j: len(state["live"].get(j, ())) for j in state["eligible_ids"]}
    options = []
    for pid in sorted(small):
        members = by_pid.get(pid, [])
        if len(members) < 2:
            continue  # coverage-1: nothing movable without breaking coverage
        movable = [r for r in members
                   if (r.status.value if hasattr(r.status, "value") else str(r.status)) != "COMPLETED"]
        if not movable:
            continue
        on_pid = {r.judge_user_id for r in members}
        recipients = [j for j in state["eligible_ids"] & large_judges
                      if j not in on_pid]
        if not recipients:
            continue
        # Score every (donor, recipient) pair by resulting workload spread
        # on the live counts the health checklist measures, then prefer
        # donors with no saved evaluation (revoking those orphans nothing).
        for r in movable:
            d = r.judge_user_id
            for t in recipients:
                sim_min = sim_max = None
                for j, k in base.items():
                    v = k - (j == d) + (j == t)
                    sim_min = v if sim_min is None or v < sim_min else sim_min
                    sim_max = v if sim_max is None or v > sim_max else sim_max
                options.append((sim_max - sim_min, r.id in with_eval,
                                pid, r.id, t, r))
    options.sort()
    for _, _, pid, _, to_judge, donor in options:
        # Verify on a scratch copy: the swap must strictly reduce the
        # component count, otherwise skip (never thrash).
        trial = {j: set(ps) for j, ps in state["live"].items()}
        trial[donor.judge_user_id].discard(pid)
        trial.setdefault(to_judge, set()).add(pid)
        trial = {j: ps for j, ps in trial.items() if ps}
        if len(components_of(trial)) >= len(comps):
            continue
        break
    else:
        return None
    donor.status = AssignmentStatus.REVOKED
    await db.flush()
    await _insert_slots(db, event_id, pid, [to_judge])
    state["live"][donor.judge_user_id].discard(pid)
    state["live"].setdefault(to_judge, set()).add(pid)
    state["coverage"].setdefault(pid, set()).discard(donor.judge_user_id)
    state["coverage"][pid].add(to_judge)
    state["loads"][donor.judge_user_id] = state["loads"].get(donor.judge_user_id, 0) - 1
    state["loads"][to_judge] = state["loads"].get(to_judge, 0) + 1
    return {"project_id": pid, "from_judge": donor.judge_user_id,
            "to_judge": to_judge}


async def _strengthen_bridges(db: AsyncSession, event_id: str, state: dict) -> list:
    """Upgrade single-shared-judge bridges into redundant ones, where safe.

    A pair sharing exactly one judge is ordered on that judge's verdicts
    alone — thin evidence the model may get wrong. Each swap revokes one
    movable (never COMPLETED) row and creates its replacement, keeping every
    project's coverage count identical: for a pair (a, b) sharing only judge
    s, some other judge t serving b is added to a in place of a donor d
    (d != s, so the existing bridge is never the thing removed). Donors with
    no saved evaluation are preferred (revoking those orphans nothing), then
    lowest resulting workload spread — same scoring as repair. Each candidate
    swap is verified on a scratch copy: the weak-pair count must strictly
    decrease and the component count must not grow; otherwise skip (never
    thrash). Bounded like repair; coverage-1 pairs have no donor distinct
    from the shared judge and stay unstrengthenable. Full pairwise redundancy
    is not always reachable — at uniform coverage 2 it conflicts with balance
    (all pairs ≥2-shared would mean all projects share one judge pair), so
    this pass takes verified improvements and reports the rest.
    """
    res = await db.execute(select(Evaluation.assignment_id).where(
        Evaluation.event_id == event_id))
    with_eval = set(r[0] for r in res.all())
    res = await db.execute(select(JudgeAssignment).where(
        JudgeAssignment.event_id == event_id,
        JudgeAssignment.status != AssignmentStatus.REVOKED))
    by_pid = {}
    for r in res.scalars().all():
        by_pid.setdefault(r.project_id, []).append(r)
    base = {j: len(state["live"].get(j, ())) for j in state["eligible_ids"]}
    strengthened = []
    for _ in range(max(1, len(state["eligible_ids"]) + 1)):
        weak = single_shared_pairs(state["coverage"])
        if not weak:
            break
        n_weak_before = len(weak)
        n_comps_before = len(components_of(state["live"]))
        options = []
        for a, b in weak:
            shared = state["coverage"][a] & state["coverage"][b]
            members_a = by_pid.get(a, [])
            if len(members_a) < 2:
                continue  # nothing movable without breaking coverage
            movable = [r for r in members_a
                       if (r.status.value if hasattr(r.status, "value") else str(r.status)) != "COMPLETED"
                       and r.judge_user_id not in shared]
            if not movable:
                continue
            on_a = {r.judge_user_id for r in members_a}
            # Recipients serve b but not a; the shared judge is already on a.
            recipients = [j for j in state["coverage"].get(b, set())
                          if j in state["eligible_ids"] and j not in on_a]
            if not recipients:
                continue
            for r in movable:
                d = r.judge_user_id
                for t in recipients:
                    sim_min = sim_max = None
                    for j, k in base.items():
                        v = k - (j == d) + (j == t)
                        sim_min = v if sim_min is None or v < sim_min else sim_min
                        sim_max = v if sim_max is None or v > sim_max else sim_max
                    options.append((sim_max - sim_min, r.id in with_eval,
                                    a, b, r.id, t, r))
        options.sort()
        done = None
        for _, _, a, b, _, to_judge, donor in options:
            trial_cov = {p: set(js) for p, js in state["coverage"].items()}
            trial_cov[a].discard(donor.judge_user_id)
            trial_cov[a].add(to_judge)
            trial_live = {j: set(ps) for j, ps in state["live"].items()}
            trial_live[donor.judge_user_id].discard(a)
            trial_live.setdefault(to_judge, set()).add(a)
            trial_live = {j: ps for j, ps in trial_live.items() if ps}
            if shared_judge_count(trial_cov, a, b) < 2:
                continue
            if len(single_shared_pairs(trial_cov)) >= n_weak_before:
                continue
            if len(components_of(trial_live)) > n_comps_before:
                continue
            done = (a, b, to_judge, donor)
            break
        if done is None:
            break
        a, b, to_judge, donor = done
        donor.status = AssignmentStatus.REVOKED
        await db.flush()
        await _insert_slots(db, event_id, a, [to_judge])
        state["live"][donor.judge_user_id].discard(a)
        state["live"].setdefault(to_judge, set()).add(a)
        state["coverage"].setdefault(a, set()).discard(donor.judge_user_id)
        state["coverage"][a].add(to_judge)
        state["loads"][donor.judge_user_id] = state["loads"].get(donor.judge_user_id, 0) - 1
        state["loads"][to_judge] = state["loads"].get(to_judge, 0) + 1
        # by_pid donor row is now REVOKED; drop it so later iterations in this
        # pass never pick it as a donor again.
        by_pid[a] = [r for r in by_pid.get(a, []) if r.id != donor.id]
        strengthened.append({"project_id": a, "linked_project": b,
                             "from_judge": donor.judge_user_id,
                             "to_judge": to_judge})
    return strengthened


async def assign_all_pending(db: AsyncSession, event_id: str) -> dict:
    """Batch mode: fill every under-covered SUBMITTED project, then verify
    connectivity, repair by rewiring where possible, and strengthen thin
    (single-shared-judge) bridges into redundant ones.

    Idempotent: a second run finds no slots and (if connected) no repairs.
    Post-close the fill finds nothing (per-project gate) and repair/strengthen
    are skipped — swaps move work, which the deadline forbids.
    """
    event = await _lock_event(db, event_id)
    state = await _load_state(db, event, with_projects=True)
    touched, created = set(), 0
    for pid in state["pids"]:
        need = max(0, event.judges_per_project - len(state["coverage"].get(pid, ())))
        if need <= 0:
            continue
        picked = _fill_project_slots(state, pid, need)
        if not picked:
            continue
        created += await _insert_slots(db, event.id, pid, picked)
        touched.add(pid)
    repairs, strengthened = [], []
    if await _svc.judging_stage(db, event) not in ("CLOSED", "RESULTS_READY"):
        repairs = await _repair_connectivity(db, event.id, state)
        # Repair inserts are replacements, not new coverage (each revokes one
        # row and creates one), so they stay out of assignments_created and
        # are reported separately — otherwise the count overstates progress.
        touched.update(r["project_id"] for r in repairs)
        strengthened = await _strengthen_bridges(db, event.id, state)
        touched.update(r["project_id"] for r in strengthened)
    comps = components_of(state["live"])
    return {"projects_touched": len(touched), "assignments_created": created,
            "connected": len(comps) <= 1, "components": len(comps),
            "repairs": repairs, "strengthened": strengthened,
            "min_bridge": min_bridge(state["coverage"]),
            "weak_bridges": len(single_shared_pairs(state["coverage"]))}


async def assign_judge_to_project(db: AsyncSession, event_id: str,
                                    project_id: str, judge_user_id: str) -> dict:
    """Organizer-picked assignment from the existing pool (no new judges).

    Unlike the balanced fills, this names one judge for one project — the
    close-call workflow (extra judging where uncertainty is highest). The
    judge must already be eligible: active roster row AND still holding the
    JUDGE role. Refuses duplicates (409), non-SUBMITTED projects (422), and
    closed windows (409 — reopen first, same as batch). May exceed
    judges_per_project: extra judging is the point, not a coverage fill.
    """
    event = await _lock_event(db, event_id)
    if await _svc.judging_stage(db, event) in ("CLOSED", "RESULTS_READY"):
        err(409, "invalid_state_transition",
            "Judging is closed — reopen the judging window before assigning extra judging.")
    p = await db.get(Project, project_id)
    if not p or p.event_id != event.id:
        err(404, "not_found", "Project not found in this event")
    if (p.status.value if hasattr(p.status, "value") else str(p.status)) != "SUBMITTED":
        err(422, "validation_error", "Only submitted projects can be assigned for judging")
    eligible = await eligible_judges(db, event.id)
    if not any(u.id == judge_user_id for u in eligible):
        err(422, "validation_error",
            "That judge is not in this event's eligible pool — roster them (with the JUDGE role) first")
    res = await db.execute(select(JudgeAssignment.judge_user_id).where(
        JudgeAssignment.project_id == project_id,
        JudgeAssignment.status != AssignmentStatus.REVOKED))
    if judge_user_id in {r[0] for r in res.all()}:
        err(409, "already_joined", "That judge already holds a live assignment for this project")
    created = await _insert_slots(db, event.id, project_id, [judge_user_id])
    if not created:
        err(409, "already_joined", "That judge already holds a live assignment for this project")
    who = next(u for u in eligible if u.id == judge_user_id)
    return {"assignment": {"project_id": project_id, "judge_user_id": judge_user_id,
                           "judge_display_name": who.display_name,
                           "judge_email": who.email, "status": "ASSIGNED"}}


async def remove_judge(db: AsyncSession, event_id: str, judge_user_id: str) -> dict:
    """Deactivate a roster row, revoke its incomplete work, and refill.

    COMPLETED assignments (and their evaluations) are never touched — history
    survives removal. Incomplete rows become REVOKED, then each affected
    project is refilled through the same balanced selection, excluding the
    removed judge and never duplicating an existing active pair.
    """
    event = await _lock_event(db, event_id)
    row = await db.get(EventJudge, (event.id, judge_user_id))
    if not row:
        err(404, "not_found", "This judge is not on this event's roster")
    row.is_active = False
    res = await db.execute(select(JudgeAssignment).where(
        JudgeAssignment.event_id == event.id,
        JudgeAssignment.judge_user_id == judge_user_id,
        JudgeAssignment.status.in_(ACTIVE)))
    incomplete = res.scalars().all()
    for a in incomplete:
        a.status = AssignmentStatus.REVOKED
    await db.flush()
    refilled, still_open = 0, 0
    for a in incomplete:
        # Refills preserve pre-close coverage, so they bypass the
        # closed-event gate.
        out = await assign_project(db, a.project_id, allow_closed=True)
        if out["assigned"]:
            refilled += 1
        else:
            still_open += 1
    return {"revoked": len(incomplete), "refilled": refilled,
            "still_open": still_open,
            "note": "completed work is untouched" if incomplete else "judge had no incomplete work"}


async def assignment_health(db: AsyncSession, event_id: str) -> dict:
    """Read-only validation checklist for the organizer console. No lock:
    slightly-racy dashboard data is fine, decisions never read this."""
    event = await db.get(Event, event_id)
    if not event:
        err(404, "not_found", "Event not found")
    state = await _load_state(db, event)
    eligible_ids = state["eligible_ids"]
    target = event.judges_per_project or 0
    live_counts = {uid: len(state["live"].get(uid, ())) for uid in eligible_ids}
    vals = sorted(live_counts.values())
    spread = (max(vals) - min(vals)) if vals else 0
    floor = min(target, len(eligible_ids)) if eligible_ids else 0
    under = sorted(pid for pid, js in state["coverage"].items() if len(js) < floor)
    titles = {}
    all_pids = list(state["coverage"].keys())
    if all_pids:
        res = await db.execute(select(Project.id, Project.title).where(
            Project.id.in_(all_pids)))
        titles = dict(res.all())
    comps = components_of(state["live"])
    maxcov = max((len(js) for js in state["coverage"].values()), default=0)
    solo = sorted(uid for uid in eligible_ids if len(state["live"].get(uid, ())) < 2)
    names = {u.id: u.display_name for u in state["eligible"]}
    checklist = []
    if not eligible_ids:
        checklist.append({"key": "roster", "level": "warn",
                          "detail": "No eligible judges on the roster — nothing can be assigned."})
    elif len(eligible_ids) < target:
        checklist.append({"key": "feasibility", "level": "warn",
                          "detail": f"Target is {target} judges per project but only "
                                    f"{len(eligible_ids)} judge(s) eligible — full coverage is "
                                    f"impossible until more judges are rostered."})
    else:
        checklist.append({"key": "feasibility", "level": "ok",
                          "detail": f"{len(eligible_ids)} eligible judges cover the target of {target} per project."})
    checklist.append({"key": "workload_spread",
                      "level": "ok" if spread <= 1 else "warn",
                      "detail": f"Live workload spread {spread} across {len(eligible_ids)} judge(s) "
                                f"(min {min(vals) if vals else 0}, max {max(vals) if vals else 0})."})
    if not under:
        checklist.append({"key": "coverage", "level": "ok",
                          "detail": "Every submitted project meets its coverage floor."})
    else:
        names_under = ", ".join(titles.get(pid, pid) for pid in under[:5])
        hint = ("run batch assignment" if len(eligible_ids) >= target
                else "roster more judges first")
        checklist.append({"key": "coverage", "level": "warn",
                          "detail": f"{len(under)} project(s) under covered ({names_under}) — {hint}."})
    if len(comps) <= 1:
        checklist.append({"key": "connectivity", "level": "ok",
                          "detail": "One connected comparison graph."})
    elif maxcov < 2:
        checklist.append({"key": "connectivity", "level": "info",
                          "detail": f"{len(comps)} disconnected components, and no project shares "
                                    f"judges (coverage 1) — raise judges-per-project so assignments "
                                    f"can link judges together."})
    else:
        checklist.append({"key": "connectivity", "level": "warn",
                          "detail": f"{len(comps)} disconnected components — run batch assignment to repair."})
    if not solo:
        checklist.append({"key": "comparisons", "level": "ok",
                          "detail": "Every judge serves 2+ projects and can form pairwise comparisons."})
    else:
        who = ", ".join(names.get(uid, uid) for uid in solo[:5])
        checklist.append({"key": "comparisons", "level": "info",
                          "detail": f"{len(solo)} judge(s) serve fewer than 2 projects ({who}) — no pairwise voice yet."})
    # --- Bridge-strength check ---
    # Connectivity is necessary but not sufficient. A single shared judge
    # between two project groups produces a near-flat BT likelihood direction
    # along which the prior (and reference choice) decides the result. Each
    # group pair should share ≥2 judges to give the model real evidence.
    #
    # For each ordered pair of projects (p1, p2) that share at least one
    # judge, count |judges(p1) ∩ judges(p2)|. Report the weakest link.
    coverage_sets = state["coverage"]  # {project_id: set of judge_ids}
    project_list = sorted(coverage_sets.keys())
    min_bridge = None
    n_weak_bridges = 0
    weak_pair_example = None
    for i, p1 in enumerate(project_list):
        for p2 in project_list[i + 1:]:
            shared = len(coverage_sets[p1] & coverage_sets[p2])
            if shared == 0:
                continue  # transitively connected only; fine here, tracked by connectivity
            if min_bridge is None or shared < min_bridge:
                min_bridge = shared
                if shared < 2:
                    weak_pair_example = (p1, p2)
            if shared < 2:
                n_weak_bridges += 1
    if min_bridge is None:
        checklist.append({"key": "bridge_strength", "level": "info",
                          "detail": "No direct shared-judge links yet — assign judges first."})
    elif min_bridge >= 2:
        checklist.append({"key": "bridge_strength", "level": "ok",
                          "detail": f"All directly-linked project pairs share ≥2 judges "
                                    f"(minimum {min_bridge}). BT comparisons are well-supported."})
    else:
        ex_titles = ""
        if weak_pair_example:
            t1 = titles.get(weak_pair_example[0], weak_pair_example[0])
            t2 = titles.get(weak_pair_example[1], weak_pair_example[1])
            ex_titles = f" (e.g. {t1!r} ↔ {t2!r})"
        checklist.append({"key": "bridge_strength", "level": "warn",
                          "detail": f"{n_weak_bridges} project pair(s) share only 1 judge{ex_titles}. "
                                    f"Comparisons between them rest on a single judge's verdicts, "
                                    f"so the model may misorder these pairs. Raise judges-per-project "
                                    f"to ≥3 and re-run batch assignment."})
    return {
        "judges": len(eligible_ids),
        "projects": len(state["coverage"]),
        "workload": {"min": min(vals) if vals else 0,
                     "max": max(vals) if vals else 0, "spread": spread},
        "coverage": {"target": target,
                     "min": min((len(v) for v in state["coverage"].values()), default=0),
                     "max": maxcov,
                     "under_covered": [{"id": pid, "title": titles.get(pid, pid)} for pid in under]},
        "connected": len(comps) <= 1,
        "components": len(comps),
        "pairwise_capacity": sum(k * (k - 1) // 2 for k in live_counts.values()),
        "checklist": checklist,
    }


async def utilization(db: AsyncSession, event_id: str) -> list[dict]:
    """Per-judge load table for the organizer console."""
    res = await db.execute(
        select(User, EventJudge.is_active).join(
            EventJudge, EventJudge.user_id == User.id).where(
            EventJudge.event_id == event_id).order_by(User.display_name))
    event = await db.get(Event, event_id)
    if not event:
        err(404, "not_found", "Event not found")
    state = await _load_state(db, event)
    done = await db.execute(
        select(Evaluation.judge_user_id, func.count()).where(
            Evaluation.event_id == event_id,
            Evaluation.status == EvaluationStatus.SUBMITTED
        ).group_by(Evaluation.judge_user_id))
    done_map = {uid: n for uid, n in done.all()}
    total = await db.execute(
        select(JudgeAssignment.judge_user_id, func.count()).where(
            JudgeAssignment.event_id == event_id
        ).group_by(JudgeAssignment.judge_user_id))
    total_map = {uid: n for uid, n in total.all()}
    out = []
    for u, active in res.all():
        k = len(state["live"].get(u.id, ()))
        out.append({
            "user_id": u.id, "email": u.email, "display_name": u.display_name,
            "role": _role_of(u), "is_active": active,
            "active_load": state["loads"].get(u.id, 0),
            "live_projects": k,
            "pairwise_capacity": k * (k - 1) // 2,
            "completed": done_map.get(u.id, 0),
            "total_assigned": total_map.get(u.id, 0),
        })
    return out
