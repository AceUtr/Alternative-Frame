# Retry Demo Word Counter

`word_counter.py` counts logical lines, whitespace-delimited words, and Unicode
characters in a UTF-8 text file. Its successful CLI output is a single valid
JSON object written to standard output.

## Usage

```bash
python retry_demo/word_counter.py retry_demo/sample.txt
```

## Tests

```bash
python -m unittest discover -s retry_demo -p "test_*.py" -v
```

`count_text(text)` returns a dictionary with integer `lines`, `words`, and
`characters` values. Words use `text.split()` semantics, and an empty string
returns zero for every count.
