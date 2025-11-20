import os
from dotenv import load_dotenv

load_dotenv()

# Configuration variables loaded from the .env file
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")

# Content Filtering Configuration
def parse_list(env_var):
    """Parse comma-separated list from env variable."""
    value = os.getenv(env_var, "")
    if not value or value.strip() == "":
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]

CONTENT_ALLOWLIST = parse_list("CONTENT_ALLOWLIST")
CONTENT_BLOCKLIST = parse_list("CONTENT_BLOCKLIST")
FILTER_NSFW = os.getenv("FILTER_NSFW", "true").lower() == "true"
FILTER_IRRELEVANT = os.getenv("FILTER_IRRELEVANT", "true").lower() == "true"

# Maximum results to process (0 = no limit)
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "20"))
