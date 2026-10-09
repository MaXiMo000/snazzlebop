"""Runtime configuration. Plain dataclass + os.environ: no extra dependency, easy to test."""

from __future__ import annotations

import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(x.strip() for x in (value or "").split(",") if x.strip())


def normalize_database_url(url: str) -> str:
    """Render hands out postgres:// or postgresql:// URLs; SQLAlchemy async needs a driver."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix) :]
            break
    if url.startswith("postgresql+asyncpg://") and "?" in url:
        # asyncpg rejects libpq-style params such as sslmode; Render's internal URL needs no TLS.
        base, query = url.split("?", 1)
        kept = [q for q in query.split("&") if q.split("=")[0] not in ("sslmode", "channel_binding")]
        url = base + ("?" + "&".join(kept) if kept else "")
    return url


JUMPSCARE_DEFAULT_NAMES: tuple[str, ...] = ()  # names come only from JUMPSCARE_NAMES (never the repo)


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    secret_key: str = field(default="", repr=False)
    database_url: str = "sqlite+aiosqlite:///./snazzlebop.db"
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    allowed_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    )
    # How many reverse proxies sit in front of the app and append to X-Forwarded-For.
    # Render alone = 1. Cloudflare in front of Render = 2. NEVER set higher than reality:
    # clients can then forge their IP and dodge the rate limits.
    trusted_proxy_hops: int = 1
    # A header the proxy overwrites with the client's address on every request, so clients can't
    # forge it (Render runs behind Cloudflare: cf-connecting-ip). When set, X-Forwarded-For and
    # trusted_proxy_hops are ignored.
    client_ip_header: str = ""
    # Shared secret a CDN adds as `X-Edge-Auth` on every request it forwards. When set, requests
    # without it are refused, so nobody can skip the CDN and feed the app a forged X-Forwarded-For.
    edge_secret: str = field(default="", repr=False)
    static_dir: str = "static"

    # Capacity limits (memory-exhaustion defences)
    max_rooms: int = 300
    max_players_per_room: int = 8
    room_code_length: int = 5
    room_idle_seconds: float = 600.0
    room_max_age_seconds: float = 6 * 3600.0
    token_ttl_seconds: float = 12 * 3600.0

    # Per-IP limits
    max_ws_per_ip: int = 12
    max_ws_total: int = 1500
    ws_msgs_per_second: float = 8.0
    ws_msg_burst: float = 16.0
    ws_max_message_bytes: int = 2048
    ws_auth_timeout: float = 5.0
    ws_idle_timeout: float = 90.0
    max_body_bytes: int = 4096
    rate_default_per_min: float = 180.0
    rate_default_burst: float = 80.0
    rate_create_per_min: float = 10.0
    rate_create_burst: float = 5.0
    rate_join_per_min: float = 40.0
    rate_join_burst: float = 12.0
    rate_auth_per_min: float = 10.0  # sign-up, log-in, recovery, password changes (per IP)
    rate_auth_burst: float = 8.0

    # Optional: fresh game content from Claude. Unset = built-in pools only.
    anthropic_api_key: str = field(default="", repr=False)
    content_model: str = "claude-opus-5-5"
    content_calls_per_hour: int = 20

    # Optional: voice and video calls through LiveKit (see calls.py). Unset = no calls.
    livekit_url: str = ""  # wss://<project>.livekit.cloud
    livekit_api_key: str = field(default="", repr=False)
    livekit_api_secret: str = field(default="", repr=False)

    # The jump-scare prank. On unless JUMPSCARE=false; JUMPSCARE_NAMES (comma separated) replaces the
    # built-in list. (A plain Settings() keeps it off, so unit tests stay quiet.)
    jumpscare: bool = False
    jumpscare_names: tuple[str, ...] = field(default=(), repr=False)

    extra: dict[str, str] = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def ws_hosts(self) -> tuple[str, ...]:
        return tuple(h for h in self.allowed_hosts if "*" not in h)


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    e = os.environ if environ is None else environ
    on_render = e.get("RENDER", "").lower() == "true"
    env = e.get("ENV") or ("production" if on_render else "development")
    production = env == "production"

    secret = e.get("SECRET_KEY", "")
    livekit_url = e.get("LIVEKIT_URL", "").strip().rstrip("/")
    if livekit_url and not (
        livekit_url.startswith("wss://") or (not production and livekit_url.startswith("ws://"))
    ):
        raise ValueError("LIVEKIT_URL must start with wss:// (ws:// only outside production)")
    if production and len(secret) < 32:
        raise RuntimeError("SECRET_KEY must be set to at least 32 characters in production")
    if not secret:
        secret = secrets.token_urlsafe(48)  # dev only: sessions reset on every restart

    hosts = list(_csv(e.get("ALLOWED_HOSTS")))
    origins = list(_csv(e.get("ALLOWED_ORIGINS")))
    render_host = e.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_host:
        hosts.append(render_host)
        origins.append(f"https://{render_host}")
    defaults = Settings()
    if not production:
        hosts = list(dict.fromkeys([*hosts, *defaults.allowed_hosts]))
        origins = list(dict.fromkeys([*origins, *defaults.allowed_origins]))
    if production and not hosts:
        raise RuntimeError("ALLOWED_HOSTS (or RENDER_EXTERNAL_HOSTNAME) must be set in production")

    def num(name: str, default: float) -> float:
        raw = e.get(name)
        return float(raw) if raw not in (None, "") else default

    hops = int(num("TRUSTED_PROXY_HOPS", defaults.trusted_proxy_hops))
    edge_secret = e.get("EDGE_SECRET", "").strip()
    if edge_secret and len(edge_secret) < 32:
        raise RuntimeError("EDGE_SECRET must be at least 32 characters")
    ip_header = e.get("CLIENT_IP_HEADER", "").strip().lower()
    if ip_header and (not re.fullmatch(r"[a-z0-9-]{1,40}", ip_header) or ip_header == "x-forwarded-for"):
        raise RuntimeError("CLIENT_IP_HEADER must be a single-value header such as cf-connecting-ip")
    if production and hops >= 2 and not edge_secret and not ip_header:
        # Behind a CDN the origin is still reachable directly; without the edge secret a direct
        # caller controls the X-Forwarded-For entry we'd trust, and walks around every rate limit.
        raise RuntimeError("TRUSTED_PROXY_HOPS >= 2 needs EDGE_SECRET in production (see SECURITY.md)")

    return Settings(
        env=env,
        secret_key=secret,
        database_url=normalize_database_url(e.get("DATABASE_URL", defaults.database_url)),
        allowed_hosts=tuple(hosts),
        allowed_origins=tuple(origins),
        trusted_proxy_hops=hops,
        edge_secret=edge_secret,
        client_ip_header=ip_header,
        static_dir=e.get("STATIC_DIR", defaults.static_dir),
        max_rooms=int(num("MAX_ROOMS", defaults.max_rooms)),
        max_ws_per_ip=int(num("MAX_WS_PER_IP", defaults.max_ws_per_ip)),
        max_ws_total=int(num("MAX_WS_TOTAL", defaults.max_ws_total)),
        anthropic_api_key=e.get("ANTHROPIC_API_KEY", "").strip(),
        content_model=e.get("CONTENT_MODEL", "").strip() or defaults.content_model,
        content_calls_per_hour=int(num("CONTENT_CALLS_PER_HOUR", defaults.content_calls_per_hour)),
        livekit_url=livekit_url,
        livekit_api_key=e.get("LIVEKIT_API_KEY", "").strip(),
        livekit_api_secret=e.get("LIVEKIT_API_SECRET", "").strip(),
        jumpscare=e.get("JUMPSCARE", "on").strip().lower() not in ("off", "0", "false", "no"),
        jumpscare_names=_csv(e.get("JUMPSCARE_NAMES")) or JUMPSCARE_DEFAULT_NAMES,
    )
