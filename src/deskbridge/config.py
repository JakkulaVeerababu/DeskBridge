import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    domain: str
    api_key: str
    max_page_size: int = 30
    max_retries: int = 5
    timeout_s: float = 15.0
    mask_pii: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        domain = os.getenv("FRESHDESK_DOMAIN", "").strip()
        key = os.getenv("FRESHDESK_API_KEY", "").strip()
        if not domain or not key:
            raise RuntimeError(
                "Set FRESHDESK_DOMAIN and FRESHDESK_API_KEY (see .env.example)"
            )
        return cls(
            domain=domain,
            api_key=key,
            max_page_size=int(os.getenv("DESKBRIDGE_MAX_PAGE_SIZE", "30")),
            mask_pii=os.getenv("DESKBRIDGE_MASK_PII", "true").lower() == "true",
        )
