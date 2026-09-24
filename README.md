# Yards Brewing Variety-Pack Automation

CS488 - Capstone Project  
**Team 1**

## Overview

This project focuses on improving the variety-pack packaging process used by Yards Brewing Company.

Yards currently produces and packages individual beer SKUs separately. When a variety pack needs to be created, those products are later brought to a separate variety-pack station where employees manually combine the correct number of cans from different product lanes, place them back into reused 12-pack cartons, and reseal the boxes.

The current process works, but it requires significant manual handling and depends heavily on employees remembering and selecting the correct number of cans from each lane. This creates opportunities for:

- Incorrect variety-pack combinations
- Miscounted cans
- Product damage during manual handling
- Rework
- Customer quality complaints
- Additional manual verification

Our goal is to design and prototype a configurable automation system that reduces these errors while integrating with as much of Yards' existing equipment as possible.

---

## Problem Statement

> **How can we automate or reduce the manual labor involved in assembling variety packs containing multiple can types while still supporting different variety-pack configurations?**

As the project progressed through research, site visits, and meetings with Yards employees and plant management, the problem became more specifically focused on **accuracy, repeatability, and quality control**.

The current design therefore targets two major portions of the process:

1. Automatically separating and counting the correct number of cans from each product lane.
2. Reliably transferring the completed group of cans into the reused variety-pack carton.

---

## Current Yards Variety-Pack Process

The existing process is primarily manual.

1. Individual beer SKUs are produced and packaged separately.
2. Products needed for a variety pack are brought to the variety-pack station.
3. Employees open the original cartons.
4. Cans are placed onto separate conveyor lanes according to SKU.
5. Employees manually select the required number of cans from each lane.
6. The selected cans are manually placed into a reused 12-pack carton.
7. The carton is resealed.
8. Finished cases are repalletized.

For the current Yards canned variety pack, the primary configuration consists of:

```text
Lane 1: 4 cans
Lane 2: 4 cans
Lane 3: 4 cans

Total: 12 cans
```

Other configurations may also be required for different products or contract packaging, so the proposed system is being designed with configurability in mind.

---

## Proposed Solution

Our current concept is a **modular retrofit** of the existing variety-pack station rather than a complete replacement of the line.

The proposed process is:

```text
Existing Product Lanes
        ↓
Double-Gate / Escapement System
        ↓
Correct Number of Cans Released
        ↓
Can Grouping / Alignment
        ↓
Camera-Based Quality Verification
        ↓
PASS / FAIL Decision
        ↓
Dead Plate / Loading Area
        ↓
Pneumatic or Mechanical Pusher
        ↓
Reused 12-Pack Carton
```

The system is currently being divided into several main subsystems.

---

## 1. Double-Gate Escapement System

Each active product lane will use a two-stage gate or escapement system.

The purpose of the escapements is to:

- Control the flow of cans
- Separate cans from the accumulated product
- Release the required quantity from each lane
- Prevent additional cans from entering the current batch
- Allow different variety-pack recipes to be selected

Yards currently uses similar double-gate escapement mechanisms elsewhere in the brewery, which gives us an existing industrial design that we can study and adapt rather than creating the mechanism completely from scratch.

The exact gate geometry and actuation method are still being developed.

---

## 2. Recipe-Controlled Dispensing

The system should not be limited to one variety-pack configuration.

Instead, the controller will store different recipes.

Example:

```text
Recipe A
Lane 1 = 4
Lane 2 = 4
Lane 3 = 4
```

A future configuration could instead use:

```text
Recipe B
Lane 1 = 6
Lane 2 = 6
Lane 3 = 0
```

The operator would select the required recipe, and the control system would determine how many cans need to be released from each lane.

---

## 3. Camera-Based Quality Verification

One of the most important issues identified by Yards is that an incorrect variety combination may not be discovered until a customer opens the finished package.

To address this, we plan to use a camera as an **independent quality-control layer**.

The mechanical system will be responsible for dispensing the expected number of cans. The camera will then inspect the completed group before it is loaded into the carton.

The vision system will verify that the visible can colors/SKUs match the selected recipe.

Example:

```text
Expected:
Red   = 4
Blue  = 4
Green = 4

Detected:
Red   = 4
Blue  = 4
Green = 4

Result: PASS
```

If the detected combination does not match the selected recipe:

```text
Expected:
Red   = 4
Blue  = 4
Green = 4

Detected:
Red   = 5
Blue  = 3
Green = 4

Result: FAIL
```

The loading mechanism would remain disabled and the operator would be alerted.

Possible fail-safe responses include:

- Warning light
- Audible alarm
- Pusher lockout
- Conveyor shutdown
- Lane-specific error indication

---

## 4. OpenCV Vision Processing

The initial vision system will use **OpenCV** rather than immediately relying on a machine-learning model.

The first goal is relatively simple:

> Determine whether the correct number of each expected can color is present.

The initial image-processing pipeline is expected to look like:

```text
Camera Image
    ↓
Region of Interest
    ↓
BGR → HSV Conversion
    ↓
Color Thresholding
    ↓
Mask Cleanup
    ↓
Object Detection
    ↓
Color Counts
    ↓
Compare With Recipe
    ↓
PASS / FAIL
```

Potential OpenCV functions include:

| Function | Purpose |
|---|---|
| `cv2.VideoCapture()` | Connect to the camera and retrieve images |
| `cv2.cvtColor()` | Convert the image from BGR to HSV |
| `cv2.inRange()` | Isolate pixels belonging to a selected color |
| `cv2.erode()` | Remove small areas of image noise |
| `cv2.dilate()` | Expand/reconnect detected regions |
| `cv2.morphologyEx()` | Perform mask cleanup operations |
| `cv2.findContours()` | Identify separate detected objects |
| `cv2.contourArea()` | Measure object size and remove false detections |
| `cv2.boundingRect()` | Determine the location and approximate size of detected objects |

Machine learning may be investigated later if traditional computer vision is not reliable enough.

---

## 5. Can Alignment and Funnel System

After the correct cans are released, they need to remain organized while moving toward the carton-loading area.

The current concept uses thin stainless-steel guide plates to:

- Corral the cans
- Prevent excessive spreading
- Align the cans with the carton opening
- Reduce the chance of cans catching on cardboard edges
- Support different pack configurations

Yards personnel suggested using thin stainless-steel plates similar to components already used elsewhere in the plant.

The guide/funnel section is also expected to be one of the primary adjustable portions of the machine.

---

## 6. Carton Loading

The reused cartons are loaded horizontally from the side.

The current design direction uses a:

**Dead plate + side-discharge pusher**

rather than relying only on gravity or conveyor force.

The general process would be:

```text
Correct 12-Can Group
        ↓
Dead Plate / Staging Area
        ↓
Carton Positioned
        ↓
Pusher Activated
        ↓
Cans Move Horizontally Into Carton
        ↓
Loaded Carton Removed
```

A pneumatic cylinder is currently one of the strongest candidates for the final pusher mechanism.

The biggest mechanical challenge is making sure the cans enter the reused carton without:

- Tipping
- Spreading apart
- Catching on the carton
- Denting
- Jamming

---

## System Architecture

The current high-level architecture is:

```text
                    ┌────────────────────┐
                    │   Recipe Selection │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ Controller / Logic │
                    └─────────┬──────────┘
                              │
             ┌────────────────┼────────────────┐
             │                │                │
             ▼                ▼                ▼
          Lane 1           Lane 2           Lane 3
        Escapement       Escapement       Escapement
             │                │                │
             └────────────────┼────────────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ Correct Can Group  │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ Camera + OpenCV QC │
                    └─────────┬──────────┘
                              │
                         PASS / FAIL
                              │
                              ▼
                    ┌────────────────────┐
                    │   Loading Pusher   │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │   Reused Carton    │
                    └────────────────────┘
```

---

## Project Priorities

The project is being developed in stages.

### Phase 1 – Requirements and Domain Research

- Understand Yards' existing canning and packaging process
- Study the current variety-pack workflow
- Research how other breweries automate variety packaging
- Identify Yards' main pain points
- Develop requirements through site visits and employee interviews

### Phase 2 – Mechanical Dispensing

- Study Yards' existing escapement systems
- Prototype one-lane can separation
- Develop gate control
- Expand to three active lanes
- Implement recipe-controlled dispensing

### Phase 3 – Vision System

- Set up camera and controlled lighting
- Capture Yards can images
- Develop OpenCV color detection
- Count individual can varieties
- Implement PASS/FAIL recipe validation

### Phase 4 – Can Grouping and Loading

- Develop stainless guide/funnel system
- Test can grouping
- Develop dead-plate loading area
- Build pneumatic/mechanical pusher
- Test horizontal loading into reused cartons

### Phase 5 – System Integration

- Connect gate logic
- Connect sensors
- Connect camera validation
- Implement fail-safe behavior
- Integrate pusher
- Measure system reliability and cycle time

---

## Success Metrics

The project is not being evaluated only on speed.

The main objective is to improve **quality and repeatability** while maintaining useful production performance.

Important metrics include:

### Variety-Pack Accuracy

```text
Correctly Configured Packs
-------------------------- × 100
Total Packs Produced
```

### Count Accuracy

The system should not silently allow an incorrect number of cans from any lane.

### Vision Accuracy

The camera should correctly distinguish valid and invalid can combinations.

### Can Damage

The automated system should not create unacceptable:

- Dents
- Scratches
- Drops
- Collisions

### Cycle Time

The system should maintain a production rate that remains useful compared with the current manual process.

### Fault Detection

The system should detect and report conditions such as:

- Incorrect variety combination
- Missing can
- Extra can
- Jammed can
- Fallen can
- Camera validation failure

---

## Current Project Status

The project is currently in the **prototype design and early implementation phase**.

Completed work includes:

- Domain research into Yards' canning and variety-pack process
- Competitive research into automated variety-pack systems
- Requirements gathering
- Initial Yards site visit
- Detailed process documentation
- Identification of the primary quality problem
- Multiple mechanical concept iterations
- Review of the proposed design with Yards plant personnel
- Validation of the double-gate escapement concept
- Initial camera and OpenCV research
- Identification of a dead-plate / side-discharge loading concept

Current work includes:

- Observing Yards' existing escapement mechanisms
- Finalizing mechanical dimensions
- Selecting sensors and control hardware
- Developing the camera validation prototype
- Designing the can-loading mechanism
- Obtaining available hardware from Yards
- Building and testing subsystem prototypes

---

## Current Design Constraints

The solution must account for:

- Limited capstone timeline
- Limited project budget
- Existing Yards equipment
- Reused cartons
- Multiple variety-pack recipes
- Easy-to-dent aluminum cans
- Variable staffing
- Intermittent variety-pack production
- Existing conveyor geometry
- Need for simple maintenance and repair

For these reasons, the project prioritizes a **modular retrofit** rather than a completely new automated production line.

---

## Technologies

Current or expected technologies include:

### Software

- Python
- OpenCV
- Git / GitHub

### Controls

- Arduino / microcontroller
- Raspberry Pi
- Sensors
- Gate/escapement control
- Alarm / fail-safe logic

### Vision

- Global-shutter USB camera
- Controlled lighting
- OpenCV image processing

### Mechanical

- Double-gate escapements
- Stainless-steel guide plates
- Bearings and brackets
- Pneumatic cylinders
- Dead plate
- Mechanical pusher
- Existing Yards conveyor

---

## Repository Structure

The repository structure will evolve as the prototype develops.

```text
yards-variety-pack-automation/
│
├── README.md
│
├── docs/
│   ├── domain-research/
│   ├── meeting-notes/
│   ├── requirements/
│   ├── diagrams/
│   └── testing/
│
├── vision/
│   ├── camera/
│   ├── color-detection/
│   ├── calibration/
│   └── tests/
│
├── controls/
│   ├── gate-control/
│   ├── sensors/
│   ├── recipes/
│   └── failsafe/
│
├── mechanical/
│   ├── escapement/
│   ├── guides/
│   └── pusher/
│
└── prototypes/
    ├── prototype-1/
    └── prototype-2/
```

---

## Team

**Penn State Abington – IT/CMPSC Capstone Team 1**

- Jonathan Alavez Reyes
- Faahil Ali
- Liya Aji
- Margaret Decker
- Sabrina Abdukadirova

Industry Partner:

**Yards Brewing Company**

---

## Important Note

This repository represents an active capstone engineering project.

Mechanical dimensions, hardware selections, software architecture, control logic, and final system design may change as the team:

- performs additional plant observations,
- receives additional Yards documentation,
- builds prototypes,
- tests the system,
- and validates assumptions with real equipment.

The goal of the repository is to preserve that engineering process while maintaining a clear source of truth for the current design.
