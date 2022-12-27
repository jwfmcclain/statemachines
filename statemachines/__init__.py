import digitalio
import time

from statemachines.flicker import FlickerPolicy, Flicker, NeoPixelFlicker

SECONDS_PER_NS = 1000 * 1000 * 1000
IMMEDATE_TRANSFER = 'IMMEDATE'

# Time event objects have `next_deadline(now)` and `happend(now)`
# methods. next_deadline returns the number of nanosetions between the
# passed value of `now` (a value recently returned by
# `time.monotonic_ns()`) and the next event time.
#
# `happend(now)` is called when deadline is reached, before any of the
# state transtions are triggered. It should return True if the event
# really did happen and False otherwise.
#

class Pulser:
    """Generates periodic time events at a fixed period. Skips events if
       it falls behind.

    """

    def __init__(self, period):
        self.period = int(period * SECONDS_PER_NS)
        self.deadline = time.monotonic_ns() + self.period

    def happend(self, now):
        self.deadline += self.period

        # If now is less than the new deadline we have 3 options
        #  1. Ignore the problem and leave the deadline as it is
        #  2. Advance the new deadline to now + period
        #  3. Raise some sort of error
        #
        # 1 has the problem if we're constantly doing too much work
        # for a period the pulser falls increasing behind and (often)
        # we will just backlog increasing amounts of work. This will
        # also starve out any other events. OTOH it is the right thing
        # if it is temporary and a state machine is counting pulses.
        #
        # 2 has the nice property that if we become overload we will
        # shed work, and state machines that work on time (v. events)
        # should be fine.
        #
        # 3 is perhaps the most principled, but we don't really have a
        # theory yet on how to flag errors and asserting out for a
        # single missed deadline seems non-optimal
        #
        # Going to go with 2, anything running at high frequency
        # likely to be time based and things that are events are
        # likely to use longer period puslers that are unlikely to be
        # overwhelmed.
        #
        # Eventually we should provide some options here.
        #
        if now > self.deadline:
            self.deadline = now + self.period

        return True

    def next_deadline(self):
        return self.deadline

    def __str__(self):
        return f"{self.__class__.__name__}:period:{self.period}:deadline:{self.deadline}"

class OneShot:
    """Slinglton time event."""

    def __init__(self, now, period):
        self.deadline = now + period

    def happend(self, now):
        return True

    def next_deadline(self):
        return self.deadline

    def __str__(self):
        return f"{self.__class__.__name__}:{self.deadline}"

# Flag events are passed between state machines. Flag events have a
# `triggered()` method that should return tue if the event occured.

class FlagOr:
    """Aggregate some number of flag events, tirggering if any are triggered."""

    def __init__(self, *argv):
        self.watch_list = argv

    def triggered(self):
        return any((x.triggered() for x in self.watch_list))

    def waiting_on(self, event):
        return event in self.watch_list

    def __str__(self):
        return f"{self.__class__.__name__}:{[str(x) for x in self.watch_list]}"

class ButtonWatcher:
    """Flag event that triggers when the specified button is
       releaed. Defaults trigger on low ot high. Implemented as a
       state machine, needs to be registered with the runtime and
       provided with a suitable frequency Pulser (e.g. 100Hz).

    """

    def __init__(self, pin, pulser, invert=False, button=None):
        self.pin = pin # Save for __str__
        self.invert = invert
        self.pulser = pulser
        if button is None:
            self.button = digitalio.DigitalInOut(pin)
            if invert:
                self.button.switch_to_input(pull=digitalio.Pull.UP)
            else:
                self.button.switch_to_input(pull=digitalio.Pull.DOWN)
        else:
            self.button = button
        self.pending_count = 0

    def start(self, now):
        if self.button.value ^ self.invert:
            return self.down, IMMEDATE_TRANSFER
        return self.up, IMMEDATE_TRANSFER

    def down(self, now):
        if self.button.value ^ self.invert:
            return self.down, self.pulser

        # trigger on release
        self.pending_count += 1
        return self.up, self.pulser

    def up(self, now):
        if self.button.value ^ self.invert:
            return self.down, self.pulser
        return self.up, self.pulser

    def consume(self):
        """Consumes a pending event. Returns True if there was a pending
           event, and False otherwise.

        """

        if self.pending_count == 0:
            return False

        self.pending_count -= 1
        return True

    def triggered(self):
        return self.pending_count > 0

    def __str__(self):
        return "{}:{}".format(self.__class__.__name__, self.pin)

class Blinker:
    def __init__(self, pin_number, event):
        self.led = digitalio.DigitalInOut(pin_number)
        self.led.direction = digitalio.Direction.OUTPUT
        self.event = event

    def start(self, now):
        return self.off, IMMEDATE_TRANSFER

    def on(self, now):
        self.led.value = True
        return self.off, self.event

    def off(self, now):
        self.led.value = False
        return self.on, self.event

    def __str__(self):
        return f"{self.__class__.__name__}:{self.led} on {self.event} ({self.led.value})"

class UnevenBlinker:
    def __init__(self, pin_number, on_seconds, off_seconds):
        self.on_period = int(on_seconds * SECONDS_PER_NS)
        self.off_period = int(off_seconds * SECONDS_PER_NS)
        self.deadline = None
        self.led = digitalio.DigitalInOut(pin_number)
        self.led.direction = digitalio.Direction.OUTPUT

    def start(self, now):
        return self.off, IMMEDATE_TRANSFER

    def off(self, now):
        self.led.value = False
        self.deadline = now + self.off_period
        return self.on, self

    def on(self, now):
        self.led.value = True
        self.deadline = now + self.on_period
        return self.off, self

    def happend(self, now):
        return True

    def next_deadline(self):
        return self.deadline

    def __str__(self):
        return f"{self.__class__.__name__}:{self.led}({self.led.value}):{self.deadline}"

class EventTracker:
    def __init__(self):
        self.events = {}

    def add(self, machine, event):
        if event not in self.events:
            self.events[event] = []
        self.events[event].append(machine)

    def delete(self, machine):
        del_list = []
        for event, machines in self.events.items():
            if machine in machines:
                machines.remove(machine)

            # Remove event if its list is now empty
            if not machines:
                del_list.append(event)
        for k in del_list:
            del self.events[k]

    def dequeue(self, event):
        rslt = self.events[event]
        del self.events[event]
        return rslt

    def process_event(self, now, event):
        triggered_machines = []
        for machine in self.dequeue(event):
            advance(now, machine, event)
            if hasattr(machine, 'triggered') and machine.triggered():
                triggered_machines.append(machine)

        return triggered_machines

    def dump(self):        
        for event, machines in self.events.items():
            print(event)
            for machine in machines:
                print(f"\t{machine}, transitions: {machine.transitions} : {machine.state.__name__}")

class TimeEventTracker(EventTracker):
    def soonest(self):
        return min(self.events, key=lambda x:x.next_deadline())

class FlagEventTracker(EventTracker):
    def __contains__(self, item):
        return item in self.events

class AggregateTracker(EventTracker):
    def search(self, trigger):
        for event in self.events:
            if event.waiting_on(trigger) and event.triggered():
                yield event

time_events = TimeEventTracker()
flag_events = FlagEventTracker()
aggregate_events = AggregateTracker()
pending_adds = []
pending_deletes = []

def do_adds(now):
    global pending_adds
    if not pending_adds:
        return

    for machine in pending_adds:
        machine.state = machine.start
        advance(now, machine, None)
    pending_adds = []

def do_deletes():
    global pending_deletes
    if not pending_deletes:
        return

    for machine in pending_deletes:
        time_events.delete(machine)
        flag_events.delete(machine)
        aggregate_events.delete(machine)
        if hasattr(machine, 'finish'):
            machine.finish()

    pending_deletes = []


def register_machine(*machines):
    for machine in machines:
        machine.transitions = 0
    pending_adds.extend(machines)

def deregister_machine(*machines):
    pending_deletes.extend(machines)


def call_state(now, machine, event):
    # print(f"Calling {machine}.{machine.state.__name__}({now}) on {event}")

    machine.transitions += 1
    last_state = machine.state
    machine.state, next_event = machine.state(now)

    if machine.state is None:
        machine.state = last_state

    return next_event
    
def advance(now, machine, event):
    try:
        next_event = call_state(now, machine, event)
        while next_event == IMMEDATE_TRANSFER:
            next_event = call_state(now, machine, event)
    except:
        # Assuming only calls to state throw exceptions
        #
        # Note, if the call to the state method failed, machine.state
        # will be the method we called.
        # print(f"{machine}.{machine.state.__name__}({now}) threw exception on {event}")
        raise

    if next_event is None:
        next_event = event

    if hasattr(next_event, 'next_deadline'):
        deadline = next_event.next_deadline()
        if type(deadline) != int:
            raise AssertionError(f"non int deadline ({deadline}) from {next_event} for {machine} from {machine.state.__name__}")
        time_events.add(machine, next_event)
    elif hasattr(next_event, 'triggered'):
        if hasattr(next_event, 'waiting_on'):
            aggregate_events.add(machine, next_event)
        else:
            flag_events.add(machine, next_event)

#
# State we keep for debugging
#

previous_now = None
monotonic_ns_calls = 0
run_loop_count = 0
state_clock = 0

def count_string():
    return f"loop_count: {run_loop_count} state_clock: {state_clock}"

def get_new_now(prev):
    global previous_now
    global monotonic_ns_calls

    if prev is not None:
        previous_now = prev

    monotonic_ns_calls += 1
    now = time.monotonic_ns()

    if previous_now is not None:
        if previous_now > now:
            print(f"monotonic_ns MOVED BACKWARD! {previous_now} {now} : {monotonic_ns_calls} {count_string()}")
        elif now - previous_now > SECONDS_PER_NS * 3600 * 24:
            print(f"monotonic_ns JUMPED MORE THAN A DAY! {previous_now} {now} : {monotonic_ns_calls} {count_string()}")
            monotonic_ns_calls += 1
            now = time.monotonic_ns()
            print(f"called monotonic_ns() again, now: {now}")

    return now


def run(aggregate_actors=[], dump_interval=None):
    global run_loop_count
    global state_clock

    now = get_new_now(None)
    do_adds(now)

    next_dump_time = now

    while True:
        run_loop_count += 1

        # Find the next event and its time
        #
        fired_event = time_events.soonest()
        deadline = fired_event.next_deadline()

        # Wait for that time
        #
        now = get_new_now(now)
        while now < deadline:
            sleep_for_sec = (deadline - now) / SECONDS_PER_NS

            time.sleep(sleep_for_sec)
            # time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + sleep_for_sec)
            # alarm.light_sleep_until_alarms(time_alarm)

            now = get_new_now(now)

        if fired_event.happend(now):
            state_clock += 1

            # Advance all the state machines that were waiting on it
            #
            triggered_machines = time_events.process_event(now, fired_event)

            # And then see if this cascaded to any flag events
            #
            while triggered_machines:
                event = triggered_machines.pop()
                if event in flag_events:
                    triggered_machines.extend(flag_events.process_event(now, event))
                else:
                    for aggregate_event in aggregate_events.search(event):
                        triggered_machines.extend(aggregate_events.process_event(now, aggregate_event))

            do_adds(now)
            do_deletes()
            for actor in aggregate_actors:
                actor()

        # Else leave in place

        if dump_interval is not None and now >= next_dump_time:
            print(f"now:{now} {count_string()}")
            print("=== time_events ===")
            time_events.dump()
            print("=== flag_events ===")
            flag_events.dump()
            print("=== aggregate_events ===")
            aggregate_events.dump()

            next_dump_time = now + dump_interval * SECONDS_PER_NS
            print(f"=== next_dump_time:{next_dump_time} ===")
