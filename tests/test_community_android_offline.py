"""Host-only offline policy tests; do not certify Android engine startup."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class OfflinePolicyTest(unittest.TestCase):
    def setUp(self):
        self.queue = []
        self.completions = 0
        babase = types.ModuleType('babase')
        babase.pushcall = self.queue.append
        class Config(dict):
            def commit(self):
                pass
        self.config = Config()
        babase.app = types.SimpleNamespace(on_initial_sign_in_complete=self.complete, config=self.config)
        modules = {'babase': babase, '_baplus': types.ModuleType('_baplus')}
        for name, symbol in [('baplus._appsubsystem', 'PlusAppSubsystem'),
                             ('baplus._cloud', 'CloudSubsystem'), ('baplus._ads', 'AdsSubsystem')]:
            module = types.ModuleType(name)
            setattr(module, symbol, type(symbol, (), {}))
            modules[name] = module
        errors = types.ModuleType('efro.error')
        errors.CommunicationError = type('CommunicationError', (Exception,), {})
        calls = types.ModuleType('efro.call')
        calls.CallbackSet = list
        modules.update({'efro.error': errors, 'efro.call': calls})
        self.patcher = patch.dict(sys.modules, modules)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        spec = importlib.util.spec_from_file_location('community_test_module',
            ROOT / 'src/assets/ba_data/python/baplus/_community.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def complete(self):
        self.completions += 1

    def drain(self):
        while self.queue:
            self.queue.pop(0)()

    def test_initial_sign_in_completes_exactly_once_asynchronously(self):
        plus = self.module.CommunityPlusAppSubsystem()
        plus.on_app_loading()
        plus.on_app_loading()
        self.assertEqual(self.completions, 0)
        self.drain()
        self.assertEqual(self.completions, 1)

    def test_offline_state_does_not_fabricate_credentials(self):
        plus = self.module.CommunityPlusAppSubsystem()
        self.assertEqual(plus.get_v1_account_state(), 'signed_out')
        self.assertIsNone(plus.accounts.primary)
        self.assertFalse(plus.accounts.have_primary_credentials())
        self.assertFalse(plus.cloud.is_connected())
        self.assertFalse(plus.supports_purchases())
        self.assertEqual(plus.get_bootstrap_server_addresses(), [])

    def test_local_profiles_initialize_and_persist_without_login(self):
        plus = self.module.CommunityPlusAppSubsystem()
        plus.on_app_loading()
        self.assertEqual(self.config['Player Profiles'], {})
        profile = {'character': 'Spaz', 'global': False, 'color': [1, 0, 0]}
        plus.add_v1_account_transaction({'type': 'ADD_PLAYER_PROFILE', 'name': '测试玩家', 'profile': profile})
        plus.run_v1_account_transactions()
        self.assertEqual(self.config['Player Profiles']['测试玩家'], profile)
        self.assertEqual(plus.get_v1_account_state(), 'signed_out')
        plus.add_v1_account_transaction({'type': 'REMOVE_PLAYER_PROFILE', 'name': '测试玩家'})
        plus.run_v1_account_transactions()
        self.assertEqual(self.config['Player Profiles'], {})

    def test_cloud_callback_gets_error_in_next_logic_cycle(self):
        cloud = self.module.OfflineCloud()
        responses = []
        cloud.send_message_cb(object(), responses.append)
        self.assertEqual(responses, [])
        self.drain()
        self.assertIsInstance(responses[0], self.module.CommunicationError)

    def test_builtin_account_profile_can_be_saved_without_official_services(self):
        plus = self.module.CommunityPlusAppSubsystem()
        plus.on_app_loading()
        plus.add_v1_account_transaction({'type': 'ADD_PLAYER_PROFILE', 'name': '__account__',
            'profile': {'character': 'Spaz', 'global': False, 'color': [1, 0, 0]}})
        plus.run_v1_account_transactions()
        self.assertEqual(self.config['Player Profiles']['__account__']['character'], 'Spaz')

    def test_cloud_future_is_failed_not_successful(self):
        future = self.module.OfflineCloud().send_message_future(object())
        with self.assertRaises(self.module.CommunicationError):
            future.result()

    def test_v1_transaction_callback_finishes_without_claiming_success(self):
        plus = self.module.CommunityPlusAppSubsystem()
        responses = []
        plus.add_v1_account_transaction({'type': 'test'}, responses.append)
        self.assertTrue(plus.have_outstanding_v1_account_transactions())
        plus.run_v1_account_transactions()
        self.assertFalse(plus.have_outstanding_v1_account_transactions())
        self.assertEqual(responses, [])
        self.drain()
        self.assertEqual(responses, [None])

    def test_coop_progress_is_committed_without_cloud(self):
        plus = self.module.CommunityPlusAppSubsystem()
        achievement = Mock()
        level = Mock()
        level.get_score_version_string.return_value = ' 2'
        classic = Mock()
        classic.ach.get_achievement.return_value = achievement
        classic.getcampaign.return_value.getlevel.return_value = level
        sys.modules['babase'].app.classic = classic

        scores = {'1 Player': [[42, {'players': [{'name': 'Player'}]}]]}
        responses = []
        with patch.object(self.config, 'commit') as commit:
            plus.add_v1_account_transaction(
                {'type': 'ACHIEVEMENT', 'name': 'Test Victory'}
            )
            plus.add_v1_account_transaction(
                {'type': 'COMPLETE_LEVEL', 'campaign': 'Easy', 'level': 'Test Level'}
            )
            plus.add_v1_account_transaction(
                {
                    'type': 'SET_LEVEL_LOCAL_HIGH_SCORES',
                    'campaign': 'Easy',
                    'level': 'Test Level',
                    'scoreVersion': ' 2',
                    'scores': scores,
                },
                responses.append,
            )
            self.assertEqual(commit.call_count, 3)

        classic.ach.get_achievement.assert_called_once_with('Test Victory')
        achievement.set_complete.assert_called_once_with()
        classic.getcampaign.assert_called_with('Easy')
        classic.getcampaign.return_value.getlevel.assert_called_with('Test Level')
        level.set_complete.assert_called_once_with(True)
        level.set_high_scores.assert_called_once_with(scores)
        scores['1 Player'].clear()
        self.assertEqual(level.set_high_scores.call_args.args[0]['1 Player'][0][0], 42)
        self.assertEqual(responses, [])
        self.drain()
        self.assertEqual(responses, [{}])

    def test_unsupported_login_and_purchase_fail_explicitly(self):
        plus = self.module.CommunityPlusAppSubsystem()
        for action in (lambda: plus.sign_in_v1('Local'), lambda: plus.purchase('pro'),
                       lambda: plus.accounts.set_primary_credentials('fake'),
                       plus.get_master_server_address):
            with self.assertRaises(self.module.CommunicationError):
                action()


if __name__ == '__main__':
    unittest.main()
