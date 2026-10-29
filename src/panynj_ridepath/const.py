"""Public RidePATH endpoint and transport limits."""

FEED_URL = "https://www.panynj.gov/bin/portauthority/ridepath.json"
MAX_RESPONSE_BYTES = 1024 * 1024

ALERTS_URL = "https://www.panynj.gov/bin/portauthority/alerts?agency=PATH&hours=8"
PLANNED_URL = "https://www.panynj.gov/api/assets/path/planned-services.json"
SITE_MODEL_URL = "https://www.panynj.gov/content/path/en/index.model.json"
SITE_CONFIG_URL = "https://www.panynj.gov/content/dam/path/trip-planner/trip-planner-config.json"
