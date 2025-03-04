# monitor/parser.py
from typing import Dict, Any
from bs4 import BeautifulSoup, Comment

def parse_html(content: str) -> Dict[str, Any]:
    soup = BeautifulSoup(content, "html.parser")
    for script in soup(["script", "style"]):
        script.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    visible_text = soup.get_text(separator="\n", strip=True)
    meta_data = {}
    for meta in soup.find_all("meta"):
        if meta.get("name") and meta.get("content"):
            meta_data[meta.get("name")] = meta.get("content")
    structure = str(soup)
    return {"text": visible_text, "structure": structure, "meta": meta_data}
