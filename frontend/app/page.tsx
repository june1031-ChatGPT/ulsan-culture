import { EventCard } from "@/components/event-card";
import { getEvents } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const result = await getEvents();

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-5 py-12 sm:px-8">
      <header className="mb-10 max-w-3xl">
        <p className="mb-3 text-sm font-semibold tracking-[0.18em] text-teal-700">ULSAN CULTURE</p>
        <h1 className="text-4xl font-bold tracking-tight text-slate-950 sm:text-5xl">울산컬처</h1>
        <p className="mt-4 text-lg leading-8 text-slate-600">
          좋은 체험, 신청일을 놓치지 마세요. 울산의 문화 프로그램과 접수 일정을 한곳에서
          확인합니다.
        </p>
      </header>

      <section aria-labelledby="events-heading">
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-teal-700">Phase 1</p>
            <h2 id="events-heading" className="mt-1 text-2xl font-bold text-slate-900">
              등록된 행사
            </h2>
          </div>
          {result.ok && <p className="text-sm text-slate-500">총 {result.data.total}건</p>}
        </div>

        {!result.ok ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-950">
            <h3 className="font-semibold">API에 연결할 수 없습니다.</h3>
            <p className="mt-2 text-sm leading-6">백엔드가 실행 중인지 확인한 뒤 새로고침해 주세요.</p>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
            <h3 className="font-semibold text-slate-900">아직 등록된 행사가 없습니다.</h3>
            <p className="mt-2 text-sm text-slate-500">Phase 2에서 공식 기관 수집 데이터가 추가됩니다.</p>
          </div>
        ) : (
          <div className="grid gap-5 md:grid-cols-2">
            {result.data.items.map((event) => (
              <EventCard event={event} key={event.id} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

