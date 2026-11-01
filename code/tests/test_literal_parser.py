import unittest
from harness_adapt.literal_parser import LiteralError, parse_data_literal


class LiteralParserTests(unittest.TestCase):
    def test_js_data_and_comments(self):
        self.assertEqual(parse_data_literal("{name:'x', inputSchema:{type:'object', // note\n required:['x',],}, ok:true, n:null,},"),
                         {'name': 'x', 'inputSchema': {'type': 'object', 'required': ['x']},
                          'ok': True, 'n': None})

    def test_reject_executable_values(self):
        for text in ["{x:process.exit()}", "{x:()=>1}", "{x:`${secret}`} ",
                     "{...obj}", "{[key]:1}", "{x:1};danger()", "{x:1,x:2}"]:
            with self.subTest(text=text), self.assertRaises(LiteralError):
                parse_data_literal(text)

    def test_urls_and_escapes(self):
        self.assertEqual(parse_data_literal("{x:'https://example.test/a', y:\"quoted\\\"word\"}"),
                         {'x': 'https://example.test/a', 'y': 'quoted"word'})

    def test_reject_nonfinite_and_incomplete(self):
        for text in ["{x:1e999}", "{x:[1,2}", "{x:'oops}"]:
            with self.subTest(text=text), self.assertRaises(LiteralError):
                parse_data_literal(text)

    def test_reject_python_only_and_identity_escapes(self):
        for text in [r"{x:'\a'}", r"{x:'\N{LATIN CAPITAL LETTER A}'}", r"{x:'\U00000041'}", r"{x:'\123'}"]:
            with self.subTest(text=text), self.assertRaises(LiteralError):
                parse_data_literal(text)

    def test_js_unicode_and_hex_escapes(self):
        self.assertEqual(parse_data_literal(r"{x:'\u0041\x42\uD83D\uDE00'}"), {'x': 'AB😀'})


if __name__ == '__main__':
    unittest.main()
