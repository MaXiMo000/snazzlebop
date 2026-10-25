import { request } from "./api";
import type { MyRatings, Ok, RatingBoard } from "./contract";

export type { MyRatings, RatingBoard } from "./contract";

export type Scope = "everyone" | "club" | "place";
export type Period = "season" | "week";

export const myRatings = () => request<MyRatings>("/api/ratings/me");
export const ratingBoard = (game: string, scope: Scope, slug: string, period: Period) =>
  request<RatingBoard>(`/api/ratings/board?${new URLSearchParams({ game, scope, slug, period }).toString()}`);
/** Whether you appear on the leaderboards of places you're verified at. */
export const setPlaceBoards = (on: boolean) => request<Ok>("/api/me/place-boards", { method: "POST", body: JSON.stringify({ on }) });
