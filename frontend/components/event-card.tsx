import type { EventItem } from "@/lib/types";

const dateFormatter = new Intl.DateTimeFormat("ko-KR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Seoul",
});

function formatDate(datetimeValue: string | null, dateValue: string | null) {
  if (datetimeValue) {
    return dateFormatter.format(new Date(datetimeValue));
  }
  if (dateValue) {
    const [year, month, day] = dateValue.split("-");
    return `${Number(year)}. ${Number(month)}. ${Number(day)}.`;
  }
  return "일정 미정";
}

export function EventCard({ event }: { event: EventItem }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-xl font-bold text-slate-950">{event.title}</h3>
        {event.registration_status && (
          <span className="shrink-0 rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-700">
            {event.registration_status}
          </span>
        )}
      </div>
      <p className="mt-2 text-sm text-slate-500">{event.organizer ?? "주최 기관 미정"}</p>
      <dl className="mt-5 grid gap-3 text-sm">
        <div className="grid grid-cols-[5rem_1fr] gap-3">
          <dt className="font-medium text-slate-500">행사 시작</dt>
          <dd className="text-slate-800">
            {formatDate(event.event_start, event.event_start_date)}
          </dd>
        </div>
        <div className="grid grid-cols-[5rem_1fr] gap-3">
          <dt className="font-medium text-slate-500">접수 시작</dt>
          <dd className="text-slate-800">
            {formatDate(event.registration_start, event.registration_start_date)}
          </dd>
        </div>
        <div className="grid grid-cols-[5rem_1fr] gap-3">
          <dt className="font-medium text-slate-500">접수 마감</dt>
          <dd className="text-slate-800">
            {formatDate(event.registration_end, event.registration_end_date)}
          </dd>
        </div>
      </dl>
    </article>
  );
}
