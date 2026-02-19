"""Custom exception hierarchy for JANATPMP.

All application-specific exceptions inherit from JANATPMPError,
allowing callers to catch broad or narrow as needed.
"""


class JANATPMPError(Exception):
    """Base exception for all JANATPMP errors."""


class SettingsError(JANATPMPError):
    """Invalid settings or configuration."""


class ProviderError(JANATPMPError):
    """Chat provider communication failure."""


class IngestionError(JANATPMPError):
    """Content ingestion failure (import, parsing, dedup)."""


class VectorStoreError(JANATPMPError):
    """Qdrant communication or embedding failure."""


class DomainNotFoundError(JANATPMPError):
    """Requested domain does not exist in the domains table."""
