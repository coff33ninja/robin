import re
import openai
import logging
import warnings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from llm_utils import _common_llm_params, resolve_model_config, get_model_choices
from config import (
    CONTENT_ALLOWLIST,
    CONTENT_BLOCKLIST,
    FILTER_NSFW,
    FILTER_IRRELEVANT,
    MAX_RESULTS,
)

warnings.filterwarnings("ignore")


def get_llm(model_choice):
    # Look up the configuration (cloud or local Ollama)
    config = resolve_model_config(model_choice)

    if config is None:  # Extra error check
        supported_models = get_model_choices()
        raise ValueError(
            f"Unsupported LLM model: '{model_choice}'. "
            f"Supported models (case-insensitive match) are: {', '.join(supported_models)}"
        )

    # Extract the necessary information from the configuration
    llm_class = config["class"]
    model_specific_params = config["constructor_params"]

    # Combine common parameters with model-specific parameters
    # Model-specific parameters will override common ones if there are any conflicts
    all_params = {**_common_llm_params, **model_specific_params}

    # Create the LLM instance using the gathered parameters
    llm_instance = llm_class(**all_params)

    return llm_instance


def refine_query(llm, user_input):
    system_prompt = """
    You are a Cybercrime Threat Intelligence Expert. Your task is to refine the provided user query that needs to be sent to darkweb search engines. 
    
    Rules:
    1. Analyze the user query and think about how it can be improved to use as search engine query
    2. Refine the user query by adding or removing words so that it returns the best result from dark web search engines
    3. Don't use any logical operators (AND, OR, etc.)
    4. Output just the user query and nothing else

    INPUT:
    """
    prompt_template = ChatPromptTemplate(
        [("system", system_prompt), ("user", "{query}")]
    )
    chain = prompt_template | llm | StrOutputParser()
    return chain.invoke({"query": user_input})


def filter_results(llm, query, results):
    if not results:
        return []

    # If MAX_RESULTS is 0, return all results without filtering
    if MAX_RESULTS == 0:
        print(f"[INFO] MAX_RESULTS=0: Processing all {len(results)} results without LLM filtering")
        return results

    # Use configured MAX_RESULTS or default to 20
    max_limit = MAX_RESULTS if MAX_RESULTS > 0 else 20

    system_prompt = f"""
    You are a Cybercrime Threat Intelligence Expert. You are given a dark web search query and a list of search results in the form of index, link and title. 
    Your task is select the Top {max_limit} relevant results that best match the search query for user to investigate more.
    Rule:
    1. Output ONLY atmost top {max_limit} indices (comma-separated list) no more than that that best match the input query

    Search Query: {{query}}
    Search Results:
    """

    final_str = _generate_final_string(results)

    prompt_template = ChatPromptTemplate(
        [("system", system_prompt), ("user", "{results}")]
    )
    chain = prompt_template | llm | StrOutputParser()
    try:
        result_indices = chain.invoke({"query": query, "results": final_str})
    except openai.RateLimitError as e:
        print(
            f"Rate limit error: {e} \n Truncating to Web titles only with 30 characters"
        )
        final_str = _generate_final_string(results, truncate=True)
        result_indices = chain.invoke({"query": query, "results": final_str})

    # Select top_k results using original (non-truncated) results
    parsed_indices = []
    for match in re.findall(r"\d+", result_indices):
        try:
            idx = int(match)
            if 1 <= idx <= len(results):
                parsed_indices.append(idx)
        except ValueError:
            continue

    # Remove duplicates while preserving order
    seen = set()
    parsed_indices = [
        i for i in parsed_indices if not (i in seen or seen.add(i))
    ]

    if not parsed_indices:
        logging.warning(
            "Unable to interpret LLM result selection ('%s'). "
            "Defaulting to the top %s results.",
            result_indices,
            min(len(results), max_limit),
        )
        parsed_indices = list(range(1, min(len(results), max_limit) + 1))

    top_results = [results[i - 1] for i in parsed_indices[:max_limit]]

    return top_results


def _generate_final_string(results, truncate=False):
    """
    Generate a formatted string from the search results for LLM processing.
    """

    if truncate:
        # Use only the first 35 characters of the title
        max_title_length = 30
        # Do not use link at all
        max_link_length = 0

    final_str = []
    for i, res in enumerate(results):
        # Truncate link at .onion for display
        truncated_link = re.sub(r"(?<=\.onion).*", "", res["link"])
        title = re.sub(r"[^0-9a-zA-Z\-\.]", " ", res["title"])
        if truncated_link == "" and title == "":
            continue

        if truncate:
            # Truncate title to max_title_length characters
            title = (
                title[:max_title_length] + "..."
                if len(title) > max_title_length
                else title
            )
            # Truncate link to max_link_length characters
            truncated_link = (
                truncated_link[:max_link_length] + "..."
                if len(truncated_link) > max_link_length
                else truncated_link
            )

        final_str.append(f"{i+1}. {truncated_link} - {title}")

    return "\n".join(s for s in final_str)


def _chunk_content(content, max_chunk_size=50000):
    """
    Split content into chunks based on URL boundaries to avoid breaking mid-content.
    Returns list of content chunks.
    """
    chunks = []
    current_chunk = ""
    
    # Split by URL markers
    sections = content.split("--- URL:")
    
    for i, section in enumerate(sections):
        if i == 0 and not section.strip().startswith("http"):
            # First section might be metadata, keep it
            current_chunk = section
            continue
        
        section_with_marker = f"--- URL:{section}"
        
        # If adding this section exceeds limit, save current chunk and start new one
        if len(current_chunk) + len(section_with_marker) > max_chunk_size and current_chunk:
            chunks.append(current_chunk)
            current_chunk = section_with_marker
        else:
            current_chunk += section_with_marker
    
    # Add the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk)
    
    return chunks if chunks else [content]


def _generate_chunk_summary(llm, query, content_chunk, chunk_num, total_chunks):
    """Generate summary for a single chunk of content."""
    system_prompt = f"""
    You are an Cybercrime Threat Intelligence Expert analyzing dark web OSINT data.
    
    This is CHUNK {chunk_num} of {total_chunks} for query: "{query}"
    
    Rules:
    1. Extract and list all source URLs from this chunk
    2. Identify all intelligence artifacts (emails, domains, cryptocurrency addresses, threat actors, malware, etc.)
    3. Note any patterns or connections
    4. Keep your analysis concise and focused on facts
    5. Do NOT generate final conclusions - this is a partial analysis
    
    Output Format:
    **Chunk {chunk_num}/{total_chunks} Analysis:**
    - Source URLs: [list all URLs]
    - Artifacts Found: [list all artifacts with context]
    - Key Observations: [2-3 bullet points]
    """
    
    prompt_template = ChatPromptTemplate(
        [("system", system_prompt), ("user", "{content}")]
    )
    chain = prompt_template | llm | StrOutputParser()
    return chain.invoke({"query": query, "content": content_chunk})


def _generate_final_summary(llm, query, chunk_summaries, excluded_info):
    """Generate final comprehensive summary from all chunk summaries."""
    # Build filtering instructions based on config
    filtering_rules = []
    
    if FILTER_NSFW:
        filtering_rules.append("- NSFW content was filtered from analysis")
    
    if FILTER_IRRELEVANT:
        filtering_rules.append("- Irrelevant/off-topic content was excluded")
    
    if CONTENT_BLOCKLIST:
        blocklist_str = ", ".join(CONTENT_BLOCKLIST)
        filtering_rules.append(f"- Blocked keywords: {blocklist_str}")
    
    if CONTENT_ALLOWLIST:
        allowlist_str = ", ".join(CONTENT_ALLOWLIST)
        filtering_rules.append(f"- Allowlisted keywords: {allowlist_str}")
    
    filtering_note = "\n".join(filtering_rules) if filtering_rules else "No content filtering applied"
    
    system_prompt = f"""
    You are an Cybercrime Threat Intelligence Expert creating a final comprehensive report.
    
    You have been provided with analysis from multiple data chunks. Synthesize them into a complete intelligence report.
    
    Filtering Applied:
    {filtering_note}

    Output Format:
    1. Input Query: {{query}}
    2. Source Links Referenced for Analysis - comprehensive list from all chunks
    3. Investigation Artifacts - all artifacts identified across all chunks (deduplicated)
    4. Key Insights - 5-7 high-level insights synthesized from all chunks
    5. Excluded Content - {excluded_info if excluded_info else "None"}
    6. Next Steps - actionable investigation steps and suggested queries

    Format your response in a structured way with clear section headings.
    """
    
    combined_analysis = "\n\n".join(chunk_summaries)
    
    prompt_template = ChatPromptTemplate(
        [("system", system_prompt), ("user", "{analysis}")]
    )
    chain = prompt_template | llm | StrOutputParser()
    return chain.invoke({"query": query, "analysis": combined_analysis})


def generate_summary(llm, query, content, max_chunk_size=50000):
    """
    Generate intelligence summary, automatically chunking large content to avoid token limits.
    """
    # Check if content needs chunking
    if len(content) <= max_chunk_size:
        # Small enough to process in one go - use original method
        filtering_rules = []
        
        if FILTER_NSFW:
            filtering_rules.append("10. Filter out not safe for work (NSFW) content from the analysis")
        
        if FILTER_IRRELEVANT:
            filtering_rules.append("11. Exclude irrelevant or off-topic content that doesn't match the query")
        
        if CONTENT_BLOCKLIST:
            blocklist_str = ", ".join(CONTENT_BLOCKLIST)
            filtering_rules.append(f"12. ALWAYS exclude content containing these keywords: {blocklist_str}")
        
        if CONTENT_ALLOWLIST:
            allowlist_str = ", ".join(CONTENT_ALLOWLIST)
            filtering_rules.append(f"13. ALWAYS include content containing these keywords even if flagged: {allowlist_str}")
        
        filtering_rules.append("14. Identify any content, links, or data that was explicitly excluded from analysis due to safety, relevance, or technical constraints.")
        
        filtering_instructions = "\n    ".join(filtering_rules) if filtering_rules else ""
        
        system_prompt = f"""
        You are an Cybercrime Threat Intelligence Expert tasked with generating context-based technical investigative insights from dark web osint search engine results.

        Rules:
        1. Analyze the Darkweb OSINT data provided using links and their raw text.
        2. Output the Source Links referenced for the analysis.
        3. Provide a detailed, contextual, evidence-based technical analysis of the data.
        4. Provide intellgience artifacts along with their context visible in the data.
        5. The artifacts can include indicators like name, email, phone, cryptocurrency addresses, domains, darkweb markets, forum names, threat actor information, malware names, TTPs, etc.
        6. Generate 3-5 key insights based on the data.
        7. Each insight should be specific, actionable, context-based, and data-driven.
        8. Include suggested next steps and queries for investigating more on the topic.
        9. Be objective and analytical in your assessment.
        {filtering_instructions}

        Output Format:
        1. Input Query: {{query}}
        2. Source Links Referenced for Analysis - this heading will include all source links used for the analysis
        3. Investigation Artifacts - this heading will include all technical artifacts identified including name, email, phone, cryptocurrency addresses, domains, darkweb markets, forum names, threat actor information, malware names, etc.
        4. Key Insights
        5. Excluded Content - this section lists any content, links, or data that was explicitly excluded from the analysis with reasons why they were excluded (e.g., not safe for work content, irrelevant results, inaccessible links, malformed data, blocked keywords, etc.). Include a disclaimer: "⚠️ DISCLAIMER: The following items were excluded from analysis. Exercise extreme caution if investigating these sources independently, as they may contain harmful, illegal, or disturbing content."
        6. Next Steps - this includes next investigative steps including search queries to search more on a specific artifacts for example or any other topic.

        Format your response in a structured way with clear section headings.

        INPUT:
        """
        prompt_template = ChatPromptTemplate(
            [("system", system_prompt), ("user", "{content}")]
        )
        chain = prompt_template | llm | StrOutputParser()
        return chain.invoke({"query": query, "content": content})
    
    # Content is too large - use chunking approach
    print(f"\n[INFO] Content size ({len(content)} chars) exceeds limit. Processing in chunks...")
    
    # Separate excluded info from main content
    excluded_info = ""
    main_content = content
    if "--- EXCLUDED" in content:
        parts = content.split("--- EXCLUDED", 1)
        main_content = parts[0]
        excluded_info = "--- EXCLUDED" + parts[1]
    
    # Split content into chunks
    chunks = _chunk_content(main_content, max_chunk_size)
    print(f"[INFO] Split into {len(chunks)} chunks for processing")
    
    # Process each chunk
    chunk_summaries = []
    for i, chunk in enumerate(chunks, 1):
        print(f"[INFO] Processing chunk {i}/{len(chunks)}...")
        summary = _generate_chunk_summary(llm, query, chunk, i, len(chunks))
        chunk_summaries.append(summary)
    
    # Generate final comprehensive summary
    print(f"[INFO] Generating final comprehensive report...")
    final_summary = _generate_final_summary(llm, query, chunk_summaries, excluded_info)
    
    return final_summary
