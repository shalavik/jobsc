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
from .smart_matcher import create_smart_matcher
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
@click.option('--smart-filter/--no-smart-filter', default=None, help='Apply smart filtering to only save relevant jobs (overrides config)')
@click.option('--min-score', type=int, default=None, help='Minimum relevance score for smart filtering (overrides config)')
def fetch(feed: str, limit: int, apply_filters: bool, smart_filter: Optional[bool], min_score: Optional[int]):
    """Fetch jobs from configured feeds."""
    config = get_config()
    fetcher = Fetcher()
    db = Database()
    job_filter = None
    if apply_filters and 'filters' in config:
        job_filter = create_filter_from_config(config['filters'])
    
    # Get smart filtering configuration from config or CLI options
    smart_config = config.get('smart_filtering', {})
    if smart_filter is None:
        smart_filter = smart_config.get('enabled', True)  # Default to enabled
    if min_score is None:
        min_score = smart_config.get('min_score', 1)  # Default min score
    
    # Initialize smart matcher if smart filtering is enabled
    smart_matcher = None
    if smart_filter:
        # Use categories from config if specified
        categories = smart_config.get('categories', [])
        if categories:
            smart_matcher = create_smart_matcher(categories)
            console.print(f"[blue]Smart filtering enabled (min score: {min_score}, categories: {', '.join(categories)})[/blue]")
        else:
            smart_matcher = create_smart_matcher()
            console.print(f"[blue]Smart filtering enabled (min score: {min_score}, all categories)[/blue]")
    else:
        console.print("[yellow]Smart filtering disabled[/yellow]")
    
    feeds_to_fetch = [
        Feed(**f) for f in config['feeds']
        if not feed or f['name'] == feed
    ]
    if not feeds_to_fetch:
        console.print(f"[red]No feeds found matching '{feed}'[/red]")
        return
    with Progress() as progress:
        task = progress.add_task("[cyan]Fetching jobs...", total=len(feeds_to_fetch))
        total_fetched = 0
        total_relevant = 0
        total_added = 0
        
        for feed_obj in feeds_to_fetch:
            try:
                console.print(f"\n[blue]Fetching from {feed_obj.name}...[/blue]")
                jobs = fetcher.fetch(feed_obj)
                
                if jobs:
                    total_fetched += len(jobs)
                    console.print(f"[green]Fetched {len(jobs)} jobs from {feed_obj.name}[/green]")
                    
                    # Apply configured filters first
                    if job_filter:
                        jobs = job_filter.filter_jobs(jobs)
                        console.print(f"[yellow]Filtered to {len(jobs)} jobs after applying configured filters[/yellow]")
                    
                    # Apply smart filtering before adding to database
                    if smart_matcher:
                        original_count = len(jobs)
                        jobs = smart_matcher.filter_jobs(jobs, min_score=min_score)
                        total_relevant += len(jobs)
                        
                        if len(jobs) < original_count:
                            filtered_out = original_count - len(jobs)
                            console.print(f"[magenta]Smart filter: kept {len(jobs)} relevant jobs, filtered out {filtered_out} irrelevant jobs[/magenta]")
                        else:
                            console.print(f"[magenta]Smart filter: all {len(jobs)} jobs are relevant[/magenta]")
                        
                        # Show what categories matched
                        if jobs:
                            category_counts = {}
                            for job in jobs:
                                scores = smart_matcher.get_match_score(job)
                                for category, score in scores.items():
                                    if score > 0:
                                        category_counts[category] = category_counts.get(category, 0) + 1
                            
                            if category_counts:
                                category_summary = ", ".join([f"{cat}: {count}" for cat, count in category_counts.items()])
                                console.print(f"[cyan]  Categories matched: {category_summary}[/cyan]")
                    
                    # Add to database
                    if jobs:
                        added = db.add_jobs(jobs[:limit])
                        total_added += added
                        console.print(f"[green]Added {added} jobs to database[/green]")
                    else:
                        console.print(f"[yellow]No relevant jobs to add from {feed_obj.name}[/yellow]")
                else:
                    console.print(f"[yellow]No jobs found in {feed_obj.name}[/yellow]")
            except Exception as e:
                console.print(f"[red]Error fetching from {feed_obj.name}: {str(e)}[/red]")
            progress.advance(task)
        
        # Show summary
        console.print(f"\n[bold green]Fetch Summary:[/bold green]")
        console.print(f"  Total jobs fetched: {total_fetched}")
        if smart_matcher:
            console.print(f"  Relevant jobs after smart filtering: {total_relevant}")
            if total_fetched > 0:
                relevance_rate = (total_relevant / total_fetched) * 100
                console.print(f"  Relevance rate: {relevance_rate:.1f}%")
        console.print(f"  Jobs added to database: {total_added}")

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

@cli.command('smart-search')
@click.option('--categories', help='Comma-separated list of categories to search (customer_support, technical_support, specialist_roles, compliance_analysis, operations)')
@click.option('--min-score', type=int, default=1, help='Minimum relevance score (1-5)')
@click.option('--limit', type=int, default=20, help='Maximum number of results to show')
@click.option('--show-keywords', is_flag=True, help='Show matching keywords for each job')
def smart_search(categories: Optional[str], min_score: int, limit: int, show_keywords: bool):
    """Search for jobs using smart title matching based on your interests."""
    db = Database()
    smart_matcher = create_smart_matcher()
    
    # Parse categories if provided
    category_list = None
    if categories:
        category_list = [cat.strip() for cat in categories.split(',')]
        # Validate categories
        valid_categories = list(smart_matcher.INTERESTED_KEYWORDS.keys())
        invalid_categories = [cat for cat in category_list if cat not in valid_categories]
        if invalid_categories:
            console.print(f"[red]Invalid categories: {invalid_categories}[/red]")
            console.print(f"[yellow]Valid categories: {valid_categories}[/yellow]")
            return
    
    # Get all jobs from database
    console.print("[blue]Searching for relevant jobs...[/blue]")
    all_jobs = db.search_jobs(filters={}, limit=1000)  # Get more jobs to filter through
    
    if not all_jobs:
        console.print("[yellow]No jobs found in the database[/yellow]")
        return
    
    # Convert to Job objects (assuming database returns JobModel objects)
    job_objects = []
    for db_job in all_jobs:
        job = Job(
            id=db_job.id,
            title=db_job.title,
            company=db_job.company,
            url=db_job.url,
            source=db_job.source,
            date=db_job.date.isoformat() if db_job.date else ""
        )
        # Add additional fields if they exist
        if hasattr(db_job, 'description'):
            job.description = db_job.description
        if hasattr(db_job, 'location'):
            job.location = db_job.location
        if hasattr(db_job, 'salary'):
            job.salary = db_job.salary
        if hasattr(db_job, 'job_type'):
            job.job_type = db_job.job_type
        if hasattr(db_job, 'experience_level'):
            job.experience_level = db_job.experience_level
        if hasattr(db_job, 'is_remote'):
            job.is_remote = db_job.is_remote
        
        job_objects.append(job)
    
    # Apply smart filtering
    if category_list:
        relevant_jobs = smart_matcher.search_jobs_by_interest(job_objects, category_list)
    else:
        relevant_jobs = smart_matcher.filter_jobs(job_objects, min_score)
    
    # Limit results
    relevant_jobs = relevant_jobs[:limit]
    
    if not relevant_jobs:
        console.print("[yellow]No relevant jobs found matching your criteria[/yellow]")
        if category_list:
            console.print(f"[blue]Searched categories: {category_list}[/blue]")
        console.print(f"[blue]Minimum score: {min_score}[/blue]")
        return
    
    # Display results
    console.print(f"[green]Found {len(relevant_jobs)} relevant jobs[/green]")
    
    table = Table(title="Smart Job Search Results")
    table.add_column("Title", style="cyan", width=30)
    table.add_column("Company", style="green", width=20)
    table.add_column("Source", style="blue", width=15)
    
    if show_keywords:
        table.add_column("Keywords", style="yellow", width=25)
    
    table.add_column("URL", style="magenta", width=30)
    
    for job in relevant_jobs:
        row_data = [
            job.title,
            job.company,
            job.source
        ]
        
        if show_keywords:
            keywords = smart_matcher.get_matching_keywords(job)
            keywords_str = ", ".join(keywords[:3])  # Show first 3 keywords
            if len(keywords) > 3:
                keywords_str += "..."
            row_data.append(keywords_str)
        
        row_data.append(job.url)
        table.add_row(*row_data)
    
    console.print(table)
    
    # Show category breakdown if no specific categories were requested
    if not category_list:
        console.print("\n[blue]Category Breakdown:[/blue]")
        category_counts = {}
        for job in relevant_jobs:
            scores = smart_matcher.get_match_score(job)
            for category, score in scores.items():
                if score > 0:
                    category_counts[category] = category_counts.get(category, 0) + 1
        
        for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            console.print(f"  {category}: {count} jobs")

def main():
    """Main entry point for the CLI."""
    cli() 