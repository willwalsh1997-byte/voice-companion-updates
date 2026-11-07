"""Email with the keyboard only (nightly sweep, November 6, 2026).

A blind user who never speaks a command: Escape, Tab, Control keys and Delete on every
email screen must do what the guide and Help say, never lose typed text, and reach the
same result as the voice command.
"""
import unittest

import attachment_screen
import companion as app
import screen_menus
import test_attachment_voice
from email_draft import VoiceEmail
from input_parity import SCREEN_KEYS


class DraftFieldKeyTests(test_attachment_voice.PlacesTestCase):
    """The To, CC, BCC and Subject boxes of a draft."""

    def new_draft(self, **fields):
        draft = VoiceEmail(self.root / 'data' / 'Email Drafts', **fields)
        draft.save()
        app.email_draft = draft
        return draft

    def field_key(self, field, value, key):
        """What the window sends for a key pressed in a header box (app_window: email_field_tab)."""
        request = app.commit_email_field_tab({'field': field, 'value': value, 'backward': False, 'key': key}, 'email_draft')
        return app.handle_keyboard(request, 'email_draft') if request else 'email_draft'

    def test_escape_with_a_subject_typed_keeps_it_and_asks(self):
        draft = self.new_draft(recipient='sam@example.com', compose_step='subject')
        self.assertEqual(self.field_key('subject', 'Lunch on Friday', 'Escape'), 'draft_leave')
        self.assertEqual(draft.subject, 'Lunch on Friday')
        self.assertEqual(app.handle_keyboard(app.navigation_key('Enter', 'draft_leave'), 'draft_leave'), 'awake')
        self.assertEqual(VoiceEmail.open_existing(self.root / 'data' / 'Email Drafts', draft.title).subject, 'Lunch on Friday')

    def test_escape_with_only_an_address_typed_asks_before_closing(self):
        draft = self.new_draft(compose_step='recipient')
        self.assertEqual(self.field_key('recipient', 'sam@example.com', 'Escape'), 'draft_leave')
        self.assertEqual(draft.recipient, 'sam@example.com')
        self.assertEqual(app.handle_keyboard(app.navigation_key('Escape', 'draft_leave'), 'draft_leave'), 'email_draft')
        self.assertIs(app.email_draft, draft)

    def test_escape_always_leaves_even_when_the_box_holds_a_half_address(self):
        # A half typed address cannot be kept; Escape must still go back, never trap the user.
        self.new_draft(compose_step='recipient')
        self.assertNotEqual(self.field_key('recipient', 'sam', 'Escape'), 'email_draft')
        self.assertNotIn('could not understand', ' '.join(self.said))

    def test_control_r_and_undo_in_the_cc_box_are_not_taken_as_an_address(self):
        draft = self.new_draft(recipient='sam@example.com', compose_step='cc')
        for key in ('Ctrl+R', 'Ctrl+Z', 'Ctrl+Y'):
            with self.subTest(key=key):
                self.said.clear()
                self.field_key('cc', '', key)
                self.assertNotIn('could not understand one complete email address', ' '.join(self.said))
                self.assertEqual(draft.cc, [])
        for field in ('cc', 'bcc'):
            with self.subTest(field=field):
                draft.compose_step = field
                self.assertNotIn('could not understand', draft.process('read email draft'))
                self.assertNotIn('could not understand', draft.process('undo'))
                self.assertEqual(getattr(draft, field), [])

    def test_a_subject_that_starts_like_a_command_is_the_subject(self):
        # They went into the message body, or opened Help, and the subject stayed empty.
        for subject in ('Read this before Friday', 'Save the date', 'Use the side door', 'Undo the damage',
                        'Redo the roof', 'Name tags for Saturday', 'Start dictation class', 'Help with the move'):
            for typed in (True, False):
                with self.subTest(subject=subject, typed=typed):
                    draft = self.new_draft(recipient='sam@example.com', compose_step='subject')
                    mode = app.handle_keyboard(subject, 'email_draft') if typed else app.handle(subject, 'email_draft')
                    self.assertEqual(mode, 'email_draft')
                    self.assertEqual(draft.subject, subject)
                    self.assertEqual([p.text for p in draft.paragraphs if p.text], [])

    def test_whole_commands_still_work_in_the_subject_box(self):
        draft = self.new_draft(recipient='sam@example.com', compose_step='subject')
        app.handle_keyboard('Read subject', 'email_draft')
        self.assertEqual(self.last(), 'Subject: not entered.')
        app.handle_keyboard('Save draft', 'email_draft')
        self.assertIn('saved locally', self.last())
        self.assertEqual(app.handle_keyboard('help with writing email', 'email_draft'), 'help')
        self.assertEqual(draft.subject, '')

    def test_a_real_address_in_the_cc_box_is_still_recorded(self):
        draft = self.new_draft(recipient='sam@example.com', compose_step='cc')
        self.assertIn('CC recorded as ann@example.com', draft.process('ann@example.com'))


class AttachmentListKeyTests(test_attachment_voice.PlacesTestCase):
    def draft_list(self):
        for name in ('a.txt', 'b.txt'):
            (self.files / name).write_text(name, encoding='utf-8')
        draft = self.draft()
        draft.attach([self.files / 'a.txt', self.files / 'b.txt', self.files / 'letter.txt'])
        return self.press('Ctrl+L', 'email_draft')

    def test_delete_keeps_the_tags_on_the_other_files(self):
        # Before: Delete took the file off and silently cleared every tag.
        mode = self.draft_list()
        self.press('Space', mode)                      # a.txt
        self.press('End', mode); self.press('Space', mode)   # letter.txt
        self.press('Up', mode); self.press('Delete', mode)   # b.txt off
        self.assertIn('Removed b.txt.', self.last())
        self.press('Ctrl+Shift+T', mode)
        self.assertEqual(self.last(), '2 attachments tagged: a.txt, letter.txt.')

    def test_deleting_a_tagged_file_drops_only_its_tag(self):
        mode = self.draft_list()
        self.press('Space', mode); self.press('Down', mode); self.press('Space', mode)
        self.press('Delete', mode)                     # b.txt, tagged
        self.press('Ctrl+Shift+T', mode)
        self.assertEqual(self.last(), '1 attachment tagged: a.txt.')

    def test_attaching_another_file_from_the_list_keeps_the_tags(self):
        mode = self.draft_list()
        self.press('Space', mode)                      # a.txt
        (self.places['documents'] / 'notes.txt').write_text('notes', encoding='utf-8')
        self.assertEqual(app.handle('Attach notes from Documents', mode), mode)
        self.assertIn('Attached notes.txt', ' '.join(self.said[-2:]))
        self.press('Ctrl+Shift+T', mode)
        self.assertEqual(self.last(), '1 attachment tagged: a.txt.')

    def test_f1_from_the_list_goes_to_the_main_menu_without_saying_back_to_draft(self):
        mode = self.draft_list()
        self.said.clear()
        self.assertEqual(self.press('F1', mode), 'awake')
        self.assertNotIn('Back to email draft', ' '.join(self.said))
        self.assertIn('Main menu.', ' '.join(self.said))
        mode = self.press('L', self.opened_message())
        self.said.clear()
        self.assertEqual(self.press('F1', mode), 'awake')
        self.assertNotIn('Back to message', ' '.join(self.said))

    def test_the_alt_menu_has_every_tag_key_as_the_guide_says(self):
        # The guide: "Press Alt to open the attachments menu. It has the same choices."
        commands = {command for _, entries in screen_menus.MENUS['attachments'][1] for _, _, command in entries}
        for key in ('Space', 'Ctrl+A', 'Ctrl+Shift+T', 'Ctrl+Shift+A'):
            with self.subTest(key=key):
                self.assertIn(SCREEN_KEYS['attachments'][key], commands)
        mode = self.draft_list()
        self.assertEqual(self.press('Alt', mode), mode)
        self.assertIn('Attachments menu', ' '.join(self.said[-2:]))


class EmptyFolderWordsTests(test_attachment_voice.PlacesTestCase):
    def test_c_e_and_h_in_an_empty_folder_say_what_every_other_key_says(self):
        from mail_voice import MailSession
        import test_attachment_flows
        class Empty(test_attachment_flows.AttachmentMailbox):
            def list_messages(self, folder, cursor=None, limit=10): return [], None
        app.mail_session = MailSession('thunderbird', str(self.root / 'data'), Empty)
        app.mail_session.process('open inbox')
        empty = app.mail_session._empty_list()
        for key in ('C', 'E', 'H'):
            with self.subTest(key=key):
                self.said.clear()
                self.assertEqual(self.press(key, 'mailbox'), 'mailbox')
                self.assertEqual(self.said, [empty])


class GuideKeyTests(unittest.TestCase):
    def test_every_email_menu_path_in_the_guide_reaches_what_it_names(self):
        # The guide said Alt, 5, then 3 adds a contact. That opens Email drafts; Add contact is Alt, 5, then 5.
        import re
        from pathlib import Path
        guide = Path(__file__).with_name('START HERE - Veteran.txt').read_text(encoding='utf-8')
        groups = screen_menus.MENUS['mailbox'][1]
        found = 0
        for line in guide.splitlines():
            for path in re.finditer(r'(?:in the inbox|in email), press Alt, (\d), then (\d)', line):
                said = re.findall(r'"([^"]+)"', line[:path.start()])[0].lower()
                command = groups[int(path[1]) - 1][1][int(path[2]) - 1][2].replace(' {value}', '')
                with self.subTest(line=line[:60]):
                    self.assertTrue(said.startswith(command), (said, command))
                found += 1
        self.assertGreaterEqual(found, 4)


class LeaveDraftWordsTests(test_attachment_voice.PlacesTestCase):
    def test_f1_from_a_draft_never_sent_says_it_was_not_sent(self):
        # It said "Check whether it was sent before sending it again." for a draft never sent.
        draft = self.draft()
        self.assertEqual(self.press('F1', 'email_draft'), 'awake')
        said = ' '.join(self.said)
        self.assertIn('Email draft saved locally as Note. It has not been sent.', said)
        self.assertNotIn('Check whether it was sent', said)
        draft.last_attempt_hash = 'tried'
        self.said.clear()
        self.press('F1', 'email_draft')
        self.assertIn('Check whether it was sent before sending it again.', ' '.join(self.said))


if __name__ == '__main__':
    unittest.main()
