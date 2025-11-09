import sys
from scraper import scrape_books_at_time

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_scraper.py <SCRAPER_TIME>")
        print("Example: python run_scraper.py '19:05'")
        sys.exit(1)

    try:
        time_str = sys.argv[1]
        scrape_books_at_time(time_str)
    except KeyboardInterrupt:
        sys.exit(0)