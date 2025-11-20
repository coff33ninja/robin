# Content Filtering Configuration

Robin now supports configurable content filtering through environment variables in your `.env` file. This gives you full control over what content gets included or excluded from your dark web OSINT analysis.

## Configuration Options

Add these settings to your `.env` file:

```env
# Content Filtering Configuration

# Comma-separated list of keywords to ALWAYS include (even if flagged as NSFW/sensitive)
# Example: drugs,weapons,hacking
CONTENT_ALLOWLIST=

# Comma-separated list of keywords to ALWAYS exclude from analysis
# Example: gore,torture,child,animal abuse
CONTENT_BLOCKLIST=

# Filter NSFW content (true/false) - if true, NSFW content will be excluded unless in allowlist
FILTER_NSFW=true

# Filter irrelevant content (true/false) - if true, off-topic results will be excluded
FILTER_IRRELEVANT=true

# Maximum number of results to process (0 = no limit, processes all results)
# Default is 20 to manage API costs and processing time
# WARNING: Processing all results can be expensive and time-consuming
MAX_RESULTS=20
```

## How It Works

### Blocklist (Highest Priority)
- Content containing **any** blocklist keyword is **always excluded**
- This takes precedence over everything else
- Use this for content you never want to see

**Example:**
```env
CONTENT_BLOCKLIST=gore,torture,child abuse,animal cruelty
```

### Allowlist (Second Priority)
- Content containing **any** allowlist keyword is **always included**
- This overrides NSFW and irrelevant filters
- Use this for sensitive topics you need to investigate

**Example:**
```env
CONTENT_ALLOWLIST=ransomware,exploit,vulnerability,breach
```

### NSFW Filter
- When `FILTER_NSFW=true`, the LLM will exclude not-safe-for-work content
- Allowlist keywords override this filter
- Set to `false` to disable NSFW filtering

### Irrelevant Filter
- When `FILTER_IRRELEVANT=true`, the LLM will exclude off-topic results
- Allowlist keywords override this filter
- Set to `false` to disable relevance filtering

### Max Results Limit
- `MAX_RESULTS` controls how many search results are processed
- Default is `20` to manage API costs and processing time
- Set to `0` to process **ALL** results without any limit
- **WARNING**: Setting to 0 can result in high API costs and long processing times

## Excluded Content Report Section

All excluded content is documented in the "Excluded Content" section of your intelligence report, which includes:

1. **Search engines that failed** - with error reasons
2. **Content filtered by blocklist** - with matched keywords
3. **NSFW content excluded** - if FILTER_NSFW is enabled
4. **Irrelevant content excluded** - if FILTER_IRRELEVANT is enabled

Each excluded item includes:
- The source URL
- Title/description (truncated)
- Reason for exclusion

A disclaimer is included warning users to exercise caution if investigating excluded sources independently.

## Example Configurations

### Conservative (Maximum Filtering)
```env
CONTENT_BLOCKLIST=gore,torture,child,animal abuse,snuff
CONTENT_ALLOWLIST=
FILTER_NSFW=true
FILTER_IRRELEVANT=true
MAX_RESULTS=20
```

### Investigative (Minimal Filtering)
```env
CONTENT_BLOCKLIST=child,animal abuse
CONTENT_ALLOWLIST=drugs,weapons,hacking,exploit,malware
FILTER_NSFW=false
FILTER_IRRELEVANT=false
MAX_RESULTS=50
```

### Targeted Research
```env
CONTENT_BLOCKLIST=gore,torture,snuff
CONTENT_ALLOWLIST=ransomware,apt,threat actor,zero day
FILTER_NSFW=true
FILTER_IRRELEVANT=true
MAX_RESULTS=30
```

### Full Unfiltered (Process Everything)
```env
CONTENT_BLOCKLIST=
CONTENT_ALLOWLIST=
FILTER_NSFW=false
FILTER_IRRELEVANT=false
MAX_RESULTS=0
```
**⚠️ WARNING**: This will process ALL search results and can result in very high API costs!

## Automatic Chunking for Large Datasets

When processing a large number of results (MAX_RESULTS=0 or high values), Robin automatically chunks the data to prevent LLM token limit issues:

- **Automatic Detection**: If content exceeds ~50,000 characters, it's automatically split into chunks
- **Smart Splitting**: Content is split at URL boundaries to keep related data together
- **Multi-Pass Analysis**: Each chunk is analyzed separately, then synthesized into a final report
- **Progress Tracking**: Console shows chunk processing progress

This allows you to process hundreds of results without hitting token limits or getting stuck in loops.

## Best Practices

1. **Always set a blocklist** - Include illegal content categories you never want to encounter
2. **Use allowlist for your research focus** - Add keywords relevant to your investigation
3. **Review excluded content** - Check the "Excluded Content" section to ensure nothing important was filtered
4. **Adjust as needed** - Refine your filters based on results
5. **Be specific** - Use precise keywords for better filtering accuracy
6. **Start with MAX_RESULTS=20** - Test your query with a smaller dataset first, then increase if needed
7. **Monitor API costs** - Large datasets (MAX_RESULTS=0) can consume significant API tokens

## Security Note

⚠️ **IMPORTANT**: Content filtering is designed to help you focus your investigation and avoid unwanted material. However:
- Filtering is not 100% accurate
- Some content may slip through or be incorrectly filtered
- Always exercise caution when investigating dark web content
- Follow your organization's security and legal guidelines
- The "Excluded Content" section may contain references to harmful material
