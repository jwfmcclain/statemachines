import board
import digitalio
import neopixel
import statemachines

pixels = neopixel.NeoPixel(board.NEOPIXEL, 10, auto_write=False)

class TrafficLight:
    def __init__(self, pixels, position, event):
        self.pixels = pixels
        self.position = position
        self.event = event

    def start(self, now):
        return self.red, statemachines.IMMEDATE_TRANSFER

    def red(self, now):
        self.pixels[self.position] = 0x100000
        return self.green, self.event

    def yellow(self, now):
        self.pixels[self.position] = 0x080800
        return self.red, self.event

    def green(self, now):
        self.pixels[self.position] = 0x001000
        return self.yellow, self.event

    def __str__(self):
        return f"{self.__class__.__name__}:{self.position}"

class ButtonLight:
    def __init__(self, pixels, position, back, forward):
        self.pixels = pixels
        self.position = position
        self.back = back
        self.forward = forward
        self.watcher = statemachines.FlagOr(forward, back)

    def start(self, now):
        return self.make_red, statemachines.IMMEDATE_TRANSFER

    def make_red(self, now):
        self.pixels[self.position] = 0x100000
        return self.red, self.watcher

    def red(self, now):
        if self.forward.consume():
            return self.make_green, statemachines.IMMEDATE_TRANSFER
        elif self.back.consume():
            return self.make_yellow, statemachines.IMMEDATE_TRANSFER

        return None, self.watcher

    def make_yellow(self, now):
        self.pixels[self.position] = 0x080800
        return self.yellow, self.watcher

    def yellow(self, now):
        if self.forward.consume():
            return self.make_red, statemachines.IMMEDATE_TRANSFER
        elif self.back.consume():
            return self.make_green, statemachines.IMMEDATE_TRANSFER

        return None, self.watcher

    def make_green(self, now):
        self.pixels[self.position] = 0x001000
        return self.green, self.watcher

    def green(self, now):
        if self.forward.consume():
            return self.make_yellow, statemachines.IMMEDATE_TRANSFER
        elif self.back.consume():
            return self.make_red, statemachines.IMMEDATE_TRANSFER

        return None, self.watcher

    def __str__(self):
        return f"{self.__class__.__name__}:{self.position}"

class Control:
    def __init__(self, pixels, pulser):
        self.pulser = pulser
        self.pixels = pixels
        self.child_pulser = statemachines.Pulser(2)
        
    def start(self, now):
        return self.on, statemachines.IMMEDATE_TRANSFER

    def on(self, now):
        self.child = TrafficLight(self.pixels, 0, self.child_pulser)
        statemachines.register_machine(self.child)
        return self.off, self.pulser

    def off(self, now):
        statemachines.deregister_machine(self.child)
        self.child = None
        self.pixels[0] = 0
        return self.on, self.pulser

    def __str__(self):
        return f"{self.__class__.__name__}:{self.child}"



statemachines.register_machine(statemachines.Blinker(board.LED, statemachines.Pulser(0.5)))

pixel_machines = (TrafficLight(pixels, i, statemachines.Pulser(p)) for i,p in
                  zip(range(1,9), (3,5,7,11,13,17,19,23)))
statemachines.register_machine(*pixel_machines )

button_pulser = statemachines.Pulser(0.01) # 100 Hz
a_watcher = statemachines.ButtonWatcher(board.BUTTON_A, button_pulser)
b_watcher = statemachines.ButtonWatcher(board.BUTTON_B, button_pulser)
led_9 = ButtonLight(pixels, 9, a_watcher, b_watcher)
statemachines.register_machine(a_watcher, b_watcher, led_9)

statemachines.register_machine(Control(pixels, statemachines.Pulser(20)))

statemachines.run((pixels.show,), dump_interval=60)
