from dataclasses import dataclass
import os
from urllib.parse import quote, urlsplit, urlunsplit


@dataclass(frozen=True)
class Settings:
    database_url: str
    dev_api_key: str
    internal_endpoint_hosts: frozenset[str]


def get_settings() -> Settings:
    hosts = os.getenv("A2A_INTERNAL_ENDPOINT_HOSTS", "localhost,127.0.0.1")
    return Settings(
        database_url=normalize_database_url(
            os.getenv(
                "A2A_DATABASE_URL",
                "postgresql+psycopg://a2a_registry:a2a_registry@localhost:5432/a2a_registry",
            )
        ),
        dev_api_key=os.getenv("A2A_DEV_API_KEY", ""),
        internal_endpoint_hosts=frozenset(h.strip().lower() for h in hosts.split(",") if h.strip()),
    )


def normalize_database_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.netloc.count("@") <= 1:
        return url
    userinfo, hostinfo = parsed.netloc.rsplit("@", 1)
    if ":" not in userinfo:
        return url
    username, password = userinfo.split(":", 1)
    safe_userinfo = f"{quote(username, safe='')}:{quote(password, safe='')}"
    return urlunsplit((parsed.scheme, f"{safe_userinfo}@{hostinfo}", parsed.path, parsed.query, parsed.fragment))


def redacted_database_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.netloc:
        return url
    host_part = parsed.hostname or ""
    if parsed.port:
        host_part = f"{host_part}:{parsed.port}"
    if parsed.username:
        host_part = f"{parsed.username}:***@{host_part}"
    return urlunsplit((parsed.scheme, host_part, parsed.path, parsed.query, parsed.fragment))
