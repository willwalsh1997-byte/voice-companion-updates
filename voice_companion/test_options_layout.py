"""Every Options page fits above the OK and Cancel row (0.2.174).

A new Email setting pushed "Add an email account" onto the OK and Cancel buttons,
where it could not be reached."""
import unittest

import settings_model
from native_settings import settings_bottom, settings_step

CONTEXTS = (
    {'engines': ('windows', 'espeak', 'ai'), 'windows_voices': ('Voice',), 'espeak_voices': ('en',),
     'ai_voices': ('coral',), 'accounts': ('a@example.com', 'b@example.com'), 'podcasts': ('Show',),
     'podcast_limits': {}},
    {'engines': ('windows',), 'windows_voices': (), 'espeak_voices': (), 'ai_voices': (),
     'accounts': (), 'podcasts': (), 'podcast_limits': {}},
)


class OptionsLayoutTests(unittest.TestCase):
    def test_every_page_fits_above_the_ok_row(self):
        for context in CONTEXTS:
            for category in settings_model.CATEGORIES:
                with self.subTest(category=category):
                    fields = settings_model.fields(category, context)
                    step = settings_step(fields)
                    self.assertGreaterEqual(step, 48 if any(f.kind not in ('check', 'action') for f in fields) else 34)
                    self.assertLessEqual(settings_bottom(fields, step), 510,
                                         category + ' has too many settings for one page')

    def test_check_boxes_never_overlap(self):
        # A check box is 27 pixels high and has no label above it.
        fields = settings_model.fields('My menu', {})
        self.assertGreaterEqual(settings_step(fields), 30)


if __name__ == '__main__':
    unittest.main()
