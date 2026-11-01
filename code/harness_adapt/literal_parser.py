"""Read a deliberately restricted JavaScript data literal without executing code.

Only JSON-like objects, arrays, quoted strings, finite numbers, true/false/null
and unquoted property names are accepted. Functions, variables, interpolation,
spreads and computed property names are rejected. This is for static audit of
published mutation hunks, never for execution of downloaded server code.
"""
import json
import math
import re


class LiteralError(ValueError):
    pass


def decode_js_string(token):
    """Conservatively decode JS string escapes, never Python-only escapes."""
    body, result, i = token[1:-1], [], 0
    simple = {'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t',
              'v': '\v', "'": "'", '"': '"', '/': '/', '\\': '\\'}
    while i < len(body):
        char = body[i]
        if char in '\r\n':
            raise LiteralError('Literal line break in string')
        if char != '\\':
            result.append(char)
            i += 1
            continue
        i += 1
        if i == len(body):
            raise LiteralError('Incomplete escape')
        key = body[i]
        if key in simple:
            result.append(simple[key])
            i += 1
        elif key in ('u', 'x'):
            count = 4 if key == 'u' else 2
            chars = body[i + 1:i + 1 + count]
            if len(chars) != count or not re.fullmatch('[0-9a-fA-F]+', chars):
                raise LiteralError('Unsupported hexadecimal escape')
            point = int(chars, 16)
            i += count + 1
            if key == 'u' and 0xD800 <= point <= 0xDBFF and body[i:i + 2] == '\\u':
                low = body[i + 2:i + 6]
                if len(low) == 4 and re.fullmatch('[0-9a-fA-F]+', low) and 0xDC00 <= int(low, 16) <= 0xDFFF:
                    point = 0x10000 + ((point - 0xD800) << 10) + int(low, 16) - 0xDC00
                    i += 6
            if 0xD800 <= point <= 0xDFFF:
                raise LiteralError('Unpaired unicode surrogate')
            result.append(chr(point))
        elif key == '0' and (i + 1 == len(body) or not body[i + 1].isdigit()):
            result.append('\0')
            i += 1
        else:
            raise LiteralError('Unsupported JS escape %r' % key)
    return ''.join(result)


class Parser:
    def __init__(self, text):
        self.text, self.i = text, 0

    def skip(self):
        while self.i < len(self.text):
            if self.text[self.i].isspace():
                self.i += 1
            elif self.text.startswith('//', self.i):
                j = self.text.find('\n', self.i + 2)
                self.i = len(self.text) if j < 0 else j + 1
            elif self.text.startswith('/*', self.i):
                j = self.text.find('*/', self.i + 2)
                if j < 0:
                    raise LiteralError('Unterminated comment')
                self.i = j + 2
            else:
                break

    def char(self, expected):
        self.skip()
        if not self.text.startswith(expected, self.i):
            raise LiteralError('Expected %r at %d' % (expected, self.i))
        self.i += len(expected)

    def string(self):
        self.skip()
        start = self.i
        quote = self.text[self.i]
        self.i += 1
        while self.i < len(self.text):
            c = self.text[self.i]
            if c == '\\':
                self.i += 2
            elif c == quote:
                self.i += 1
                token = self.text[start:self.i]
                value = decode_js_string(token)
                if not isinstance(value, str):
                    raise LiteralError('String required')
                return value
            else:
                self.i += 1
        raise LiteralError('Unterminated string')

    def identifier(self):
        self.skip()
        m = re.match(r'[A-Za-z_$][A-Za-z0-9_$]*', self.text[self.i:])
        if not m:
            raise LiteralError('Identifier required')
        self.i += len(m.group())
        return m.group()

    def value(self):
        self.skip()
        if self.i >= len(self.text):
            raise LiteralError('Unexpected end')
        c = self.text[self.i]
        if c in ('"', "'"):
            return self.string()
        if c == '{':
            self.i += 1
            result = {}
            self.skip()
            while self.i < len(self.text) and self.text[self.i] != '}':
                key = self.string() if self.text[self.i] in ('"', "'") else self.identifier()
                if key in result:
                    raise LiteralError('Duplicate object key')
                self.char(':')
                result[key] = self.value()
                self.skip()
                if self.text[self.i:self.i + 1] != ',':
                    break
                self.i += 1
                self.skip()
            self.char('}')
            return result
        if c == '[':
            self.i += 1
            result = []
            self.skip()
            while self.i < len(self.text) and self.text[self.i] != ']':
                result.append(self.value())
                self.skip()
                if self.text[self.i:self.i + 1] != ',':
                    break
                self.i += 1
                self.skip()
            self.char(']')
            return result
        m = re.match(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?', self.text[self.i:])
        if m:
            self.i += len(m.group())
            v = json.loads(m.group())
            if isinstance(v, float) and not math.isfinite(v):
                raise LiteralError('Finite number required')
            return v
        key = self.identifier()
        if key not in ('true', 'false', 'null'):
            raise LiteralError('Executable or unsupported value %r' % key)
        return {'true': True, 'false': False, 'null': None}[key]


def parse_data_literal(text):
    parser = Parser(text.strip().rstrip(',').strip())
    value = parser.value()
    parser.skip()
    if parser.i != len(parser.text):
        raise LiteralError('Trailing executable or unsupported text')
    return value
