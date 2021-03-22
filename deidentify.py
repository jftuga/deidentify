r"""
deidentify.py
-John Taylor
Mar-16-2021

Deidentify a file by replacing all proper/given names with a user-defined replacement string and
then also replace pronouns such as 'he' to HE/SHE.

Parsed entities and pronouns will be saved in a temporary JSON file. Since this program will
probably not be 100% accurate, a small number of "possible misses" are also saved to this file.
Note that there can still be identifiable words in the output that are not substituted or contained
in the "possible misses" list. YMMV!

Example
=======
Input:
I think John Smith likes programming. You can tell he enjoys using Python.

Output:
I think EMPLOYEE likes programming. You can tell HE/SHE enjoys using Python.

Algorithm
=========
1) find the starting positions of all proper/given names: John Smith
2) find the starting positions of all pronouns: he
3) merge these two lists into one, merged list:
   ( { "type": "entity", "text": "John Smith", "start_char": 8 },
     { "type": "pronoun", "text": "he", "idx": 51 } )
   -- Note that start_char is used for entities and idx is used for pronouns
4) sort the merged list in reverse order according to starting position; (highest position first):
   ( { "type": "pronoun", "text": "he", "idx": 51 },
     { "type": "entity", "text": "John Smith", "start_char": 8 } )
5) iterate through the reverse-sorted merged list, replacing names and pronouns: John Smith -> EMPLOYEE, he -> HE/SHE

"""

import argparse
import json
import os.path
import sys
from operator import itemgetter

GENDER_PRONOUNS = {
    "he": "HE/SHE",
    "him": "HIM/HER",
    "his": "HIS/HER",
    "himself": "HIMSELF/HERSELF",
    "she": "HE/SHE",
    "her": "HIM/HER",
    "hers": "HIS/HERS",
    "herself": "HIMSELF/HERSELF",
    "mr.": "",
    "mrs.": "",
    "ms.": ""}

HTML_BEGIN = """<!DOCTYPE html>
<html>
<head>
<style>
#span1 {
  background: yellow;
  color: black;
  display: inline-block;
  font-weight: bold;
}
#span2 {
  background: turquoise;
  color: black;
  display: inline-block;
  font-weight: bold;
}
</style>
</head>
<body>
"""

HTML_END = """</body>
</html>
"""


def safe_print(data, is_error=False):
    dest = sys.stdout if not is_error else sys.stderr
    # can also use 'replace' instead of 'ignore' for errors= parameter
    print(str(data).encode(sys.stdout.encoding, errors='ignore').decode(sys.stdout.encoding), file=dest)


class DeIdentify:
    nlp = None  # nlp is of type spacy.lang

    def __init__(self, message: str, load=True):
        if load:
            import spacy
            DeIdentify.nlp = spacy.load('en_core_web_trf')
        self.message = message
        self.entities = []
        self.pronouns = []
        self.merged = []
        self.missed = []
        self.doc = None

    def get_entities(self):
        if len(self.message) <= 7:
            return

        if not self.doc:
            self.doc = DeIdentify.nlp(self.message)

        if 0:
            for ent in self.doc.ents:
                print(f"=ENTITIES {ent.text=}, {ent.start_char=}, {ent.end_char=}, {ent.label_=}")
        if 0:
            for token in self.doc:
                print(
                    f"=TOKENS {token.text=}, {token.lemma_=}, {token.pos_=}, {token.tag_=}, {token.dep_=}, {token.shape_=}, , {token.idx=}")

        for ent in self.doc.ents:
            if "PERSON" == ent.label_:
                # print(f"{ent.text}, {ent.start_char}, {ent.end_char}, {ent.label}")
                record = {"text": ent.text, "start_char": ent.start_char, "end_char": ent.end_char}
                self.entities.append(record)

        return self.entities

    def get_pronouns(self):
        if not self.doc:
            self.doc = DeIdentify.nlp(self.message)

        gender_keys = GENDER_PRONOUNS.keys()
        for token in self.doc:
            if (token.pos_ == "PRON" or token.pos_ == "PROPN") and token.text.lower() in gender_keys:
                # print(f"{token.text=}, {token.lemma_=}, {token.pos_=}, {token.tag_=}, {token.dep_=}, {token.shape_=}, , {token.idx=}")
                record = {"text": token.text, "idx": token.idx}
                self.pronouns.append(record)

        return self.pronouns

    def save_metadata(self, fname: str):
        with open(fname, encoding="latin1", mode="w") as fp:
            # self.entities and self.pronouns must be sorted by start_char/idx in reverse order (highest to lowest)
            sorted_entities = sorted(self.entities, key=itemgetter("start_char"), reverse=True)
            sorted_pronouns = sorted(self.pronouns, key=itemgetter("idx"), reverse=True)
            sorted_missed = sorted(self.missed, key=itemgetter("idx"), reverse=True)
            json.dump({"message": self.message, "entities": sorted_entities, "pronouns": sorted_pronouns,
                       "possible_misses": sorted_missed}, fp, skipkeys=False, ensure_ascii=False, indent=4)

    def replace_merged(self, want_html: bool, replacement: str) -> str:
        if 1:
            for obj in self.merged:
                text = obj["item"]["text"]
                if obj["type"] == "pronoun":
                    position = obj["item"]["idx"]
                elif obj["type"] == "entity":
                    position = obj["item"]["start_char"]
                if 0:
                    print(f"xx: {obj['type']}, {position}, {text}")
            if 0:
                print("=" * 77)

        for obj in self.merged:
            if obj["type"] == "pronoun":
                start = obj["item"]["idx"]
                end = start + len(obj["item"]["text"])

                anon = GENDER_PRONOUNS[obj["item"]["text"].lower()]

                if want_html and len(anon):
                    anon = '<span id="span1">' + anon + '</span>'

                self.message = self.message[:start] + anon + self.message[end:]
            elif obj["type"] == "entity":
                start = obj["item"]["start_char"]
                end = obj["item"]["end_char"]

                bold_replacement = '<span id="span2">' + replacement + '</span>' if want_html else replacement
                self.message = self.message[:start] + bold_replacement + self.message[end:]
            else:
                print(f"Error #74023: unknown object type: {obj['type']}")
                sys.exit(1)

        return self.message

    def merge_metadata(self):
        if 0:
            for ent in self.entities:
                print(ent)
            print("=" * 77)

        p = 0  # pronouns
        e = 0  # entities

        if len(self.pronouns) >= len(self.entities):
            while p < len(self.pronouns):
                idx = self.pronouns[p]["idx"]
                start_char = self.entities[e]["start_char"]
                if e == len(self.entities):
                    keyval = {"type": "pronoun", "index": p, "item": self.pronouns[p]}
                    p += 1
                    self.merged.append(keyval)
                    break
                if idx > start_char:
                    keyval = {"type": "pronoun", "index": p, "item": self.pronouns[p]}
                    p += 1
                else:
                    keyval = {"type": "entity", "index": e, "item": self.entities[e]}
                    e += 1
                self.merged.append(keyval)
            # there may be more entities that occur after the last pronoun is encountered
            while e < len(self.entities):
                keyval = {"type": "entity", "index": e, "item": self.entities[e]}
                e += 1
                self.merged.append(keyval)
            # there may be more pronouns that occur after the last entity is encountered
            while p < len(self.pronouns):
                keyval = {"type": "pronoun", "index": p, "item": self.pronouns[p]}
                p += 1
                self.merged.append(keyval)
        else:  # there are more entities than pronouns
            while e < len(self.entities):
                start_char = self.entities[e]["start_char"]
                if p == len(self.pronouns):
                    keyval = {"type": "entity", "index": e, "item": self.entities[e]}
                    e += 1
                    self.merged.append(keyval)
                    break
                idx = self.pronouns[p]["idx"]
                if start_char > idx:
                    keyval = {"type": "entity", "index": e, "item": self.entities[e]}
                    e += 1
                else:
                    keyval = {"type": "pronoun", "index": p, "item": self.pronouns[p]}
                    p += 1
                self.merged.append(keyval)
            # there may be more pronouns that occur after the last entity is encountered
            while p < len(self.pronouns):
                keyval = {"type": "pronoun", "index": p, "item": self.pronouns[p]}
                p += 1
                self.merged.append(keyval)
            # there may be more entities that occur after the last pronoun is encountered
            while e < len(self.entities):
                keyval = {"type": "entity", "index": e, "item": self.entities[e]}
                e += 1
                self.merged.append(keyval)

        if 0:
            import pprint
            print("xxx merged")
            pprint.pprint(self.merged)

        if 0:
            print("=" * 77)
            print(self.message)

    def possible_misses(self) -> list:
        previous = None
        previous_idx = 0
        for token in self.doc:
            if token.text == "'s" and token.pos_ == 'VERB':
                self.missed.append({"text": "%s%s" % (previous, token.text), "idx": previous_idx})
            previous = token.text
            previous_idx = token.idx

        return self.missed

    def load_metadata(self, fname: str):
        with open(fname, encoding="latin1") as fp:
            a = json.load(fp)
            self.entities = sorted(a["entities"], key=itemgetter("start_char"), reverse=True)
            self.pronouns = sorted(a["pronouns"], key=itemgetter("idx"), reverse=True)
            self.message = a["message"]


#############################################################################################################

def create_json_filename(input_file: str) -> str:
    filename, _ = os.path.splitext(input_file)
    return filename + "--tokens.json"


def replacer(want_html: bool, replacement: str, input_file: str) -> str:
    a = DeIdentify("", load=False)
    a.load_metadata(create_json_filename(input_file))
    a.merge_metadata()
    return a.replace_merged(want_html, replacement)


def finder(input_file: str) -> tuple:
    with open(input_file, encoding="latin1") as fp:
        data = fp.read()

    a = DeIdentify(data)

    verbose = False

    if verbose: print("=" * 77)
    entities = a.get_entities()
    if verbose: print(f"{entities=}")

    if verbose: print("=" * 77)
    pronouns = a.get_pronouns()
    if verbose: print(f"{pronouns=}")

    if verbose:
        print("-----")
        print(f"{len(entities)=}")
        print(f"{len(pronouns)=}")
        print()

    possible_misses = a.possible_misses()
    if verbose and len(possible_misses):
        print("=" * 77)
        safe_print(f"{possible_misses=}")

    a.save_metadata(create_json_filename(input_file))
    return len(entities), len(pronouns), len(possible_misses)


def start_deidentification(want_html: bool, input_file: str, replacement: str, output_file: str):
    print(f"starting deidentification...", file=sys.stderr)
    entities, pronouns, possible_misses = finder(input_file)
    print(f"deidentification results: {entities=}, {pronouns=}, {possible_misses=}", file=sys.stderr)

    replaced_text = replacer(want_html, replacement, input_file)
    if not len(output_file):
        safe_print(replaced_text)
    else:
        with open(output_file, encoding="latin1", mode="w") as fp:
            if want_html:
                fp.write(HTML_BEGIN)
                replaced_text = replaced_text.replace("\n", "<br />\n")
            fp.write(replaced_text)
            if want_html:
                fp.write(HTML_END)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="text file to deidentify")
    parser.add_argument("-r", "--replacement", help="a word/phrase to replace identified names with", required=True)
    parser.add_argument("-o", "--output_file", help="output file")
    parser.add_argument("-H", "--html", help="output in HTML format", action="store_true")
    args = parser.parse_args()

    output_file = args.output_file if args.output_file else ""
    start_deidentification(args.html, args.input_file, args.replacement, output_file)


if "__main__" == __name__:
    main()

# end of script
