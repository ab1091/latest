import unittest

from api.sms.router import _is_contextual_opt_out_reply


OPT_OUT_PROMPT = (
    "Hello! Would you rather call or text? "
    "Reply NO THANKS to opt out of future text messages."
)


class ContextualOptOutTests(unittest.TestCase):
    def test_decline_variants_opt_out_after_explicit_prompt(self):
        for reply in ("No", "N", "NO!", "No thanks", "no thank you", "Nope", "Nah", "Not interested", "Sorry", "Sorry no", "No sorry", "Sorry not interested"):
            with self.subTest(reply=reply):
                self.assertTrue(_is_contextual_opt_out_reply(reply, OPT_OUT_PROMPT))

    def test_bare_no_is_not_global_opt_out(self):
        self.assertFalse(_is_contextual_opt_out_reply("No", "Do you smoke?"))
        self.assertFalse(_is_contextual_opt_out_reply("No", "Would you like a phone call?"))

    def test_unrelated_reply_does_not_opt_out(self):
        self.assertFalse(_is_contextual_opt_out_reply("Text please", OPT_OUT_PROMPT))
        self.assertFalse(_is_contextual_opt_out_reply("Call me", OPT_OUT_PROMPT))


if __name__ == "__main__":
    unittest.main()
