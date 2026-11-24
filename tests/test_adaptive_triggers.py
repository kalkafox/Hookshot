"""host/adaptive_triggers.h: which effect each of a DualSense's triggers plays, and the bytes SDL sends. Compiled and run;
then the wiring (host/pad_sdl.c, host/oot_wheel.c, the menu's row, the option number, the switch) read from the source.

The rule: only in play, and only with the Adaptive triggers row on (HOS_ADAPTIVE_TRIGGERS over it). The trigger ZR is on
plays the bow's draw (any arrow on it), a softer draw for the Slingshot and a wall past the middle for the Hookshot or the
Longshot, nothing for another item; the trigger ZL is on a light wall from the second zone; a trigger bound to neither is
free, and one bound to both plays ZR's. The zone bytes match RenHDrum's (the bow at strength 8 is its test's
21 FF 03 D1 C6 DA 3F); the report is SDL's DS5EffectsState_t with only the triggers' enable bits (0x04 right, 0x08 left),
the right trigger's 11 bytes at 10 and the left's at 21, so the rumble and the lights are left alone.

    python -I -B tests/test_adaptive_triggers.py [--cxx c++]
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]

TEST = r"""
#include <stdio.h>
#include "adaptive_triggers.h"
static int failed;
#define CHECK(x) do { if (!(x)) printf("FAIL %d: %s\n", __LINE__, #x), failed = 1; } while (0)
static int same(const uint8_t *a, const uint8_t *b, int n) { return !memcmp(a, b, (size_t)n); }
int main(void) {
    enum { N = TRIG_LEVEL_NORMAL, L = TRIG_LEVEL_LIGHT, S = TRIG_LEVEL_STRONG, O = TRIG_LEVEL_OFF };
    enum { ZL = TRIG_ROLE_ZL, ZR = TRIG_ROLE_ZR, NONE = TRIG_ROLE_NONE };
    static const uint8_t FREE[11] = {0x05};
    uint8_t e[11], f[11];
    /* the level: the switch over the row */
    CHECK(trig_level(NULL, 2) == N && trig_level("", 0) == O && trig_level(NULL, 3) == S);
    CHECK(trig_level("0", 2) == O && trig_level("3", 0) == S && trig_level("off", 3) == O && trig_level("on", 0) == N);
    CHECK(trig_level("4", 1) == L && trig_level("yes", 1) == L && trig_level("12", 0) == O);   /* (else: the row) */
    CHECK(trig_level(NULL, 9) == N && trig_level(NULL, -1) == N);   /* (a value out of range: the default) */
    /* the items */
    CHECK(trig_item_kind(30) == TRIG_ITEM_BOW && trig_item_kind(46) == TRIG_ITEM_BOW && trig_item_kind(48) == TRIG_ITEM_BOW);
    CHECK(trig_item_kind(4) == TRIG_ITEM_SLINGSHOT && trig_item_kind(5) == TRIG_ITEM_HOOKSHOT && trig_item_kind(6) == TRIG_ITEM_HOOKSHOT);
    CHECK(trig_item_kind(3) == TRIG_ITEM_BOOMERANG && trig_item_kind(7) == TRIG_ITEM_HAMMER);
    CHECK(trig_item_kind(2) == TRIG_ITEM_BOMB && trig_item_kind(9) == TRIG_ITEM_BOMB);
    CHECK(trig_item_kind(0) == TRIG_ITEM_STICK && trig_item_kind(1) == TRIG_ITEM_NUT);
    CHECK(trig_item_kind(-1) == TRIG_ITEM_NONE && trig_item_kind(8) == TRIG_ITEM_NONE && trig_item_kind(10) == TRIG_ITEM_NONE);
    CHECK(trig_item_kind(49) == TRIG_ITEM_NONE && trig_item_kind(53) == TRIG_ITEM_NONE);
    /* every kind has a name for the log, and an unknown one reads free */
    for (int k = 0; k < TRIG_ITEM_KINDS; k++) CHECK(trig_item_name(k) && *trig_item_name(k));
    CHECK(!strcmp(trig_item_name(TRIG_ITEM_KINDS), "free") && !strcmp(trig_item_name(-1), "free"));
    /* the roles, by the controls (7 and 8 standing for the left and right triggers' HOS_PAD_*) */
    {
        const int zl[2] = {7, -1}, zr[2] = {8, -1}, both[2] = {7, 8}, none[2] = {-1, -1}, other[2] = {3, -1};
        CHECK(trig_role(7, zl, zr) == ZL && trig_role(8, zl, zr) == ZR);
        CHECK(trig_role(7, zr, zl) == ZR && trig_role(8, zr, zl) == ZL);   /* (swapped in the controls: the effects follow) */
        CHECK(trig_role(7, other, other) == NONE && trig_role(8, none, none) == NONE);
        CHECK(trig_role(7, both, both) == ZR);   /* (bound to both: ZR's) */
        CHECK(trig_role(-1, none, none) == NONE);
        CHECK(trig_role(8, other, (const int[2]){3, 8}) == ZR);   /* (the second input of ZR) */
    }
    /* RenHDrum's bow at strength 8: the draw on ZR at Strong */
    {
        static const uint8_t BOW8[11] = {0x21, 0xFF, 0x03, 0xD1, 0xC6, 0xDA, 0x3F, 0, 0, 0, 0};
        trig_effect(ZR, S, 1, TRIG_ITEM_BOW, e);
        CHECK(same(e, BOW8, 11));
    }
    /* the draw stiffens with the pull, every zone held, and the level orders them */
    for (int lv = L; lv <= S; lv++)
        for (int item = TRIG_ITEM_BOW; item <= TRIG_ITEM_SLINGSHOT; item++) {
            trig_effect(ZR, lv, 1, item, e);
            CHECK(e[0] == TRIG_MODE_FEEDBACK && e[1] == 0xFF && e[2] == 0x03);
            const uint32_t force = (uint32_t)e[3] | (uint32_t)e[4] << 8 | (uint32_t)e[5] << 16 | (uint32_t)e[6] << 24;
            int prev = 0;
            for (int z = 0; z < 10; z++) {
                const int s = (int)(force >> (3 * z) & 7) + 1;
                CHECK(s >= prev);
                prev = s;
            }
            CHECK(!e[7] && !e[8] && !e[9] && !e[10]);
        }
    trig_effect(ZR, N, 1, TRIG_ITEM_BOW, e); trig_effect(ZR, N, 1, TRIG_ITEM_SLINGSHOT, f);
    CHECK(!same(e, f, 11) && e[6] > f[6]);   /* (the Slingshot's top is below the bow's) */
    trig_effect(ZR, L, 1, TRIG_ITEM_BOW, f);
    CHECK(e[6] > f[6]);                      /* (Light below Normal) */
    /* the walls: the Hookshot past the middle, the shield from the second zone */
    trig_effect(ZR, N, 1, TRIG_ITEM_HOOKSHOT, e);
    CHECK(e[0] == TRIG_MODE_FEEDBACK && e[1] == 0xE0 && e[2] == 0x03);   /* (zones 5 to 9) */
    trig_effect(ZL, N, 1, TRIG_ITEM_NONE, e);
    CHECK(e[0] == TRIG_MODE_FEEDBACK && e[1] == 0xFC && e[2] == 0x03);   /* (zones 2 to 9) */
    {   /* Normal's shield: strength 2 (1 in each 3-bit zone) from zone 2 */
        uint32_t force = 0;
        for (int z = 2; z < 10; z++) force |= 1u << (3 * z);
        CHECK(e[3] == (uint8_t)force && e[4] == (uint8_t)(force >> 8) && e[5] == (uint8_t)(force >> 16) && e[6] == (uint8_t)(force >> 24));
    }
    trig_effect(ZL, N, 1, TRIG_ITEM_BOW, f);
    CHECK(same(e, f, 11));   /* (the shield whatever is on ZR) */
    /* RenHDrum's weapon vectors: start 2 end 5 strength 8, start 4 end 8 strength 3 */
    {
        static const uint8_t W258[11] = {0x25, 0x24, 0x00, 0x07, 0, 0, 0, 0, 0, 0, 0};
        static const uint8_t W483[11] = {0x25, 0x10, 0x01, 0x02, 0, 0, 0, 0, 0, 0, 0};
        trig_weapon(2, 5, 8, e); CHECK(same(e, W258, 11));
        trig_weapon(4, 8, 3, e); CHECK(same(e, W483, 11));
        trig_weapon(0, 0, 0, e); CHECK(e[0] == 0x25 && e[1] == 0x0C && e[2] == 0 && e[3] == 0);   /* (clamped: 2, 3, 1) */
        trig_weapon(9, 12, 20, e); CHECK(e[1] == 0x80 && e[2] == 0x01 && e[3] == 7);              /* (clamped: 7, 8, 8) */
    }
    /* the new items on ZR: the Boomerang's click past the middle, the Hammer's heavy wall, the bombs' and the nuts'
       light clicks, the stick's band */
    trig_effect(ZR, N, 1, TRIG_ITEM_BOOMERANG, e);
    CHECK(e[0] == TRIG_MODE_WEAPON && e[1] == 0x48 && e[2] == 0 && e[3] == 4);   /* (zones 3 and 6, strength 5) */
    trig_effect(ZR, N, 1, TRIG_ITEM_HAMMER, e);
    CHECK(e[0] == TRIG_MODE_FEEDBACK && e[1] == 0xFE && e[2] == 0x03);          /* (zones 1 to 9) */
    {   /* Normal's Hammer: strength 6 (5 in each 3-bit zone) from zone 1 */
        uint32_t force = 0;
        for (int z = 1; z < 10; z++) force |= 5u << (3 * z);
        CHECK(e[3] == (uint8_t)force && e[4] == (uint8_t)(force >> 8) && e[5] == (uint8_t)(force >> 16) && e[6] == (uint8_t)(force >> 24));
    }
    trig_effect(ZR, N, 1, TRIG_ITEM_BOMB, e);
    CHECK(e[0] == TRIG_MODE_WEAPON && e[1] == 0x14 && e[2] == 0 && e[3] == 2);   /* (zones 2 and 4, strength 3) */
    trig_effect(ZR, N, 1, TRIG_ITEM_NUT, e);
    CHECK(e[0] == TRIG_MODE_WEAPON && e[1] == 0x0C && e[2] == 0 && e[3] == 1);   /* (zones 2 and 3, strength 2) */
    trig_effect(ZR, N, 1, TRIG_ITEM_STICK, e);
    CHECK(e[0] == TRIG_MODE_FEEDBACK && e[1] == 0x3C && e[2] == 0);             /* (zones 2 to 5, free after) */
    /* the level orders every new item's strength, and the shield stays on ZL whatever is on ZR */
    for (int item = TRIG_ITEM_BOOMERANG; item < TRIG_ITEM_KINDS; item++) {
        trig_effect(ZR, L, 1, item, e); trig_effect(ZR, S, 1, item, f);
        CHECK(!same(e, f, 11));
        trig_effect(ZL, N, 1, item, e); trig_effect(ZL, N, 1, TRIG_ITEM_NONE, f);
        CHECK(same(e, f, 11));
        trig_effect(ZR, N, 0, item, e); CHECK(same(e, FREE, 11));   /* (not in play: free) */
    }
    /* free: another item on ZR, a trigger bound to neither, not in play, Off */
    trig_effect(ZR, N, 1, TRIG_ITEM_NONE, e); CHECK(same(e, FREE, 11));
    trig_effect(NONE, S, 1, TRIG_ITEM_BOW, e); CHECK(same(e, FREE, 11));
    trig_effect(ZR, N, 0, TRIG_ITEM_BOW, e); CHECK(same(e, FREE, 11));
    trig_effect(ZL, N, 0, TRIG_ITEM_NONE, e); CHECK(same(e, FREE, 11));
    trig_effect(ZR, O, 1, TRIG_ITEM_BOW, e); CHECK(same(e, FREE, 11));
    trig_effect(ZL, O, 1, TRIG_ITEM_NONE, e); CHECK(same(e, FREE, 11));
    trig_effect(ZR, 7, 1, TRIG_ITEM_BOW, e); CHECK(same(e, FREE, 11));   /* (a level out of range) */
    /* the report: only the triggers' bits, right at 10, left at 21 */
    {
        uint8_t left[11], right[11], r[47];
        trig_effect(ZL, N, 1, TRIG_ITEM_BOW, left); trig_effect(ZR, N, 1, TRIG_ITEM_BOW, right);
        trig_report(left, right, r);
        CHECK(r[0] == 0x0C && r[1] == 0);
        for (int k = 2; k < 10; k++) CHECK(r[k] == 0);   /* (no rumble, no volume, no mic light) */
        CHECK(same(r + 10, right, 11) && same(r + 21, left, 11));
        for (int k = 32; k < 47; k++) CHECK(r[k] == 0);  /* (no lights) */
        CHECK(!trig_report_free(r));
        trig_report(FREE, FREE, r);
        CHECK(trig_report_free(r) && r[0] == 0x0C);       /* (free is still sent: it lets an effect go) */
        trig_report(FREE, right, r);
        CHECK(!trig_report_free(r));
    }
    if (!failed) printf("adaptive triggers: ok\n");
    return failed;
}
"""


def text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def flat(s):
    return re.sub(r"\s+", " ", s)


def function(src, head):
    at = src.index(head)
    start = src.index("{", at)
    depth = 0
    for i in range(start, len(src)):
        depth += src[i] == "{"
        depth -= src[i] == "}"
        if depth == 0:
            return src[at:i + 1]
    raise RuntimeError("no end for " + head)


def wiring():
    """the source around the header: the problems found, as messages"""
    bad = []

    def check(ok, why):
        if not ok:
            bad.append(why)

    pad = text("host/pad_sdl.c")
    poll = flat(function(pad, "static void pads_poll"))
    check('#include "adaptive_triggers.h"' in pad, "host/pad_sdl.c does not include host/adaptive_triggers.h")
    check("rx_option(HOS_OPT_ADAPTIVE_TRIGGERS, TRIG_LEVEL_NORMAL)" in poll, "the poll does not read the row (Normal by default)")
    check('getenv("HOS_ADAPTIVE_TRIGGERS")' in poll, "the poll does not read HOS_ADAPTIVE_TRIGGERS")
    check("hos_oot_in_play() && !rx_option(1, 0) && !hos_oc_wait" in poll,
          "the triggers are not freed with the Insert menu open or in the ocarina's note wait")
    check("const int trig_item = hos_oot_zr_item();" in poll, "the poll does not read the item on ZR")
    check("hos_binding(HOS_BIND_PAD, HOS_SW_ZL, k)" in poll and "hos_binding(HOS_BIND_PAD, HOS_SW_ZR, k)" in poll,
          "the triggers do not follow the controls")
    check("trig_poll(i, trig_lvl, trig_play, trig_item, trig_zl, trig_zr, now);" in poll, "the poll does not play the triggers")
    check("pads[slot].trig_known = pads[slot].trig_refused = 0;" in poll, "a pad opening does not get its triggers freed")
    tp = flat(function(pad, "static void trig_poll"))
    check("const int item = trig_item_kind(zr_item);" in tp, "the triggers do not go by the item on ZR's kind")
    check("trig_item_name(item)" in tp and "ZR item %d" in tp, "the log does not name the effect and ZR's item number")
    check("pads[i].vib_kind != VIB_PAD_DUALSENSE || pads[i].steam" in tp, "triggers sent to a pad that is not a DualSense of SDL's")
    check("trig_role(HOS_PAD_LTRIGGER, zl, zr)" in tp and "trig_role(HOS_PAD_RTRIGGER, zl, zr)" in tp,
          "the triggers' roles are not the left and right triggers'")
    check("atexit(trig_at_exit)" in tp, "the triggers are not freed at exit")
    check("now - pads[i].trig_ns < 2000000000LL" in tp, "a stiff trigger is not sent again")
    check("hos_sdl_pad_effect(pads[i].gc, r, TRIG_REPORT_SIZE)" in flat(function(pad, "static void trig_send")),
          "the report does not go through SDL's effect call")
    check(re.search(r"uint8_t trig_sent\[47\];", function(pad, "static struct {")) is not None,
          "the pads table does not keep the 47 bytes last sent")

    wheel = text("host/oot_wheel.c")
    check("trig_follow(c, hos_now_ns());" in function(wheel, "int hos_wheel_menu_tick"),
          "the HUD's update does not follow the item on ZR for the triggers")
    check("int hos_oot_in_play(void)" in wheel and "int hos_oot_zr_item(void)" in wheel, "host/oot_wheel.c lacks the triggers' calls")

    api, replay, menu = text("gpu/vk/vk_api.h"), text("gpu/vk/vk_replay.cpp"), text("gpu/vk/vk_menu.cpp")
    check("enum { HOS_OPT_ADAPTIVE_TRIGGERS = 62 };" in api, "vk_api.h: HOS_OPT_ADAPTIVE_TRIGGERS is not 62")
    check(len(re.findall(r"HOS_OPT_\w+ = 62\b", api)) == 1, "vk_api.h: option 62 taken twice")
    check("if (id == HOS_OPT_ADAPTIVE_TRIGGERS) return opts.adaptive_triggers;" in replay, "vk_replay.cpp: t.option does not read the row")
    check('"Adaptive triggers", &opts.adaptive_triggers, 0, 3, 1, tx_adaptive_triggers,' in flat(menu), "vk_menu.cpp: no row 0 to 3")
    check("int adaptive_triggers = 2;" in text("gpu/vk/vk_menu.h"), "vk_menu.h: the row is not Normal by default")
    check("SW(HOS_ADAPTIVE_TRIGGERS," in text("gpu/vk/switches.def"), "switches.def: no row for HOS_ADAPTIVE_TRIGGERS")
    return bad


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cxx", default=os.environ.get("CXX", "c++"))
    a = p.parse_args()
    bad = wiring()
    for why in bad:
        print("FAIL " + why)
    with tempfile.TemporaryDirectory() as d:
        c = Path(d) / "adaptive_triggers.c"
        c.write_text(TEST, encoding="utf-8")
        exe = Path(d) / ("adaptive_triggers.exe" if os.name == "nt" else "adaptive_triggers")
        subprocess.run([a.cxx, "-I", str(ROOT / "host"), "-x", "c", "-std=c11", "-Wall", "-Wextra", "-Werror", str(c), "-o",
                        str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    if bad:
        sys.exit(1)
    print("adaptive triggers wiring: ok")


if __name__ == "__main__":
    main()
