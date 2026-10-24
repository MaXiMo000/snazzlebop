/**
 * The HTTP API's types, generated from the backend's contract (frontend/openapi.json, written by
 * scripts/export_openapi.py; `npm run gen:api` regenerates api.gen.ts). Import response types from
 * here, never hand-write them: CI fails when the backend and these drift apart.
 */
import type { components } from "./api.gen";

type Schemas = components["schemas"];

export type ApiErrorBody = Schemas["ErrorBody"];
export type ApiGameCard = Schemas["GameCard"];
export type RoomPass = Schemas["RoomPass"];
export type TvPass = Schemas["TvPass"];
export type Account = Schemas["PublicUser"];
export type UserBody = Schemas["UserBody"];
export type NewAccount = Schemas["NewAccount"];
export type Me = Schemas["Me"];
export type Stats = Schemas["MyStats"];
export type FriendList = Schemas["Friends"];
export type ShopItem = Schemas["ShopItem"];
export type Shop = Schemas["Shop"];
export type Board = Schemas["Leaderboard"];
export type Ok = Schemas["Ok"];
export type MfaStatus = Schemas["MfaStatus"];
export type MfaSetup = Schemas["MfaSetup"];
export type BackupCodes = Schemas["BackupCodes"];

// The WebSocket "state" frame (backend app/schemas.py RoomFrame).
export type ApiRoomFrame = Schemas["RoomFrame"];
