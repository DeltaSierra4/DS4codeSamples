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


def gen_summary(system_message, chatlog)
    client = OpenAI(api_key="""YOUR API KEY""")
    context = [
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": "\n".join(chatlog)
            }
        ]

    response = client.responses.create(
        model="gpt-5.1",
        reasoning={"effort": "medium"},
        input=context
    )
    
    print(response.output_text)


if __name__ == "__main__":
    chatlog_obtained = False
    while not chatlog_obtained:
        print("Type in the file path to the htm file containing your chatlogs.")
        try:
            rows = extract_log_rows(input())
        except FileNotFoundError as fnf:
            print(f"File not found. Please try again: {str(fnf)}")
            continue
        except Exception:
            print("Conversion to chatlog failed. Check your file and try again.")
            continue
        chatlog_obtained = True

    system_message = r"""
You are an AI assistant specialized in summarizing conversations from chat logs.
Provide a concise, informative summary of the conversation, highlighting:
    - Main topics discussed
    - Key points or decisions made
    - Timeline of important events
    
Focus on extracting meaningful content from the chat, ignoring reactions, acknowledgments, 
and trivial messages. Pay special attention to discussions about problems, solutions, 
and decisions that were made.
    
Keep the summary factual and objective. Do not make things up that weren't discussed
in the chatlog."""
    system_message = system_message.strip()

    summary_string = gen_summary(system_message, rows)
    print(summary_string)
