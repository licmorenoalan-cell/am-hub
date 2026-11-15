import unittest
from am_hub_tasks import (categoria_visual_tarea, opciones_categorias_tareas,
 resolver_categoria_tarea, es_categoria_impositiva, construir_siguiente_ocurrencia)

class TaskCategoriesTests(unittest.TestCase):
 def test_laborales_heredadas(self):
  self.assertEqual(categoria_visual_tarea('', 'Sueldos - CITTADINI'), 'SUELDOS')
  self.assertEqual(categoria_visual_tarea('Bandeja de entrada', 'Boletas sindicales - BERG'), 'BOLETAS SINDICALES')
  self.assertEqual(categoria_visual_tarea('Laboral', 'Liquidación de sueldos — ARLEO'), 'SUELDOS')
  self.assertEqual(categoria_visual_tarea('Comercial', 'Sueldos propuesta'), 'Comercial')
 def test_no_calendario_fiscal(self):
  for cat in ['SUELDOS','BOLETAS SINDICALES']:
   self.assertFalse(es_categoria_impositiva(cat))
   result=construir_siguiente_ocurrencia(dict(id='1', categoria=cat, tarea=cat, fecha_limite='2026-11-10', frecuencia='Mensual'), 'test')
   self.assertEqual(result['fecha_limite'],'2026-12-10')
 def test_catalogo_sin_duplicados(self):
  opts=opciones_categorias_tareas(['sueldos',' IVA ','  Mi   categoría  ','mi categoría'])
  self.assertEqual(opts.count('SUELDOS'),1)
  self.assertEqual(opts.count('IVA'),1)
  self.assertEqual(opts.count('Mi categoría'),1)
 def test_creacion_y_validacion(self):
  opts=opciones_categorias_tareas(['Clientes'])
  self.assertEqual(resolver_categoria_tarea('Crear nueva categoría',' clientes ',opts),'Clientes')
  self.assertEqual(resolver_categoria_tarea('Crear nueva categoría','Nueva',opts),'Nueva')
  self.assertEqual(resolver_categoria_tarea('Sin categoría','',opts),'')
  self.assertEqual(resolver_categoria_tarea('SUELDOS','',opts),'SUELDOS')
  for choice,new in [('Crear nueva categoría',''),('IVA','Nueva'),('Crear nueva categoría','x'*81),('Crear nueva categoría','Sin categoría')]:
   with self.assertRaises(ValueError): resolver_categoria_tarea(choice,new,opts)

class CategoryFormTests(unittest.TestCase):
 def test_create_custom_category_in_one_submission_and_repeat(self):
  from pathlib import Path
  import textwrap
  from streamlit.testing.v1 import AppTest
  source=Path('app.py').read_text()
  start=source.index('                catalogo_categorias = opciones_categorias_tareas(')
  end=source.index('\n            with col_2:',start)
  snippet=textwrap.dedent(source[start:end])
  app=AppTest.from_string('import streamlit as st\nimport pandas as pd\nfrom am_hub_tasks import opciones_categorias_tareas, resolver_categoria_tarea\ntareas_vista_base=pd.DataFrame({"_categoria_visual":["IVA","Clientes"]})\nwith st.form("f"):\n'+textwrap.indent(snippet,'    ')+'\n    if st.form_submit_button("Crear"):\n        st.session_state["categoria"] = resolver_categoria_tarea(categoria_elegida, categoria_nueva, catalogo_categorias)\n').run()
  self.assertFalse(app.exception)
  self.assertIn('SUELDOS',app.selectbox[0].options)
  self.assertIn('BOLETAS SINDICALES',app.selectbox[0].options)
  app.selectbox[0].select('Crear nueva categoría'); app.text_input[0].set_value(' Auditoría ')
  app.button[0].click().run()
  self.assertEqual(app.session_state['categoria'],'Auditoría')
  app.button[0].click().run()
  self.assertEqual(app.session_state['categoria'],'Auditoría')
  self.assertFalse(app.exception)
