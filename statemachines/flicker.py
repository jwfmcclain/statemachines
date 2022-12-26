import random
import statemachines

# Percent chance the color will hold unchanged after brightening
BRIGHT_HOLD_PERCENT = 20
 
# Percent chance the color will hold unchanged after dimming
DIM_HOLD_PERCENT = 5

class FlickerPolicy:
    def __init__(self, down_min_secs=0.04, down_max_secs=1.0,
                 up_min_secs=0.04, up_max_secs=1.0,
                 bright_hold_min_secs=0, bright_hold_max_secs=0.1,
                 dim_hold_min_secs=0, dim_hold_max_secs=0.05,
                 bottom_chance = 15,
                 index_bottom=64, # Absolute minimum red value (green value is a function of red's value)
                 index_min=128,   # Minimum red value during "normal" flickering (not a dramatic change)
                 index_max=255):  # Maximum red value
        self._down_min_nanosecs = int(down_min_secs * statemachines.SECONDS_PER_NS)
        self._down_max_nanosecs = int(down_max_secs * statemachines.SECONDS_PER_NS)
        self._up_min_nanosecs = int(up_min_secs * statemachines.SECONDS_PER_NS) 
        self._up_max_nanosecs = int(up_max_secs * statemachines.SECONDS_PER_NS)
        self._bright_hold_min_nanosecs = int(bright_hold_min_secs * statemachines.SECONDS_PER_NS)
        self._bright_hold_max_nanosecs = int(bright_hold_max_secs * statemachines.SECONDS_PER_NS)
        self._dim_hold_min_nanosecs = int(dim_hold_min_secs * statemachines.SECONDS_PER_NS)
        self._dim_hold_max_nanosecs = int(dim_hold_max_secs * statemachines.SECONDS_PER_NS)

        self._bottom_chance = bottom_chance
        
        self._index_bottom = index_bottom
        self._index_min = index_min
        self._index_max = index_max
       
    def limit_index(self, index):
        return max(min(index, self._index_max), self._index_bottom)

    def at_least_min(self, n):
        return n >= self._index_min

    def pick_down_end(self, start):
        drop = random.randint(0, 100) < self._bottom_chance
        if start > self._index_bottom and drop:
            return random.randint(self._index_bottom, start)
        else:
            if start < self._index_min:
                return self._index_min
            else:
                return random.randint(self._index_min, start)

    def pick_up_end(self, start):
        return random.randint(start, self._index_max)
    
    def pick_down_nanosecs(self):
        return random.randint(self._down_min_nanosecs, self._down_max_nanosecs)

    def pick_up_nanosecs(self):
        return random.randint(self._up_min_nanosecs, self._up_max_nanosecs)

    def pick_bright_hold_nanosecs(self):
        return random.randint(self._bright_hold_min_nanosecs, self._bright_hold_max_nanosecs)

    def pick_dim_hold_nanosecs(self):
        return random.randint(self._dim_hold_min_nanosecs, self._dim_hold_max_nanosecs)
    
class Flicker:
    def __init__(self, event, policy):
        self.event = event
        self._policy = policy
        self.clear()
        
    def clear(self):
        self._index_start = self._policy.limit_index(255)
        self._index_end = self._policy.limit_index(255)
        self._flicker_nanosecs = 0
        self._flicker_start = 0

    def index_to_color(self, index):
        if self._policy.at_least_min(index):
            return index, int((index * 3) / 8), 0
        else:
            return index, int((index * 3.25) / 8), 0
        
    def set_level(self, index):
        index = self._policy.limit_index(index)
        self.set_color(*self.index_to_color(index))

    def suppress(self):
        return None
    
    def elapsed(self, now):
        return now - self._flicker_start
            
    def start(self, now):
        return self.top, statemachines.IMMEDATE_TRANSFER

    def finish(self):
        self.set_color(0, 0, 0)

    def suppressed(self, now):
        suppress_until = self.suppress()
        if suppress_until is None:
            self.clear()
            return self.start(now)

        return self.suppressed, suppress_until

    def start_flicker(self, now, length, index_end_policy):
        self._flicker_nanosecs = length
        self._flicker_start = now
        self._index_start = self._index_end
        self._index_end = index_end_policy(self._index_start)

    def start_hold(self, now, length):
        self._flicker_nanosecs = length
        self._flicker_start = now

    def enter_suppresion(self, suppress_until):
        self.set_color(0, 0, 0)
        return self.suppressed, suppress_until

    def top(self, now):
        suppress_until = self.suppress()
        if suppress_until is not None:
            return self.enter_suppresion(suppress_until)
        
        self.start_flicker(now, self._policy.pick_down_nanosecs(), self._policy.pick_down_end)
        return self.down, self.event

    def bottom(self, now):
        suppress_until = self.suppress()
        if suppress_until is not None:
            return self.enter_suppresion(suppress_until)

        self.start_flicker(now, self._policy.pick_up_nanosecs(), self._policy.pick_up_end)
        return self.up, self.event

    def progress(self, elapsed):
        return self._index_start + int((self._index_end - self._index_start)
                                       * elapsed / self._flicker_nanosecs)
    
    def up(self, now):
        suppress_until = self.suppress()
        if suppress_until is not None:
            return self.enter_suppresion(suppress_until)

        elapsed = self.elapsed(now)
        if elapsed < self._flicker_nanosecs:
            # In progress, update pixel and loop
            self.set_level(self.progress(elapsed))
            return self.up, None

        # Done, set final level then hold, or reverse
        self.set_level(self._index_end)
        if random.randint(0, 100) < BRIGHT_HOLD_PERCENT:
            self.start_hold(now, self._policy.pick_bright_hold_nanosecs())
            return self.top, statemachines.OneShot(now, self._flicker_nanosecs)

        return self.top, self.event

    def down(self, now):
        suppress_until = self.suppress()
        if suppress_until is not None:
            return self.enter_suppresion(suppress_until)

        elapsed = self.elapsed(now)
        if elapsed < self._flicker_nanosecs:
            # In progress, update pixel and loop
            self.set_level(self.progress(elapsed))
            return self.down, None

        # Done, set final level then hold, or reverse
        self.set_level(self._index_end)
        if random.randint(0, 100) < DIM_HOLD_PERCENT:
            self.start_hold(now, self._policy.pick_dim_hold_nanosecs())
            return self.bottom, statemachines.OneShot(now, self._flicker_nanosecs)

        return self.bottom, self.event

    def __str__(self):
        return f"{self.__class__.__name__}:{self.event}:suppressed:{self.suppress()}"

class NeoPixelFlicker(Flicker):
    def __init__(self, pixels, position, event, policy):
        super().__init__(event, policy)
        self.pixels = pixels
        self.position = position

    def set_color(self, red, green, blue):
        self.pixels[self.position] = (red, green, blue)

    def __str__(self):
        return f"{self.__class__.__name__}:{self.position}:suppressed:{self.suppress()}"


