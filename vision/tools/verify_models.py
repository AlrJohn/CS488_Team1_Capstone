"""Verify the shipped model identities without loading pickle or opening hardware."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    pt = ROOT / 'models/can-camera-v1.pt'
    hef = ROOT / 'models/can-camera-v1.hef'
    for model, identity in [(pt, pt.with_suffix('.json')), (hef, hef.with_suffix('.hef.json'))]:
        metadata = json.loads(identity.read_text())
        if hashlib.sha256(model.read_bytes()).hexdigest() != metadata['sha256']:
            raise ValueError('Changed model: ' + model.name)
    metadata = json.loads(hef.with_suffix('.hef.json').read_text())
    pt_metadata = json.loads(pt.with_suffix('.json').read_text())
    source = pt_metadata.get('source_checkpoint_sha256', pt_metadata['sha256'])
    if metadata['source_checkpoint_sha256'] != source:
        raise ValueError('HEF and PC checkpoint do not share a model identity')
    print('Verified: camera-v1 PC weights and Hailo-8 HEF, from the same checkpoint.')


if __name__ == '__main__':
    main()
