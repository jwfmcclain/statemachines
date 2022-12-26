import board
import digitalio
import neopixel
import statemachines

class ButtonCounter:
    def __init__(self, back, forward):
        self._count = 0
        self.back = back
        self.forward = forward
        self.watcher = statemachines.FlagOr(forward, back)

    def count(self):
        return self._count
        
    def start(self, now):
        return self.press, self.watcher

    def press(self, now):
        if self.forward.consume():
            self._count += 1

        if self.back.consume():
            self._count -= 1

        self._count %= 10

        print(self.count())
        return None, None

    def __str__(self):
        return f"{self.__class__.__name__}:{self.back}:{self.forward}:{self._count}"



class TestFlicker(statemachines.NeoPixelFlicker):
    def __init__(self, pixels, position, event, policy, counter):
        super().__init__(pixels, position, event, policy)
        self.counter = counter

    def suppress(self):
        if self.counter.count() != self.position:
            return None

        return self.event
    
blinker = statemachines.Blinker(board.LED, statemachines.Pulser(0.5))
statemachines.register_machine(blinker)

high_pulser = statemachines.Pulser(0.01) # 100 Hz

a_watcher = statemachines.ButtonWatcher(board.BUTTON_A, high_pulser)
b_watcher = statemachines.ButtonWatcher(board.BUTTON_B, high_pulser)
counter   = ButtonCounter(a_watcher, b_watcher)
statemachines.register_machine(a_watcher)
statemachines.register_machine(b_watcher)
statemachines.register_machine(counter)

pixels = neopixel.NeoPixel(board.NEOPIXEL, 10, auto_write=False)
flicker_policy = statemachines.FlickerPolicy(index_bottom=2,
                                             index_min=8,
                                             index_max=32)

statemachines.register_machine(
    *(TestFlicker(pixels, i, high_pulser, flicker_policy, counter) for i in range(0,len(pixels))))

statemachines.run((pixels.show,), dump_interval=600)
