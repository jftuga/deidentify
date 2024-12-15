# Text De-identification Tool

## INTRODUCTION

This command-line tool automatically identifies and replaces personal
information in text documents using Natural Language Processing (NLP)
techniques. It focuses on finding and replacing person names and
gender-specific pronouns while maintaining the text's readability and
structure.

[Natural Language Processing](https://en.wikipedia.org/wiki/Natural_language_processing)
is a field of artificial intelligence that enables computers to
understand, interpret, and manipulate human language. This tool
specifically uses
[Named Entity Recognition](https://en.wikipedia.org/wiki/Named-entity_recognition)
(NER), an NLP technique that locates and classifies named entities
(like person names, organizations, locations) in text. NER helps identify
person names even in complex contexts, making it more reliable than simple
word matching.

Key Features:
- Automatic detection of person names using
  [spaCy's transformer model](https://spacy.io/universe/project/spacy-transformers)
- Gender-specific pronoun replacement with neutral alternatives
- Intelligent encoding detection and Unicode handling
- Optional HTML output with color-coded replacements
- Detection of potentially missed names *(possessives, hyphenated names)*
- Efficient metadata caching for quick reprocessing

## INSTALLATION

1. Clone the repository:
```shell
git clone https://github.com/jftuga/deidentify.git
cd deidentify
```

2. Create and activate a Python virtual environment:
```shell
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```shell
pip install -r requirements.txt
```
**Note:** *As of 2024-12-15, spaCy is not yet supported on macOS with Python 3.13.*

4. Download the spaCy model:
```shell
python -m spacy download en_core_web_trf
```
**Note:** The transformer model is large (~500MB) but provides superior accuracy.

## USAGE

Basic usage with output to STDOUT:
```shell
python deidentify.py input.txt -r "PERSON"
```

Generate color-coded HTML output:
```shell
python deidentify.py input.txt -r "[REDACTED]" -H -o output.html
```

Command line options:
```shell
usage: deidentify.py [-h] -r REPLACEMENT [-o OUTPUT_FILE] [-H] [-v] input_file

positional arguments:
  input_file            text file to deidentify

options:
  -h, --help            show this help message and exit
  -r REPLACEMENT, --replacement REPLACEMENT
                        a word/phrase to replace identified names with
  -o OUTPUT_FILE, --output_file OUTPUT_FILE
                        output file
  -H, --html            output in HTML format
  -v, --version         display program version and then exit
```

### HTML Output Colors:
* Yellow: Gender-specific pronouns replaced with neutral alternatives
* Turquoise: Person names replaced with specified text, given by the `-r` switch

### Possible Misses

These are listed as `possible_misses` in an intermediate JSON file named
`input--tokens.json` when using `input.txt` as the input file name.

### Example

Input:
```
John Smith's report was excellent. He clearly understands the topic.
```

Output:
```
PERSON's report was excellent. HE/SHE clearly understand the topic.
```

## TECHNICAL DETAILS

The tool processes text in two stages:

1. Identification Stage: Uses spaCy's transformer model to identify:
* * Person names through Named Entity Recognition
* * Gender-specific pronouns through part-of-speech tagging

2. Replacement Stage: Replaces identified items while maintaining text integrity:
* * Processes text from end to beginning to preserve character positions
* * Handles gender-specific pronouns with neutral alternatives
* * Supports optional  HTML output with color-coded replacements
* * Handles various Unicode punctuation variants

### Text Processing Features:

* Intelligent encoding detection using the `chardet` third-party Python module
* Unicode punctuation normalization
* Safe handling of mixed encodings
* Metadata caching for efficient reprocessing

### spaCy NER model

The `en_core_web_trf` (Transformer-based) model is used because:
* Highest accuracy for most NLP tasks, especially for named entity recognition
  and dependency parsing
* Best performance on complex or ambiguous sentences
* Most robust handling of modern language and edge cases

However, be aware of these shortcomings vs
[other spaCy models](https://spacy.io/models/en):
* Much slower than statistical models
* Higher memory requirements (~200MB+)
* Not suitable for real-time processing of large volumes of text
* Requires GPU for optimal performance, but is still performant with CPU-only

## ACKNOWLEDGEMENTS

This tool relies on several excellent open-source projects:

* [spaCy](https://github.com/explosion/spaCy) - Industrial-strength Natural Language Processing
* [chardet](https://github.com/chardet/chardet) - Universal character encoding detector

## LICENSE

[MIT LICENSE](https://github.com/jftuga/deidentify/blob/main/LICENSE)
