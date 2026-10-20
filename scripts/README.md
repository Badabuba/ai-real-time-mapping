# Scripts

Майбутні тонкі CLI entry points:

- download/verify dataset manifest;
- run SLAM baseline;
- run geometry inference;
- align and fuse artifacts;
- evaluate one run;
- aggregate benchmark runs.

Business logic має бути у src/rt_mapping, а scripts лише парсить аргументи/config та викликає модулі. Команди додаються до root README тільки після smoke verification.
