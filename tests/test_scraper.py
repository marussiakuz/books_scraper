"""Tests for book scraper functionality.

All tests use mocking to isolate from real network requests 
and external dependencies. HTML content is loaded from local 
test files instead of making actual HTTP requests.
"""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

try:
    from books_scraper import scraper
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import scraper


REQUESTS_GET_MODULE_PATH = 'books_scraper.scraper.SESSION.get'
TEST_DIR = os.path.dirname(os.path.abspath(__file__))


@pytest.mark.parametrize("invalid_url", [
    "ssh://server.com",
    "http://",
    "https://",
    "books.toscrape.com",
    "htts://books.toscrape.com",
])
def test_get_book_data_invalid_url(invalid_url):
    """Test that get_book_data raises error with invalid URL"""
    with pytest.raises(scraper.ScraperException,
                       match=f"Incorrect URL: {invalid_url}"):
        scraper.get_book_data(invalid_url)


@pytest.mark.parametrize("invalid_time", [
    "19:",
    "24:00",
    ":20",
    "07:60",
    "-19:00",
])
def test_scrape_books_at_time_invalid_time(invalid_time):
    """Test that scrape_books_at_time raises error with invalid time"""
    with pytest.raises(scraper.ScraperException,
                       match=f"Incorrect time format: {invalid_time}, "
                             f"should be HH:MM"):
        scraper.scrape_books_at_time(invalid_time)


def test_get_book_data_returns_correct_data():
    """
    Test that get_book_data by url returns correct book data structure.

    Checks:
    checks that a dictionary is returned;
    checks that all expected keys are present;
    checks that the types for each field are correct;
    checks that the function correctly extracted specific
    values from the HTML
    """
    html_content = (Path(Path(TEST_DIR) / "resources/get_book_data/test.html")
                    .read_text(encoding='utf-8'))
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = html_content
    mock_response.encoding = 'utf-8'

    test_url = ("https://books.toscrape.com/1000-places-to-see-before-you-die"
                "/index.html")

    with patch(REQUESTS_GET_MODULE_PATH) as mock_get:
        mock_get.return_value = mock_response
        result = scraper.get_book_data(test_url)
        mock_get.assert_called_once_with(test_url)

        assert isinstance(result, dict)

        expected_keys = {
            'title', 'price', 'available_count', 'rate', 'description',
            'UPC', 'Product Type', 'Price (excl. tax)', 'Price (incl. tax)',
            'Tax', 'Availability', 'Number of reviews'
        }
        assert set(result.keys()) == expected_keys, "Keys mismatch"

        assert isinstance(result['title'], str), "title type isn't str"
        assert isinstance(result['description'], str), \
            "description type isn't str"
        assert isinstance(result['price'], str), "price type isn't str"
        assert isinstance(result['available_count'], str), \
            "available_count type isn't str"
        assert isinstance(result['rate'], int), "rate type isn't int"

        assert result['title'] == '1,000 Places to See Before You Die', \
            "title mismatch"
        assert result['price'] == '£26.08', "price mismatch"
        assert result['available_count'] == '1', "available_count mismatch"
        assert result['rate'] == 5, "rate mismatch"
        assert result['description'] == (
            "Around the World, continent by continent, here is the best the "
            "world has to offer: 1,000 places guaranteed to give travelers "
            "the shivers. Sacred ruins, grand hotels, wildlife preserves, "
            "hilltop villages, snack shacks, castles, festivals, reefs, "
            "restaurants, cathedrals, hidden islands, opera houses, museums, "
            "and more. Each entry tells exactly why it's essential to visit "
            "...more"
        ), "description mismatch"
        assert result['UPC'] == '228ba5e7577e1d49', "UPC mismatch"
        assert result['Product Type'] == 'Books', "Product Type mismatch"
        assert result['Number of reviews'] == '0', "Number of reviews mismatch"


def test_scrape_books_returns_correct_data():
    """Test that scrape_books returns correct book data structure.

    Checks:
    checks that the result is a list;
    checks that exactly 5 books are returned (because the test data
    contains 5 books)
    checks that each element of the list is a dictionary
    checks that each dictionary contains all the expected keys
    """

    with patch(REQUESTS_GET_MODULE_PATH, side_effect=mock_requests_get):
        result = scraper.scrape_books(is_save=False)
        expected_keys = (
            {'title', 'price', 'available_count', 'rate', 'description'}
        )

        assert isinstance(result, list), "Should return list of book datas"
        assert len(result) == 5, "Should return 5 books"

        for i, book in enumerate(result):
            assert isinstance(book, dict), \
                f"Book data {i} should be dictionary"
            missing_keys = expected_keys - set(book.keys())
            assert missing_keys == set(), \
                f"Book data {i} missing key: {missing_keys}"


def test_scrape_books_creates_correct_file():
    """
    Test that scrape_books creates file with expected content
    in artifacts directory.
    Creates a mock for the file path and intercepts writing to the file.

    Checks:
    checks that the scrape_books function correctly creates a file
    with data when the save flag is enabled;
    checks that the function tries to create the required folder;
    checks that the function returns the correct data (5 books)
    checks that the file was physically created and that it is not empty
    compares the contents of the created file with the expected file
    """
    with patch(REQUESTS_GET_MODULE_PATH, side_effect=mock_requests_get):
        # mock for path
        mock_path = Mock()
        mock_path.__fspath__ = Mock(
            return_value="artifacts/books_data.txt")
        mock_path.__str__ = Mock(return_value="artifacts/books_data.txt")
        mock_path.parent.mkdir = Mock()
        mock_path.parent = Mock()

        written_data = []

        def mock_write(data):
            written_data.append(data)
            return len(data)

        # mock for file
        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_file.write = Mock(side_effect=mock_write)

        with patch('books_scraper.scraper.Path', return_value=mock_path), \
                patch('builtins.open', return_value=mock_file):
            result = scraper.scrape_books(is_save=True)

            assert isinstance(result, list)
            assert len(result) == 5

            # check mkdir called
            mock_path.parent.mkdir.assert_called_once_with(parents=True,
                                                           exist_ok=True)
            # check file write called
            assert mock_file.write.called

            file_content = "".join(written_data)
            assert len(file_content) > 0

            expected_file = (Path(
                Path(TEST_DIR) / "resources/scrape_books/books_data.txt")
            )
            expected_content = expected_file.read_text(encoding='utf-8')
            assert file_content == expected_content


def mock_requests_get(url: str) -> Mock:
    """
    Create mock requests.get function that reads HTML from test resources
    by URL (from directory tests/resources/scrape_books/...).

    Args:
        url: URL to link to a specific HTML file from test resources

    Returns:
        Mock function for requests.get
    """

    mock_resp = Mock()
    mock_resp.encoding = 'utf-8'

    postfix = url.split('/')[-1]
    file_path = Path(Path(TEST_DIR) / f"resources/scrape_books/{postfix}")

    if file_path.exists():
        html_content = file_path.read_text(encoding='utf-8')
        mock_resp.text = html_content
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.content = html_content.encode('utf-8')
    else:
        mock_resp.status_code = 404

    return mock_resp
