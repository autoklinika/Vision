"""Independent pre-merge regressions for modular thermal inspection."""
import json
import os
import struct
import unittest
from dataclasses import replace

from vision_core import GateError, State
from vision_core.archive import digest
from vision_modules.thermal import (
    CAPTURE, QA, ThermalFrame, ThermalInspectionSession, ThermalQualityPolicy
)
import test_thermal_inspection as thermal_tests


class ThermalPublicationAudit(unittest.TestCase):
    def setUp(self):
        self.fixture=thermal_tests.ThermalTests('runTest')
        self.fixture.setUp()
        x=self.fixture
        self.photo=x.through_s08()
        x.w.start(CAPTURE,CAPTURE)
        self.thermal=ThermalInspectionSession(x.w,x.archive)
        native=b'original thermal bytes from synthetic sensor'
        pixels=struct.pack('<4H',20,40,60,80)
        self.frame=ThermalFrame(
            x.ctx,CAPTURE,1000,x.ctx.frame_id,'thermal-frame',x.plan.digest,
            'relative_u16_le',2,2,native,pixels,digest(native),digest(pixels),
            'fixture-sensor','fixture-provenance',True,True,'cal')
    def tearDown(self):
        self.fixture.doCleanups()
        self.fixture.tearDown()

    def take_good_thermal(self):
        x=self.fixture
        self.thermal.accept_frame(self.frame)
        x.w.start(QA,QA)
        self.thermal.assess(ThermalQualityPolicy('policy',2,2,0,0,min_dynamic_range=10))
        x.w.start('S09','S09')
        x.w.complete(x.ev('S09'))
        x.w.start('S10','S10')

    def test_missing_thermal_map_blocks_session_archive(self):
        x=self.fixture
        self.take_good_thermal()
        file=x.archive.path/('thermal-map-'+self.frame.map_sha256+'.bin')
        file.unlink()
        with self.assertRaises(GateError):
            self.photo.archive_session()
        self.assertNotEqual(x.w.states['S10'],State.SUCCEEDED)
        self.assertFalse((x.archive.path/'manifest-v1.json').exists())

    def test_corrupt_thermal_native_blocks_session_archive(self):
        x=self.fixture
        self.take_good_thermal()
        file=x.archive.path/('thermal-native-'+self.frame.native_sha256+'.bin')
        file.chmod(0o600);file.write_bytes(b'corrupted native');file.chmod(0o400)
        with self.assertRaises(GateError):
            self.photo.archive_session()
        self.assertNotEqual(x.w.states['S10'],State.SUCCEEDED)
        self.assertFalse((x.archive.path/'manifest-v1.json').exists())

    def test_saturated_outlier_cannot_make_flat_relative_map_pass(self):
        x=self.fixture
        data=struct.pack('<4H',0,100,100,100)
        frame=replace(self.frame,thermal_map=data,map_sha256=digest(data))
        self.thermal.accept_frame(frame)
        x.w.start(QA,QA)
        with self.assertRaises(GateError):
            self.thermal.assess(ThermalQualityPolicy('policy',2,2,0.25,0,min_dynamic_range=50))
        self.assertEqual(x.w.states['S09'],State.BLOCKED)

class ThermalTypeAudit(unittest.TestCase):
    def test_numeric_frame_id_rejected(self):
        x=thermal_tests.ThermalTests('runTest')
        x.setUp()
        try:
            x.ps['thermal']=replace(x.ps['thermal'],frame_id=123)
            x.w=x.make()
            from vision_core.repeatability import create_plan
            x.plan=create_plan(x.ctx,x.ps,{'cal':'v1'},{},x.obs,1000,10,
                               min_coverage=.9,require_raw=True,extra_kinds=x.w.extra_kinds)
            x.ready()
            with self.assertRaises(GateError):
                x.session.accept_frame(replace(x.frame,frame_id=123))
        finally:
            x.tearDown()
