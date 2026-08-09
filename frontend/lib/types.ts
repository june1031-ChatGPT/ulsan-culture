export type EventItem = {
  id: number;
  title: string;
  organizer: string | null;
  event_start: string | null;
  event_end: string | null;
  registration_start: string | null;
  registration_end: string | null;
  registration_status: string | null;
};

export type EventListResponse = {
  items: EventItem[];
  total: number;
  limit: number;
  offset: number;
};

