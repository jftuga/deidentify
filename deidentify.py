r"""
deidentify.py
-John Taylor
Mar-16-2021
Dec-14-2024 v1.1.0

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
4) sort the merged list in reverse order according to start position; (highest position first):
   ( { "type": "pronoun", "text": "he", "idx": 51 },
     { "type": "entity", "text": "John Smith", "start_char": 8 } )
5) iterate through the reverse-sorted merged list, replacing names and pronouns:
   John Smith -> EMPLOYEE; he -> HE/SHE

Commentary
==========
When doing text replacements, if you start from the beginning of the file and work forward,
each replacement would shift the positions of all subsequent text. This would invalidate all
the character position indices stored for later entities and pronouns.

Order matters when modifying text. By moving backwards through the file during replacements,
you can avoid having to recalculate position indices after each change. Each replacement only
affects text before it, not after it, so all the stored character positions remain valid for
subsequent replacements. Therefore, there is no need to recalculate positions after each
replacement.
"""

import argparse
import chardet
import json
import os.path
import sys
from operator import itemgetter

pgmName = "deidentify"
pgmUrl = "https://github.com/jftuga/deidentify"
pgmVersion = "1.1.0"

GENDER_PRONOUNS = {
    "he": "HE/SHE",
    "him": "HIM/HER",
    "his": "HIS/HER",
    "himself": "HIMSELF/HERSELF",
    "she": "HE/SHE",
    "her": "HIS/HER",
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


def safe_print(data, is_error: bool = False):
    """Safely prints data to stdout or stderr while handling encoding issues.

    Converts input data to string and processes it through an encode/decode cycle
    to handle any problematic characters that might cause encoding errors.
    Characters that cannot be encoded are ignored rather than raising an error.

    Args:
        data: Data to print. Will be converted to string using str().
        is_error (bool, optional): If True, prints to stderr instead of stdout.
            Defaults to False.

    Note:
        Uses the current stdout encoding for both encode and decode operations.
        Silently ignores characters that cannot be encoded rather than failing.
    """
    dest = sys.stdout if not is_error else sys.stderr
    # can also use 'replace' instead of 'ignore' for errors= parameter
    print(str(data).encode(sys.stdout.encoding, errors='ignore').decode(sys.stdout.encoding), file=dest)

class DeIdentify:
    """A text de-identification system for removing personal identifiers from text.

    This class processes text to identify and replace personal information including
    person names (entities) and gender-specific pronouns. It uses spaCy's transformer
    model for accurate natural language processing and maintains character-level
    position information throughout to ensure correct text replacement.

    Key Features:
        - Person name detection using spaCy NER (Named Entity Recognition)
        - Gender-specific pronoun identification
        - Position-aware merging of entities and pronouns
        - Detection of potentially missed compounds (possessives, hyphenated names)
        - Optional HTML output with styled replacements
        - Debug mode for detailed processing information
        - Metadata persistence (save/load) with ordered storage

    Example:
        >>> deid = DeIdentify("John and his brother Mike went to the store.")
        >>> deid.get_entities()  # Finds "John" and "Mike"
        >>> deid.get_pronouns()  # Finds "his"
        >>> deid.merge_metadata()  # Combines in correct order
        >>> anonymized = deid.replace_merged(want_html=False, replacement="[PERSON]")
        >>> print(anonymized)
        "PERSON and HIS/HER PERSON went to the store."

    Typical workflow:
        1. Initialize with text
        2. Extract entities using get_entities()
        3. Extract pronouns using get_pronouns()
        4. Optionally check for missed entities with possible_misses()
        5. Merge metadata to maintain order
        6. Replace with anonymized versions using replace_merged()
        7. Optionally save metadata for later use

    Dependencies:
        - spaCy with en_core_web_trf model
        - GENDER_PRONOUNS mapping for pronoun replacement
        - JSON for metadata persistence

    Note:
        - Requires messages longer than 7 characters
        - Uses utf-8 encoding for metadata files
        - Maintains reverse-sorted order of entities and pronouns by position
        - Debug mode available for detailed processing information
    """
    nlp = None  # nlp is of type spacy.lang

    def __init__(self, message: str, load: bool = True, debug: bool = False):
        """Initializes a DeIdentify instance for processing text.

        Creates a new instance for identifying and replacing personal information
        in text. Optionally loads the spaCy transformer model for English.

        Args:
            message (str): The text to be processed
            load (bool, optional): Whether to load the spaCy model. Defaults to True.
                Set to False if the model is already loaded or should be loaded later.

        Class Variables:
            nlp: spaCy language model (en_core_web_trf)

        Instance Variables:
            message (str): The input text to be processed
            entities (list): Stores identified named entities
                Each entity is a dict with text, start_char, and end_char
            pronouns (list): Stores identified pronouns
                Each pronoun is a dict with text and idx
            merged (list): Combined and ordered list of entities and pronouns
                Each item includes type information and original data
            missed (list): Potential entities missed by initial processing
                Each item is a dict with text and idx
            doc (spacy.Doc): spaCy Doc object for NLP processing
                Initialized lazily when needed
            debug (bool): Flag for enabling debug output
                Defaults to False

        Note:
            Uses spaCy's transformer model (en_core_web_trf) for superior
            accuracy in entity recognition and part-of-speech tagging.
        """
        if load:
            import spacy
            DeIdentify.nlp = spacy.load('en_core_web_trf')
        self.message = message
        self.entities = []
        self.pronouns = []
        self.merged = []
        self.missed = []
        self.doc = None
        self.debug = debug

    def get_entities(self):
        """Extracts person entities from the message text using spaCy NLP.

        Processes self.message to identify named entities of type "PERSON",
        storing their text and position information. Requires message text
        to be at least 8 characters long.

        Uses spaCy for NLP processing, creating self.doc if not already initialized.
        Each identified person entity is added to self.entities with position
        information.

        Returns:
            list: List of dictionaries containing person entities, where each
                dictionary has:
                - text (str): The entity text
                - start_char (int): Starting character position
                - end_char (int): Ending character position

        Note:
            - Modifies self.entities in place
            - Returns None if message is too short (<=7 characters)
            - Only extracts entities labeled as "PERSON"
        """
        if len(self.message) <= 7:
            return

        if not self.doc:
            self.doc = DeIdentify.nlp(self.message)

        if self.debug:
            for ent in self.doc.ents:
                print(f"=ENTITIES {ent.text=}, {ent.start_char=}, {ent.end_char=}, {ent.label_=}")
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
        """Extracts gender-specific pronouns from the message text using spaCy NLP.

        Processes self.message to identify pronouns and proper nouns that match
        the keys in GENDER_PRONOUNS. Uses spaCy for token identification and
        part-of-speech tagging.

        Each matching token is added to self.pronouns with its text and position
        information.

        Returns:
            list: List of dictionaries containing gender-specific pronouns, where
                each dictionary has:
                - text (str): The pronoun text
                - idx (int): Character position in the message

        Note:
            - Modifies self.pronouns in place
            - Only includes tokens that are:
                1. Tagged as PRON (pronoun) or PROPN (proper noun)
                2. Have lowercase form in GENDER_PRONOUNS keys
        """
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
        """Saves the current metadata state to a JSON file.

        Writes the message text and sorted lists of entities, pronouns, and possible
        missed items to a formatted JSON file. All lists are sorted in reverse order
        (highest to lowest position index) before saving.

        Args:
            fname (str): Path where the JSON file should be written

        Note:
            - File is written using utf-8 encoding
            - JSON is pretty-printed with 4-space indentation
            - Non-ASCII characters are preserved in output
            - Data is sorted before saving:
                - entities by start_char
                - pronouns by idx
                - possible misses by idx
            - Output JSON structure:
                {
                    "message": str,
                    "entities": list,
                    "pronouns": list,
                    "possible_misses": list
                }
        """
        with open(fname, encoding="utf-8", mode="w") as fp:
            # self.entities and self.pronouns must be sorted by start_char/idx in reverse order (highest to lowest)
            sorted_entities = sorted(self.entities, key=itemgetter("start_char"), reverse=True)
            sorted_pronouns = sorted(self.pronouns, key=itemgetter("idx"), reverse=True)
            sorted_missed = sorted(self.missed, key=itemgetter("idx"), reverse=True)
            json.dump({"message": self.message, "entities": sorted_entities, "pronouns": sorted_pronouns,
                       "possible_misses": sorted_missed}, fp, skipkeys=False, ensure_ascii=False, indent=4)

    def replace_merged(self, want_html: bool, replacement: str) -> str:
        """Replaces pronouns and entities in the message text with alternative text.

        Processes all items in self.merged to perform two types of replacements:
        1. Pronouns are replaced with gender-neutral alternatives from GENDER_PRONOUNS
        2. Entities are replaced with the provided replacement string

        Replacements can optionally be wrapped in HTML span tags with specific IDs:
        - Pronouns: <span id="span1">replacement</span>
        - Entities: <span id="span2">replacement</span>

        Args:
            want_html (bool): If True, wrap replacements in HTML span tags
            replacement (str): String to replace entities with

        Returns:
            str: The modified message text with all replacements applied

        Raises:
            SystemExit: If an unknown object type is encountered in self.merged
                (Error #74023)

        Note:
            Modifies self.message in place and returns the same modified string.
            Uses positional indices from the original items:
            - Pronouns: idx and text length
            - Entities: start_char and end_char
        """
        position = 0
        for obj in self.merged:
            text = obj["item"]["text"]
            if obj["type"] == "pronoun":
                position = obj["item"]["idx"]
            elif obj["type"] == "entity":
                position = obj["item"]["start_char"]
            if self.debug:
                print(f"xx: {obj['type']}, {position}, {text}")
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
        """Merges entity and pronoun metadata into a single ordered sequence.

        Processes entity and pronoun information stored in self.entities and self.pronouns,
        combining them into a single ordered sequence in self.merged based on their positions
        in the text. Each merged item contains type information ("entity" or "pronoun") and
        maintains the original metadata.

        The method handles five cases:
        1. No entities and no pronouns: Returns without modification
        2. Only entities: Adds all entities in order
        3. Only pronouns: Adds all pronouns in order
        4. More pronouns than entities: Merges based on position, handling remaining items
        5. More entities than pronouns: Merges based on position, handling remaining items

        For cases 4 and 5, items are ordered by comparing pronoun 'idx' values with entity
        'start_char' values to maintain the original text sequence.

        The method modifies self.merged in place, adding dictionaries with keys:
        - type: String indicating "entity" or "pronoun"
        - index: Integer index of the item within its type
        - item: Original entity or pronoun dictionary
        """
        if self.debug:
            for ent in self.entities:
                print(ent)
            print("=" * 77)

        p = 0  # pronouns
        e = 0  # entities

        # case 1: there are no entities and no pronouns
        if len(self.entities) == 0 and len(self.pronouns) == 0:
            return

        # case 2: there are entities, but no pronouns
        if len(self.entities) >0 and len(self.pronouns) == 0:
            while e < len(self.entities):
                keyval = {"type": "entity", "index": e, "item": self.entities[e]}
                e += 1
                self.merged.append(keyval)
            return

        # case 3: there are pronouns but no entities
        if len(self.pronouns) > 0 and len(self.entities) == 0:
            while p < len(self.pronouns):
                keyval = {"type": "pronoun", "index": p, "item": self.pronouns[p]}
                p += 1
                self.merged.append(keyval)

        # case 4: there are more pronouns than entities
        if len(self.pronouns) >= len(self.entities):
            while p < len(self.pronouns):
                if e == len(self.entities):
                    break
                if e == len(self.entities):
                    keyval = {"type": "pronoun", "index": p, "item": self.pronouns[p]}
                    p += 1
                    self.merged.append(keyval)
                    break
                idx = self.pronouns[p]["idx"]
                start_char = self.entities[e]["start_char"]
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
        else:  # case 5: there are more entities than pronouns
            while e < len(self.entities):
                if p == len(self.pronouns):
                    break
                if p == len(self.pronouns):
                    keyval = {"type": "entity", "index": e, "item": self.entities[e]}
                    e += 1
                    self.merged.append(keyval)
                    break
                idx = self.pronouns[p]["idx"]
                start_char = self.entities[e]["start_char"]
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

        if self.debug:
            import pprint
            print("xxx merged")
            pprint.pprint(self.merged)
            print("=" * 77)
            print(self.message)

    def possible_misses(self) -> list:
        """Identifies potentially missed compound tokens in the document.

        Analyzes the document tokens sequentially to identify two types of potential
        missed compounds:
        1. Possessive constructions where "'s" appears as a verb
        2. Hyphenated proper nouns where a proper noun follows a hyphen

        Uses spaCy token attributes (text, pos_, tag_, idx) to identify these cases.
        Each identified case is added to self.missed with the combined text and
        position information.

        Returns:
            list: A list of dictionaries containing missed compounds, where each
                dictionary has:
                - text (str): The combined text of the compound (previous + current token)
                - idx (int): The character index of the start of the compound
        """
        previous = None
        previous_idx = 0
        previous_tag = ""
        for token in self.doc:
            if token.text == "'s" and token.pos_ == 'VERB':
                self.missed.append({"text": "%s%s" % (previous, token.text), "idx": previous_idx})
            if token.pos_ == "PROPN" and token.tag_ == "NNP" and previous_tag == "HYPH":
                self.missed.append({"text": "%s%s" % (previous, token.text), "idx": previous_idx})
            previous = token.text
            previous_idx = token.idx
            previous_tag = token.tag_

        return self.missed

    def load_metadata(self, fname: str):
        """Loads and processes metadata from a JSON file.

        Opens the specified JSON file and loads entity, pronoun, and message data.
        Entities and pronouns are sorted in reverse order by their position indices.
        Data is stored in instance variables.

        Args:
            fname (str): Path to the JSON file containing metadata.
                File must contain a JSON object with keys:
                - "entities": List of dictionaries with "start_char" field
                - "pronouns": List of dictionaries with "idx" field
                - "message": String containing the message text

        Note:
            File is read using utf-8 encoding.
            Entities are sorted by "start_char" in reverse order.
            Pronouns are sorted by "idx" in reverse order.
        """
        with open(fname, encoding="utf-8") as fp:
            a = json.load(fp)
            self.entities = sorted(a["entities"], key=itemgetter("start_char"), reverse=True)
            self.pronouns = sorted(a["pronouns"], key=itemgetter("idx"), reverse=True)
            self.message = a["message"]

#############################################################################################################

def create_json_filename(input_file: str) -> str:
    """Creates the metadata JSON filename for a given input file.

    Takes an input filename and creates a corresponding metadata filename
    by replacing the original extension with "--tokens.json".

    Args:
        input_file (str): Original input file path

    Returns:
        str: Path for the metadata JSON file.
            Example: "text.txt" -> "text--tokens.json"

    Note:
        Preserves the original file path, only modifies the extension.
    """
    filename, _ = os.path.splitext(input_file)
    return filename + "--tokens.json"

def replacer(want_html: bool, replacement: str, input_file: str) -> str:
    """Performs de-identification replacement on pre-processed text using stored metadata.

    A utility function that loads previously processed metadata for a text file
    and performs entity/pronoun replacement. Creates a DeIdentify instance without
    loading the spaCy model since the text has already been processed.

    Args:
        want_html (bool): If True, wrap replacements in HTML span tags
        replacement (str): Text to use when replacing identified entities
        input_file (str): Path to the original input file (metadata file path will be derived)

    Returns:
        str: The processed text with entities and pronouns replaced

    Note:
        Expects metadata file to exist (created by previous processing).
        Does not load spaCy model since metadata contains necessary information.
        Uses create_json_filename() to determine metadata file location.
    """
    a = DeIdentify("", load=False)
    a.load_metadata(create_json_filename(input_file))
    a.merge_metadata()
    return a.replace_merged(want_html, replacement)

def normalize_punctuation(text: str) -> str:
    """Normalizes Unicode variants of common punctuation marks to their ASCII equivalents.

    Converts various Unicode punctuation marks to their basic ASCII counterparts:
    - Converts typographic apostrophes (U+2019, U+2018, etc.) to ASCII apostrophe (U+0027)
    - Converts en dashes, em dashes, and other hyphens to ASCII hyphen-minus (U+002D)
    - Converts curly quotes to straight quotes (U+0022)
    - Converts ellipsis character to three periods
    - Converts various spaces to regular space
    - Converts bullet points to asterisk
    - Preserves but normalizes common symbols (©, ®, ™)

    Args:
        text: Input string containing possibly non-ASCII punctuation marks.

    Returns:
        A new string with all Unicode punctuation variants replaced with ASCII equivalents.

    Examples:
        >>> text = "Here's a fancy—text with "quotes" and bullets•"
        >>> normalize_punctuation(text)
        "Here's a fancy-text with \"quotes\" and bullets*"
    """
    # Dictionary mapping unicode variants to ASCII versions
    replacements = {
        # Apostrophe variants -> ASCII apostrophe (U+0027)
        chr(0x2019): "'",  # RIGHT SINGLE QUOTATION MARK
        chr(0x2018): "'",  # LEFT SINGLE QUOTATION MARK
        chr(0x02BC): "'",  # MODIFIER LETTER APOSTROPHE
        chr(0x02B9): "'",  # MODIFIER LETTER PRIME
        chr(0x0060): "'",  # GRAVE ACCENT
        chr(0x00B4): "'",  # ACUTE ACCENT

        # Hyphen variants -> ASCII hyphen-minus (U+002D)
        chr(0x2010): "-",  # HYPHEN
        chr(0x2011): "-",  # NON-BREAKING HYPHEN
        chr(0x2012): "-",  # FIGURE DASH
        chr(0x2013): "-",  # EN DASH
        chr(0x2014): "-",  # EM DASH
        chr(0x2015): "-",  # HORIZONTAL BAR
        chr(0x00AD): "-",  # SOFT HYPHEN
        chr(0x2212): "-",  # MINUS SIGN

        # Double quote variants -> ASCII double quote (U+0022)
        chr(0x201C): '"',  # LEFT DOUBLE QUOTATION MARK
        chr(0x201D): '"',  # RIGHT DOUBLE QUOTATION MARK
        chr(0x201F): '"',  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK

        # Ellipsis -> three periods
        chr(0x2026): '...',  # HORIZONTAL ELLIPSIS

        # Space variants -> ASCII space
        chr(0x00A0): ' ',  # NO-BREAK SPACE
        chr(0x202F): ' ',  # NARROW NO-BREAK SPACE
        chr(0x2009): ' ',  # THIN SPACE
        chr(0x2007): ' ',  # FIGURE SPACE

        # Bullet variants -> asterisk
        chr(0x2022): '*',  # BULLET
        chr(0x2023): '*',  # TRIANGULAR BULLET
        chr(0x25E6): '*',  # WHITE BULLET
        chr(0x2043): '*',  # HYPHEN BULLET
        chr(0x00B7): '*',  # MIDDLE DOT
        chr(0x2219): '*',  # BULLET OPERATOR

        # Normalize common symbols
        chr(0x00A9): '(c)',  # COPYRIGHT SIGN
        chr(0x00AE): '(r)',  # REGISTERED SIGN
        chr(0x2122): '(tm)'  # TRADEMARK SIGN
    }

    # Replace each variant with its ASCII equivalent
    normalized_text = text
    for unicode_char, ascii_char in replacements.items():
        normalized_text = normalized_text.replace(unicode_char, ascii_char)

    return normalized_text

def read_file_with_detection(filename: str) -> tuple[str, str]:
    """Detects file encoding and reads its contents in a single file read operation.

    Opens the file once in binary mode, uses the bytes for encoding detection,
    then decodes those same bytes using the detected encoding.

    Uses the chardet library to analyze the raw bytes of a file and determine its
    most likely character encoding (e.g., 'utf-8', 'ascii', 'windows-1252', etc.).

    Args:
        filename: Path to the file to read.

    Returns:
        A tuple containing (file_contents: str, detected_encoding: str).
        The file_contents will be decoded using the detected encoding.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        IOError: If there are issues reading the file.
        UnicodeDecodeError: If the content cannot be decoded with the detected encoding.

    Examples:
        >>> contents, encoding = read_file_with_detection('myfile.txt')
        >>> print(f"File was in {encoding} encoding and contains: {contents[:50]}")
    """
    with open(filename, 'rb') as file:
        raw_bytes = file.read()

    detected_encoding = chardet.detect(raw_bytes)['encoding']
    file_contents = raw_bytes.decode(detected_encoding)

    return file_contents, detected_encoding

def finder(input_file: str) -> tuple:
    """Processes a text file to identify entities, pronouns, and potential misses.

    Reads the input file and performs full natural language processing to identify
    person names (entities), gender-specific pronouns, and potentially missed
    compounds. Saves the processing results as metadata for later use in
    de-identification.

    Args:
        input_file (str): Path to the text file to process.

    Returns:
        tuple: Contains three integers:
            - Number of entities (person names) found
            - Number of gender-specific pronouns found
            - Number of potentially missed compounds

    Note:
        - Creates and saves metadata file using create_json_filename()
        - Initializes spaCy NLP pipeline for processing
        - Intelligently determine file encoding via 'chardet' module
        - Contains disabled verbose debug output options
        - Uses safe_print for debug output to handle encoding issues
    """

    data, _ = read_file_with_detection(input_file)
    data = normalize_punctuation(data)

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
    """Performs complete de-identification process on a text file.

    Main entry point for the de-identification workflow. Processes the input file
    to identify personal information, then replaces identified items with anonymous
    text. Can output as plain text or HTML, either to stdout or to a file.

    Args:
        want_html (bool): If True, format output as HTML with styling
        input_file (str): Path to the text file to de-identify
        replacement (str): Text to use when replacing identified entities
        output_file (str): Path for output file. If empty, prints to stdout

    Note:
        - Reports progress to stderr
        - Processes file in two steps: identification then replacement
        - Uses utf-8 encoding for file operations
        - In HTML mode:
            - Adds HTML_BEGIN and HTML_END wrappers
            - Converts newlines to <br /> tags
        - Uses safe_print for stdout to handle encoding issues
    """
    print(f"starting deidentification...", file=sys.stderr)
    entities, pronouns, possible_misses = finder(input_file)
    print(f"deidentification results: {entities=}, {pronouns=}, {possible_misses=}", file=sys.stderr)

    replaced_text = replacer(want_html, replacement, input_file)
    if not len(output_file):
        safe_print(replaced_text)
    else:
        with open(output_file, encoding="utf-8", mode="w") as fp:
            if want_html:
                fp.write(HTML_BEGIN)
                replaced_text = replaced_text.replace("\n", "<br />\n")
            fp.write(replaced_text)
            if want_html:
                fp.write(HTML_END)

def main():
    """Command-line entry point for text de-identification tool.

    Parses command line arguments and initiates the de-identification process.

    Command-line arguments:
        input_file: Text file to process (required, positional)
        -r, --replacement: Text to replace identified names with (required)
        -o, --output_file: Output file path (optional)
        -H, --html: Enable HTML output format (optional flag)
        -v, --version: Display version information and exit

    Example usage:
        program.py input.txt -r "PERSON" -o output.txt
        program.py input.txt -r "PERSON" -H -o output.html

    Note:
        If no output file is specified, writes to stdout.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="text file to deidentify")
    parser.add_argument("-r", "--replacement", help="a word/phrase to replace identified names with", required=True)
    parser.add_argument("-o", "--output_file", help="output file")
    parser.add_argument("-H", "--html", help="output in HTML format", action="store_true")
    parser.add_argument("-v", "--version", help="display program version and then exit", action="version", version=f"{pgmName}, v{pgmVersion},  {pgmUrl}")
    args = parser.parse_args()

    output_file = args.output_file if args.output_file else ""
    start_deidentification(args.html, args.input_file, args.replacement, output_file)


if "__main__" == __name__:
    main()

# end of script
