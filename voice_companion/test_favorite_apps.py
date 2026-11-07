"""Organizer, Favorite apps, My menu and the F1 keys (Will, November 6, 2026).

- Organizer follows Office tools on the main menu. It holds Address manager and Schedule
  manager, the old Contacts and Calendar, in alphabetical order. The old words still work.
- F1 goes to the main menu from every screen. F1 twice quickly opens help for the screen;
  on the main menu that is the user guide.
- Control+F1 opens Favorite apps: the apps chosen in Options, My menu, then Change favorite apps.
"""
import unittest
from unittest import mock

import companion
import settings_model
import task_navigation
from f1_key import F1Presses
from test_core_email_fixes import CompanionTestCase


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class F1PressTests(unittest.TestCase):
    def test_one_press_waits_then_goes_to_the_main_menu(self):
        clock = Clock()
        presses = F1Presses(clock)
        self.assertIsNone(presses.press())
        self.assertIsNone(presses.due())          # still waiting for a second press
        clock.now += 0.5
        self.assertEqual(presses.due(), 'F1')
        self.assertIsNone(presses.due())          # only once

    def test_two_quick_presses_are_help_and_never_the_main_menu(self):
        clock = Clock()
        presses = F1Presses(clock)
        presses.press()
        clock.now += 0.2
        self.assertEqual(presses.press(), 'Double:F1')
        clock.now += 1
        self.assertIsNone(presses.due())

    def test_two_slow_presses_are_two_single_presses(self):
        clock = Clock()
        presses = F1Presses(clock)
        presses.press()
        clock.now += 0.6
        self.assertIsNone(presses.press())        # a new first press
        self.assertIsNone(presses.due())          # the first one was overtaken, not lost twice
        clock.now += 0.6
        self.assertEqual(presses.due(), 'F1')

    def test_window_code_uses_the_wait(self):
        from pathlib import Path
        source = (Path(__file__).parent / 'app_window.py').read_text(encoding='utf-8')
        self.assertIn("self.commands.put(('keyboard','Double:F1'))", source)
        self.assertIn("root.after(int(F1_WAIT*1000)+20,single_f1)", source)
        settings = (Path(__file__).parent / 'native_settings.py').read_text(encoding='utf-8')
        self.assertIn("self.keyboard('Double:F1')", settings)
        self.assertIn("self.f1_presses.due()", settings)


class MenuTests(CompanionTestCase):
    def setUp(self):
        super().setUp()
        for name, value in dict(TASK_NAV=None, NAMED_LIST=None, OPEN_NOTE=None, OFFICE_RETURN=False,
                                FAVORITES_AFTER=False, MAIN_MENU_INDEX=None).items():
            p = mock.patch.object(companion, name, value); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(companion, 'note_buffer', []); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(companion, 'PREFERENCES', dict(companion.PREFERENCES)); p.start(); self.addCleanup(p.stop)

    def key(self, key, mode):
        request = companion.navigation_key(key, mode)
        return mode if request is None else companion.handle(request, mode)

    def choose(self, *names):
        for name in names:
            companion.PREFERENCES[task_navigation.favorite_key(name)] = True

    # Organizer

    def test_organizer_follows_office_tools(self):
        names = [name for name, _ in companion.MAIN_MENU_CHOICES]
        self.assertEqual(names[:3], ['File manager', 'Office tools', 'Organizer'])
        mode = companion.handle('Organizer.', 'awake')
        self.assertEqual(mode, 'organizer_menu')
        self.assertTrue(self.said[-1].startswith('Organizer. Address manager'), self.said[-1])
        self.assertEqual([name for name, _, _ in companion.task_navigation().items('organizer_menu')],
                         ['Address manager', 'Schedule manager'])

    def test_address_manager_opens_from_organizer_and_comes_back(self):
        mode = companion.handle('organizer', 'awake')
        mode = self.key('Enter', mode)
        self.assertEqual(mode, 'contacts')
        self.assertTrue(any(said.startswith('Address manager.') for said in self.said), self.said)
        for _ in range(5):
            mode = self.key('Escape', mode)
            if mode != 'contacts': break
        self.assertEqual(mode, 'organizer_menu')
        self.assertTrue(self.said[-1].startswith('Organizer. Address manager'), self.said[-1])
        self.assertEqual(self.key('Escape', mode), 'awake')

    def test_new_and_old_names_open_the_same_screens(self):
        for said in ('Address manager.', 'open address manager', 'contacts', 'address book'):
            with self.subTest(said=said):
                self.assertEqual(companion.handle(said, 'awake'), 'contacts')
        import calendar_screen
        for said in ('Schedule manager.', 'open schedule manager', 'calendar'):
            with self.subTest(said=said), mock.patch.object(calendar_screen, 'handle', side_effect=lambda m, text, mode, typed:
                                                             'calendar' if m.normalized_command(text) in calendar_screen.OPEN else None):
                self.assertEqual(companion.handle(said, 'awake'), 'calendar')

    def test_help_topics_answer_to_both_names(self):
        from pathlib import Path
        import onboard_help
        guide = Path(companion.__file__).with_name('START HERE - Veteran.txt')
        for wanted, chapter in (('address manager', 'Address manager'), ('contacts', 'Address manager'),
                                ('schedule manager', 'Schedule manager'), ('calendar', 'Schedule manager'),
                                ('organizer', 'Getting started'), ('favorite apps', 'Getting started')):
            with self.subTest(wanted=wanted):
                session = onboard_help.HelpSession(guide)
                words = session.topic(wanted)
                self.assertNotIn(onboard_help.NOT_FOUND, words)
                self.assertEqual(session.topics[session.topic_index]['name'].casefold(), chapter.casefold(), words)

    def test_file_manager_is_first_and_returns_to_the_main_menu(self):
        mode = self.key('Home', 'awake')
        self.assertTrue(self.said[-1].startswith('File manager'), self.said[-1])
        mode = self.key('Enter', mode)
        self.assertEqual(mode, 'files')
        for _ in range(10):
            mode = self.key('Escape', mode)
            if mode != 'files': break
        self.assertEqual(mode, 'awake')

    # F1

    def test_f1_goes_to_the_main_menu_from_every_screen(self):
        for mode in ('awake', 'document', 'email_draft', 'note', 'mailbox', 'web', 'files', 'local_media',
                     'media_menu', 'word_processor', 'file_reader', 'settings', 'help', 'media', 'tutorial',
                     'office_menu', 'organizer_menu', 'favorites_menu', 'contacts', 'calendar'):
            with self.subTest(mode=mode):
                self.assertEqual(companion.navigation_key('F1', mode), '@main_menu')

    def test_f1_twice_is_help_for_the_screen(self):
        cases = {'awake': 'help', 'note': 'help with notepad', 'mailbox': 'help with email', 'web': 'help with web',
                 'contacts': 'help with contacts', 'calendar': 'help with calendar', 'files': 'file manager help',
                 'office_menu': 'help with main menu', 'organizer_menu': 'help with main menu',
                 'favorites_menu': 'help with main menu', 'tutorial': 'list commands'}
        for mode, request in cases.items():
            with self.subTest(mode=mode):
                self.assertEqual(companion.navigation_key('Double:F1', mode), request)

    def test_f1_twice_on_the_main_menu_opens_the_user_guide(self):
        self.assertEqual(self.key('Double:F1', 'awake'), 'help')

    def test_f1_twice_in_a_document_is_document_help(self):
        self.open_document()
        self.assertEqual(companion.navigation_key('Double:F1', 'document'), 'help with documents')

    def test_menus_say_f1_twice_for_help_and_f1_for_the_main_menu(self):
        navigation = companion.task_navigation()
        items = navigation.items('notepad_menu')
        self.assertIn('Main menu, 4 of 4. F1.', navigation.describe(items[3], 3, 4).replace(' (M)', ''))
        items = navigation.items('reader_menu')
        help_item = next(i for i, item in enumerate(items) if item[0] == 'Help')
        self.assertTrue(navigation.describe(items[help_item], help_item, len(items)).endswith('F1 twice.'))

    def test_spoken_messages_name_f1_twice_for_help(self):
        self.assertIn('Press F1 twice for help.', companion.MAIN_MENU_NOT_UNDERSTOOD)
        import startup_speech
        self.assertTrue(all('Press F1 for' not in words for words in vars(startup_speech).values() if isinstance(words, str)))

    # Favorite apps

    def test_control_f1_opens_favorite_apps_from_every_screen(self):
        for mode in ('awake', 'document', 'note', 'web', 'files', 'settings', 'office_menu'):
            with self.subTest(mode=mode):
                self.assertEqual(companion.navigation_key('Ctrl+F1', mode), '@favorites')

    def test_empty_favorite_apps_says_how_to_add_apps(self):
        mode = self.key('Ctrl+F1', 'awake')
        self.assertEqual(mode, 'favorites_menu')
        self.assertEqual(self.said[-1], 'Favorite apps. No apps are in it yet. To add apps, press Enter on '
                                        'Change favorite apps. Change favorite apps (C), 1 of 1.')

    def test_favorite_apps_lists_the_chosen_apps_in_order(self):
        self.choose('YouTube', 'Notepad', 'File manager')
        mode = companion.handle('favorite apps', 'awake')
        self.assertEqual(mode, 'favorites_menu')
        names = [name for name, _, _ in companion.task_navigation().items('favorites_menu')]
        self.assertEqual(names, ['File manager', 'Notepad', 'YouTube', 'Change favorite apps'])
        self.assertTrue(self.said[-1].startswith('Favorite apps. File manager'), self.said[-1])

    def test_web_favorites_keep_their_words(self):
        # "Favorites" and "My favorites" are the web browser's saved pages, not Favorite apps.
        for said in ('favorites', 'my favorites', 'Favourites.'):
            with self.subTest(said=said):
                self.assertNotIn(companion.normalized_command(said), task_navigation.FAVORITES_OPEN)

    def test_saying_favorite_apps_when_empty_says_how_to_add_apps(self):
        self.assertEqual(companion.handle('Favorite apps.', 'awake'), 'favorites_menu')
        self.assertIn('No apps are in it yet.', self.said[-1])

    def test_an_app_from_favorite_apps_comes_back_there(self):
        self.choose('Notepad', 'Address manager')
        mode = self.key('Ctrl+F1', 'awake')
        self.key('Down', mode)                       # Notepad, then Address manager
        mode = self.key('Enter', mode)
        self.assertEqual(mode, 'contacts')
        for _ in range(5):
            mode = self.key('Escape', mode)
            if mode != 'contacts': break
        self.assertEqual(mode, 'favorites_menu')
        self.assertTrue(self.said[-1].startswith('Favorite apps. Address manager'), self.said[-1])
        # F1 from there: the main menu, and the way back is used up.
        self.assertEqual(self.key('F1', mode), 'awake')
        self.assertFalse(companion.OFFICE_RETURN)

    def test_control_f1_in_a_note_saves_it_then_opens_favorite_apps(self):
        self.choose('Word processor')
        mode = self.key('Ctrl+N', companion.handle('notepad', 'awake'))
        self.assertEqual(mode, 'note')
        companion.handle('Buy milk.', mode)
        with mock.patch.object(companion, 'save_note', return_value=True) as save:
            mode = self.key('Ctrl+F1', mode)
        self.assertEqual(mode, 'favorites_menu')
        self.assertTrue(save.called)
        self.assertNotIn(companion.MAIN_MENU_PROMPT, self.said[-1])
        self.assertIn('Favorite apps. Word processor', self.said[-1])
        self.assertFalse(companion.FAVORITES_AFTER)

    def test_control_f1_in_a_changed_document_asks_to_save_first(self):
        document = self.open_document()
        companion.INPUT_MODE = 'dictation'
        companion.handle('Dinner is at six.', 'document')
        mode = self.key('Ctrl+F1', 'document')
        self.assertEqual(mode, 'document_save')
        self.assertTrue(companion.FAVORITES_AFTER)
        self.assertIn('Dinner is at six.', companion.document_text(document))

    def test_canceling_the_save_question_forgets_favorite_apps(self):
        companion.FAVORITES_AFTER = True
        self.assertEqual(companion.office_return('cancel', 'document_save', 'document'), 'document')
        self.assertFalse(companion.FAVORITES_AFTER)

    def test_change_favorite_apps_opens_options_on_my_menu(self):
        mode = self.key('Ctrl+F1', 'awake')
        panel = mock.Mock()
        def opened(mode):
            companion.SETTINGS_PANEL = panel
            return 'settings'
        with mock.patch.object(companion, 'open_settings', side_effect=opened), \
                mock.patch.object(companion, 'SETTINGS_PANEL', None):
            self.assertEqual(self.key('Enter', mode), 'settings')
        panel.command.assert_called_once_with('My menu')
        self.assertEqual(companion.SETTINGS_RETURN_MODE, 'favorites_menu')
        self.assertEqual(companion.options_return_notice('favorites_menu'), 'Back to Favorite apps.')

    def test_my_menu_by_voice(self):
        with mock.patch.object(companion.screen_menu(), 'run', return_value='settings') as run:
            for said in ('Change favorite apps.', 'my menu'):
                self.assertEqual(companion.handle(said, 'awake'), 'settings')
        run.assert_called_with('@options:My menu', 'awake')

    # My menu in Options

    def test_my_menu_is_last_in_options_with_a_box_for_each_app(self):
        self.assertEqual(settings_model.CATEGORIES[-1], 'My menu')
        fields = settings_model.fields('My menu', {})
        self.assertEqual([f.label for f in fields],
                         [name + ' in Favorite apps' for name, _ in task_navigation.FAVORITE_APPS])
        self.assertTrue(all(f.kind == 'check' for f in fields))
        session = settings_model.SettingsSession({}, {})
        self.assertFalse(session.values['favorite_youtube'])
        self.assertEqual(session.set('favorite_youtube', 'on'), 'YouTube in Favorite apps on')
        self.assertTrue(session.values['favorite_youtube'])

    def test_every_favorite_app_command_opens_something(self):
        for name, command in task_navigation.FAVORITE_APPS:
            with self.subTest(name=name):
                self.assertTrue(command)
                self.assertNotEqual(companion.normalized_command(command), '')


if __name__ == '__main__':
    unittest.main()
