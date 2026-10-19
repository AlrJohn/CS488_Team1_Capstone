"""Per-carton cumulative ledger for explicit transfer events, never frame totals."""
import math

COLORS=('red','green','blue')

class PackLedger:
    def __init__(self,recipe=None):
        self.recipe=self._quantities(recipe or dict.fromkeys(COLORS,4))
        if not sum(self.recipe.values()):raise ValueError('Recipe must contain at least one can')
        self.box=1
        self.counts=dict.fromkeys(COLORS,0)
        self.events=[]
        self.reviews=[]
        self._seen={}
        self._transactions=[]

    @staticmethod
    def _quantities(value):
        if not isinstance(value,dict) or set(value)-set(COLORS):raise ValueError('Quantities use red, green and blue only')
        result={c:value.get(c,0) for c in COLORS}
        if any(type(n) is not int or n<0 for n in result.values()):raise ValueError('Can quantities must be nonnegative integers')
        return result

    @staticmethod
    def _time(timestamp):
        if isinstance(timestamp,bool) or not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp) or timestamp<0:
            raise ValueError('Timestamp must be finite nonnegative seconds')

    def _log(self,kind,timestamp,**detail):
        self._time(timestamp)
        event={'box':self.box,'kind':kind,'seconds':timestamp,'counts':dict(self.counts),**detail}
        self.events.append(event)
        return event

    def review(self,message,timestamp):
        if not isinstance(message,str) or not message:raise ValueError('Review needs a message')
        if message not in self.reviews:
            self.reviews.append(message)
            self._log('review',timestamp,message=message)

    def apply(self,event_id,quantities,direction,timestamp,*,box=None,evidence=None):
        """Apply once: +1 assumed-packed pick, -1 defect, 0 uncounted rejection."""
        self._time(timestamp)
        if not isinstance(event_id,str) or not event_id:raise ValueError('Transfer needs a unique event ID')
        if type(direction) is not int or direction not in (-1,0,1):raise ValueError('Direction must be +1, -1 or 0')
        quantities=self._quantities(quantities)
        if not sum(quantities.values()):raise ValueError('Transfer must contain at least one can')
        box=self.box if box is None else box
        if type(box) is not int or box!=self.box:raise ValueError('Transfer belongs to a different box')
        key=(box,event_id);payload=(direction,tuple(quantities[c] for c in COLORS))
        if key in self._seen:
            previous_payload,event=self._seen[key]
            if previous_payload!=payload:raise ValueError('Event ID reused for a different transfer')
            return event
        updated={c:self.counts[c]+direction*quantities[c] for c in COLORS}
        if any(n<0 for n in updated.values()):
            self.review('Defect removal exceeds counted cans; verify this box before continuing',timestamp)
            event=self._log('rejected_defect',timestamp,event_id=event_id,quantities=quantities,evidence=evidence)
        else:
            self.counts=updated
            event=self._log({1:'pick',-1:'defect',0:'defect_excluded'}[direction],timestamp,event_id=event_id,
                quantities=quantities,direction=direction,evidence=evidence)
            if direction:self._transactions.append(event)
        self._seen[key]=(payload,event)
        return event

    def undo(self,timestamp):
        self._time(timestamp)
        if not self._transactions:return None
        previous=self._transactions[-1]
        updated={c:self.counts[c]-previous['direction']*previous['quantities'][c] for c in COLORS}
        if any(n<0 for n in updated.values()):
            self.review('Cannot undo this transfer without negative counts; verify the box',timestamp)
            return None
        self._transactions.pop();self.counts=updated
        # Keep its event ID in _seen: another delivery of the same event must
        # not re-add an explicitly undone transfer.
        return self._log('undo',timestamp,reference_event_id=previous['event_id'])

    def acknowledge_review(self,timestamp):
        self._log('manual_count_verified',timestamp,previous_reviews=list(self.reviews))
        self.reviews.clear()

    def resolve_review(self,message,timestamp):
        """Resolve only a specific recovered candidate; preserve other reviews."""
        if message in self.reviews:
            self.reviews.remove(message)
            self._log('review_resolved',timestamp,message=message)

    def snapshot(self,*,pending=False):
        if self.reviews:status='REVIEW'
        elif any(self.counts[c]>self.recipe[c] for c in COLORS):status='OVER TARGET'
        elif self.counts!=self.recipe:status='IN PROGRESS'
        elif pending:status='WAIT'
        else:status='RECIPE REACHED'
        return {'box':self.box,'counts':dict(self.counts),'recipe':dict(self.recipe),
            'total':sum(self.counts.values()),'target_total':sum(self.recipe.values()),
            'status':status,'ready':status=='RECIPE REACHED','reviews':list(self.reviews)}

    def new_box(self,timestamp):
        closed=self.snapshot()
        self._log('box_closed',timestamp,final=closed)
        self.box+=1;self.counts=dict.fromkeys(COLORS,0)
        self.reviews.clear();self._transactions.clear()
        self._log('new_box',timestamp)
        return closed
