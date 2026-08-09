import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EventCard } from "./event-card";


describe("EventCard", () => {
  it("행사일과 접수일을 별도로 표시한다", () => {
    render(
      <EventCard
        event={{
          id: 1,
          title: "어린이 별자리 관측",
          organizer: "울산과학관",
          event_start: "2026-08-29T14:00:00+09:00",
          event_end: "2026-08-29T16:00:00+09:00",
          event_start_date: null,
          event_end_date: null,
          registration_start: "2026-08-13T09:00:00+09:00",
          registration_end: "2026-08-20T18:00:00+09:00",
          registration_start_date: null,
          registration_end_date: null,
          registration_status: "접수예정",
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "어린이 별자리 관측" })).toBeInTheDocument();
    expect(screen.getByText("행사 시작")).toBeInTheDocument();
    expect(screen.getByText("접수 시작")).toBeInTheDocument();
    expect(screen.getByText("접수 마감")).toBeInTheDocument();
  });

  it("시간을 모르는 날짜-only 값은 날짜로 표시한다", () => {
    render(
      <EventCard
        event={{
          id: 2,
          title: "날짜만 공개된 행사",
          organizer: null,
          event_start: null,
          event_end: null,
          event_start_date: "2026-08-29",
          event_end_date: "2026-08-30",
          registration_start: null,
          registration_end: null,
          registration_start_date: "2026-08-13",
          registration_end_date: "2026-08-20",
          registration_status: null,
        }}
      />,
    );

    expect(screen.getByText("2026. 8. 29.")).toBeInTheDocument();
    expect(screen.getByText("2026. 8. 13.")).toBeInTheDocument();
    expect(screen.getByText("2026. 8. 20.")).toBeInTheDocument();
  });
});
