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
export type ClubSummary = Schemas["ClubSummary"];
export type ClubList = Schemas["ClubList"];
export type ClubDetail = Schemas["ClubDetail"];
export type ClubBoards = Schemas["ClubBoards"];
export type BillingConfig = Schemas["BillingConfig"];
export type PlusCheckout = Schemas["PlusCheckout"];
export type MyPlus = Schemas["MyPlus"];
export type PlusManage = Schemas["PlusManage"];
export type ClubRules = Schemas["ClubRules"];
export type NewInvite = Schemas["NewInvite"];
export type Inbox = Schemas["Inbox"];
export type InboxItem = Schemas["InboxItem"];
export type NotifyPrefs = Schemas["NotifyPrefs"];
export type Invitees = Schemas["Invitees"];
export type BlockList = Schemas["BlockList"];
export type ClubReports = Schemas["ClubReports"];
export type SiteInfo = Schemas["SiteInfo"];
export type StaffQueue = Schemas["StaffQueue"];
export type MyPlaces = Schemas["MyPlaces"];
export type PlaceList = Schemas["PlaceList"];
export type PlaceStarted = Schemas["PlaceStarted"];
export type StaffPlaces = Schemas["StaffPlaces"];
export type SessionList = Schemas["SessionList"];
export type Identities = Schemas["Identities"];
export type MyRatings = Schemas["MyRatings"];
export type Progress = Schemas["Progress"];
export type CoinHistory = Schemas["CoinHistory"];
export type BattleRecord = Schemas["BattleRecord"];
export type RatingBoard = Schemas["RatingBoard"];

// The WebSocket "state" frame (backend app/schemas.py RoomFrame).
export type ApiRoomFrame = Schemas["RoomFrame"];
