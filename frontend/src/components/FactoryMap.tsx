"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Search,
  Target,
  ClipboardList,
  Palette,
  Factory,
  CheckCircle2,
  Tag,
  FileCheck,
  PackageCheck,
  Megaphone,
  LineChart,
  TrendingUp,
  Lock,
  User,
  ArrowRight,
  type LucideIcon,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

/**
 * The production pipeline rendered as a literal factory floor plan: each
 * stage is a room, hallways connect them, and a quiet presence indicator
 * shows inside a room only while that stage has real activity. All of it --
 * which rooms are staffed, which are idle, which are still "under
 * construction" -- is read from the most recent real WorkflowRun. Nothing
 * here is decorative fake activity; an empty system renders every room
 * empty, honestly. Deliberately restrained: one small line icon per room,
 * no color-saturated badges, no cartoon avatars -- see globals.css for the
 * design-discipline note this follows.
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
  icon: LucideIcon;
}[] = [
  { stage: "research", label: "Research Lab", col: 0, row: 0, zone: "core", icon: Search },
  { stage: "opportunity_selection", label: "Selection Room", col: 1, row: 0, zone: "core", icon: Target },
  { stage: "product_planning", label: "Planning Desk", col: 2, row: 0, zone: "core", icon: ClipboardList },
  { stage: "creative_direction", label: "Design Studio", col: 3, row: 0, zone: "core", icon: Palette },
  { stage: "production", label: "Production Floor", col: 3, row: 1, zone: "core", icon: Factory },
  { stage: "quality_assurance", label: "QA Bay", col: 2, row: 1, zone: "core", icon: CheckCircle2 },
  { stage: "listing_creation", label: "Listing Desk", col: 1, row: 1, zone: "core", icon: Tag },
  { stage: "authorization", label: "Approval Office", col: 0, row: 1, zone: "core", icon: FileCheck },
  { stage: "publication", label: "Shipping Dock", col: 0, row: 2, zone: "core", icon: PackageCheck },
  { stage: "marketing", label: "Marketing Wing", col: 1, row: 2, zone: "planned", icon: Megaphone },
  { stage: "sales_monitoring", label: "Sales Watch", col: 2, row: 2, zone: "planned", icon: LineChart },
  { stage: "optimization", label: "R&D Annex", col: 3, row: 2, zone: "planned", icon: TrendingUp },
];

const ROOM_W = 190;
const ROOM_H = 118;
const GAP = 52;
const HALL = 2;
const PAD = 24;

function roomPos(col: number, row: number) {
  return { x: PAD + col * (ROOM_W + GAP), y: PAD + row * (ROOM_H + GAP) };
}

function statusVisual(status: string | undefined, zone: "core" | "planned") {
  if (zone === "planned") {
    return { iconColor: "var(--text-faint)", labelColor: "var(--text-faint)", pill: "chip-dim", present: false };
  }
  switch (status) {
    case "completed":
    case "published":
    case "published_simulated":
      return { iconColor: "var(--success-strong)", labelColor: "var(--text)", pill: "chip-neon", present: true };
    case "running":
      return { iconColor: "var(--blue-strong)", labelColor: "var(--text)", pill: "chip-blue", present: true };
    case "failed":
      return { iconColor: "var(--danger)", labelColor: "var(--text)", pill: "chip-danger", present: false };
    default:
      return { iconColor: "var(--text-faint)", labelColor: "var(--text-dim)", pill: "chip-dim", present: false };
  }
}

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

  // Stable per-hallway animation delay so handoff markers don't all march in lockstep.
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
    const reversed = orientation === "horiz" ? pb.x < pa.x : pb.y < pa.y;
    return { key: `${a.stage}-${b.stage}`, fromStage: a.stage, style, active, orientation, reversed };
  });

  return (
    <div className="panel p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="font-semibold text-[14px]">Factory Floor</h2>
          <p className="text-xs text-[var(--text-faint)] mt-0.5">Live view of the production pipeline</p>
        </div>
        <span className="chip chip-dim">{runLabel}</span>
      </div>

      <div className="overflow-x-auto pb-2">
        <div className="relative" style={{ width, height, minWidth: width }}>
          {hallways.map((h) => {
            const wrap =
              h.orientation === "horiz"
                ? { left: h.style.left, top: h.style.top - 7, width: h.style.width, height: h.style.height + 14 }
                : { left: h.style.left - 7, top: h.style.top, width: h.style.width + 14, height: h.style.height };
            const lineInset =
              h.orientation === "horiz" ? { left: 0, top: 7, width: wrap.width, height: HALL } : { left: 7, top: 0, width: HALL, height: wrap.height };

            return (
              <div key={h.key} className="absolute" style={wrap}>
                <div className={`absolute hallway-line ${h.active ? "hallway-active" : ""}`} style={lineInset} />
                {h.active && (
                  <span
                    className={`hall-walker ${h.orientation} ${h.reversed ? "reversed" : ""}`}
                    style={{ animationDelay: `${hallwayDelays[h.fromStage] ?? 0}s` }}
                  >
                    <ArrowRight size={11} strokeWidth={2} />
                  </span>
                )}
              </div>
            );
          })}

          {STAGE_LAYOUT.map((room) => {
            const status = room.stage === currentStage ? "running" : taskMap[room.stage];
            const v = statusVisual(status, room.zone);
            const pos = roomPos(room.col, room.row);
            const Icon = room.icon;

            return (
              <div
                key={room.stage}
                className={`absolute room-card p-3.5 ${room.zone === "planned" ? "room-planned" : ""}`}
                style={{ left: pos.x, top: pos.y, width: ROOM_W, height: ROOM_H, overflow: "hidden" }}
              >
                <div className="flex items-start justify-between">
                  <Icon size={17} strokeWidth={1.6} color={v.iconColor} />
                  <span className={`chip ${v.pill} !text-[9px] !py-0.5 !px-1.5`}>
                    {room.zone === "planned" ? "planned" : status || "idle"}
                  </span>
                </div>
                <div className="text-[13px] font-medium mt-2.5" style={{ color: v.labelColor }}>
                  {room.label}
                </div>

                {room.zone === "planned" ? (
                  <div className="text-[10px] text-[var(--text-faint)] mt-1 flex items-center gap-1">
                    <Lock size={10} strokeWidth={1.75} />
                    not yet built
                  </div>
                ) : (
                  <div className="text-[10px] text-[var(--text-faint)] mt-1">
                    {status === "running" ? "In progress" : status === "failed" ? "Failed" : v.present ? "Completed" : "Idle"}
                  </div>
                )}

                {v.present && (
                  <div className="absolute bottom-3 right-3 opacity-60">
                    <User size={13} strokeWidth={1.75} color={v.iconColor} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex gap-2 mt-5 flex-wrap">
        <span className="chip chip-neon">Completed</span>
        <span className="chip chip-blue">Active now</span>
        <span className="chip chip-dim">Idle</span>
        <span className="chip chip-dim">
          <Lock size={10} strokeWidth={1.75} /> Not yet built
        </span>
      </div>
    </div>
  );
}
