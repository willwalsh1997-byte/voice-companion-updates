"""Keyboard-only sweep of the main menu, Office tools and Shut down or restart (November 6, 2026).

A user who never speaks: F1 twice (help), F1 (main menu) and Alt+O must work in the new submenus, Escape on a question goes
back one level, the account type question must not be cut off or left behind, and the way back
to Office tools must never send you there from the main menu by surprise."""
import unittest
from unittest import mock

import companion
from test_core_email_fixes import CompanionTestCase


class KeyboardOnlyStartupTests(CompanionTestCase):
    def setUp(self):
        super().setUp()
        for name, value in dict(TASK_NAV=None, NAMED_LIST=None, OPEN_NOTE=None, OFFICE_RETURN=False,
                                MAIN_MENU_INDEX=None, account_setup=False, ACCOUNT_MENU_INDEX=None,
                                ACCOUNT_ENTRY=None, THUNDERBIRD_SETUP=None, POWER_ACTION=None,
                                POWER_RETURN_MODE='awake', SETTINGS_PANEL=None, SETTINGS_RETURN_MODE='awake').items():
            p = mock.patch.object(companion, name, value); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(companion, 'note_buffer', []); p.start(); self.addCleanup(p.stop)

    def key(self, key, mode):
        """As the window's key loop does: the key's request, then the keyboard handler."""
        asleep = mode == 'sleep' and key in __import__('input_parity').SCREEN_KEYS['sleep']
        request = companion.navigation_key(key, 'sleep' if asleep else companion.SLEEP_RETURN_MODE if mode == 'sleep' else mode)
        if request is None:
            return mode
        if mode == 'sleep' and request.lower() in ('wake up', 'wake companion'):
            return companion.resume_from_sleep()
        return companion.handle_keyboard(request, mode)

    def office(self):
        # File manager is first on the main menu; Office tools is second (November 6, 2026).
        mode = self.key('Home', 'awake')
        mode = self.key('Down', mode)
        return self.key('Enter', mode)

    def no_account(self):
        store = mock.Mock(); store.accounts.return_value = []; store.selected.return_value = None
        return mock.patch.object(companion, 'connected_accounts', return_value=[])

    # F1 twice opens Help for the screen, as on every other screen (guide 1.4).
    def test_f1_opens_help_in_office_tools_and_power_menu(self):
        for opened in ('office tools', 'organizer', 'shut down or restart'):
            mode = companion.handle(opened, 'awake')
            self.assertEqual(self.key('Double:F1', mode), 'help', opened)
            self.assertIn('Use the main menu', self.said[-1])
            companion.help_session = None

    # Alt+O opens Options on every screen (guide 1.4).
    def test_alt_o_opens_options_from_the_main_menu_groups(self):
        with mock.patch('app_settings.open_settings', lambda m, mode: 'settings'):
            for opened, expected in (('office tools', 'office_menu'), ('shut down or restart', 'power_menu'),
                                     ('media menu', 'media_menu')):
                mode = companion.handle(opened, 'awake')
                self.assertEqual(self.key('Alt+O', mode), 'settings', opened)
                self.assertEqual(companion.SETTINGS_RETURN_MODE, expected)
                companion.OFFICE_RETURN = False

    # Escape on "Restart the computer?" goes back to Shut down or restart, on the same item.
    def test_canceling_a_power_choice_goes_back_one_level(self):
        mode = companion.handle('shut down or restart', 'awake')
        mode = self.key('Down', mode)
        mode = self.key('Enter', mode)
        self.assertEqual(mode, 'power_confirm')
        mode = self.key('Escape', mode)
        self.assertEqual(mode, 'power_menu')
        self.assertEqual(self.said[-1], 'Canceled. Shut down or restart. Restart the computer (R), 2 of 2.')
        # Main menu at the question still goes to the main menu.
        mode = self.key('Enter', mode)
        self.assertEqual(companion.handle('main menu', mode), 'awake')
        self.assertIn('Main menu', self.said[-1])

    def test_power_choice_from_the_main_menu_by_voice_still_cancels_to_the_main_menu(self):
        mode = companion.handle('restart computer', 'awake')
        self.assertEqual(self.key('Escape', mode), 'awake')
        self.assertTrue(self.said[-1].startswith('Canceled. Main menu.'), self.said[-1])

    # Email with no account from Office tools: the account question is the last thing said.
    def test_email_with_no_account_question_is_not_cut_off_by_main_menu(self):
        with self.no_account():
            mode = self.office()
            mode = self.key('Down', mode)                    # Notepad
            mode = self.key('Down', mode)                    # Email
            mode = self.key('Enter', mode)
        self.assertTrue(companion.account_setup)
        self.assertFalse(any(text.startswith('Main menu') for text in self.said[-1:]), self.said[-2:])
        self.assertIn('Which email account type?', self.said[-1])
        self.assertEqual(self.key('Escape', mode), 'office_menu')

    # Main menu, F1 or Help must not leave the account question running behind them.
    def test_main_menu_ends_the_account_question(self):
        for leave in ('F1', 'main menu'):
            with self.no_account():
                mode = companion.handle('email', 'awake')
            self.assertTrue(companion.account_setup)
            mode = self.key(leave, mode) if leave == 'F1' else companion.handle(leave, mode)
            self.assertEqual(mode, 'awake', leave)
            self.assertFalse(companion.account_setup, leave)
            self.assertTrue(self.said[-1].startswith('Account setup canceled. Main menu.'), self.said[-1])
            self.key('Down', mode)
            self.assertEqual(self.said[-1], 'File manager (F), 1 of 10.')

    def test_f1_at_the_account_question_says_the_question_again(self):
        # F1 twice quickly says it again; F1 once is the main menu.
        with self.no_account():
            mode = companion.handle('email', 'awake')
        self.assertEqual(self.key('Double:F1', mode), 'awake')
        self.assertTrue(companion.account_setup)
        self.assertTrue(self.said[-1].startswith('Which email account type?'), self.said[-1])

    def test_waking_up_at_the_account_question_asks_it_again(self):
        with self.no_account():
            mode = companion.handle('email', 'awake')
        mode = self.key('Ctrl+F12', mode)
        self.assertEqual(mode, 'sleep')
        with mock.patch.object(companion, 'microphone_state', return_value='on'):
            mode = self.key('Ctrl+F12', mode)
        self.assertEqual(mode, 'awake')
        self.assertTrue(self.said[-1].startswith('I am listening. Which email account type?'), self.said[-1])

    # A key that opens another screen (Control+T, the tutorial) ends the account question there.
    def test_another_screen_ends_the_account_question(self):
        with self.no_account():
            mode = companion.handle('email', 'awake')
        mode = self.key('Ctrl+T', mode)
        self.assertEqual(mode, 'tutorial')
        self.assertFalse(companion.account_setup)
        self.key('Down', mode)
        self.assertNotIn('Thunderbird', self.said[-1])
        self.assertTrue(self.said[-1].startswith('Getting started'), self.said[-1])

    def test_sleep_keeps_the_account_question(self):
        with self.no_account():
            mode = companion.handle('email', 'awake')
        self.assertEqual(self.key('Ctrl+F12', mode), 'sleep')
        self.assertTrue(companion.account_setup)

    def test_alt_at_the_account_question_says_the_question(self):
        with self.no_account():
            mode = companion.handle('email', 'awake')
        self.key('Alt', mode)
        self.assertTrue(self.said[-1].startswith('Answer the question first. Which email account type?'), self.said[-1])
        self.assertIsNone(companion.MAIN_MENU_INDEX)

    def test_enter_with_no_account_type_chosen_names_the_keys(self):
        with self.no_account():
            mode = companion.handle('email', 'awake')
        self.key('Enter', mode)
        self.assertEqual(self.said[-1], 'Press T for Thunderbird or Y for Yahoo, or use the arrows. Then press Enter. '
                                        'Escape cancels.')
        self.assertTrue(companion.account_setup)

    # Options or Help opened from Office tools, then the main menu: Down moves on the main menu.
    def test_main_menu_keys_stay_on_the_main_menu_after_options_or_help_from_office_tools(self):
        for detour in ('options', 'help'):
            mode = self.office()
            with mock.patch('app_settings.open_settings', lambda m, mode: 'settings'):
                companion.handle(detour, mode)
            if detour == 'help':
                mode = self.key('Escape', 'help')          # Topic list: Escape closes Help.
                self.assertEqual(mode, 'office_menu')
            else:
                mode = 'office_menu'                       # Options closed (poll_settings).
            mode = self.key('Escape', mode)
            self.assertEqual(mode, 'awake', detour)
            mode = self.key('Down', mode)
            self.assertEqual(mode, 'awake', detour)
            self.assertEqual(self.said[-1], 'File manager (F), 1 of 10.')
            # An app opened from the main menu by name goes back to the main menu.
            mode = companion.handle('notepad', mode)
            self.assertEqual(self.key('Escape', mode), 'awake', detour)
            companion.help_session = None


if __name__ == '__main__':
    unittest.main()
