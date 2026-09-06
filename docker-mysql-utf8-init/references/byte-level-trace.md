# Byte-level trace of double/triple encoding

This is the exact byte-by-byte trace that surfaced during the bug. The
intuition is: latin1 re-encodes each byte as a char, but bytes above 0x7F
either map to control chars (which can't be re-encoded normally) or get
expanded to multi-byte sequences, producing inconsistent double/triple
encoding across the string.

## Starting point

The Chinese word `系统管理` (4 characters, 12 bytes in UTF-8):

| Char | Code point | UTF-8 bytes |
|---|---|---|
| 系 | U+7CFB | E7 B3 BB |
| 统 | U+7EDF | E7 BB 9F |
| 管 | U+7BA1 | E7 AE A1 |
| 理 | U+7406 | E7 90 86 |

Concatenated: `E7 B3 BB E7 BB 9F E7 AE A1 E7 90 86`

## Double encoding (what should happen with latin1 → utf-8)

Treating the 12 bytes as 12 latin1 characters, then UTF-8 encoding each:

- `E7` → latin1 char `ç` (U+00E7) → UTF-8: `C3 A7`
- `B3` → latin1 char `³` (U+00B3) → UTF-8: `C2 B3`
- `BB` → latin1 char `»` (U+00BB) → UTF-8: `C2 BB`
- `E7` → `ç` → `C3 A7`
- `BB` → `»` → `C2 BB`
- `9F` → latin1 control char (0x9F, undefined) → escape path
- ...

The escape path for 0x9F is what creates the inconsistency. The MySQL
client library sees `9F` in a latin1 string, decides it cannot round-trip
through latin1, and re-encodes the surrounding context.

## Actual stored bytes (from the bug)

```
c3a7 c2b3 c2bb c3a7 c2bb c5b8 c3a7 c2ae c2a1 c3a7 c290 e280a0
```

Mapping back through `0x9F` position:

- `c3a7` `c2b3` `c2bb` ← double-encoded `E7 B3 BB` (`系`)
- `c3a7` `c2bb` `c5b8` ← mixed encoding for `E7 BB 9F` (`统`)
  - `E7` → `c3 a7` (double-encoded)
  - `BB` → `c2 bb` (double-encoded)
  - `9F` → `c5 b8` (TRIPLE-encoded: the 0x9F was treated as U+0178 = `Ÿ`,
    then UTF-8 encoded, doubling the encoding depth for that one byte)

So `9F` got triple-encoded while its neighbors got double-encoded. This
is exactly why the simple `CONVERT USING utf8` recovery does not work:
different bytes in the same string have been encoded different numbers
of times, so a single decode step will only fix some of them.

## Why latin1 cannot round-trip arbitrary bytes

latin1 (ISO-8859-1) maps bytes 0x00–0x9F to C0 control characters
(C0–C9F in Unicode). These are valid Unicode characters but they're
control codes with no glyph representation. MySQL's connection layer
handles them by escaping into a wider Unicode range:

- `0x80` → U+0080 (Padding Character)
- `0x81` → U+0081 (High Octet Preset)
- ...
- `0x9F` → U+0178 (LATIN CAPITAL LETTER Y WITH DIAERESIS, `Ÿ`)
- `0xA0`–`0xFF` → matching Latin-1 Supplement code points

The first 32 code points (0x00–0x1F) and the 0x7F (DEL) are C0 controls,
not Latin-1 Supplement, so they would in theory round-trip via
latin1. But 0x80–0x9F are NOT Latin-1 Supplement, even though they look
like they should be — the Latin-1 Supplement block in Unicode starts at
U+00A0, so 0x80–0x9F in raw latin1 bytes cannot be faithfully encoded
as Unicode without using the C1 controls.

The MySQL connection driver treats those C1 bytes as if they were meant
to be Latin-1, lifts them up to the Latin-1 Supplement range in Unicode
(`0x9F` → U+0178 → UTF-8: `C5 B8`), and the result is a one-byte
expansion that looks like an extra UTF-8 encode.

## Diagnostic shortcut

Any column whose first byte is `0xC3` or `0xC2` is double-encoded. Any
column whose first byte is `0xE7`, `0xE6`, `0xE5`, `0xE4`, or any byte
≥ 0xC0 with the second byte ≥ 0x80 is correct UTF-8 (i.e., ASCII range
first bytes never start real UTF-8 multibyte sequences).

```sql
SELECT HEX(SUBSTRING(col, 1, 1)) FROM tbl LIMIT 1;
-- C3 or C2 → double-encoded, suspicious
-- C5 → also suspicious (triple-encoded `Ÿ` residue)
-- E7 / E6 / F0 / etc. → correct UTF-8
```

For a quick count:

```sql
SELECT COUNT(*) FROM tbl WHERE HEX(SUBSTRING(col, 1, 1)) IN ('C3', 'C2');
-- non-zero → double-encoded rows exist
```