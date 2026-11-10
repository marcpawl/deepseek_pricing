#!/usr/bin/env python3
"""Tkinter front end that displays DeepSeek peak and non-peak windows.

``tkinter`` is imported inside :meth:`DeepSeekMonitorApp.__init__` rather
than at module scope, so this module can be imported on a machine where
tkinter is not installed. The helpers that only do schedule arithmetic
are then usable, and testable, without a GUI toolkit.
"""
import itertools
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from deepseek_pricing import schedule

# How many pricing periods to inspect when looking for non-peak windows.
# Each day contributes at most a few periods, so this covers many days.
LOOKAHEAD_PERIODS = 30
# Minutes before a peak window starts that the UI switches to yellow.
WARNING_MINUTES = 15


class DeepSeekMonitorApp:

    def __init__(self):
        # Imported here so that merely importing this module does not
        # require tkinter, which some distributions ship separately.
        from tkinter import Tk, Label, Button, Canvas, Frame, Scrollbar

        self.root = Tk()
        self.root.title("DeepSeek Primetime Monitor")
        self.root.geometry("800x550")

        # The schedule can be taller than the window, so the text lives on
        # a canvas that scrolls. The scrollbar only appears while the text
        # actually overflows the visible area.
        self.scroll_frame = Frame(self.root)
        self.scroll_frame.pack(expand=True, fill="both")

        self.canvas = Canvas(
            self.scroll_frame, highlightthickness=0, borderwidth=0
        )
        self.scrollbar = Scrollbar(
            self.scroll_frame,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.canvas.configure(yscrollcommand=self.sync_scrollbar)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.scrollbar.grid_remove()
        self.scroll_frame.rowconfigure(0, weight=1)
        self.scroll_frame.columnconfigure(0, weight=1)

        # Use Courier to keep the tabular data perfectly aligned
        self.label = Label(
            self.canvas,
            text="Initializing...",
            font=("Courier", 11, "bold"),
            justify="left",
            padx=20,
            pady=20,
        )
        self.label_window = self.canvas.create_window(
            (0, 0), window=self.label, anchor="nw"
        )
        self.label.bind("<Configure>", self.update_scroll_region)
        self.canvas.bind("<Configure>", self.resize_label)
        self.canvas.bind_all("<MouseWheel>", self.scroll_wheel)
        self.canvas.bind_all("<Button-4>", self.scroll_wheel)
        self.canvas.bind_all("<Button-5>", self.scroll_wheel)

        self.ack_button = Button(
            self.root,
            text="Acknowledge",
            font=("Helvetica", 12, "bold"),
            command=self.acknowledge_and_restore,
            bg="#ffffff",
            fg="#000000",
            relief="raised",
            bd=4,
            padx=10,
            pady=5,
        )
        self.ack_button_visible = False

        self.current_state = None
        self.acknowledged = False
        # Window state captured before the alert forced it fullscreen, so
        # acknowledge can put it back exactly how the user had it.
        self.pre_alert_state = "normal"
        self.pre_alert_fullscreen = False

        self.force_to_foreground()

        self.monitor_thread = threading.Thread(
            target=self.timing_loop, daemon=True
        )
        self.monitor_thread.start()

    def force_to_foreground(self):
        """Bring the window to the front and out of minimization."""
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(1000, lambda: self.root.attributes("-topmost", False))

    def update_scroll_region(self, _event=None):
        """Grow the scrollable area to match the size of the text block."""
        region = self.canvas.bbox("all")
        if region is not None:
            self.canvas.configure(scrollregion=region)

    def resize_label(self, event):
        """Stretch the text block to the canvas width so its color fills."""
        self.canvas.itemconfigure(self.label_window, width=event.width)

    def sync_scrollbar(self, first, last):
        """Show the scrollbar only while the text overflows the canvas."""
        self.scrollbar.set(first, last)
        # Compare heights rather than the yview fractions: when the text
        # shrinks while scrolled down, the fractions stay away from
        # (0.0, 1.0) for one update even though nothing overflows.
        region = self.canvas.bbox("all")
        needed = (
            region is not None
            and (region[3] - region[1]) > self.canvas.winfo_height()
        )
        visible = bool(self.scrollbar.winfo_ismapped())
        if needed and not visible:
            self.scrollbar.grid()
        elif not needed and visible:
            self.scrollbar.grid_remove()
            self.canvas.yview_moveto(0.0)

    def scroll_wheel(self, event):
        """Scroll the schedule with the mouse wheel or touchpad."""
        if not self.scrollbar.winfo_ismapped():
            return
        if getattr(event, "num", None) == 4:
            steps = -1
        elif getattr(event, "num", None) == 5:
            steps = 1
        elif getattr(event, "delta", 0):
            steps = -1 if event.delta > 0 else 1
        else:
            return
        self.canvas.yview_scroll(steps, "units")

    def capture_window_state(self):
        """Remember how the window looked before an alert resized it."""
        self.pre_alert_state = self.root.state()
        self.pre_alert_fullscreen = bool(
            self.root.attributes("-fullscreen")
        )

    def acknowledge_and_restore(self):
        """Dismiss the alert and return to the pre-alert window state."""
        self.acknowledged = True
        self.root.attributes("-fullscreen", self.pre_alert_fullscreen)
        if self.pre_alert_fullscreen:
            self.root.deiconify()
        elif self.pre_alert_state == "zoomed":
            self.root.state("zoomed")
        elif self.pre_alert_state == "iconic":
            self.root.iconify()
        else:
            self.root.state("normal")

    def trigger_chime(self):
        try:
            self.root.bell()
        except Exception:
            pass

    def get_next_non_peak_windows(self, utc_now, count=3):
        """Return the next N distinct non-peak windows."""
        periods = schedule.pricing_periods(LOOKAHEAD_PERIODS, utc_now)
        windows = (
            period for period in periods
            if period["pricing"] == schedule.NONPEAK
        )
        return [
            (
                datetime.fromisoformat(period["startTime"]),
                datetime.fromisoformat(period["endTime"]),
            )
            for period in itertools.islice(windows, count)
        ]

    def get_pricing_periods(self, utc_now, count=3):
        """Return the next N pricing periods with parsed datetimes."""
        periods = schedule.pricing_periods(count, utc_now)
        return [
            {
                "start": datetime.fromisoformat(period["startTime"]),
                "end": datetime.fromisoformat(period["endTime"]),
                "pricing": period["pricing"],
            }
            for period in itertools.islice(periods, count)
        ]

    def format_countdown(self, delta):
        """Converts a timedelta into an hh:mm countdown string layout."""
        total_seconds = int(delta.total_seconds())
        if total_seconds <= 0:
            return "Active Now"
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h:{minutes:02d}m"

    def build_time_display(self, local_now, utc_now, beijing_now):
        """Format the clock lines shown above the schedule."""
        return (
            f"Local Time:   {local_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"UTC Time:     {utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"Beijing Time: {beijing_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"{'-'*76}\n"
        )

    def compute_color(self, utc_now):
        """Map the current pricing state to a UI color.

        Peak is red, non-peak that starts within WARNING_MINUTES minutes is
        yellow, and everything else is green.
        """
        now_period, next_period = itertools.islice(
            self.get_pricing_periods(utc_now, count=2), 2
        )
        if now_period["pricing"] == schedule.PEAK:
            return "red"
        minutes_until_peak = (
            next_period["start"] - utc_now
        ).total_seconds() / 60.0
        if minutes_until_peak <= WARNING_MINUTES:
            return "yellow"
        return "green"

    def evaluate_status(self):
        local_now = datetime.now().astimezone()
        utc_now = local_now.astimezone(ZoneInfo("UTC"))
        beijing_now = utc_now.astimezone(schedule.BEIJING)

        time_display = self.build_time_display(
            local_now, utc_now, beijing_now
        )
        color = self.compute_color(utc_now)

        status_headers = {
            "red": "CRITICAL: DeepSeek Peak Pricing Window Active!",
            "yellow": "WARNING: Peak Window Approaching Soon!",
            "green": "SAFE: DeepSeek Operations are Off-Peak."
        }

        # 2. Fetch the next 3 distinct non-peak windows
        np_windows = self.get_next_non_peak_windows(utc_now, count=3)

        # 3. Construct the comprehensive timetable layout
        table_output = "UPCOMING SCHEDULE: NEXT 3 DISTINCT NON-PEAK WINDOWS\n"
        table_output += f"{'='*76}\n"

        for idx, (start_dt, end_dt) in enumerate(np_windows, 1):
            # Calculate zone conversions for start parameters
            s_local = start_dt.astimezone(local_now.tzinfo)
            s_beijing = start_dt.astimezone(beijing_now.tzinfo)

            # Calculate zone conversions for end parameters
            e_local = end_dt.astimezone(local_now.tzinfo)
            e_beijing = end_dt.astimezone(beijing_now.tzinfo)

            # Determine temporal countdown metrics from current moment
            countdown_start = self.format_countdown(start_dt - utc_now)
            countdown_end = self.format_countdown(end_dt - utc_now)

            window_label = f"WINDOW #{idx}"
            if (
                idx == 1
                and color in ("green", "yellow")
                and (start_dt <= utc_now < end_dt)
            ):
                window_label += " (CURRENTLY ACTIVE)"

            table_output += f"{window_label}\n"
            table_output += f"{'-'*76}\n"
            table_output += (
                " Zone    | Start Time                     | End Time\n"
            )
            table_output += f"{'-'*76}\n"
            table_output += (
                f" Local   | {s_local.strftime('%Y-%m-%d %H:%M %Z'):<26} | "
                f"{e_local.strftime('%Y-%m-%d %H:%M %Z')}\n"
            )
            table_output += (
                f" UTC     | {start_dt.strftime('%Y-%m-%d %H:%M UTC'):<26} | "
                f"{end_dt.strftime('%Y-%m-%d %H:%M UTC')}\n"
            )
            table_output += (
                f" Beijing | {s_beijing.strftime('%Y-%m-%d %H:%M %Z'):<26} | "
                f"{e_beijing.strftime('%Y-%m-%d %H:%M %Z')}\n"
            )
            table_output += f"{'-'*76}\n"
            table_output += (
                f" Status  | Opens: {countdown_start:<23} | "
                f"Closes: {countdown_end}\n"
            )
            table_output += f"{'='*76}\n\n"

        final_text = f"{time_display}{status_headers[color]}\n\n{table_output}"
        return color, final_text

    def update_ui(self, color, display_text):
        self.label.config(text=display_text, bg=color)
        # The canvas shows through below the text when the window is
        # taller than the schedule, so it has to carry the same color.
        self.canvas.config(bg=color)

        alert = color in ("yellow", "red")
        if alert and self.current_state not in ("yellow", "red"):
            # Entering an alert: remember the window state to restore to,
            # and clear any acknowledgement left over from a previous one.
            self.capture_window_state()
            self.acknowledged = False
        elif not alert:
            self.acknowledged = False

        if alert:
            if not self.acknowledged:
                self.root.attributes("-fullscreen", True)
            if not self.ack_button_visible:
                self.ack_button.pack(side="bottom", fill="x", padx=20, pady=20)
                self.ack_button_visible = True
        else:
            self.root.attributes("-fullscreen", False)
            if self.ack_button_visible:
                self.ack_button.pack_forget()
                self.ack_button_visible = False

        if color != self.current_state:
            self.current_state = color
            if alert and not self.acknowledged:
                self.force_to_foreground()
            if alert:
                self.trigger_chime()

    def timing_loop(self):
        color, text = self.evaluate_status()
        self.root.after(0, self.update_ui, color, text)

        while True:
            now = datetime.now()
            seconds_to_wait = 60 - now.second - (now.microsecond / 1000000.0)
            time.sleep(seconds_to_wait)

            color, text = self.evaluate_status()
            self.root.after(0, self.update_ui, color, text)

    def run(self):
        self.root.mainloop()


def main():
    """Launch the monitor window."""
    app = DeepSeekMonitorApp()
    app.run()


if __name__ == "__main__":
    main()
