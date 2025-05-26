# Test-Driven Development (TDD) Guide for JobRadar

## Overview

This guide explains how to use Test-Driven Development (TDD) methodology for the JobRadar application. TDD follows the **Red-Green-Refactor** cycle to drive development through tests.

## TDD Principles

### The Red-Green-Refactor Cycle

1. **🔴 RED**: Write a failing test first
   - Write a test for the functionality you want to implement
   - The test should fail because the functionality doesn't exist yet
   - This defines the requirements and expected behavior

2. **🟢 GREEN**: Write minimal code to make the test pass
   - Implement just enough code to make the test pass
   - Don't worry about perfect code - focus on making it work
   - The goal is to get from red to green as quickly as possible

3. **🔄 REFACTOR**: Improve the code while keeping tests green
   - Clean up the code without changing its behavior
   - Improve structure, readability, and performance
   - All tests must continue to pass

## TDD Test Structure

### Test Organization

Our TDD tests are organized by component:

```
tests/test_tdd_comprehensive.py
├── TestJobModelTDD          # Job model tests
├── TestSmartMatcherTDD      # Smart matching tests
├── TestFetcherTDD           # Web scraping tests
├── TestDatabaseTDD          # Data persistence tests
├── TestRateLimiterTDD       # Rate limiting tests
├── TestJobFilterTDD         # Job filtering tests
├── TestConfigTDD            # Configuration tests
└── TestIntegrationTDD       # End-to-end tests
```

### Test Naming Convention

Tests are named to indicate their TDD phase:

- **RED tests**: `test_feature_should_fail()` - Tests that drive new requirements
- **GREEN tests**: `test_feature_works()` - Tests that verify basic functionality
- **REFACTOR tests**: Tests remain the same, but code is improved

## Running TDD Tests

### Basic Test Execution

```bash
# Run all TDD tests
pytest tests/test_tdd_comprehensive.py -v

# Run specific test class
pytest tests/test_tdd_comprehensive.py::TestJobModelTDD -v

# Run with coverage
pytest tests/test_tdd_comprehensive.py --cov=jobradar --cov-report=html
```

### TDD Development Workflow

```bash
# 1. Run tests to see current state (should have some failures)
pytest tests/test_tdd_comprehensive.py -v

# 2. Pick a failing test and implement minimal code
# 3. Run tests again to see if it passes
pytest tests/test_tdd_comprehensive.py::TestJobModelTDD::test_job_creation_with_required_fields -v

# 4. Refactor if needed and run all tests
pytest tests/test_tdd_comprehensive.py -v
```

## TDD Examples

### Example 1: Job Model Development

#### 🔴 RED Phase - Write Failing Test

```python
def test_job_creation_with_required_fields(self):
    """RED: Test that Job requires essential fields."""
    with pytest.raises((ValueError, TypeError)):
        Job()  # Should fail without required fields
```

#### 🟢 GREEN Phase - Minimal Implementation

```python
# In jobradar/models.py
class Job:
    def __init__(self, id=None, title=None, company=None, url=None, source=None, date=None):
        if not id or not title:
            raise ValueError("Job requires id and title")
        self.id = id
        self.title = title
        self.company = company
        self.url = url
        self.source = source
        self.date = date
```

#### 🔄 REFACTOR Phase - Improve Code

```python
# Improved version with better validation
class Job:
    def __init__(self, id, title, company, url, source, date):
        self._validate_required_fields(id, title)
        self.id = id
        self.title = title
        self.company = company
        self.url = url
        self.source = source
        self.date = date
    
    def _validate_required_fields(self, id, title):
        if not id or not isinstance(id, str) or not id.strip():
            raise ValueError("Job ID is required and must be a non-empty string")
        if not title or not isinstance(title, str) or not title.strip():
            raise ValueError("Job title is required and must be a non-empty string")
```

### Example 2: Smart Matcher Development

#### 🔴 RED Phase - Define Requirements

```python
def test_relevance_score_returns_numeric_value(self):
    """RED: Test that relevance scoring returns a number."""
    matcher = SmartMatcher()
    score = matcher.calculate_relevance_score("Customer Support Engineer", "TechCorp")
    
    assert isinstance(score, (int, float))
    assert 0 <= score <= 10
```

#### 🟢 GREEN Phase - Basic Implementation

```python
# In jobradar/smart_matcher.py
class SmartMatcher:
    def calculate_relevance_score(self, title, company):
        # Minimal implementation to pass test
        if "support" in title.lower():
            return 8
        return 3
```

#### 🔄 REFACTOR Phase - Sophisticated Algorithm

```python
class SmartMatcher:
    def __init__(self, min_relevance_score=5):
        self.min_relevance_score = min_relevance_score
        self.keywords = {
            'high_relevance': ['customer support', 'technical support', 'customer success'],
            'medium_relevance': ['support', 'service', 'help'],
            'low_relevance': ['engineer', 'specialist', 'representative']
        }
    
    def calculate_relevance_score(self, title, company, description=""):
        score = 0
        title_lower = title.lower()
        
        # High relevance keywords
        for keyword in self.keywords['high_relevance']:
            if keyword in title_lower:
                score += 3
        
        # Medium relevance keywords
        for keyword in self.keywords['medium_relevance']:
            if keyword in title_lower:
                score += 2
        
        # Low relevance keywords
        for keyword in self.keywords['low_relevance']:
            if keyword in title_lower:
                score += 1
        
        return min(score, 10)  # Cap at 10
```

## TDD Best Practices

### 1. Start with the Simplest Test

```python
# Good: Simple, focused test
def test_job_has_id(self):
    job = Job(id="123", title="Test", company="Corp", url="", source="test", date="")
    assert job.id == "123"

# Avoid: Complex test that tests multiple things
def test_job_creation_and_validation_and_scoring(self):
    # Too much in one test
```

### 2. Write Tests for Behavior, Not Implementation

```python
# Good: Tests behavior
def test_smart_matcher_identifies_relevant_jobs(self):
    matcher = SmartMatcher()
    is_relevant = matcher.is_relevant("Customer Support Engineer", "TechCorp")
    assert is_relevant is True

# Avoid: Tests implementation details
def test_smart_matcher_uses_specific_algorithm(self):
    matcher = SmartMatcher()
    assert hasattr(matcher, '_calculate_keyword_score')  # Implementation detail
```

### 3. Keep Tests Independent

```python
# Good: Each test is independent
def test_database_saves_job(self):
    db = Database(":memory:")
    job = Job(...)
    db.save_job(job)
    assert len(db.get_all_jobs()) == 1

def test_database_handles_duplicates(self):
    db = Database(":memory:")  # Fresh database
    job = Job(...)
    db.save_job(job)
    db.save_job(job)  # Duplicate
    assert len(db.get_all_jobs()) == 1
```

### 4. Use Descriptive Test Names

```python
# Good: Descriptive names
def test_rate_limiter_waits_between_requests_to_same_feed(self):
def test_job_filter_blocks_jobs_from_blacklisted_companies(self):
def test_fetcher_retries_on_network_timeout(self):

# Avoid: Generic names
def test_rate_limiter(self):
def test_filter(self):
def test_fetch(self):
```

## TDD Development Workflow

### Step-by-Step Process

1. **Choose a Feature**: Pick the next feature to implement
2. **Write a Failing Test**: Create a test that defines the expected behavior
3. **Run the Test**: Verify it fails (RED)
4. **Write Minimal Code**: Implement just enough to pass the test
5. **Run the Test**: Verify it passes (GREEN)
6. **Refactor**: Improve the code while keeping tests green
7. **Repeat**: Move to the next feature

### Example Development Session

```bash
# 1. Start with failing tests
$ pytest tests/test_tdd_comprehensive.py::TestSmartMatcherTDD::test_relevance_score_returns_numeric_value -v
FAILED - AttributeError: 'SmartMatcher' object has no attribute 'calculate_relevance_score'

# 2. Implement minimal code to pass
# (Add basic calculate_relevance_score method)

# 3. Run test again
$ pytest tests/test_tdd_comprehensive.py::TestSmartMatcherTDD::test_relevance_score_returns_numeric_value -v
PASSED

# 4. Run all tests to ensure nothing broke
$ pytest tests/test_tdd_comprehensive.py -v

# 5. Refactor and repeat
```

## Integration with Existing Code

### Working with Legacy Code

When adding TDD to existing code:

1. **Start with New Features**: Use TDD for new functionality
2. **Add Tests for Bug Fixes**: Write tests that reproduce bugs, then fix them
3. **Refactor with Tests**: Add tests before refactoring existing code

### Mocking External Dependencies

```python
# Mock external services
@patch('requests.get')
def test_fetcher_handles_network_error(self, mock_get):
    mock_get.side_effect = requests.exceptions.Timeout()
    fetcher = Fetcher()
    # Test error handling

# Mock database for faster tests
@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    yield db
    db.close()
    os.unlink(db_path)
```

## Measuring TDD Success

### Test Coverage

```bash
# Generate coverage report
pytest tests/test_tdd_comprehensive.py --cov=jobradar --cov-report=html

# View coverage
open htmlcov/index.html
```

### Test Quality Metrics

- **Test Coverage**: Aim for >90% line coverage
- **Test Speed**: Tests should run quickly (< 1 second each)
- **Test Independence**: Tests should not depend on each other
- **Test Clarity**: Tests should be easy to read and understand

## Common TDD Pitfalls

### 1. Writing Tests After Code
```python
# Wrong: Code first, then test
def calculate_score(self, title):
    return len(title) * 2

def test_calculate_score(self):
    assert calculate_score("test") == 8  # Test written to match implementation
```

### 2. Testing Implementation Details
```python
# Wrong: Testing internal methods
def test_internal_method(self):
    matcher = SmartMatcher()
    assert matcher._private_method() == "something"

# Right: Testing public behavior
def test_relevance_scoring(self):
    matcher = SmartMatcher()
    score = matcher.calculate_relevance_score("Customer Support", "TechCorp")
    assert score > 5
```

### 3. Overly Complex Tests
```python
# Wrong: Complex test setup
def test_complex_scenario(self):
    # 50 lines of setup
    # Multiple assertions
    # Testing multiple behaviors

# Right: Simple, focused tests
def test_single_behavior(self):
    # Simple setup
    # Single assertion
    # One behavior
```

## Resources

- [TDD Test File](../tests/test_tdd_comprehensive.py)
- [JobRadar Components](../jobradar/)
- [Test Configuration](../pytest.ini)

## Next Steps

1. Run the TDD tests to see current state
2. Pick a failing test and implement the feature
3. Follow the Red-Green-Refactor cycle
4. Add new tests for additional features
5. Refactor existing code with test coverage

Remember: **The goal of TDD is not just testing, but driving better design through tests!** 