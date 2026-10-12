"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";

/**
 * The production pipeline rendered as a literal factory floor plan: each
 * stage is a room, hallways connect them, and little workers wander inside
 * a room only while that stage has real activity. All of it -- which rooms
 * are staffed, which are idle, which are still "under construction" -- is
 * read from the most recent real WorkflowRun. Nothing here is decorative
 * fake activity; an empty system renders every room empty, honestly.
 * Worker positions wander via CSS only (randomized once per mount, not
 * re-rolled on every poll) so they drift instead of teleporting.
 */

type TaskStatus = { stage: string; agent_key: string; status: string };
type WorkflowRunDetail = { id: number; status: string; current_stage: string | null; tasks: TaskStatus[] };
type WorkflowRunSummary = { id: number; status: string };

const STAGE_LAYOUT: {
  stage: string;
  label: string;
  col: number;
  row: number;
  zone: "core" | "planned";
  icon: string;
  worker: string;
}[] = [
  { stage: "research", label: "Research Lab", col: 0, row: 0, zone: "core", icon: "\u{1F50E}", worker: "\u{1F9D1}‍\u{1F52C}" },
  { stage: "opportunity_selection", label: "Selection Room", col: 1, row: 0, zone: "core", icon: "\u{1F3AF}", worker: "\u{1F9D1}‍\u{1F4BC}" },
  { stage: "product_planning", label: "Planning Desk", col: 2, row: 0, zone: "core", icon: "\u{1F4CB}", worker: "\u{1F9D1}‍\u{1F4BB}" },
  { stage: "creative_direction", label: "Design Studio", col: 3, row: 0, zone: "core", icon: "\u{1F3A8}", worker: "\u{1F9D1}‍\u{1F3A8}" },
  { stage: "production", label: "Production Floor", col: 3, row: 1, zone: "core", icon: "\u{1F3ED}", worker: "\u{1F477}" },
  { stage: "quality_assurance", label: "QA Bay", col: 2, row: 1, zone: "core", icon: "\u{1F50D}", worker: "\u{1F575}️" },
  { stage: "listing_creation", label: "Listing Desk", col: 1, row: 1, zone: "core", icon: "\u{1F3F7}️", worker: "\u{1F9D1}‍\u{1F4BB}" },
  { stage: "authorization", label: "Approval Office", col: 0, row: 1, zone: "core", icon: "\u{1F4DD}", worker: "\u{1F9D1}‍⚖️" },
  { stage: "publication", label: "Shipping Dock", col: 0, row: 2, zone: "core", icon: "\u{1F4E6}", worker: "\u{1F9D1}‍✈️" },
  { stage: "marketing", label: "Marketing Wing", col: 1, row: 2, zone: "planned", icon: "\u{1F4E3}", worker: "" },
  { stage: "sales_monitoring", label: "Sales Watch", col: 2, row: 2, zone: "planned", icon: "\u{1F4CA}", worker: "" },
  { stage: "optimization", label: "R&D Annex", col: 3, row: 2, zone: "planned", icon: "\u{1F4C8}", worker: "" },
];

const ROOM_W = 190;
const ROOM_H = 132;
const GAP = 56;
const HALL = 3;
const PAD = 24;
// Secondary worker shown alongside the room's thematic specialist when a
// stage is actively running (busier-looking than a single completed stage).
const HELPER_EMOJI = ["\u{1F9D1}", "\u{1F469}", "\u{1F468}"];
const HANDOFF_ITEM = "\u{1F4E6}";

function roomPos(col: number, row: number) {
  return { x: PAD + col * (ROOM_W + GAP), y: PAD + row * (ROOM_H + GAP) };
}

function statusVisual(status: string | undefined, zone: "core" | "planned") {
  if (zone === "planned") {
    return {
      iconBg: "linear-gradient(135deg, #2a2117 0%, #1a1611 100%)",
      label: "var(--text-faint)",
      pill: "chip-amber",
      workers: 0,
      active: false,
    };
  }
  switch (status) {
    case "completed":
    case "published":
    case "published_simulated":
      return {
        iconBg: "linear-gradient(135deg, var(--accent) 0%, #059669 100%)",
        label: "var(--text)",
        pill: "chip-neon",
        workers: 1,
        active: true,
      };
    case "running":
      return {
        iconBg: "linear-gradient(135deg, var(--blue) 0%, #2563eb 100%)",
        label: "var(--text)",
        pill: "chip-blue",
        workers: 2,
        active: true,
      };
    case "failed":
      return {
        iconBg: "linear-gradient(135deg, var(--danger) 0%, #dc2626 100%)",
        label: "var(--text)",
        pill: "chip-dim",
        workers: 0,
        active: false,
      };
    default:
      return {
        iconBg: "linear-gradient(135deg, var(--surface-hover) 0%, var(--surface) 100%)",
        label: "var(--text-dim)",
        pill: "chip-dim",
        workers: 0,
        active: false,
      };
  }
}

type WorkerSeed = { p1x: number; p1y: number; p2x: number; p2y: number; p3x: number; p3y: number; dur: number; delay: number; emoji: string };

export default function FactoryMap() {
  const [taskMap, setTaskMap] = useState<Record<string, string>>({});
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [runLabel, setRunLabel] = useState<string>("No workflow run yet");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const runs = await apiFetch<WorkflowRunSummary[]>("/missions/workflow-runs");
        if (!runs.length) return;
        const latest = await apiFetch<WorkflowRunDetail>(`/missions/workflow-runs/${runs[0].id}`);
        if (cancelled) return;
        const map: Record<string, string> = {};
        for (const t of latest.tasks) map[t.stage] = t.status;
        setTaskMap(map);
        setCurrentStage(latest.status === "running" ? latest.current_stage : null);
        setRunLabel(`Run #${latest.id} -- ${latest.status}`);
      } catch {
        /* leave the floor plan in its honest empty state */
      }
    }
    load();
    const interval = setInterval(load, 6000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // Randomized once per mount so workers drift smoothly instead of
  // re-teleporting every time the 6s poll refreshes stage status.
  const workerSeeds = useMemo(() => {
    const bound = Math.min(ROOM_W, ROOM_H) / 2 - 26;
    const rand = (n: number) => Math.round((Math.random() * 2 - 1) * n);
    const seeds: Record<string, WorkerSeed[]> = {};
    for (const s of STAGE_LAYOUT) {
      seeds[s.stage] = Array.from({ length: 2 }, (_, i) => ({
        p1x: rand(bound), p1y: rand(bound),
        p2x: rand(bound), p2y: rand(bound),
        p3x: rand(bound), p3y: rand(bound),
        dur: 7 + Math.random() * 5,
        delay: Math.random() * 3,
        emoji: i === 0 ? s.worker : HELPER_EMOJI[(i + s.label.length) % HELPER_EMOJI.length],
      }));
    }
    return seeds;
  }, []);

  // Stable per-hallway animation delay so handoff walkers don't all march in lockstep.
  const hallwayDelays = useMemo(
    () => Object.fromEntries(STAGE_LAYOUT.map((s) => [s.stage, Math.random() * 1.8])),
    []
  );

  const width = 4 * ROOM_W + 3 * GAP + PAD * 2;
  const height = 3 * ROOM_H + 2 * GAP + PAD * 2;

  const hallways = STAGE_LAYOUT.slice(0, -1).map((a, i) => {
    const b = STAGE_LAYOUT[i + 1];
    const pa = roomPos(a.col, a.row);
    const pb = roomPos(b.col, b.row);
    const aStatus = taskMap[a.stage];
    const active = aStatus === "completed" || aStatus === "published" || aStatus === "published_simulated";

    const orientation: "horiz" | "vert" = a.row === b.row ? "horiz" : "vert";
    const style =
      orientation === "horiz"
        ? { left: Math.min(pa.x, pb.x) + ROOM_W, top: pa.y + ROOM_H / 2 - HALL / 2, width: GAP, height: HALL }
        : { left: pa.x + ROOM_W / 2 - HALL / 2, top: Math.min(pa.y, pb.y) + ROOM_H, width: HALL, height: GAP };
    // Reversed for a right-to-left or bottom-to-top leg of the snake layout,
    // so the handoff walker always visibly travels from the finished room
    // toward the next one rather than backwards.
    const reversed = orientation === "horiz" ? pb.x < pa.x : pb.y < pa.y;
    return { key: `${a.stage}-${b.stage}`, fromStage: a.stage, style, active, orientation, reversed };
  });

  return (
    <div className="panel p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="font-semibold text-[15px]">Factory Floor</h2>
          <p className="text-xs text-[var(--text-faint)] mt-0.5">Live view of the production pipeline</p>
        </div>
        <span className="chip chip-dim">{runLabel}</span>
      </div>

      <div className="overflow-x-auto pb-2">
        <div className="relative" style={{ width, height, minWidth: width }}>
          {hallways.map((h) => {
            // The walker's CSS keyframes move it with percentage top/left, which
            // resolve against THIS wrapper's own box -- so the wrapper must have
            // an explicit, correctly-sized width/height (not just "absolute" with
            // no dimensions), or the percentages resolve against an indeterminate
            // containing block and the walker ends up positioned nonsensically.
            const wrap =
              h.orientation === "horiz"
                ? { left: h.style.left, top: h.style.top - 8, width: h.style.width, height: h.style.height + 16 }
                : { left: h.style.left - 8, top: h.style.top, width: h.style.width + 16, height: h.style.height };
            const lineInset =
              h.orientation === "horiz" ? { left: 0, top: 8, width: wrap.width, height: HALL } : { left: 8, top: 0, width: HALL, height: wrap.height };

            return (
              <div key={h.key} className="absolute" style={wrap}>
                <div
                  className={`absolute rounded-full hallway-line ${h.active ? "hallway-active" : ""}`}
                  style={lineInset}
                />
                {h.active && (
                  <span
                    className={`hall-walker ${h.orientation} ${h.reversed ? "reversed" : ""}`}
                    style={{ animationDelay: `${hallwayDelays[h.fromStage] ?? 0}s` }}
                  >
                    {HANDOFF_ITEM}
                  </span>
                )}
              </div>
            );
          })}

          {STAGE_LAYOUT.map((room) => {
            const status = room.stage === currentStage ? "running" : taskMap[room.stage];
            const v = statusVisual(status, room.zone);
            const pos = roomPos(room.col, room.row);
            const seeds = workerSeeds[room.stage] || [];
            const activeWorkers = seeds.slice(0, v.workers);

            return (
              <div
                key={room.stage}
                className={`absolute room-card p-3.5 ${v.active ? "room-active" : ""} ${
                  room.zone === "planned" ? "room-planned" : ""
                }`}
                style={{ left: pos.x, top: pos.y, width: ROOM_W, height: ROOM_H, overflow: "hidden" }}
              >
                <div className="flex items-start justify-between">
                  <div className="icon-badge" style={{ background: v.iconBg }}>
                    {room.icon}
                  </div>
                  <span className={`chip ${v.pill} !text-[9px] !py-0.5 !px-2`}>
                    {room.zone === "planned" ? "planned" : status || "idle"}
                  </span>
                </div>
                <div className="text-[13px] font-semibold mt-2.5" style={{ color: v.label }}>
                  {room.label}
                </div>

                {room.zone === "planned" ? (
                  <div className="text-[10px] text-[var(--text-faint)] mt-1 flex items-center gap-1">
                    <span>{"\u{1F6A7}"}</span> not yet built
                  </div>
                ) : activeWorkers.length === 0 ? (
                  <div className="text-[10px] text-[var(--text-faint)] mt-1">Idle</div>
                ) : (
                  <div className="text-[10px] text-[var(--text-dim)] mt-1">
                    {v.workers === 2 ? "In progress" : "Completed"}
                  </div>
                )}

                {activeWorkers.map((w, i) => (
                  <span
                    key={i}
                    className="worker-token"
                    style={
                      {
                        left: "62%",
                        top: "68%",
                        "--p1x": `${w.p1x}px`, "--p1y": `${w.p1y}px`,
                        "--p2x": `${w.p2x}px`, "--p2y": `${w.p2y}px`,
                        "--p3x": `${w.p3x}px`, "--p3y": `${w.p3y}px`,
                        "--dur": `${w.dur}s`,
                        "--delay": `${w.delay}s`,
                      } as React.CSSProperties
                    }
                  >
                    {w.emoji}
                  </span>
                ))}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex gap-2 mt-5 flex-wrap">
        <span className="chip chip-neon">Completed</span>
        <span className="chip chip-blue">Active now</span>
        <span className="chip chip-dim">Idle</span>
        <span className="chip chip-amber">{"\u{1F6A7}"} Not yet built</span>
      </div>
    </div>
  );
}
