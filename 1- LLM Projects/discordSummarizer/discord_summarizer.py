from bs4 import BeautifulSoup
import re
from pathlib import Path


def extract_log_rows(html_path: str):
    html_path = Path(html_path)

    if not html_path.exists():
        raise FileNotFoundError(f"File not found: {html_path}")

    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Regex for id="log-row-{integer}"
    log_row_pattern = re.compile(r"^log-row-\d+$")

    log_rows = soup.find_all(
        "tr",
        id=log_row_pattern
    )
    return extract_author_and_message(log_rows)


def extract_author_and_message(tr_rows: list) -> list[str]:
    """
    Given a list of BeautifulSoup <tr> Tag objects, return a list of strings containing
    the HTML of the author <td> and message <td>.
    """
    extracted = []

    # Regex to remove Discord attachment query params (?ex=...&)
    #attachment_query_re = re.compile(r"\?ex=[^&]+&[^)]*\)")
    attachment_query_re = re.compile(r"ex=[^&]+&is=[^&]+&hm=[^&]+&\)")

    # Regex to replace Discord user mentions
    mention_re = re.compile(r"<@(\d+)>")

    for tr_element in tr_rows:
        # tr_element is already a BeautifulSoup Tag object representing a <tr>
        # No need to create a new BeautifulSoup object or find 'tr' again

        tds = tr_element.find_all("td")

        if len(tds) < 3:
            continue  # malformed row

        author_td = tds[1]
        message_td = tds[2]

        # Skip if message cell is empty or whitespace-only
        if not message_td.get_text(strip=True):
            continue

        # Remove attachment query gibberish (keep closing parenthesis)
        message_text = attachment_query_re.sub(")", message_td.get_text(strip=True)).replace("?\n)", ")")
        #print(message_text)

        # Replace <@123> with user-123
        message_text = mention_re.sub(r"user-\1", message_text)
        #print(message_text)

        extracted.append(
            f"{author_td.get_text(strip=True)}: {message_text}"#{message_td.get_text(strip=True)}"
        )

    return extracted


if __name__ == "__main__":
    rows = extract_log_rows("sample2.htm")

    for row in rows:
        print(row)
        print("-" * 80)
