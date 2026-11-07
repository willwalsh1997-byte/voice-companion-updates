"""Nightly sweep, November 6, 2026: Word processor, Notepad, Document reader and File manager
used with the keyboard only, as a blind user who never speaks a command."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import companion as app
from real_window_tests import real_window
from file_manager import FileManager
from test_file_manager import FakeFiles, settle


class FileManagerKeys(unittest.TestCase):
    """Keys pressed on the File manager screen go through the app, as the window sends them."""
    files = ('a.txt', 'b.txt')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in self.files:
            (self.root / name).write_text('x')
        self.backend = FakeFiles(self.root)
        self.fm = FileManager(self.backend)
        self.fm.refresh()
        settle(self.fm)
        self.fm.command('enter')
        settle(self.fm)
        self.spoken = []
        for patcher in (patch.object(app, 'FILE_MANAGER', self.fm), patch.object(app, 'APP_WINDOW', None),
                        patch.object(app, 'speak', self.say),
                        patch.object(app, 'sync_app_context'), patch.object(app, 'CONFIRM_CHOICE', 'no'),
                        patch.object(app, 'LAST_YES_NO', '')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def say(self, text, *args, **kwargs):
        app.remember_question(text)
        self.spoken.append(text)

    def key(self, key):
        """Press one key; return what was said."""
        self.spoken.clear()
        request = app.navigation_key(key, 'files')
        if request:
            app.handle(request, 'files')
        notices = settle(self.fm)
        return ' '.join(self.spoken + ([notices] if notices else []))

    def typed(self, text):
        """Type into the box File manager shows (a new name or a search), then press Enter."""
        self.spoken.clear()
        app.handle_keyboard(text, 'files')
        notices = settle(self.fm)
        return ' '.join(self.spoken + ([notices] if notices else []))


class DeleteQuestionKeys(FileManagerKeys):
    def test_y_deletes_and_n_keeps_as_on_every_other_question(self):
        # The window sends a letter as "Letter:" and the character, upper case with Shift.
        # Y and N did nothing at all here, and said nothing.
        self.assertIn('Say Yes or No', self.key('Delete'))
        said = self.key('Letter:n')
        self.assertIn('canceled', said)
        self.assertIsNone(self.fm.pending)
        self.assertEqual(self.backend.actions, [])
        self.key('Delete')
        self.key('Letter:Y')
        self.assertEqual(self.backend.actions[0][0], 'delete')

    def test_f1_says_the_question_again(self):
        # Will, October 31, 2026: F1 in a yes or no question says the question again. Here it was silent.
        # F1 twice quickly since November 6, 2026 (F1 once is the main menu).
        question = self.key('Delete')
        self.assertEqual(self.key('Double:F1'), question)
        self.assertEqual(self.fm.pending[0], 'delete')
        self.assertEqual(self.backend.actions, [])


class NameAndSearchBoxes(FileManagerKeys):
    files = ('a.txt', 'help.txt', 'commands.docx')

    def test_help_typed_as_a_search_is_searched(self):
        # Typing "help" in the Control+F box read the whole File manager help, and the box stayed open.
        self.key('Ctrl+F')
        self.assertIn('1 match.', self.typed('help'))
        self.assertIsNone(self.fm.pending)
        self.assertEqual(self.fm.current().name, 'help.txt')

    def test_commands_typed_as_a_new_name_renames(self):
        self.key('Home')
        self.key('F2')
        self.typed('commands.txt')
        self.assertEqual(self.backend.actions[-1][0], 'rename')
        self.assertEqual(self.backend.actions[-1][3], 'commands.txt')
        self.key('F2')
        self.typed('Help')
        self.assertEqual(self.backend.actions[-1][3], 'Help')

    def test_help_said_in_the_rename_box_gives_help_and_keeps_the_box(self):
        # Spoken "File manager help" or "Help." renamed the file to "file manager help.txt" or "help.txt".
        self.key('Home')
        self.key('F2')
        for words in ('File manager help.', 'Help.'):
            self.spoken.clear()
            app.handle(words, 'files')
            settle(self.fm)
            self.assertIn('F2 renames', ' '.join(self.spoken))
            self.assertEqual(self.fm.pending[0], 'rename')
        self.assertEqual(self.backend.actions, [])

class PropertiesKeys(FileManagerKeys):
    def test_a_file_key_in_properties_closes_them_first(self):
        # F2 in Properties renamed the file, and the screen kept the old properties: the arrows
        # still said "Name: a.txt". As in the Alt menu, a file key closes Properties and acts on the file.
        self.key('Alt+Enter')
        self.assertEqual(self.fm.menu, 'properties')
        self.key('Down')
        self.assertIn('Rename a.txt', self.key('F2'))
        self.assertFalse(self.fm.menu)
        self.typed('c.txt')
        self.assertEqual(self.backend.actions[-1][3], 'c.txt')
        self.assertNotIn('Name:', self.key('Down'))

    def test_arrows_letters_and_escape_still_read_properties(self):
        self.key('Alt+Enter')
        self.assertIn('Type:', self.key('Down'))
        self.assertIn('Name:', self.key('Home'))
        self.key('Letter:s')
        self.assertEqual(self.fm.menu, 'properties')
        self.assertIn('a.txt, file', self.key('Escape'))
        self.assertFalse(self.fm.menu)


class FirstLetterKeys(FileManagerKeys):
    files = ('apple.txt', 'banana.txt', 'berry.txt')

    def test_escape_after_one_letter_goes_up_a_folder(self):
        # One letter only jumps; nothing is filtered. Escape said "Name filter cleared" and stayed.
        self.assertIn('banana.txt', self.key('Letter:b'))
        self.key('Down')
        said = self.key('Escape')
        self.assertNotIn('filter', said)
        self.assertIsNone(self.fm.location)

    def test_escape_after_several_letters_clears_the_filter_first(self):
        self.fm.view.last_key = 0
        self.key('Letter:b')
        self.key('Letter:e')
        self.assertEqual([item.name for item in self.fm.items], ['berry.txt'])
        self.assertIn('Name filter cleared', self.key('Escape'))
        self.assertEqual(len(self.fm.items), 3)
        self.assertEqual(self.fm.location, str(self.root))


class AltMenuKeys(FileManagerKeys):
    def press(self, *keys):
        mode = 'files'
        for key in keys:
            self.spoken.clear()
            request = app.navigation_key(key, mode)
            if request:
                mode = app.handle(request, mode) or mode
            settle(self.fm)
        return mode

    def test_go_to_main_menu_in_the_alt_menu_goes_to_the_main_menu(self):
        # Alt, Go to, Main menu, Enter said "No item is named main menu".
        self.assertEqual(self.press('Alt', 'End', 'Enter', 'End', 'Enter'), 'awake')
        self.assertNotIn('No item', ' '.join(self.spoken))

    def test_every_alt_menu_item_does_something_with_enter(self):
        from file_manager import GROUPS
        for number, (key, (name, items)) in enumerate(GROUPS.items()):
            for index, (label, _, voice) in enumerate(items):
                if voice in ('email this file', 'attach to draft'):
                    continue  # they open other screens (attachment_screen.py)
                self.fm.pending = None
                self.fm.menu = True
                self.fm.menu_index = number
                self.fm.command('enter')
                self.fm.menu_index = index
                self.spoken.clear()
                mode = app.handle('enter', 'files')
                said = ' '.join(self.spoken) + settle(self.fm)
                self.assertNotIn('No item is named', said, label)
                self.fm.command('escape') if self.fm.pending else None
                settle(self.fm)
                if self.fm.location is None:
                    self.fm.command('enter')
                    settle(self.fm)


    def test_menu_items_are_said_without_a_double_period(self):
        # "Actions, group.. 1 of 4." and "Say refresh.. 1 of 5." on the screen and in braille.
        self.assertEqual(self.fm.command('file manager menu'), 'File manager menu. Actions, group. 1 of 4.')
        self.assertNotIn('..', self.fm.command('enter'))
        self.assertNotIn('..', self.fm.command('next'))


class NameClashKeys(FileManagerKeys):
    def test_a_used_name_keeps_the_rename_box_open(self):
        # F2, then a name already in the folder: the box closed, and only then did Windows say
        # "That name already exists. Choose another name." The user had to press F2 again.
        self.key('Home')
        self.key('F2')
        said = self.typed('b.txt')
        self.assertIn('already', said)
        self.assertEqual(self.fm.pending[0], 'rename')
        self.assertEqual(self.backend.actions, [])
        self.typed('c.txt')
        self.assertEqual(self.backend.actions[-1][3], 'c.txt')

    def test_the_same_name_in_new_capitals_is_allowed(self):
        self.key('Home')
        self.key('F2')
        self.typed('A.txt')
        self.assertEqual(self.backend.actions[-1][3], 'A.txt')


class DoneMessages(FileManagerKeys):
    def test_delete_and_rename_say_what_was_done(self):
        # Both said only "File action complete."
        self.key('Home')
        self.key('F2')
        self.assertIn('Renamed a.txt to c.txt.', self.typed('c.txt'))
        self.key('Delete')
        self.assertIn('Deleted a.txt.', self.key('Up') + self.key('Enter'))
        self.key('Ctrl+A')
        self.key('Delete')
        self.assertIn('Deleted 2 items.', self.key('Letter:y'))


class EmptyBoxHints(FileManagerKeys):
    def test_enter_in_an_empty_box_says_what_that_box_wants(self):
        # Enter in an empty search box said "Enter a new file name, including the extension."
        for key, words in (('Ctrl+F', 'part of a name'), ('Ctrl+Shift+F', 'part of a name'), ('Alt+Z', 'name for the zip'),
                           ('F2', 'new name'), ('Alt+Shift+Z', 'name for the zip')):
            self.fm.pending = None
            self.key(key)
            hint = app.app_context('files').get('file_empty_hint', '')
            self.assertIn(words, hint, key)
            self.assertIn('Escape cancels', hint, key)
        self.typed('photos')
        self.assertIn('password', app.app_context('files')['file_empty_hint'])


class CancelWords(FileManagerKeys):
    def test_escape_names_what_was_canceled(self):
        # Every box said "File action canceled", even a search.
        for key, words in (('Ctrl+F', 'Search canceled.'), ('F2', 'Rename canceled.'), ('Alt+Z', 'Zip canceled.'),
                           ('Delete', 'Nothing was deleted.')):
            self.key(key)
            self.assertIn(words, self.key('Escape'), key)
            self.assertIsNone(self.fm.pending)


class SearchKeys(FileManagerKeys):
    files = ('apple.txt', 'banana.txt', 'cherry.txt')

    def test_match_counts_use_the_right_word(self):
        # "1 matches."
        self.key('Ctrl+F')
        self.assertTrue(self.typed('ban').startswith('1 match. banana.txt'))
        self.key('Ctrl+Shift+X')
        self.key('Ctrl+F')
        self.assertTrue(self.typed('a').startswith('2 matches.'))
        self.key('Ctrl+F')
        self.assertTrue(self.typed('zzz').startswith('No matches.'))

    def test_subfolder_search_results_count_one_result(self):
        self.key('Ctrl+Shift+F')
        self.assertIn('1 search result. cherry.txt', self.typed('cherry'))

    def test_subfolder_search_in_the_drive_list_says_so_before_asking(self):
        # It asked for a name first, then said "Open a drive or folder before searching subfolders."
        self.key('Ctrl+D')
        said = self.key('Ctrl+Shift+F')
        self.assertIn('Open a drive or folder', said)
        self.assertIsNone(self.fm.pending)


class DocumentValuePrompts(unittest.TestCase):
    def test_every_document_value_item_asks_in_plain_words(self):
        # Control+Shift+F said "set font. Type or say the value, then Enter." Other document menu
        # items said "heading.", "line spacing.", "selection end at." and so on.
        import re
        from task_navigation import DOCUMENT_ACTIONS, TaskNavigation
        commands = sorted({command for items in DOCUMENT_ACTIONS.values() for _, _, command in items if '{value}' in command})
        self.assertIn('set font {value}', commands)
        said = []
        nav = TaskNavigation(app)
        with patch.object(app, 'speak', said.append):
            for command in commands:
                said.clear()
                self.assertEqual(nav.action(command, 'document'), 'task_input')
                self.assertNotIn('the value', said[-1], command)
                self.assertTrue(re.match(r'[A-Z]', said[-1]), said[-1])
                self.assertIn('Escape cancels.', said[-1], command)


@real_window
class FileBoxWindowTests(unittest.TestCase):
    """The real window: Enter in an empty File manager box says what that box wants.
    Not yet in the build's window list: try it on a claude/try- branch first (CLAUDE.md)."""
    def setUp(self):
        from app_window import CompanionWindow
        self.window = CompanionWindow('file box test')
        self.window.start()

    def tearDown(self):
        if self.window.thread.is_alive():
            self.call(lambda: self.window.root.destroy())
        self.window.thread.join(5)
        self.assertFalse(self.window.thread.is_alive())

    def call(self, function):
        import threading
        done = threading.Event()
        errors = []

        def run():
            try:
                self.window.root.update_idletasks()
                function()
            except Exception as exc:
                errors.append(exc)
            finally:
                done.set()
        self.window.ui_actions.put(('ui_call', run))
        if not done.wait(5):
            self.fail(self.window.debug_state())
        if errors:
            raise errors[0]

    def wait(self, condition):
        import time
        end = time.monotonic() + 5
        while not condition() and time.monotonic() < end:
            time.sleep(.015)
        if not condition():
            self.fail(self.window.debug_state())

    def test_empty_search_box_enter_says_to_type_part_of_a_name(self):
        hint = 'Type part of a name, then press Enter. Escape cancels.'
        self.window.set_context(dict(mode='files', source=None, text='', file_items=['a.txt, file'], file_index=0, ack=0,
                                     focus=True, file_name_input=True, file_rename_value='', menu_letters=False,
                                     file_input_label='Search names in this list', file_empty_hint=hint))
        self.wait(lambda: self.window.context.get('file_name_input'))
        self.call(lambda: (self.window.typed.focus_force(), self.window.typed.delete(0, 'end'),
                           self.window.typed.event_generate('<KeyPress>', keysym='Return')))
        self.wait(lambda: hint in list(self.window.key_feedback.queue))
        self.assertTrue(self.window.commands.empty())


if __name__ == '__main__':
    unittest.main()
