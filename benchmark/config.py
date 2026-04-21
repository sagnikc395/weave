TOSCRAPE_URLS = [
    f"http://books.toscrape.com/catalogue/page-{i}.html" for i in range(1, 21)
]

LOCAL_URLS = [f"http://localhost:8765/page/{i}" for i in range(1, 21)]

# local server
DENSE_TEXT = " ".join(f"word{i}" for i in range(2000))  # ~22 KB of parseable text
