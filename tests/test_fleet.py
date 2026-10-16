import copy
import json
import unittest
from sqlalchemy import create_engine, text
from am_hub_fleet import CLIENT, ASSETS, authorized, initialize, load, save, validate

class FleetTest(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        initialize(self.engine)
        self.session=dict(logged_in=True,username='SMPA',role='cliente',cliente=CLIENT)
        self.payload=load(self.engine)['payload']
    def test_scope(self):
        self.assertTrue(authorized(self.session,[]))
        self.assertFalse(authorized(dict(self.session,cliente='Otro'),[]))
        self.assertFalse(authorized(dict(self.session,logged_in=False),[]))
        with self.assertRaises(PermissionError):
            save(self.engine,dict(self.session,cliente='Otro'),[],{})
    def test_save_conflict_and_retry(self):
        req=dict(request='a',revision=0,payload=self.payload)
        save(self.engine,self.session,[],req)
        save(self.engine,self.session,[],req)
        self.assertEqual(load(self.engine)['revision'],1)
        with self.assertRaises(ValueError):
            save(self.engine,self.session,[],dict(req,request='b'))
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM fleet_sandbox_history')).scalar(),1)
    def test_invalid(self):
        p=copy.deepcopy(self.payload);p['movements'][0]['paid']=1e14
        with self.assertRaises(ValueError): validate(p)
        p=copy.deepcopy(self.payload);p['movements'][0]['vehicle']='missing'
        with self.assertRaises(ValueError): validate(p)
        p=copy.deepcopy(self.payload);p['activity'][0]['days']=50
        with self.assertRaises(ValueError): validate(p)
        p=copy.deepcopy(self.payload);p['opening']['date']='2026-02-30'
        with self.assertRaises(ValueError): validate(p)
    def test_reinitialize_preserves_changes(self):
        self.payload['vehicles'][0]['driver']='Prueba compartida'
        save(self.engine,self.session,[],dict(request='a',revision=0,payload=self.payload))
        initialize(self.engine)
        self.assertEqual(load(self.engine)['payload']['vehicles'][0]['driver'],'Prueba compartida')
