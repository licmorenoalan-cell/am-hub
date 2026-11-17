import unittest
from am_hub_payment_notice import notice_items, calendar_attachments


class NoticeValidationContextTests(unittest.TestCase):
    def setUp(self):
        self.pay = dict(impuesto="Ingresos Brutos", periodo="10/2026",
                        resultado="A pagar", monto="100,00", vencimiento="")
        self.credit = dict(impuesto="IVA", periodo="10/2026",
                           resultado="Saldo a favor", monto="200,00", vencimiento="")
        self.fields = dict(cliente="PRUEBA", email="test@example.com",
                           avisos=[self.pay, self.credit])

    def test_missing_payable_date_identifies_correct_notice(self):
        with self.assertRaisesRegex(ValueError, r"Aviso 1 · Ingresos Brutos · 10/2026: Vencimiento inválido"):
            notice_items(self.fields)

    def test_context_follows_reordered_items(self):
        self.fields["avisos"].reverse()
        with self.assertRaisesRegex(ValueError, r"Aviso 2 · Ingresos Brutos · 10/2026: Vencimiento inválido"):
            notice_items(self.fields)

    def test_correct_date_preserves_credit_without_calendar(self):
        self.pay["vencimiento"] = "17/11/2026"
        self.assertEqual(len(notice_items(self.fields)), 2)
        self.assertEqual(len(calendar_attachments(self.fields)), 1)
        self.assertEqual(self.credit["vencimiento"], "")

    def test_recipient_still_required(self):
        self.pay["vencimiento"] = "17/11/2026"
        self.fields["email"] = ""
        with self.assertRaisesRegex(ValueError, "destinatarios válidos"):
            notice_items(self.fields)

    def test_mixed_ui_has_one_editable_date_and_no_credit_date_warning(self):
        import sys
        from unittest.mock import MagicMock, patch
        from am_hub_payment_notice import render_payment_notice
        docs = []
        for name in ("CM03", "IVA"):
            doc = MagicMock()
            doc.name = name + ".pdf"
            doc.getvalue.return_value = b"%PDF-" + name.encode()
            docs.append(doc)
        ui = MagicMock()
        ui.session_state = {}
        ui.secrets = {}
        ui.file_uploader.return_value = docs
        ui.button.return_value = False
        ui.checkbox.return_value = True
        ui.selectbox.side_effect = lambda label, options, **kw: options[kw.get("index", 0)]
        date_fields = []
        def inp(label, value="", **kw):
            if label.startswith("Vencimiento /"):
                date_fields.append(kw["key"])
                return "17/11/2026"
            return value
        ui.text_input.side_effect = inp
        def parse(text):
            item = self.pay if "CM03" in text else self.credit
            return dict(item, cuit="30123456781", advertencias=["vencimiento: no identificado de forma única; completar/revisar."])
        with patch.dict(sys.modules, {"streamlit": ui}), patch("am_hub_payment_notice.pdf_text", side_effect=lambda raw: "DJ MENSUAL - CM03" if b"CM03" in raw else "IVA SIMPLE"), patch("am_hub_notice_extract.parse_ddjj", side_effect=parse):
            render_payment_notice("PRUEBA", {"cuit": "30123456781", "email_destinatarios": "test@example.com"})
        self.assertEqual(len(date_fields), 1)
        ui.error.assert_not_called()
        warnings = [c.args[0] for c in ui.caption.call_args_list if c.args[0].startswith("vencimiento:")]
        self.assertEqual(len(warnings), 1)
        text = ui.text_area.call_args.kwargs["value"]
        self.assertIn("17/11/2026", text)
        self.assertIn("Saldo a favor", text)
        calendars = [c.kwargs.get("file_name", "") for c in ui.download_button.call_args_list if c.kwargs.get("file_name", "").endswith(".ics")]
        self.assertEqual(len(calendars), 1)
