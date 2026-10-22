"""Behavioral checks for the shared V4 rules; no private footage is required."""
from pathlib import Path
import json
import sys
import unittest
import numpy as np

VISION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VISION))
from common.color_analysis import sample_colors
from common.geometry import Boxes
from common.instance_memory import InstanceMemory
from common.instance_quality import deduplicate
from common.observer import RoiObserver
from common.pack_crossing import RoiCounter, left_defect_boundary
from common.pack_ledger import PackLedger
from common.settings import Settings


class RuntimeTests(unittest.TestCase):
    def test_color_uses_can_mask_instead_of_box_background(self):
        settings = Settings.load(VISION/'configs/colors.json')
        frame = np.full((100,100,3),(0,240,0),np.uint8)
        frame[20:80,40:60] = (240,0,0)
        masks = np.zeros((1,100,100),np.uint8)
        masks[0,20:80,40:60] = 1
        labels, _ = sample_colors(frame,masks,settings)
        self.assertEqual(labels,['blue'])

    def test_duplicate_filter_keeps_touching_distinct_cans(self):
        masks = np.zeros((3,60,100),np.uint8)
        masks[0,10:50,5:45] = 1
        masks[1] = masks[0]
        masks[2,10:50,45:85] = 1
        keep, removed = deduplicate(masks,['blue']*3,[.9,.8,.85])
        self.assertEqual(keep,[0,2])
        self.assertEqual(len(removed),1)

    def test_missing_images_do_not_create_confirmation_hits(self):
        memory = InstanceMemory()
        last = None
        for index in range(1,6):
            observations = [] if index in (2,4) else [dict(track_id=1,color='red',xyxy_roi=[30,20,50,70],confidence=.9)]
            _, confirmed = memory.update(observations,index/30,index)
            last = confirmed
            if index < 3:
                self.assertFalse(any(v['color']=='red' for v in confirmed.values()))
        self.assertEqual(last[1]['color'],'red')
        self.assertEqual(last[1]['observations'],3)

    def test_conflicting_color_tie_stays_unknown(self):
        memory = InstanceMemory()
        for index,color in enumerate(['red','blue','red','blue'],1):
            _, confirmed = memory.update([dict(track_id=1,color=color,xyxy_roi=[30,20,50,70],confidence=.9)],index/30,index)
            if index==2:
                self.assertEqual(confirmed[1]['color'],'unknown')
            if index==3:
                self.assertEqual(confirmed[1]['color'],'red')
        self.assertEqual(confirmed[1]['color'],'unknown')

    def test_unknown_color_and_expired_hits_do_not_confirm(self):
        memory = InstanceMemory()
        for index in range(1,7):
            color = 'red' if index in (1,6) else 'unknown'
            _, confirmed = memory.update([dict(track_id=1,color=color,xyxy_roi=[30,20,50,70],confidence=.9)],index/30,index)
            self.assertFalse(any(v['color']=='red' for v in confirmed.values()))

    def test_changed_raw_tracker_id_reconnects_one_instance(self):
        memory = InstanceMemory()
        ids = []
        for index,raw_id in enumerate([1,1,7,7],1):
            observed,_ = memory.update([dict(track_id=raw_id,color='blue',xyxy_roi=[30+index,20,50+index,70],confidence=.9)],index/30,index)
            ids.append(observed[0]['track_id'])
        self.assertEqual(len(set(ids)),1)

    def test_same_identity_admits_once_and_ordinary_disappearance_keeps_count(self):
        ledger = PackLedger()
        counter = RoiCounter((100,100),ledger,reject_boundary=left_defect_boundary(.15))
        for index in range(1,7):
            obs = [dict(track_id=1,color='red',xyxy_roi=[40,20,60,70],confidence=.9)] if index<5 else []
            counter.update(obs,{1:dict(color='red')} if index>=3 else {},index,index/30)
        self.assertEqual(ledger.counts,dict(red=1,green=0,blue=0))

    def test_left_crossing_subtracts_previously_counted_can(self):
        ledger = PackLedger()
        counter = RoiCounter((100,100),ledger,reject_boundary=left_defect_boundary(.3))
        for index,cx in enumerate([65,65,65,30,10,10],1):
            obs = [dict(track_id=1,color='green',xyxy_roi=[cx-5,20,cx+5,70],confidence=.9)]
            counter.update(obs,{1:dict(color='green')},index,index/30)
        self.assertEqual(ledger.counts['green'],0)
        self.assertEqual([e['kind'] for e in ledger.events],['pick','defect'])

    def test_defect_side_first_appearance_does_not_add_or_subtract(self):
        ledger = PackLedger()
        counter = RoiCounter((100,100),ledger,reject_boundary=left_defect_boundary(.3))
        for index in range(1,4):
            counter.update([dict(track_id=1,color='blue',xyxy_roi=[3,20,15,70],confidence=.9)],
                           {1:dict(color='blue')},index,index/30)
        self.assertEqual(sum(ledger.counts.values()),0)
        self.assertEqual(ledger.events[0]['kind'],'defect_excluded')

    def test_two_observation_confirmation_and_pair_admission_together(self):
        observer = RoiObserver(json.loads((VISION/'configs/runtime.json').read_text())['tracker'])
        ledger = PackLedger()
        counter = RoiCounter((100,100),ledger,reject_boundary=left_defect_boundary(.15))
        for index in range(1,3):
            data = np.array([[30,20,45,70,.9,0],[60,20,75,70,.9,0]],np.float32)
            observed,confirmed = observer.update(Boxes(data,(100,100)),['blue','blue'],index/30)
            counter.update(observed,confirmed,index,index/30)
            self.assertEqual(ledger.counts['blue'],0 if index==1 else 2)
        self.assertEqual(ledger.counts['blue'],2)

    def test_over_target_is_visible_and_new_box_clears_counts(self):
        ledger = PackLedger()
        for index in range(5):
            ledger.apply(str(index),{'red':1},1,index)
        self.assertEqual(ledger.counts['red'],5)
        self.assertEqual(ledger.snapshot()['status'],'OVER TARGET')
        ledger.new_box(6)
        self.assertEqual(ledger.box,2)
        self.assertEqual(sum(ledger.counts.values()),0)


if __name__ == '__main__':
    unittest.main()
