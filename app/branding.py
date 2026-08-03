"""Public product identity and compatibility constants."""

BRAND_NAME = "Prometheus"
BRAND_VERSION = "0.8.0"
BRAND_STAGE = "Experience Kernel & Forge"

# These identifiers are persisted in existing workspaces. Keep them stable
# until an explicit, versioned migration is introduced.
LEGACY_STATE_DIRECTORY = ".adam"
LEGACY_FILE_PROTOCOL_PREFIX = "ADAM"
LEGACY_LOCAL_STORAGE_KEY = "adam.activeCommandId"
ACTIVE_LOCAL_STORAGE_KEY = "prometheus.activeCommandId"

PROMOTION_CONFIRMATION = "PROMETHEUS ONAYLIYORUM"
LEGACY_PROMOTION_CONFIRMATION = "ADAM ONAYLIYORUM"
