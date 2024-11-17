import time

class Timer:
    def __init__(self):
        self.timings = {}

    def start_timer(self, name):
        """
        Record the start time for the given timer name.
        """
        if name not in self.timings:
            self.timings[name] = {"start": None, "total": 0, "count": 0}
        self.timings[name]["start"] = time.time() * 1000  # Record start time in milliseconds

    def stop_timer(self, name):
        """
        Record the stop time for the given timer name and update the average.
        """
        if name in self.timings and self.timings[name]["start"] is not None:
            end_time = time.time() * 1000  # Get current time in milliseconds
            duration = end_time - self.timings[name]["start"]
            self.timings[name]["total"] += duration
            self.timings[name]["count"] += 1
            self.timings[name]["start"] = None  # Reset start time
            #print(f"TIMER: {name} took {duration}ms")

    def show_timers(self):
        """
        Display the average times for all timers, sorted from slowest to fastest.
        """
        print("\n--\nTimer Results (sorted by average time):")
        sorted_timers = sorted(
            self.timings.items(),
            key=lambda item: item[1]["total"] / item[1]["count"] if item[1]["count"] > 0 else 0,
            reverse=True
        )

        for name, timing in sorted_timers:
            if timing["count"] > 0:
                average_time = timing["total"] / timing["count"]
                print(f"{name}: {average_time:.2f} ms (average over {timing['count']} runs)")
            else:
                print(f"{name}: No completed timings recorded.")
                
        print("\n")

