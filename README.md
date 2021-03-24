# deidentify
Deidentify people's names along with pronoun substitution

## Synopsis

This program is used to substitute a person's given name and/or surname along with any gender specific pronouns.

## Example

```
Input:
I think John Smith likes programming. You can tell he enjoys using Python.

Output:
I think PERSON likes programming. You can tell HE/SHE enjoys using Python.
```

## Configuration

* This program relies on [Spacy](https://spacy.io/) for [Named-entitiy recognition](https://en.wikipedia.org/wiki/Named-entity_recognition) and [pronoun](https://en.wikipedia.org/wiki/Pronoun) substitution.
* For best results, you can set up a [Python Virtual Environment](https://docs.python.org/3/library/venv.html) and install `Spacy` with these settings:
* ![Spacy Settings](spacy_settings.png)
* `Spacy` can be installed with [other Spacy configuration options](https://spacy.io/usage).
* Once you have activated your [Python Virtual Environment](https://docs.python.org/3/library/venv.html), you can then install `Spacy`:

```shell
python -m pip install --upgrade pip
pip install setuptools wheel
pip install spacy
python -m spacy download en_core_web_trf
```

## Usage
```
usage: deidentify.py [-h] -r REPLACEMENT [-o OUTPUT_FILE] [-H] input_file

positional arguments:
  input_file            text file to deidentify

optional arguments:
  -h, --help            show this help message and exit
  -r REPLACEMENT, --replacement REPLACEMENT
                        a word/phrase to replace identified names with
  -o OUTPUT_FILE, --output_file OUTPUT_FILE
                        output file
  -H, --html            output in HTML format
```

## Operation

```shell
-- Windows 

cd deidentify
scripts\activate
python deidentify.py -r PERSON -o output.txt input.txt
diff input.txt output.txt

-- Linux

cd deidentify
source bin/activate
python deidentify.py -r PERSON -o output.txt input.txt
diff input.txt output.txt

-- HTML Output

python deidentify.py -H -r PERSON -o output.htm input.txt
```
