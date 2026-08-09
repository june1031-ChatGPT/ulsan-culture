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
          registration_start: "2026-08-13T09:00:00+09:00",
          registration_end: "2026-08-20T18:00:00+09:00",
          registration_status: "접수예정",
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "어린이 별자리 관측" })).toBeInTheDocument();
    expect(screen.getByText("행사 시작")).toBeInTheDocument();
    expect(screen.getByText("접수 시작")).toBeInTheDocument();
    expect(screen.getByText("접수 마감")).toBeInTheDocument();
  });
});

