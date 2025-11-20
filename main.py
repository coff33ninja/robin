import click
import subprocess
import os
import sys
import time
import atexit
from yaspin import yaspin
from datetime import datetime
from scrape import scrape_multiple
from search import get_search_results
from llm import get_llm, refine_query, filter_results, generate_summary
from llm_utils import get_model_choices

MODEL_CHOICES = get_model_choices()

# Global variable to track Tor process
_tor_process = None


def start_tor():
    """Start Tor service if not already running."""
    global _tor_process
    
    # Check if Tor is already running on port 9050
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 9050))
    sock.close()
    
    if result == 0:
        click.echo("✓ Tor is already running on port 9050")
        return
    
    # Find tor executable
    tor_path = os.path.join(os.path.dirname(__file__), "tor", "tor.exe")
    
    if not os.path.exists(tor_path):
        click.echo("⚠ Warning: Tor executable not found. Please ensure Tor is running manually.")
        return
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"tor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    try:
        click.echo("Starting Tor service...")
        click.echo(f"Tor logs will be saved to: {log_file}")
        
        # Open log file for writing
        log_handle = open(log_file, 'w', encoding='utf-8')
        
        _tor_process = subprocess.Popen(
            [tor_path],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        # Wait for Tor to be ready (check port 9050)
        for i in range(30):  # Wait up to 30 seconds
            time.sleep(1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', 9050))
            sock.close()
            if result == 0:
                click.echo("✓ Tor service started successfully")
                click.echo(f"Check {log_file} for Tor connection details")
                return
            if i % 5 == 0:
                click.echo(f"Waiting for Tor... ({i}/30 seconds)")
        
        click.echo("⚠ Warning: Tor may not have started properly")
        click.echo(f"Check the log file for details: {log_file}")
    except Exception as e:
        click.echo(f"⚠ Warning: Could not start Tor: {e}")
        click.echo(f"Check the log file for details: {log_file}")


def stop_tor():
    """Stop Tor service if it was started by this script."""
    global _tor_process
    if _tor_process:
        click.echo("\nStopping Tor service...")
        _tor_process.terminate()
        try:
            _tor_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _tor_process.kill()
        click.echo("✓ Tor service stopped")


# Register cleanup function
atexit.register(stop_tor)


@click.group()
@click.version_option()
def robin():
    """Robin: AI-Powered Dark Web OSINT Tool."""
    pass


@robin.command()
@click.option(
    "--model",
    "-m",
    default="gpt-5-mini",
    show_default=True,
    type=click.Choice(MODEL_CHOICES),
    help="Select LLM model to use (e.g., gpt4o, claude sonnet 3.5, ollama models)",
)
@click.option("--query", "-q", required=True, type=str, help="Dark web search query")
@click.option(
    "--threads",
    "-t",
    default=5,
    show_default=True,
    type=int,
    help="Number of threads to use for scraping (Default: 5)",
)
@click.option(
    "--output",
    "-o",
    type=str,
    help="Filename to save the final intelligence summary. If not provided, a filename based on the current date and time is used.",
)
def cli(model, query, threads, output):
    """Run Robin in CLI mode.\n
    Example commands:\n
    - robin -m gpt4o -q "ransomware payments" -t 12\n
    - robin --model claude-3-5-sonnet-latest --query "sensitive credentials exposure" --threads 8 --output filename\n
    - robin -m llama3.1 -q "zero days"\n
    """
    # Start Tor service
    start_tor()
    
    llm = get_llm(model)

    # Show spinner while processing the query
    with yaspin(text="Processing...", color="cyan") as sp:
        refined_query = refine_query(llm, query)

        search_results = get_search_results(
            refined_query.replace(" ", "+"), max_workers=threads
        )

        search_filtered = filter_results(llm, refined_query, search_results)

        scraped_results = scrape_multiple(search_filtered, max_workers=threads)
        sp.ok("✔")

    # Prepare excluded info
    excluded_info = ""
    
    # Add excluded search engines
    if hasattr(search_results, 'excluded_services') and search_results.excluded_services:
        excluded_info += "\n\n--- EXCLUDED SEARCH ENGINES ---\n"
        excluded_info += "The following search engines were excluded from results due to errors:\n"
        for exc in search_results.excluded_services:
            excluded_info += f"- {exc['url']}: {exc['reason']}\n"
    
    # Add excluded content (filtered by blocklist)
    if hasattr(search_results, 'excluded_content') and search_results.excluded_content:
        excluded_info += "\n\n--- EXCLUDED CONTENT (FILTERED) ---\n"
        excluded_info += "The following content was filtered based on your blocklist settings:\n"
        for exc in search_results.excluded_content:
            excluded_info += f"- {exc['link']} ({exc['title'][:50]}...): {exc['reason']}\n"

    # Generate the intelligence summary.
    summary = generate_summary(llm, query, scraped_results + excluded_info)

    # Save or print the summary
    if not output:
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"summary_{now}.md"
    else:
        filename = output + ".md"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(summary)
        click.echo(f"\n\n[OUTPUT] Final intelligence summary saved to {filename}")


@robin.command()
@click.option(
    "--ui-port",
    default=8501,
    show_default=True,
    type=int,
    help="Port for the Streamlit UI",
)
@click.option(
    "--ui-host",
    default="localhost",
    show_default=True,
    type=str,
    help="Host for the Streamlit UI",
)
def ui(ui_port, ui_host):
    """Run Robin in Web UI mode."""
    # Start Tor service
    start_tor()
    
    # Use streamlit's internet CLI entrypoint
    from streamlit.web import cli as stcli

    # When PyInstaller one-file, data files livei n _MEIPASS
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(__file__)

    ui_script = os.path.join(base, "ui.py")
    # Build sys.argv
    sys.argv = [
        "streamlit",
        "run",
        ui_script,
        f"--server.port={ui_port}",
        f"--server.address={ui_host}",
        "--global.developmentMode=false",
    ]
    # This will never return until streamlit exits
    sys.exit(stcli.main())


if __name__ == "__main__":
    robin()
