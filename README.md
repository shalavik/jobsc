# JobRadar (jobsc)

A Python-based CLI and web dashboard for aggregating, filtering, and viewing remote job listings from multiple sources.

## Features
- Fetch jobs from RSS, JSON, and custom HTML sources
- **Smart job filtering** - Only stores relevant jobs using intelligent matching
- Advanced filtering (keywords, location, salary, job type, experience, remote, source)
- Deduplication and persistence in SQLite
- Web dashboard for interactive job search
- Telegram notification support (optional)
- Extensible parser and notifier architecture

## Smart Filtering

JobRadar includes intelligent job filtering that happens **during the fetch process**, ensuring only relevant jobs enter your database. This dramatically improves performance and keeps your database clean.

### Benefits
- 🎯 **Precision**: Only stores jobs matching your interests
- 💾 **Efficiency**: Up to 98% reduction in database size
- ⚡ **Performance**: Faster searches with less data
- 🧹 **Clean Data**: No irrelevant jobs cluttering results

### How It Works
The smart matcher uses keyword categories to identify relevant jobs:
- **Customer Support**: customer service, support, customer experience
- **Technical Support**: technical support, product support, helpdesk, L1/L2/L3
- **Specialist Roles**: implementation specialist, solutions engineer
- **Compliance & Analysis**: AML analyst, compliance officer, fraud analysis
- **Operations**: business operations, operations manager

### Configuration
Add smart filtering configuration to your `projectrules` file:

```yaml
smart_filtering:
  enabled: true               # Enable smart filtering by default
  min_score: 1               # Minimum relevance score (1-5)
  categories:                # Categories of jobs you're interested in
    - customer_support       # Customer service, support, customer experience
    - technical_support      # Technical support, product support, helpdesk
    - specialist_roles       # Integration specialist, solutions engineer, etc.
    - compliance_analysis    # AML, compliance, fraud analysis, KYC/EDD
    - operations            # Operations, business operations
```

### CLI Usage

**Fetch with smart filtering (default):**
```bash
jobradar fetch
```

**Override smart filtering:**
```bash
jobradar fetch --no-smart-filter          # Disable smart filtering
jobradar fetch --min-score 2              # Increase minimum score
```

**Search for smart-matched jobs:**
```bash
jobradar smart-search --categories customer_support --limit 10
```

### Demo
Run the demo to see the effectiveness:
```bash
python demo_smart_filtering.py
```

## Project Structure

```
/Users/slavaidler/project/jobsc/
├── feeds.yml (symlink to projectrules)
├── jobs.db
├── jobradar/
│   ├── cli.py
│   ├── database.py
│   ├── filters.py
│   ├── smart_matcher.py         # Smart filtering logic
│   ├── models.py
│   ├── fetchers.py
│   ├── core.py
│   ├── notifiers/
│   ├── parsers/
│   └── web/
│       ├── app.py
│       └── templates/
│           └── index.html
├── tests/
├── demo_smart_filtering.py      # Effectiveness demo
├── pyproject.toml
└── README.md
```

## Setup

1. **Clone the repository and enter the project directory:**
   ```bash
   cd /Users/slavaidler/project/jobsc
   ```

2. **Install dependencies:**
   ```bash
   pip install -e .[dev]
   ```

3. **Ensure configuration file exists:**
   - Use `feeds.yml` (symlinked to `projectrules`) for feed configuration.

4. **(Optional) Set up Telegram notifications:**
   - Add `TG_TOKEN` and `TG_CHAT_ID` to your environment or a `.env` file.

## Usage

### Fetch Jobs
Fetch jobs from all configured feeds and store them in the database:
```bash
jobradar fetch
```

### Start the Web Dashboard
Run the dashboard and open it in your browser:
```bash
jobradar web --port 8080
```
Visit [http://localhost:8080](http://localhost:8080)

### Filtering and Search
Use the dashboard's filter panel to search jobs by:
- Keywords
- Location
- Salary range
- Job type
- Experience level
- Remote status
- Source

### Run Tests
Run all tests with:
```bash
pytest
```

## Notes
- The database schema must match the latest model. If you add new fields, update the schema accordingly.
- If you encounter errors about missing columns, run the appropriate `ALTER TABLE` commands or delete `jobs.db` to recreate it.
- For troubleshooting, check logs and ensure all dependencies are installed.

## License
MIT