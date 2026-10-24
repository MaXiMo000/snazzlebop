import { request } from "./api";
import type { MyPlaces, PlaceList, PlaceStarted, StaffPlaces } from "./contract";

export type { MyPlaces, PlaceList, StaffPlaces } from "./contract";

const post = <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });

export const allPlaces = () => request<PlaceList>("/api/places");
export const myPlaces = () => request<MyPlaces>("/api/me/places");
/** Email a code to a college or work address. */
export const startPlace = (email: string) => post<PlaceStarted>("/api/me/places/start", { email });
export const confirmPlace = (code: string) => post<MyPlaces>("/api/me/places/confirm", { code });
export const removePlace = (slug: string) => post<MyPlaces>(`/api/me/places/${encodeURIComponent(slug)}/remove`);

// -- staff: the places people can verify
export const staffPlaces = () => request<StaffPlaces>("/api/staff/places");
export const savePlace = (body: { slug?: string; name: string; kind: string; domains: string[] }) =>
  post<StaffPlaces>("/api/staff/places", body);
export const declineRequest = (domain: string) => post<StaffPlaces>("/api/staff/places/requests/decline", { domain });
