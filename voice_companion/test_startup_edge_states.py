"""Startup, settings and updates in empty and edge states (bug sweep, November 4, 2026)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import companion
from test_core_email_fixes import CompanionTestCase


class DamagedSpeechSettingsTests(unittest.TestCase):
    """speech-settings.json holding a list, null or text stopped startup with "Voice Companion
    could not start speech": the startup code called settings.get on something that was not a
    set of settings, and that error was not one it expected."""

    def test_settings_of_the_wrong_shape_read_as_none_saved(self):
        for text in ('[]', 'null', '"rate"', '5', '{"rate":', ''):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as folder:
                (Path(folder) / 'speech-settings.json').write_text(text, encoding='utf-8')
                self.assertEqual(companion.read_speech_settings(folder), {})

    def test_a_missing_file_is_the_first_start(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(companion.read_speech_settings(folder), {})

    def test_saved_settings_are_read_even_after_notepad_saved_them(self):
        saved = {'rate': 3, 'volume': 80, 'voice': 'Microsoft Zira'}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'speech-settings.json').write_text(json.dumps(saved), encoding='utf-8-sig')
            self.assertEqual(companion.read_speech_settings(folder), saved)

    def test_startup_reads_speech_settings_through_the_safe_reader(self):
        source = (Path(__file__).resolve().parent / 'companion.py').read_text(encoding='utf-8')
        main = source[source.index("if __name__ == '__main__':"):]
        self.assertTrue('settings = read_speech_settings(APP)' in main, 'startup must use read_speech_settings')
        self.assertFalse("json.loads((APP / 'speech-settings.json')" in main, 'startup reads the file directly')


class F1RepeatsTheUpdateQuestionTests(CompanionTestCase):
    """F1 in a yes or no question says it again (Will, October 31, 2026); F1 twice quickly since
    November 6, 2026, when F1 once became the main menu key. It found the question
    by the words "yes or no". With the microphone off, the update question says "Press Y or N"
    instead, so F1 said nothing at all, just when keys are the only way in. At startup it
    repeated the whole startup announcement instead of the question."""

    def setUp(self):
        super().setUp()
        def heard(text, *args, **kwargs):
            companion.remember_question(text); self.said.append(str(text))
        p = patch.object(companion, 'speak', heard); p.start(); self.addCleanup(p.stop)
        for name, value in dict(LAST_YES_NO='', MICROPHONE_FAILED=False, STARTUP_UPDATE_PENDING=False,
                                STARTUP_QUESTION=None, STARTUP_NOTICES=[], MAIN_MENU_LEAD='', UPDATE_OFFER=False,
                                UPDATE_RETURN_MODE='awake', PREFERENCES={'check_updates': True},
                                PREFERENCES_DAMAGED=False).items():
            p = patch.object(companion, name, value, create=True); p.start(); self.addCleanup(p.stop)
        p = patch.object(companion.sys, 'argv', ['companion']); p.start(); self.addCleanup(p.stop)

    def updates(self):
        from test_startup_announcement import FakeUpdates
        return FakeUpdates(('available', {'version': '9.9.9-test'}))

    def test_f1_repeats_the_offer_with_the_microphone_off_or_on(self):
        for off in (True, False):
            with self.subTest(microphone_off=off), patch.object(companion, 'MICROPHONE_OFF', off), \
                    patch.object(companion, 'UPDATES', self.updates()):
                companion.UPDATES.check()
                self.assertEqual(companion.poll_app_updates('awake'), 'update_offer')
                question = self.said[-1]
                self.said.clear()
                self.assertIsNone(companion.navigation_key('Double:F1', 'update_offer'))
                self.assertEqual(self.said, [question])
                companion.handle('no', 'update_offer')

    def test_f1_after_the_startup_announcement_says_only_the_question(self):
        for off in (True, False):
            with self.subTest(microphone_off=off), patch.object(companion, 'MICROPHONE_OFF', off), \
                    patch.object(companion, 'UPDATES', self.updates()):
                self.said.clear()
                self.assertEqual(companion.announce_startup(), 'update_offer')
                self.assertTrue(self.said[-1].startswith('Voice Companion'), self.said)
                self.said.clear()
                self.assertIsNone(companion.navigation_key('Double:F1', 'update_offer'))
                self.assertEqual(self.said, [companion.update_offer_question()])
                companion.handle('no', 'update_offer')


class GuideMatchesTheAppTests(unittest.TestCase):
    """Online (Azure) recognition and its permission were removed in 0.2.201, but the guide's
    privacy part still told people to give that permission in Input options."""

    def test_the_guide_no_longer_asks_for_online_recognition_permission(self):
        folder = Path(__file__).resolve().parent
        for name in ('START HERE - Veteran.txt', 'START HERE - Veteran.html'):
            with self.subTest(name=name):
                text = (folder / name).read_text(encoding='utf-8')
                self.assertNotIn('Online recognition', text)
                self.assertIn('An AI voice needs your permission in Synthesizer options.', text)


class TranscriptHeldOpenTests(unittest.TestCase):
    """At about 2 MB the transcript moves to speech-transcript-old.txt. When that file was held
    (open in Word, or being scanned), the move failed for every line, so every later line was
    lost until it was let go: the transcript stopped in the middle of what a helper wanted to read."""

    def test_lines_are_kept_when_the_old_transcript_cannot_be_replaced(self):
        import speech_transcript
        from speech_transcript import Transcript
        with tempfile.TemporaryDirectory() as folder:
            transcript = Transcript(limit=200); self.addCleanup(transcript.stop)
            transcript.start(folder)
            with patch('speech_transcript.os.replace', side_effect=PermissionError('in use')):
                for number in range(10):
                    transcript.said('Sentence number ' + str(number) + ' is here.')
            text = (Path(folder) / speech_transcript.NAME).read_text(encoding='utf-8')
            self.assertIn('Sentence number 9 is here.', text)
            self.assertEqual(text.count('Sentence number'), 10)
            # Once the old file is free again, the transcript moves as usual.
            transcript.said('After the file was closed.')
            self.assertTrue((Path(folder) / speech_transcript.OLD_NAME).exists())
            self.assertIn('After the file was closed.', (Path(folder) / speech_transcript.NAME).read_text(encoding='utf-8'))
            # Close the transcript before the folder is removed: Windows cannot delete an open file.
            transcript.stop()


class HelpToleratesSpeechTests(CompanionTestCase):
    """Recognizers write "e-mail" and add commas. "Help with e-mail." said there was no help
    topic for e-mail, and "Help, please." on the main menu was not understood."""

    def test_help_with_e_mail_opens_the_email_topic(self):
        for words in ('Help with e-mail.', 'Help with E-mail', 'help with the e-mail'):
            with self.subTest(words=words):
                self.said.clear()
                self.assertEqual(companion.handle(words, 'awake'), 'help')
                self.assertNotIn('did not find', self.said[-1])
                self.assertIn('read and organize email', self.said[-1].casefold())
                companion.handle('main menu', 'help')

    def test_topic_names_with_punctuation_still_match(self):
        from onboard_help import HelpSession
        notes = self.folder / 'Voice Companion Release Notes.txt'
        notes.write_text('New in this version\n\nFaster startup.', encoding='utf-8')
        session = HelpSession(companion.GUIDE, release_notes_path=notes)
        for name in ('sleep exit and computer power', 'sleep, exit, and computer power', 'whats new', "what's new"):
            with self.subTest(name=name):
                self.assertNotIn('did not find', session.topic(name))

    def test_help_please_with_a_comma_opens_help(self):
        for words in ('Help, please.', 'Help please'):
            with self.subTest(words=words):
                self.assertEqual(companion.handle(words, 'awake'), 'help')
                self.assertIn('User guide', self.said[-1])
                companion.handle('main menu', 'help')


class OptionsSaveTests(unittest.TestCase):
    """preferences.json was written to a side file and put in place without being flushed to the
    disk, and a failed write (a full disk) left preferences.writing behind. The shared atomic
    writer flushes first and removes its side file on failure, as the other settings files do."""

    def test_a_failed_save_keeps_the_old_options_and_leaves_no_side_file(self):
        import app_settings
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'preferences.json').write_text('{"verbosity": "low"}', encoding='utf-8')
            m = SimpleNamespace(APP=folder, PREFERENCES={'verbosity': 'high'})
            with patch('storage.os.fsync', side_effect=OSError(28, 'No space left on device')):
                with self.assertRaises(OSError):
                    app_settings.save_preferences(m)
            self.assertEqual(json.loads((folder / 'preferences.json').read_text(encoding='utf-8')), {'verbosity': 'low'})
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ['preferences.json'])
            app_settings.save_preferences(m)
            self.assertEqual(json.loads((folder / 'preferences.json').read_text(encoding='utf-8')), {'verbosity': 'high'})


if __name__ == '__main__':
    unittest.main()
