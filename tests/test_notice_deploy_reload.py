import unittest,sys,types
from unittest.mock import patch,MagicMock

BLOCK = "# Streamlit may retain imported modules while app.py reruns after a deploy.\n# Reload only a stale module, not the user's session data or uploaded PDFs.\nimport importlib\nimport am_hub_payment_notice as notice_module\nimport am_hub_notice_extract as extract_module\nif getattr(notice_module, \"PARSER_REVISION\", \"\") != \"unified-ddjj-vep-v3\":\n    notice_module = importlib.reload(notice_module)\nif getattr(extract_module, \"EXTRACTOR_REVISION\", \"\") != \"iva-simple-cm03-v3\":\n    extract_module = importlib.reload(extract_module)\nif (getattr(notice_module, \"PARSER_REVISION\", \"\") != \"unified-ddjj-vep-v3\"\n        or getattr(extract_module, \"EXTRACTOR_REVISION\", \"\") != \"iva-simple-cm03-v3\"):\n    st.warning(\"Actualización de avisos en curso. Recargá en unos segundos antes de cargar documentos.\")\n    return\nrender_payment_notice = notice_module.render_payment_notice\nst.caption(\"Avisos fiscales · versión 2026.11.16-3 · cargador único DDJJ / VEP\")"
class NoticeDeployTests(unittest.TestCase):
 def test_stale_modules_reload_without_clearing_session(self):
  notice=types.ModuleType('am_hub_payment_notice');notice.PARSER_REVISION='old';notice.render_payment_notice=lambda:None
  extract=types.ModuleType('am_hub_notice_extract');extract.EXTRACTOR_REVISION='old'
  ui=MagicMock();ui.session_state={'uploaded':'keep'}
  def refresh(module):
   if module is notice:module.PARSER_REVISION='unified-ddjj-vep-v3'
   else:module.EXTRACTOR_REVISION='iva-simple-cm03-v3'
   return module
  scope={'st':ui};exec('def run():\n'+''.join('    '+line+'\n' for line in BLOCK.splitlines()),scope)
  with patch.dict(sys.modules,{'am_hub_payment_notice':notice,'am_hub_notice_extract':extract}),patch('importlib.reload',side_effect=refresh) as reload:
   scope['run']();self.assertEqual(reload.call_count,2)
   scope['run']();self.assertEqual(reload.call_count,2)
  self.assertEqual(ui.session_state,{'uploaded':'keep'});ui.warning.assert_not_called();self.assertIn('2026.11.16-3',ui.caption.call_args.args[0])
