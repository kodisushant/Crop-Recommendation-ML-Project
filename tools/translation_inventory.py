"""Audit visible template copy without touching form values or URLs."""
from html.parser import HTMLParser
from pathlib import Path
import json
import re

class Texts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texts=set()
    def handle_data(self,text):
        text=' '.join(text.split())
        if re.search('[A-Za-z]{2}',text) and not text.startswith(('{%','{{')):
            self.texts.add(text)

if __name__=='__main__':
    parser=Texts()
    for file in (Path(__file__).resolve().parents[1]/'templates').glob('*.html'):
        parser.feed(file.read_text(encoding='utf-8'))
    print(json.dumps(sorted(parser.texts),ensure_ascii=False,indent=2))
