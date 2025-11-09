"""
Book Scraper Library.

This module provides functionality for scraping book data from website
books.toscrape.com and scheduling scraping tasks.
"""

import json
import re
import sys
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter

import requests
import schedule
from bs4 import BeautifulSoup
from rich.console import Console
from rich.live import Live
from rich.text import Text


class ScraperException(Exception):
    """Base exception for the scraper."""


def _create_session() -> requests.Session:
    """Create configured HTTP session with retry strategy."""
    session = requests.Session()

    adapter = HTTPAdapter(
        pool_connections=10,
        pool_maxsize=10,
        max_retries=3
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    return session

# Constants
DEFAULT_SCRAPER_TIME = '19:00'
HTML_PARSER = 'html.parser'
BASE_URL = "https://books.toscrape.com/catalogue/"
SESSION = _create_session()


def timer(func):
    """
    Decorator to measure and print function execution time.

    Args:
        func: Function to measure execution time for

    Returns:
        function: Wrapped function with timing functionality
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        """
        Measure execution time of the wrapped function.

        Args:
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            The result of the wrapped function
        """
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        print(
            f"Function '{func.__name__}' executed in "
            f"{execution_time:.0f} seconds"
        )
        return result

    return wrapper

@timer
def scrape_books(is_save: bool = True) -> list[dict]:
    """
    Scrape books from all catalog pages.

    Iterates through all pages of the catalog and parses book data.
    Optionally saves results to a file.

    Args:
        is_save: Flag to save results to file, defaults to True

    Returns:
        List of dictionaries with book data
    """
    page_url = BASE_URL + '/page-1.html'
    response = SESSION.get(page_url)
    total_count = _determine_total_count(response.text)
    list_books = []
    console = Console(file=sys.stderr, force_terminal=True)

    with Live(
            _get_progress_display(total_count, len(list_books)),
            refresh_per_second=1, console=console, transient=True
    ) as live:
        while response:
            soup = BeautifulSoup(response.text, HTML_PARSER)
            div_tags = soup.find(
                'div', attrs={'class': 'col-sm-8 col-md-9'}
            )
            last_link = None

            for tag in div_tags.find_all('a'):
                href = tag.get('href')
                if (last_link and href == last_link or
                        tag.find_parent('li', attrs={'class': 'previous'})):
                    continue
                if tag.find_parent('li', attrs={'class': 'next'}):
                    response = SESSION.get(
                        f'https://books.toscrape.com/catalogue/{href}'
                    )
                    break
                last_link = href
                (list_books.append(get_book_data(
                    f'https://books.toscrape.com/catalogue/{href}'))
                )
            else:
                response = None
                live.update(
                    _get_progress_display(total_count, len(list_books))
                )
            live.update(_get_progress_display(total_count, len(list_books)))

    if is_save:
        file_path = Path("artifacts/books_data.txt")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        _save_to_file(list_books, file_path)

    return list_books


def get_book_data(book_url: str) -> dict:
    """
    Extract book data from individual book page.

    Collects title, price, rating, stock count, description,
    and product information from the table.

    Args:
        book_url: URL of the book page

    Returns:
        Dictionary with book data
    """
    _check_valid_http_url(book_url)
    book_data = {}

    response = SESSION.get(book_url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, HTML_PARSER)

    # Extract main product information
    product_main = soup.find(
        'div', attrs={'class': 'col-sm-6 product_main'}
    )
    book_data['title'] = product_main.find('h1').text
    book_data['price'] = product_main.find(
        'p', attrs={'class': 'price_color'}
    ).text

    # Extract stock information
    stock_info = product_main.find(
        'p', attrs={'class': 'instock availability'}
    )
    for child in stock_info.children:
        numbers = re.findall(r'\d+', child.text)
        if numbers:
            book_data['available_count'] = numbers[0]

    # Extract rating
    rating_map = {'One': 1, 'Two': 2, 'Three': 3, 'Four': 4, 'Five': 5}
    rating_element = stock_info.find_next_siblings()[0]
    book_data['rate'] = rating_map[rating_element.get('class')[1]]

    # Extract description if exists
    description_div = soup.find(
        'div', attrs={'id': 'product_description'}
    )
    if description_div:
        book_data['description'] = description_div.find_next_siblings()[0].text

    # Extract product information table
    product_table = soup.find(
        'table', attrs={'class': 'table table-striped'}
    )
    for row in product_table.find_all('tr'):
        key = row.find_next('th').text
        value = row.find_next('td').text
        book_data[key] = value

    return book_data


def scrape_books_at_time(scraper_time: str) -> None:
    """
    Schedule book scraping at specified time.

    Args:
        scraper_time: Time in HH:MM format for daily execution
    """
    _check_valid_time(scraper_time)
    schedule.every().day.at(scraper_time).do(scrape_books)
    console = Console(file=sys.stderr, force_terminal=True)
    live_stopped = False

    with Live(
            _get_scheduled_display(scraper_time), refresh_per_second=1,
            console=console, transient=True
    ) as live:
        while True:
            if schedule.idle_seconds() < 1:
                live.stop()
                live_stopped = True
            schedule.run_pending()
            time.sleep(1)
            if live_stopped and schedule.idle_seconds() > 1:
                live.start()
                live_stopped = False
            if not live_stopped:
                live.update(_get_scheduled_display(scraper_time))


def _check_valid_time(time_str: str) -> None:
    """
    Check if the time string matches HH:MM format with valid values.

    Args:
        time_str: Time string to validate in HH:MM format

    Raises:
        ScraperException: If time format is invalid or values are out
        of range
    """
    pattern = r'^([01]?\d|2[0-3]):([0-5]\d)$'
    if not re.match(pattern, time_str):
        raise ScraperException(
            f'Incorrect time format: {time_str}, should be HH:MM'
        )

def _check_valid_http_url(url: str) -> None:
    """
    Validate HTTP/HTTPS URL format.

    Args:
        url: URL string to validate

    Raises:
        ScraperException: If URL format is invalid
    """
    try:
        result = urlparse(url)
        is_valid = all([
            result.scheme in ['http', 'https'],
            result.netloc
        ])
        if not is_valid:
            raise ScraperException(f'Incorrect URL: {url}')
    except Exception as e:
        raise ScraperException(f'Incorrect URL: {url}') from e


def _determine_total_count(html_text: str) -> int:
    """
    Determine total count of books from catalog page.

    Args:
        html_text: HTML content of the catalog page

    Returns:
        Total number of books

    Raises:
        ScraperException: If total count cannot be determined
    """
    try:
        soup = BeautifulSoup(html_text, HTML_PARSER)
        div_tags = soup.find('div', class_='col-sm-8 col-md-9')
        form_tag = div_tags.find('form', class_='form-horizontal')
        count_text = form_tag.find_next('strong').text
        return int(count_text)
    except (AttributeError, ValueError) as e:
        raise ScraperException('Cannot determine total book count') from e


def _get_scheduled_display(scraper_time: str) -> Text:
    """
    Create progress display for scheduled scraping.

    Args:
        scraper_time: Scheduled time in HH:MM format

    Returns:
        Text object with progress information
    """
    now: datetime = datetime.now()
    target_time: datetime = now.replace(
        hour=int(scraper_time.split(':')[0]),
        minute=int(scraper_time.split(':')[1]),
        second=0,
        microsecond=0
    )

    # if time has passed today, schedule for tomorrow
    if target_time <= now:
        target_time += timedelta(days=1)

    time_left: timedelta = target_time - now
    total_seconds: float = time_left.total_seconds()

    # format time display
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return Text.from_markup(
        f"The scraping is daily scheduled for [bold green]"
        f"{scraper_time}[/bold green]. The next launch is in: "
        f"[cyan]{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}[/cyan]"
    )

def _get_progress_display(total_count: int, processed_books: int) -> Text:
    """
    Create progress display for book scraping process.

    Args:
        total_count: Total number of books to process
        processed_books: Number of books already processed

    Returns:
        Text object with progress bar
    """
    progress_percent = (processed_books / total_count * 100) \
        if total_count > 0 else 0
    progress_percent = max(0, min(100, progress_percent))

    bar_length = 30
    filled_length = int(bar_length * progress_percent / 100)
    bar_view = '█' * filled_length + '░' * (bar_length - filled_length)

    return Text.from_markup(
        f"Processed {processed_books} books from {total_count}. "
        f"Progress: [{bar_view}] [yellow]{progress_percent:.1f}%[/yellow]"
    )


def _save_to_file(books_data: list[dict], file_path: Path) -> None:
    """
    Save book data as JSON to file.

    Args:
        books_data: List of book dictionaries
        file_path: Path to save file
    """
    if not books_data:
        return
    with open(file_path, 'w', encoding='utf-8') as file:
        for book in books_data:
            json.dump(book, file, ensure_ascii=False, indent=2)
            file.write('\n')


# Example usage
if __name__ == "__main__":
    try:
        scrape_books_at_time(DEFAULT_SCRAPER_TIME)
    except KeyboardInterrupt:
        sys.exit(0)
