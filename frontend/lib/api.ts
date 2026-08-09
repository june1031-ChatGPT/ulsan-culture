import type { EventListResponse } from "@/lib/types";

type EventsResult =
  | { ok: true; data: EventListResponse }
  | { ok: false; error: string };


export async function getEvents(): Promise<EventsResult> {
  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/api/events`, { cache: "no-store" });
    if (!response.ok) {
      return { ok: false, error: `API responded with ${response.status}` };
    }
    return { ok: true, data: (await response.json()) as EventListResponse };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown API error";
    return { ok: false, error: message };
  }
}

