import unittest
from harness_adapt.runner import build_protocol


class CLIProtocolTests(unittest.TestCase):
    def test_unexposed_parameters_are_never_claimed_as_controls(self):
        config = {'backend': 'codex_cli', 'model': 'fixed-alias', 'judge_model': 'fixed-alias',
                  'max_rounds': 8, 'fixed_time': '2026-10-27', 'codex_cli_expected_version': 'fixed-version',
                  'judge_runs': 1, 'benchmark_commit': 'source', 'temperature': None,
                  'seed': None, 'max_tokens': None}
        p = build_protocol(config, {'tasks_sha256': 'tasks'}, {'early': {'tools': []}})
        self.assertFalse(p['decoding']['sampling_parameters_controlled'])
        self.assertNotIn('temperature', p['decoding'])
        self.assertNotIn('seed', p['decoding'])
        self.assertNotIn('max_tokens', p['decoding'])
        self.assertEqual(p['decoding']['unsupported_parameters'], ['temperature', 'seed', 'max_tokens'])
        self.assertTrue(p['judge']['independent_ephemeral_session'])


if __name__ == '__main__':
    unittest.main()
