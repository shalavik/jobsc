"""Command-line interface for JobRadar."""
import click
import yaml
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from datetime import datetime
from typing import Optional
from .models import Feed, Job
from .fetchers import Fetcher
from .database import Database
from .filters import create_filter_from_config
from .web.app import run_server
from .config import get_config
import sqlite3
import os

console = Console()

@click.group()
def cli():
    """JobRadar - Job listing aggregator."""
    pass

@cli.command()
def list_feeds():
    """List configured job feeds."""
    config = get_config()
    table = Table(title="Configured Feeds")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("URL", style="blue")
    for feed in config['feeds']:
        table.add_row(
            feed['name'],
            feed['type'],
            feed['url']
        )
    console.print(table)

@cli.command()
@click.option('--feed', help='Specific feed to fetch from')
@click.option('--limit', type=int, default=100, help='Maximum number of jobs to fetch')
@click.option('--apply-filters/--no-filters', default=True, help='Apply configured filters')
def fetch(feed: str, limit: int, apply_filters: bool):
    """Fetch jobs from configured feeds."""
    config = get_config()
    fetcher = Fetcher()
    db = Database()
    job_filter = None
    if apply_filters and 'filters' in config:
        job_filter = create_filter_from_config(config['filters'])
    feeds_to_fetch = [
        Feed(**f) for f in config['feeds']
        if not feed or f['name'] == feed
    ]
    if not feeds_to_fetch:
        console.print(f"[red]No feeds found matching '{feed}'[/red]")
        return
    with Progress() as progress:
        task = progress.add_task("[cyan]Fetching jobs...", total=len(feeds_to_fetch))
        for feed in feeds_to_fetch:
            try:
                console.print(f"\n[blue]Fetching from {feed.name}...[/blue]")
                jobs = fetcher.fetch(feed)
                if jobs:
                    if job_filter:
                        jobs = job_filter.filter_jobs(jobs)
                        console.print(f"[yellow]Filtered to {len(jobs)} jobs[/yellow]")
                    added = db.add_jobs(jobs[:limit])
                    console.print(f"[green]Added {added} jobs from {feed.name}[/green]")
                else:
                    console.print(f"[yellow]No jobs found in {feed.name}[/yellow]")
            except Exception as e:
                console.print(f"[red]Error fetching from {feed.name}: {str(e)}[/red]")
            progress.advance(task)

@cli.command()
@click.option('--company', help='Filter by company name')
@click.option('--title', help='Filter by job title')
@click.option('--source', help='Filter by source')
@click.option('--remote/--no-remote', help='Filter by remote status')
@click.option('--location', help='Filter by location')
@click.option('--salary-min', type=int, help='Minimum salary in thousands (e.g., 100 for $100k)')
@click.option('--salary-max', type=int, help='Maximum salary in thousands (e.g., 150 for $150k)')
@click.option('--job-type', help='Filter by job type (e.g., Full-time, Contract)')
@click.option('--experience', help='Filter by experience level (e.g., Senior, Mid-level)')
@click.option('--limit', type=int, default=10, help='Maximum number of results to show')
@click.option('--apply-filters/--no-filters', default=True, help='Apply configured filters')
def search(
    company: Optional[str],
    title: Optional[str],
    source: Optional[str],
    remote: Optional[bool],
    location: Optional[str],
    salary_min: Optional[int],
    salary_max: Optional[int],
    job_type: Optional[str],
    experience: Optional[str],
    limit: int,
    apply_filters: bool
):
    """Search for jobs in the database with advanced filtering."""
    config = get_config()
    db = Database()
    
    # Build filter dictionary
    filters = {}
    if company:
        filters['company'] = company
    if title:
        filters['title'] = title
    if source:
        filters['source'] = source
    if remote is not None:
        filters['is_remote'] = remote
    if location:
        filters['location'] = location
    if salary_min:
        filters['salary_min'] = salary_min * 1000  # Convert to actual salary
    if salary_max:
        filters['salary_max'] = salary_max * 1000  # Convert to actual salary
    if job_type:
        filters['job_type'] = job_type
    if experience:
        filters['experience_level'] = experience
    
    # Get jobs from database
    jobs = db.search_jobs(filters=filters, limit=limit * 2)  # Get more jobs to account for filtering
    
    # Apply configured filters if requested
    if apply_filters and 'filters' in config:
        job_filter = create_filter_from_config(config['filters'])
        jobs = job_filter.filter_jobs(jobs)
        jobs = jobs[:limit]  # Apply limit after filtering
    
    if not jobs:
        console.print("[yellow]No jobs found matching your criteria[/yellow]")
        return
    
    table = Table(title="Search Results")
    table.add_column("Title", style="cyan")
    table.add_column("Company", style="green")
    table.add_column("Location", style="blue")
    table.add_column("Salary", style="magenta")
    table.add_column("Type", style="yellow")
    table.add_column("Experience", style="red")
    table.add_column("Source", style="blue")
    table.add_column("URL", style="yellow")
    
    for job in jobs:
        table.add_row(
            job.title,
            job.company,
            getattr(job, 'location', 'N/A'),
            getattr(job, 'salary', 'N/A'),
            getattr(job, 'job_type', 'N/A'),
            getattr(job, 'experience_level', 'N/A'),
            job.source,
            job.url
        )
    
    console.print(table)

@cli.command()
@click.option('--days', type=int, default=30, help='Delete jobs older than this many days')
def cleanup(days: int):
    """Clean up old jobs from the database."""
    db = Database()
    
    deleted = db.delete_old_jobs(days=days)
    console.print(f"[green]Deleted {deleted} old jobs[/green]")

@cli.command()
@click.option('--host', default='0.0.0.0', help='Host to bind the server to')
@click.option('--port', type=int, default=5000, help='Port to bind the server to')
@click.option('--debug', is_flag=True, help='Run in debug mode')
def web(host: str, port: int, debug: bool):
    """Start the web dashboard."""
    console.print(f"[green]Starting web dashboard at http://{host}:{port}[/green]")
    run_server(host=host, port=port, debug=debug)

@cli.command()
def migrate():
    """Migrate the jobs database to the latest schema."""
    db_path = os.environ.get('JOBRADAR_DB', 'jobs.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # List of (column name, SQL type)
    columns = [
        ('job_type', 'TEXT'),
        ('experience_level', 'TEXT'),
        ('is_remote', 'BOOLEAN'),
        ('skills', 'TEXT'),
        ('description', 'TEXT'),
        ('location', 'TEXT'),
        ('salary', 'TEXT'),
        ('created_at', 'DATETIME'),
        ('updated_at', 'DATETIME')
    ]
    # Get current columns
    cursor.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cursor.fetchall()}
    for col, typ in columns:
        if col not in existing:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col} {typ}")
    conn.commit()
    conn.close()
    console.print("[green]Database migration complete.[/green]")

def main():
    """Main entry point for the CLI."""
    cli() 