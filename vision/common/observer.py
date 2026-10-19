"""V4 observer definitions extracted without changing their count/identity logic."""
from collections import Counter, defaultdict
from types import SimpleNamespace
from .vendor.trackers.byte_tracker import BYTETracker
from .instance_memory import InstanceMemory, clipped_edges
IterableSimpleNamespace=SimpleNamespace
TRACKER={'track_high_thresh': 0.25, 'track_low_thresh': 0.1, 'new_track_thresh': 0.25, 'track_buffer': 30, 'match_thresh': 0.8, 'fuse_score': False}

def eligible(history,frame,span=5,required=3):
    """Only actual observed frames count; gaps/Kalman predictions never add hits."""
    result={}
    for identity,observations in history.items():
        recent=[r for r in observations if frame-span+1<=r["index"]<=frame]
        if len({r["index"] for r in recent})>=required:
            votes=Counter(r["color"] for r in recent)
            winner=max(votes,key=votes.get)
            result[identity]={"observations":len(recent),"color":winner if winner!="unknown" and votes[winner]>=required else "unknown",
                              "votes":dict(votes)}
    return result

class Observer:
    def __init__(self, tracker_parameters=None):
        self.tracker = BYTETracker(IterableSimpleNamespace(**(TRACKER if tracker_parameters is None else tracker_parameters)))
        self.history = defaultdict(list)
        self.index = 0

    def update(self, boxes, labels, now):
        self.index += 1
        self.tracker.update(boxes)
        current = [t for t in self.tracker.tracked_stracks
                   if t.frame_id == self.tracker.frame_id]
        identities = {int(t.idx): int(t.track_id) for t in current}
        if len(identities) != len(current):
            raise RuntimeError("Tracker assigned a detection more than once")
        observed = []
        for i, box in enumerate(boxes.xyxy):
            identity = identities.get(i)
            item = {"index": self.index, "timestamp_seconds": now,
                    "detection": i, "track_id": identity, "color": labels[i],
                    "xyxy_roi": box.tolist(), "confidence": float(boxes.conf[i])}
            observed.append(item)
            if identity is not None:
                self.history[identity].append(item)
        for identity in list(self.history):
            self.history[identity] = [r for r in self.history[identity]
                                     if r["index"] >= self.index - 4]
            if not self.history[identity]:
                del self.history[identity]
        return observed, eligible(self.history, self.index)

live=SimpleNamespace(Observer=Observer)

class RoiObserver:
    """Use ByteTrack hints plus physical-instance history across identity changes."""
    def __init__(self,parameters,*,clear_frames=3,clear_seconds=.35):
        self.inner=live.Observer(parameters);self.memory=InstanceMemory();self.index=0;self.group=1
        self.clear_frames=clear_frames;self.clear_seconds=clear_seconds
        self.empty_frames=0;self.empty_since=None;self.cleared=False

    def update(self,boxes,labels,now):
        self.index+=1
        raw,_=self.inner.update(boxes,labels,now)
        observed,confirmed=self.memory.update(raw,now,self.index)
        h,w=boxes.orig_shape
        busy=False
        for item in observed:
            box=item['xyxy_roi'];cx=(box[0]+box[2])/2/w;cy=(box[1]+box[3])/2/h
            item['inside_roi']=0<=cx<=1 and 0<=cy<=1
            item['roi_group']=self.group;item['roi_edges']=clipped_edges(box,(h,w))
            color=confirmed.get(item['track_id'],{}).get('color')
            if item['inside_roi'] and (item['color'] in ('red','green','blue') or color in ('red','green','blue')):busy=True
        if not busy:
            if not self.empty_frames:self.empty_since=now
            self.empty_frames+=1
            if not self.cleared and self.empty_frames>=self.clear_frames and now-self.empty_since>=self.clear_seconds:
                self.memory.retire_lost(self.index);self.group+=1;self.cleared=True
        else:self.empty_frames=0;self.empty_since=None;self.cleared=False
        return observed,confirmed
