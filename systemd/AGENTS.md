zero2dash systemd + ops rules (systemd/)
Safety boundary
Any change to systemd units or timers is operationally risky. Ask for explicit approval before proposing:
    • sudo cp … /etc/systemd/system/
    • systemctl enable/disable/start/stop
    • Edits that change schedules, users or groups, permissions or unit paths.
Conventions
    • Units currently assume the repository path /home/pihole/zero2dash and use EnvironmentFile=-/home/pihole/zero2dash/.env.
    • display.service and night.service conflict; be careful when changing dependencies to avoid oscillation.
    • Keep ExecStartPre (pihole-display-pre.sh) consistent across units unless you understand the display driver stack.
When changing schedules
    • Day and night schedules are defined in day.timer and night.timer via OnCalendar. If you propose changing these times, include:
    • Rationale for the change.
    • Expected impact on users.
    • A rollback plan (revert timers and reload the daemon).
Hardening suggestions (optional follow‑up only)
If asked to harden:
    • Propose running under a dedicated user/group and granting access to framebuffer/input via group membership.
    • Add systemd hardening directives incrementally (e.g., PrivateTmp=yes, ProtectSystem=strict) with rollback steps.
