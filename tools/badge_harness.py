# Drives Mona Kart on the badge: title, countdown, race with steering, forced finish; RLE screenshots.
import sys, os, time, builtins, gc
from array import array
DEV = '/state/dev_kart'
captured = []
class Result:
    result = None
builtins.run = lambda fn: (captured.append(fn), Result())[1]
held_now = set(); pressed_now = set()
badge.pressed = lambda b=None: (b in pressed_now) if b is not None else set(pressed_now)
badge.held = lambda b=None: (b in held_now) if b is not None else set(held_now)
try: os.mkdir('/state/shots')
except OSError: pass
for n in os.listdir('/state/shots'): os.remove('/state/shots/' + n)
try: os.remove('/state/mona_kart.json')
except OSError: pass
sys.path.insert(0, DEV); os.chdir(DEV)
src = open(DEV + '/__init__.py').read().replace('APP_DIR = "/system/apps/mona_kart"', 'APP_DIR = "%s"' % DEV)
g = {'__name__': 'kart_dev'}
t = time.ticks_ms(); exec(src, g); print('import', time.ticks_diff(time.ticks_ms(), t), 'ms; segments', g['SEGMENTS'])
update = captured[0]
def rle(raw):
    pixels = array('H', raw); out = array('H'); prev = pixels[0]; count = 0
    for value in pixels:
        if value == prev and count < 65535: count += 1
        else: out.append(count); out.append(prev); prev = value; count = 1
    out.append(count); out.append(prev); return out
shots = 0
def step(buttons=()):
    global pressed_now, held_now
    buttons = set(buttons); pressed_now = buttons - held_now; held_now = buttons
    t = time.ticks_ms(); update(); cost = time.ticks_diff(time.ticks_ms(), t)
    raw = bytes(screen.raw); badge.update(); return cost, raw
def shot(label, raw, cost=None):
    global shots
    with open('/state/shots/%d.rle' % shots, 'wb') as f: f.write(rle(raw))
    print('SHOT %d [%s] frame %s ms mode %d' % (shots, label, cost, g['mode'])); shots += 1
def run_for(ms, buttons=()):
    start = time.ticks_ms(); worst = 0; total = 0; n = 0; raw = None
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        cost, raw = step(buttons); worst = max(worst, cost); total += cost; n += 1
    return worst, total // max(1, n), raw
badge.update()
cost, raw = step(); shot('title', raw, cost)
step((BUTTON_SELECT,))
worst, avg, raw = run_for(600); shot('countdown', raw, avg)
worst, avg, raw = run_for(3000); print('countdown frames avg', avg, 'worst', worst)
worst, avg, raw = run_for(1500); shot('race start straight', raw, avg); print('  avg', avg, 'worst', worst)
for n, r in enumerate(g['rivals']):
    r.z = g['player'].z + (3 + n * 2) * g['SEG_LEN']; r.speed = g['player'].speed; r.lap = g['player'].lap
worst, avg, raw = run_for(250); shot('rivals ahead', raw, avg); print('  rivals visible?', [int((r.z - g['player'].z) // g['SEG_LEN']) for r in g['rivals']])
worst, avg, raw = run_for(1500, (BUTTON_RIGHT,)); shot('steering right', raw, avg); print('  avg', avg, 'worst', worst, 'x', g['player'].x, 'speed', g['player'].speed, 'z', g['player'].z)
worst, avg, raw = run_for(2500, (BUTTON_LEFT,)); shot('steering left / offroad?', raw, avg); print('  avg', avg, 'worst', worst, 'x', g['player'].x)
worst, avg, raw = run_for(4000); shot('later on the lap', raw, avg); print('  avg', avg, 'worst', worst, 'z', g['player'].z, 'lap', g['player'].lap, 'rank', g['rank'](), 'rival z', [int(r.z) for r in g['rivals']])
# jump to just before the finish of lap 3 to see the results
p = g['player']; p.lap = 2; p.z = g['TRACK_LEN'] - 900
worst, avg, raw = run_for(2500); print('after jump: mode', g['mode'], 'lap', p.lap, 'rank', g['final_rank'])
cost, raw = step(); shot('finish', raw, cost)
step((BUTTON_SELECT,)); worst, avg, raw = run_for(400); shot('race again countdown', raw, avg)
g['on_exit']()
gc.collect(); print('DONE', shots, 'state', g['state'], 'free', gc.mem_free())
