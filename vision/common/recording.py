"""Save actual acquisition images, then encode timed previews after the trial.

Lossless PNG sources make later inference reproducible. A bounded background
writer offloads image compression without discarding observations. Preview
videos use acquisition timing; their final closing image is explicitly marked
as synthetic and is never an additional observation.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import statistics
import subprocess
import sys
import threading
import time
import cv2


def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


class Trial:
    def __init__(self, metadata, root, executable):
        self.path=Path(root)/'sessions'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ')
        self.path.mkdir(parents=True,exist_ok=False)
        for name in ('source_frames','annotated_frames'):(self.path/name).mkdir()
        self.metadata={**metadata,'recording_format':{'version':2,'source_pattern':'source_frames/{index:06d}.png',
            'source_is_lossless':True,'video_timing':'variable frame rate; terminal closing duplicate excluded from analysis'}}
        dump(self.path/'settings.json',self.metadata)
        dump(self.path/'raw.mp4.orientation.json',{'version':1,'rotate_180':metadata['rotate_180']})
        self.executable=executable
        self.stream=(self.path/'observations.jsonl').open('w',encoding='utf-8')
        self.queue=queue.Queue(maxsize=8)
        self.error=None;self.closed=False;self.frames=0;self.first_match=None
        self.timestamps=[];self.backpressure_seconds=0.
        self.group_evidence=None  # Current recorder is for cumulative box-count trials.
        self.worker=threading.Thread(target=self._write_images,name='can-trial-image-writer',daemon=True)
        self.worker.start()
        print('Recording trial: '+str(self.path),flush=True)

    def _write_images(self):
        while True:
            item=self.queue.get()
            try:
                if item is None:return
                if self.error is not None:continue
                index,raw,annotated=item
                ok_raw=cv2.imwrite(str(self.path/'source_frames'/f'{index:06d}.png'),raw,[cv2.IMWRITE_PNG_COMPRESSION,1])
                ok_annotated=cv2.imwrite(str(self.path/'annotated_frames'/f'{index:06d}.jpg'),annotated,[cv2.IMWRITE_JPEG_QUALITY,95])
                if not ok_raw or not ok_annotated:raise RuntimeError('Could not save acquisition images')
            except Exception as exc:self.error=exc
            finally:self.queue.task_done()

    def add(self,frame,view,record):
        if self.closed:raise ValueError('Trial already closed')
        if self.error:raise RuntimeError('Recording writer failed') from self.error
        index=record['index']
        if index!=self.frames+1:raise ValueError('Acquisition indices must be consecutive')
        if self.timestamps and record['timestamp_seconds']<=self.timestamps[-1]:
            raise ValueError('Acquisition timestamps must increase')
        if self.group_evidence:self.group_evidence.add(record)
        started=time.perf_counter()
        self.queue.put((index,frame.copy(),view.copy()))
        self.backpressure_seconds+=time.perf_counter()-started
        self.stream.write(json.dumps(record)+'\n');self.stream.flush()
        self.timestamps.append(record['timestamp_seconds']);self.frames+=1
        if record['pattern_matches_now'] and self.first_match is None:
            self.first_match={'frame':index,'seconds':record['timestamp_seconds'],
                'confirmed':record['confirmed'],'five_frame_span_seconds':record['five_frame_span_seconds']}

    def _encode(self,name,folder,extension):
        # Image demuxer time base of 1ms avoids the default 25Hz quantization.
        lines=['ffconcat version 1.0']
        gaps=[b-a for a,b in zip(self.timestamps,self.timestamps[1:])]
        final_gap=statistics.median(gaps) if gaps else 1/30
        for i,timestamp in enumerate(self.timestamps,1):
            duration=self.timestamps[i]-timestamp if i<len(self.timestamps) else final_gap
            lines.extend([f"file '{folder}/{i:06d}.{extension}'",'option framerate 1000',f'duration {duration:.9f}'])
        lines.extend([f"file '{folder}/{self.frames:06d}.{extension}'",'option framerate 1000'])
        concat=self.path/(name+'-frames.ffconcat');concat.write_text('\n'.join(lines)+'\n')
        command=[self.executable,'-hide_banner','-loglevel','error','-n','-f','concat','-safe','0','-i',str(concat),
            '-an','-fps_mode','vfr','-c:v','libx264','-preset','ultrafast','-crf','18','-threads','2',
            '-pix_fmt','yuv420p','-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-video_track_timescale','1000000',
            '-movflags','+faststart',str(self.path/(name+'.mp4'))]
        options={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}
        result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=45,**options)
        if result.returncode:raise RuntimeError(name+' preview encoding failed: '+result.stderr.decode(errors='replace'))

    def close(self):
        if self.closed:return
        self.closed=True
        self.queue.put(None)
        self.worker.join(timeout=30)
        self.stream.close()
        summary={'processed_frames':self.frames,'last_frame_seconds':self.timestamps[-1] if self.timestamps else None,
            'first_pattern_match':self.first_match,'pattern_seen':self.first_match is not None,
            'recording_format':2,'source_frames':self.frames,'preview_terminal_duplicate':True,
            'writer_backpressure_seconds':self.backpressure_seconds,'claim':'Temporal target presence; no verified picks/placement',
            'dataset_role':'unassigned; source sessions must be split before training'}
        if self.group_evidence:summary['four_can_evaluation']=self.group_evidence.summary()
        try:
            if self.worker.is_alive():raise RuntimeError('Image writer did not finish')
            if self.error:raise RuntimeError('Image writer failed') from self.error
            if self.frames:
                print('Finalizing timed preview videos; source images already saved.',flush=True)
                with ThreadPoolExecutor(max_workers=2) as workers:
                    jobs=[workers.submit(self._encode,'raw','source_frames','png'),
                          workers.submit(self._encode,'annotated','annotated_frames','jpg')]
                    for job in jobs:job.result()
            summary['recording_status']='complete'
        except Exception as exc:
            summary['recording_status']='preview-encoding-failed; acquisition images retained'
            summary['recording_error']=str(exc)
            raise
        finally:dump(self.path/'summary.json',summary)
        print(f'Saved {self.frames} actual images: {self.path}',flush=True)
        if self.group_evidence:print('Four-can trial: '+json.dumps(self.group_evidence.summary()),flush=True)
