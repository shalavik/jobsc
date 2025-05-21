# JobRadar (jobsc)

A Python-based CLI and web dashboard for aggregating, filtering, and viewing remote job listings from multiple sources.

## Features
- Fetch jobs from RSS, JSON, and custom HTML sources
- Advanced filtering (keywords, location, salary, job type, experience, remote, source)
- Deduplication and persistence in SQLite
- Web dashboard for interactive job search
- Telegram notification support (optional)
- Extensible parser and notifier architecture

## Project Structure

```
/Users/slavaidler/project/jobsc/
├── feeds.yml (symlink to projectrules)
├── jobs.db
├── jobradar/
│   ├── cli.py
│   ├── database.py
│   ├── filters.py
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