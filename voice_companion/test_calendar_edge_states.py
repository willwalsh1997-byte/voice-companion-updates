"""Calendar and Contacts in empty and edge states (bug sweep, November 4, 2026).

Each test here failed before its fix. The simulated Thunderbird and the fixed clock
(Monday, October 26, 2026, five hours behind UTC) are those of test_calendar_screen.
"""
import unittest
from unittest import mock

import calendar_screen
import companion as app
import contacts_screen
import pim_sources
import thunderbird_pim
from test_calendar_contacts_sources import TWO, ContactsSourceHarness
from test_calendar_screen import CalendarHarness


class CalendarRemovedWhileOpenTests(CalendarHarness):
    """The calendar on screen is removed in Thunderbird while Calendar is open, then the person
    refreshes. Before, Companion said "All calendars is no longer in Thunderbird"."""
    thunderbird_env = TWO

    def test_the_removed_calendar_is_named(self):
        mode = self.open()
        app.handle('show Family calendar', mode)
        real = thunderbird_pim.calendars
        with mock.patch.object(thunderbird_pim, 'calendars', lambda: [c for c in real() if c.get('id') != 'cal-family']):
            app.handle('refresh', mode)
        self.assertTrue(self.said().startswith('Family, Gmail, me@gmail.com is no longer in Thunderbird, '
                                               'so all calendars are shown.'), self.said())
        self.assertEqual(calendar_screen.SOURCE, pim_sources.ALL)


class ContactsRemovedWhileOpenTests(ContactsSourceHarness):
    def test_the_removed_address_book_is_named(self):
        mode = self.open()
        app.handle('show Personal Address Book', mode)
        real = thunderbird_pim.contacts

        def without_it():
            answer = real()
            return dict(answer, books=[b for b in answer['books'] if b.get('id') != 'book-personal'],
                        contacts=[c for c in answer['contacts'] if c.get('bookId') != 'book-personal'])
        with mock.patch.object(thunderbird_pim, 'contacts', without_it):
            app.handle('refresh contacts', mode)
        self.assertIn('Personal Address Book is no longer in Thunderbird, so all address books are shown.', self.said())
        self.assertNotIn('All address books is no longer', self.said())
        self.assertEqual(contacts_screen.SOURCE, pim_sources.ALL)


class LocalAddressBookFileTests(unittest.TestCase):
    """The contacts saved on this computer (address-book.json). Before, a damaged file was written
    over by the next new contact, a file saved by Notepad with a byte order mark read as empty,
    and a file Windows held for a moment was replaced by a one-contact list."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def book(self):
        from address_book import AddressBook
        return AddressBook(self.root)

    def test_a_byte_order_mark_is_not_damage(self):
        import json
        self.book().path.write_text('\ufeff' + json.dumps({'ann': {'name': 'Ann', 'address': 'ann@example.com'}}), encoding='utf-8')
        self.assertEqual(self.book().get('Ann')['address'], 'ann@example.com')

    def test_a_damaged_file_is_kept_before_a_new_contact_is_saved(self):
        damaged = '{"ann": {"name": "Ann", "address": "ann@example.com"}, "bo'
        self.book().path.write_text(damaged, encoding='utf-8')
        self.book().save('Bob', 'bob@example.com')
        self.assertEqual(self.book().get('Bob')['address'], 'bob@example.com')
        kept = self.root / 'address-book.damaged.json'
        self.assertEqual(kept.read_text(encoding='utf-8'), damaged)

    def test_a_file_that_cannot_be_read_now_is_never_written_over(self):
        book = self.book()
        book.save('Ann', 'ann@example.com')
        before = book.path.read_text(encoding='utf-8')
        real = type(book.path).read_text

        def held(path, *args, **kwargs):
            if path == book.path:
                raise PermissionError(13, 'The file is in use')
            return real(path, *args, **kwargs)
        with mock.patch.object(type(book.path), 'read_text', held):
            with self.assertRaises(ValueError) as caught:
                book.save('Bob', 'bob@example.com')
            with self.assertRaises(ValueError):
                book.delete('Ann')
        self.assertNotIn('Errno', str(caught.exception))
        self.assertIn('Try again', str(caught.exception))
        self.assertEqual(book.path.read_text(encoding='utf-8'), before)

    def test_a_file_that_cannot_be_written_says_so_plainly(self):
        book = self.book()
        with mock.patch('address_book.write_text_atomic', side_effect=OSError(28, 'No space left on device')):
            with self.assertRaises(ValueError) as caught:
                book.save('Bob', 'bob@example.com')
        self.assertNotIn('Errno', str(caught.exception))
        self.assertFalse(book.path.exists())


class LastContactOnThisComputerTests(ContactsSourceHarness):
    """Two accounts, "Saved on this computer" shown, and its only contact deleted. Before, the
    view jumped to every address book without a word, and later said "Saved on this computer is
    no longer in Thunderbird"."""

    def test_deleting_the_only_one_leaves_an_empty_list_here(self):
        from address_book import AddressBook
        AddressBook(self.root, 'me@gmail.com').save('Zed Local', 'zed@example.com')
        mode = self.open()
        app.handle('show saved on this computer', mode)
        self.assertTrue(self.said().startswith('Showing Saved on this computer. 1 contact. Zed Local'), self.said())
        app.handle('delete contact', mode)
        app.handle('yes', mode)
        self.assertEqual(self.said(), 'Deleted Zed Local. No contacts here. Press Control+L to show another address book, '
                                      'or Control+N to add a contact.')
        app.handle('where am i', mode)
        self.assertEqual(self.said(), 'Address manager. Showing Saved on this computer. No contacts here. Press Control+L to show '
                                      'another address book, or Control+N to add a contact.')
        app.handle('close contacts', mode)
        self.open()
        self.assertEqual(self.said(), 'Address manager. Showing Saved on this computer. No contacts here. Press Control+L to show '
                                      'another address book, or Control+N to add a contact.')
        self.assertNotIn('no longer in Thunderbird', self.everything_said())


class DatesThatDoNotExistTests(CalendarHarness):
    """"Add lunch February 30 at noon": before, the event was put on the day on screen at noon,
    named "February 30 lunch". "Move event to February 29 at 2" moved it to 2 PM the same day."""

    def test_adding_says_why_and_asks_again(self):
        mode = self.open()
        mode = app.handle('add event February 30 at 3 PM called Lunch', mode)
        self.assertEqual(mode, 'task_input')
        self.assertEqual(self.said(), 'There is no February 30. Say another date. Escape cancels.')
        self.assertIsNone(calendar_screen.PENDING)
        mode = app.handle('February 29 at 3 PM', mode)
        self.assertEqual(self.said(), 'February 29 is only in a leap year, such as 2028. Say the year too. Escape cancels.')
        mode = app.handle('tomorrow at 3 PM called Lunch', mode)
        self.assertEqual(mode, 'calendar')
        self.assertTrue(self.said().startswith('Add Lunch, Tomorrow, Tuesday, October 27, three PM'), self.said())

    def test_asking_about_a_day_that_does_not_exist_says_why(self):
        self.assertEqual(app.handle("What's on my calendar for February 30?", 'awake'), 'awake')
        self.assertEqual(self.said(), 'There is no February 30.')
        app.handle('What do I have on February 29?', 'awake')
        self.assertEqual(self.said(), 'February 29 is only in a leap year, such as 2028. Say the year too.')
        mode = self.open()
        for words in ("What's on February 30?", 'February 30.'):
            with self.subTest(words=words):
                self.assertEqual(app.handle(words, mode), 'task_input')
                self.assertEqual(self.said(), 'There is no February 30. Say another date. Escape cancels.')
                app.handle('escape', 'task_input')

    def test_moving_says_why_and_asks_again(self):
        mode = self.open()
        mode = app.handle('move event to February 30 at 2', mode)
        self.assertEqual(mode, 'task_input')
        self.assertEqual(self.said(), 'There is no February 30. Say another date. Escape cancels.')
        self.assertIsNone(calendar_screen.PENDING)


class NoCalendarTests(CalendarHarness):
    """Thunderbird has no calendars turned on (or only ones that cannot be changed)."""

    def setUp(self):
        super().setUp()
        self.stack.enter_context(mock.patch.object(thunderbird_pim, 'calendars', return_value=[]))
        self.stack.enter_context(mock.patch.object(thunderbird_pim, 'events', return_value={'events': [], 'failed': []}))

    def test_adding_from_the_main_menu_stays_on_the_main_menu(self):
        # Before, Calendar opened without a word, so the person did not know where they were.
        mode = app.handle('add appointment tomorrow at 3 PM called doctor', 'awake')
        self.assertEqual(mode, 'awake')
        self.assertEqual(self.said(), 'Thunderbird has no calendar that can be changed. Press F1 twice to learn how to add one.')

    def test_control_l_does_not_speak_of_one_email_account(self):
        mode = self.open()
        self.press('Ctrl+L', mode)
        self.assertEqual(self.said(), 'Thunderbird has no calendars turned on. Press F1 twice to learn how to add one.')


class EmptyContactsTests(ContactsSourceHarness):
    """No address books in Thunderbird and no contacts at all."""
    thunderbird_env = {}

    def setUp(self):
        super().setUp()
        self.stack.enter_context(mock.patch.object(
            thunderbird_pim, 'contacts', return_value={'books': [], 'contacts': [], 'failed': 0, 'failedBooks': []}))

    def test_control_l_does_not_speak_of_one_email_account(self):
        mode = self.open()
        self.press('Ctrl+L', mode)
        self.assertEqual(self.said(), 'All your contacts are shown.')

    def test_email_a_name_that_is_not_there_says_so(self):
        # Before, the Contacts screen answered with its list of commands.
        mode = self.open()
        app.handle('Email John.', mode)
        self.assertEqual(self.said(), 'No contact named john. No contacts yet. Press Control+N to add one, or say add contact.')


class AcrossMidnightDetailsTests(unittest.TestCase):
    """Enter on an event that ends after midnight, read on a day other than the day it starts.
    Before: "Party. Yesterday, Sunday, October 25, ten PM to one AM tomorrow." (it ended today)."""

    def test_the_end_is_the_next_day_not_tomorrow(self):
        from datetime import date, datetime
        import calendar_events
        from test_calendar_screen import ZONE
        with mock.patch.object(calendar_events, 'LOCAL_ZONE', ZONE):
            item = {'id': 'p', 'calendarId': 'c', 'calendar': 'Home', 'title': 'Party', 'allDay': False,
                    'start': calendar_events.utc_ms(datetime(2026, 10, 25, 22)), 'end': calendar_events.utc_ms(datetime(2026, 10, 26, 1))}
            event = calendar_events.from_thunderbird(item)
            self.assertEqual(event.details(date(2026, 10, 26)),
                             'Party. Yesterday, Sunday, October 25, ten PM to one AM the next day. Calendar: Home.')
            self.assertEqual(event.details(date(2026, 10, 25)),
                             'Party. Today, Sunday, October 25, ten PM to one AM tomorrow. Calendar: Home.')
            # The delete question names the day, so "tomorrow" there is only right when that day is today.
            clock = mock.Mock(CLOCK=lambda: datetime(2026, 10, 23, 9))
            with mock.patch.object(calendar_screen, 'DAY', date(2026, 10, 25)):
                self.assertEqual(calendar_screen.delete_question(clock, event),
                                 'Delete Party, Sunday, October 25, ten PM to one AM the next day? Say Yes or No. Escape keeps it.')


if __name__ == '__main__':
    unittest.main()
