"""Mouse/keyboard color setup using the same camera and model as the counter."""
from dataclasses import asdict
import time

import cv2
import numpy as np

from common.color_analysis import sample_colors
from common.color_calibration import (COLORS, Verification, collect_pixels, fit_profile,
                                      save_profile, select_seed)
from common.geometry import restore_view
from common.instance_memory import context_area
from common.settings import Settings
from .camera import measure_delivery

WINDOW = 'Yards color setup'
PALETTE = {'red': (30, 40, 230), 'green': (30, 190, 30), 'blue': (230, 100, 30),
           'unknown': (150, 150, 150)}


class CalibrationSession:
    """Keep collection and fresh verification separate from pack counting."""

    def __init__(self, base, policy):
        self.base, self.policy = base, policy
        self.original_settings = Settings.from_dict(base)
        self.samples = {name: [] for name in COLORS}
        self.seeds, self.verification, self.attempts = {}, {}, []
        self.profile, self.settings, self.fit_report = None, None, {}
        self.phase, self.target, self.active = 'collect', 'red', None
        self.started, self.last_sample = 0., float('-inf')
        self.message = 'Show one RED can in the yellow area, then click its colored label.'

    def can_save(self):
        """Allow saving only when the fitted profile has passed all colors."""
        return (self.profile is not None and not self.active and set(self.verification) == set(COLORS)
                and all(item.summary()['passed'] for item in self.verification.values()))

    def set_seed(self, frame, mask, point):
        """Choose the label color, not white printing or another detected can."""
        if self.phase != 'collect' or self.active:
            raise ValueError('Use Recollect before choosing a new label patch.')
        if mask is None:
            raise ValueError('Show exactly one detected can inside the yellow area.')
        seed = select_seed(frame, mask, point, self.policy)
        self.seeds[self.target] = seed
        self.samples[self.target] = []
        self.message = self.target.upper() + ' patch selected. Press Collect and turn the can slowly.'

    def action(self, name, now):
        """Apply a button action; return save/cancel when the screen should exit."""
        if name == 'quit':
            return 'cancel'
        if self.active:
            raise ValueError('Finish this short capture first, or quit to cancel.')
        if name in COLORS:
            self.target = name
            self.message = ('Click a colored label patch, then Collect.' if self.phase == 'collect'
                            else 'Use fresh movements of the selected can, then press Verify.')
        elif name == 'collect':
            if self.phase != 'collect' or self.target not in self.seeds:
                raise ValueError('Click a colored patch on the selected can first.')
            self.samples[self.target] = []
            self.active = 'collect'
            self.started, self.last_sample = now, float('-inf')
            self.message = 'Collecting: turn the can slowly; show the front and colored sides.'
        elif name == 'fit':
            profile, report = fit_profile(self.base, self.samples, self.seeds, self.policy)
            self.profile, self.fit_report = profile, report
            self.settings = Settings.from_dict(profile)
            self.phase, self.target, self.verification = 'verify', 'red', {}
            self.message = 'Profile fitted. Show RED again with NEW movements; press Verify.'
        elif name == 'verify':
            if self.phase != 'verify' or self.settings is None:
                raise ValueError('Collect all three colors and Fit first.')
            self.verification[self.target] = Verification(self.target, self.policy)
            self.active = 'verify'
            self.started, self.last_sample = now, float('-inf')
            self.message = 'Verifying: move/turn the selected can. Unknown and wrong colors count as failures.'
        elif name == 'redo':
            self.samples[self.target] = []
            self.seeds.pop(self.target, None)
            self.profile, self.settings, self.verification = None, None, {}
            self.phase = 'collect'
            self.message = 'Recollect ' + self.target.upper() + '. All color verifications will need repeating.'
        elif name == 'save':
            if not self.can_save():
                raise ValueError('Pass fresh verification for red, green and blue before saving.')
            return 'save'
        return None

    def observe(self, frame, mask, predicted, now):
        """Sample spaced observed frames, without turning missing masks into hits."""
        if not self.active:
            return
        if self.active == 'collect' and now-self.started >= self.policy.collection_timeout_seconds:
            self.active = None
            self.message = 'Collection timed out. Check mask visibility/light/FPS, then Collect again.'
            return
        if now-self.last_sample < self.policy.sample_interval_seconds:
            return
        self.last_sample = now
        if self.active == 'collect':
            if mask is None:
                self.message = 'Waiting for exactly one detected can in the yellow area.'
                return
            try:
                pixels = collect_pixels(frame, mask, self.seeds[self.target], self.policy)
            except ValueError as exc:
                self.message = str(exc)
                return
            self.samples[self.target].append(pixels)
            if len(self.samples[self.target]) >= self.policy.collection_frames:
                self.active = None
                self.message = self.target.upper() + ' collected. Choose the next color, or Fit when all are ready.'
        else:
            item = self.verification[self.target]
            item.add(predicted if mask is not None else 'unknown')
            result = item.summary()
            if result['total'] >= self.policy.verification_frames:
                self.active = None
                self.attempts.append(dict(color=self.target, **result))
                self.message = (self.target.upper() + (' PASS. Choose the next color or Save & Test.' if result['passed']
                                else ' FAIL. Retry fresh verification or Recollect this color.'))


def buttons(session):
    """Return visible button bounds and enabled states for rendering and clicks."""
    idle = not session.active
    definitions = [
        ('red', '1: Red', idle), ('green', '2: Green', idle), ('blue', '3: Blue', idle),
        ('collect', 'C: Collect', idle and session.phase == 'collect' and session.target in session.seeds),
        ('fit', 'F: Fit', idle and session.phase == 'collect'
         and all(len(session.samples[name]) >= session.policy.collection_frames for name in COLORS)),
        ('verify', 'V: Verify', idle and session.phase == 'verify'),
        ('save', 'S: Save & Test', session.can_save()),
        ('redo', 'T: Recollect', idle), ('quit', 'Q: Cancel', True),
    ]
    return [dict(action=name, label=label, enabled=enabled,
                 bounds=(10+(index % 7)*180, 760+(index//7)*49, 170, 42))
            for index, (name, label, enabled) in enumerate(definitions)]


def _text(canvas, message, y, size=.60):
    """Fit one readable status line into the setup window."""
    width = cv2.getTextSize(message, 0, size, 1)[0][0]
    scale = min(1., (canvas.shape[1]-24)/max(1, width))
    cv2.putText(canvas, message, (12, y), 0, size*scale, (235, 235, 235), 1, cv2.LINE_AA)


def draw_screen(frame, roi, origin, mask, session, stats):
    """Draw touch-sized buttons and return the camera-to-preview transform."""
    canvas = np.full((860, 1280, 3), 24, np.uint8)
    _text(canvas, 'Yards color setup | ' + session.phase.upper() + ' | selected: ' + session.target.upper(), 28, .75)
    hint = ('Show one can. Select its color, click a COLORED patch, then Collect. Turn it slowly.'
            if session.phase == 'collect' else 'Use fresh movements for each color. Verify all three before Save & Test.')
    _text(canvas, hint, 58)
    _text(canvas, f'Camera-only delivery: {stats.get("camera_fps", 0):.1f} FPS | setup processing: {stats.get("fps", 0):.1f} FPS | NO PACK COUNTING', 88)
    progress = 'Samples: ' + ' | '.join(f'{name.upper()} {len(session.samples[name])}/{session.policy.collection_frames}' for name in COLORS)
    verified = []
    for name in COLORS:
        result = session.verification[name].summary() if name in session.verification else None
        state = ('PASS' if result['passed'] else f'{result["correct"]}/{result["total"]}') if result else '-'
        verified.append(name.upper() + ' ' + state)
    _text(canvas, progress + '     Verify: ' + ' | '.join(verified), 118)
    _text(canvas, f'Original: {stats.get("original", "unknown")} | Proposed: {stats.get("proposed", "not fitted")} | cans in area: {stats.get("cans", 0)}', 148)
    _text(canvas, session.message, 178)
    view = frame.copy()
    if mask is not None:
        cx, cy = origin
        mx, my, mw, mh = cv2.boundingRect(mask.astype(np.uint8))
        if mw and mh:
            tile = view[cy+my:cy+my+mh, cx+mx:cx+mx+mw]
            selected = mask[my:my+mh, mx:mx+mw].astype(bool)
            color = PALETTE.get(stats.get('proposed'), PALETTE.get(stats.get('original'), PALETTE['unknown']))
            tile[selected] = (tile[selected]*.75+np.asarray(color)*.25).astype(np.uint8)
    x, y, width, height = roi
    cv2.rectangle(view, (x, y), (x+width-1, y+height-1), (0, 230, 255), 2)
    scale = min(1260/view.shape[1], 550/view.shape[0])
    rw, rh = round(view.shape[1]*scale), round(view.shape[0]*scale)
    left, top = (1280-rw)//2, 200+(550-rh)//2
    canvas[top:top+rh, left:left+rw] = cv2.resize(view, (rw, rh))
    for button in buttons(session):
        bx, by, bw, bh = button['bounds']
        color = (80, 85, 90) if button['enabled'] else (42, 42, 42)
        if button['action'] == session.target:
            color = PALETTE[session.target]
        cv2.rectangle(canvas, (bx, by), (bx+bw, by+bh), color, -1)
        cv2.putText(canvas, button['label'], (bx+8, by+27), 0, .58,
                    (255, 255, 255) if button['enabled'] else (130, 130, 130), 1, cv2.LINE_AA)
    # Store the actual rounded scales used for each axis, not an ideal ratio.
    return canvas, (left, top, rw/view.shape[1], rh/view.shape[0], rw, rh)


def image_point(point, transform, origin):
    """Map a click on the displayed camera image into context-mask coordinates."""
    x, y = point
    left, top, sx, sy, width, height = transform
    if not left <= x < left+width or not top <= y < top+height:
        return None
    return int((x-left)/sx)-origin[0], int((y-top)/sy)-origin[1]


def configure_camera(capture, backend, runtime, view, base, policy, output, *,
                     camera_info=None, already_oriented=False, preview_fps=10.):
    """Run live setup; return a new verified profile path or None on cancel.

    The caller owns the camera and backend. No ledger or GPIO operations occur
    here. The same open resources can be used by the counter after setup.
    """
    session = CalibrationSession(base, policy)
    clicks, shown = [], None
    def clicked(event, x, y, flags, parameter):
        """Queue clicks against the displayed frame, not a later camera frame."""
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append((x, y))
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, 1100, 740)
    cv2.setMouseCallback(WINDOW, clicked)
    try:
        placeholder = np.full((720, 1280, 3), 50, np.uint8)
        session.message = 'Warming the camera and measuring delivery before model processing...'
        canvas, _ = draw_screen(placeholder, [0, 0, 1280, 720], (0, 0), None, session, {})
        cv2.imshow(WINDOW, canvas)
        cv2.waitKey(1)
        delivery = measure_delivery(capture, policy.probe_seconds, policy.warmup_seconds)
        # The caller has loaded the backend, but no inference ran in this probe.
        delivery.update(model_loaded=True, inference_during_measurement=False)
        camera_fps = delivery.get('delivered_fps') or 0.
        session.message = 'Show one RED can in the yellow area. Click its colored label, then Collect.'
        last_draw, stamps = float('-inf'), []
        shortcuts = {ord('1'): 'red', ord('2'): 'green', ord('3'): 'blue', ord('c'): 'collect',
                     ord('f'): 'fit', ord('v'): 'verify', ord('s'): 'save', ord('t'): 'redo',
                     ord('q'): 'quit', 27: 'quit'}
        while True:
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError('Camera stopped during color setup.')
            if runtime['rotate_180'] and not already_oriented:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            roi = restore_view(view, frame.shape[:2])
            x, y, width, height = roi
            cx, cy, cw, ch = context_area(roi, frame.shape[:2], runtime['tracking_context']['padding_fraction'])
            context = frame[cy:cy+ch, cx:cx+cw]
            masks, boxes, _ = backend.predict(context)
            eligible = [i for i, box in enumerate(boxes.xyxy)
                        if x <= cx+(box[0]+box[2])/2 < x+width and y <= cy+(box[1]+box[3])/2 < y+height]
            mask = masks[eligible[0]] if len(eligible) == 1 else None
            original = sample_colors(context, [mask], session.original_settings)[0][0] if mask is not None else 'unknown'
            proposed = (sample_colors(context, [mask], session.settings)[0][0] if mask is not None else 'unknown') if session.settings else 'not fitted'
            now = time.perf_counter()
            stamps = (stamps+[now])[-30:]
            fps = (len(stamps)-1)/(stamps[-1]-stamps[0]) if len(stamps) > 1 else 0.
            session.observe(context, mask, proposed, now)
            if preview_fps == 0 or now-last_draw >= 1/preview_fps:
                stats = dict(camera_fps=camera_fps, fps=fps, cans=len(eligible), original=original, proposed=proposed)
                canvas, transform = draw_screen(frame, roi, (cx, cy), mask, session, stats)
                shown = dict(context=context, mask=mask, origin=(cx, cy), transform=transform)
                cv2.imshow(WINDOW, canvas)
                last_draw = now
            key = cv2.waitKey(1) & 255
            actions = [shortcuts[key]] if key in shortcuts else []
            for point in clicks:
                button = next((b for b in buttons(session) if b['bounds'][0] <= point[0] < b['bounds'][0]+b['bounds'][2]
                               and b['bounds'][1] <= point[1] < b['bounds'][1]+b['bounds'][3]), None)
                if button:
                    if button['enabled']:
                        actions.append(button['action'])
                elif shown:
                    local = image_point(point, shown['transform'], shown['origin'])
                    if local is not None:
                        try:
                            session.set_seed(shown['context'], shown['mask'], local)
                        except ValueError as exc:
                            session.message = str(exc)
            clicks.clear()
            try:
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    return None
            except cv2.error:
                return None  # Some GUI backends raise after the X button closes a window.
            for action in actions:
                try:
                    outcome = session.action(action, now)
                    if outcome == 'cancel':
                        return None
                    if outcome == 'save':
                        path = save_profile(output, session.profile, session.verification,
                                            dict(policy=asdict(policy), fit=session.fit_report,
                                                 verification_attempts=session.attempts, camera=camera_info,
                                                 camera_delivery=delivery, model_sha256=runtime['model_sha256'],
                                                 source_rotation_180=runtime['rotate_180'], view=view))
                        print('Saved verified color profile: ' + str(path.resolve()), flush=True)
                        return path
                except (ValueError, OSError) as exc:
                    session.message = str(exc)
    finally:
        try:
            cv2.destroyWindow(WINDOW)
        except cv2.error:
            pass  # Closing the window's X button may already have destroyed it.
