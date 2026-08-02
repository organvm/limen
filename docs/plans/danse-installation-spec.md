# The Thing Without a Name: Installation Specification (Omega Phase)

## Overview
The interactive (Omega) phase of the project transforms the generative engine from a screen-bound artifact into a physical, responsive environment. Visitors enter a pitch-black room where the digital structure reacts to their real-time skeletal geometry via MediaPipe.

## Hardware & Environment
- **Room**: Pitch black, minimum 20ft x 20ft.
- **Projection Surface**: Large-scale bobbinet (sharkstooth scrim) hung in the center of the room, allowing viewers to walk completely around and behind it.
- **Projectors**: Two synchronized projectors (Tier A and Tier B).
- **Rule of Display**: There must be NO edge-blending. The physical projection constraints should mirror the architectural framing constraints of the digital slices.
- **Camera**: Infrared or low-light capable webcam positioned dead-center, tracking the viewer.

## Software Integration
- `apps/danse/join.html` loads the MediaPipe `pose_landmarker` via WebAssembly/WebGL.
- It extracts 33 bodily landmarks from the viewer.
- The normalized coordinates (X, Y, Z depth) are passed into the generative engine (`engine.js`).
- The viewer's live depth (Z-axis) controls the spread of the generative cubist slices. The closer the viewer gets, the further the slices are blown apart in 3D space, effectively tearing the body apart visually as they approach.
- The viewer's lateral movement (X-axis) controls the panning of the WebAudio score engine, pulling the generated sound physically across the room in sync with their body.
