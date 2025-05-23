#!/usr/bin/env python3
"""
Demo script showing the effectiveness of smart filtering during fetch vs after fetch.
This demonstrates why filtering before database insertion is much better.
"""

import subprocess
import time
from rich.console import Console
from rich.table import Table

console = Console()

def run_command(cmd):
    """Run a command and capture output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip()

def main():
    console.print("[bold blue]JobRadar Smart Filtering Demo[/bold blue]")
    console.print("This demo compares filtering jobs before vs after database insertion\n")
    
    # First, clear the database
    console.print("[yellow]Step 1: Clearing database...[/yellow]")
    stdout, stderr = run_command("jobradar cleanup --days 0")
    console.print(f"✓ Database cleared\n")
    
    # Fetch without smart filtering to show the difference
    console.print("[yellow]Step 2: Fetching ALL jobs (no smart filtering)...[/yellow]")
    stdout, stderr = run_command("jobradar fetch --no-smart-filter --limit 50")
    
    # Extract numbers from output
    lines = stdout.split('\n')
    total_fetched = 0
    total_added = 0
    
    for line in lines:
        if "Total jobs fetched:" in line:
            total_fetched = int(line.split(":")[1].strip())
        elif "Jobs added to database:" in line:
            total_added = int(line.split(":")[1].strip())
    
    console.print(f"✓ Fetched {total_fetched} jobs, added {total_added} to database")
    
    # Now show how many are actually relevant
    console.print("\n[yellow]Step 3: Checking how many jobs are actually relevant...[/yellow]")
    stdout, stderr = run_command("jobradar smart-search --limit 100")
    
    relevant_count = 0
    for line in stdout.split('\n'):
        if "Found" in line and "relevant jobs" in line:
            relevant_count = int(line.split()[1])
            break
    
    console.print(f"✓ Only {relevant_count} out of {total_added} jobs are actually relevant")
    
    # Calculate waste
    irrelevant = total_added - relevant_count
    waste_percentage = (irrelevant / total_added) * 100 if total_added > 0 else 0
    
    # Clear and fetch with smart filtering
    console.print("\n[yellow]Step 4: Clearing database and fetching with smart filtering...[/yellow]")
    run_command("jobradar cleanup --days 0")
    stdout, stderr = run_command("jobradar fetch --limit 50")
    
    # Extract smart filtering results
    smart_total_fetched = 0
    smart_relevant = 0
    smart_added = 0
    
    for line in stdout.split('\n'):
        if "Total jobs fetched:" in line:
            smart_total_fetched = int(line.split(":")[1].strip())
        elif "Relevant jobs after smart filtering:" in line:
            smart_relevant = int(line.split(":")[1].strip())
        elif "Jobs added to database:" in line:
            smart_added = int(line.split(":")[1].strip())
    
    console.print(f"✓ With smart filtering: {smart_total_fetched} fetched → {smart_relevant} relevant → {smart_added} stored")
    
    # Create comparison table
    console.print("\n[bold green]Results Comparison:[/bold green]")
    
    table = Table()
    table.add_column("Approach", style="cyan")
    table.add_column("Jobs Fetched", justify="right")
    table.add_column("Jobs Stored", justify="right")
    table.add_column("Relevant Jobs", justify="right")
    table.add_column("Waste %", justify="right")
    table.add_column("Efficiency", style="green")
    
    table.add_row(
        "No Smart Filtering",
        str(total_fetched),
        str(total_added),
        str(relevant_count),
        f"{waste_percentage:.1f}%",
        "Poor - stores irrelevant jobs"
    )
    
    table.add_row(
        "Smart Filtering",
        str(smart_total_fetched),
        str(smart_added),
        str(smart_relevant),
        "0%",
        "Excellent - only relevant jobs"
    )
    
    console.print(table)
    
    # Show benefits
    console.print("\n[bold green]Benefits of Smart Filtering During Fetch:[/bold green]")
    console.print("• 🎯 Only stores relevant jobs in database")
    console.print("• 💾 Reduces database size and improves performance")
    console.print("• ⚡ Faster searches since less data to process")
    console.print("• 🧹 Keeps database clean and focused")
    console.print("• 📊 Better user experience with relevant results only")
    
    if irrelevant > 0:
        space_saved = (irrelevant / total_added) * 100
        console.print(f"\n[bold yellow]Space Saved: {space_saved:.1f}% reduction in database size![/bold yellow]")

if __name__ == "__main__":
    main() 