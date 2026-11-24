# Face Attendance v5 — Operator-started automatic kiosk scanning

## Automatic scan behavior
- Operator opens the kiosk on the entrance smartphone, enters the organization code, and enables the camera.
- Operator explicitly taps **Start automatic scanning**.
- The browser captures a frame every 3 seconds and submits it to the server for face detection and matching.
- On a successful match, the app records CHECK_IN or CHECK_OUT using Asia/Kolkata time, displays the result, and stops scanning so the member can leave the frame.
- Operator taps Start again for the next person. This avoids the camera repeatedly recording the same person while they remain in view.
- Operator can stop scanning at any time.
- Camera can be switched between rear and front.

## Important privacy and safety behavior
Automatic scanning does not run until an operator deliberately starts it. Put a clear notice at the kiosk, explain what biometric processing is used for, and provide a non-biometric/manual attendance option. Do not point the camera at a general public area or scan passers-by. The current implementation does not provide liveness / presentation-attack detection; a photo or screen replay may fool face matching. Do not use it for consequential attendance decisions until a tested server-side liveness system, secure storage, access controls, audit logs, deletion/retention process and security review are added.

## Setup
Same as v4: Python 3.10/3.11, `pip install -r requirements.txt`, `python app.py`. For mobile camera access from a separate phone, deploy behind HTTPS. Add the site to the phone home screen if desired.
