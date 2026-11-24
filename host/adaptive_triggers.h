/* (hookshot) A DualSense's adaptive triggers: which effect each trigger plays, and the bytes SDL sends for it. Pure: no
   SDL, no state; host/pad_sdl.c decides with it and tests/test_adaptive_triggers.py compiles it.

   The Controls page's Adaptive triggers row (HOS_OPT_ADAPTIVE_TRIGGERS; HOS_ADAPTIVE_TRIGGERS=0..3 over it): 0 Off, 1
   Light, 2 Normal (the default), 3 Strong. The effects follow what the game is doing, and only in play (the HUD updating,
   no pause menu, item row, Insert menu or ocarina wait: host/oot_wheel.c's hos_oot_in_play, host/pad_sdl.c); otherwise
   both triggers are free:
     the trigger ZR is on   the bow (with any arrow): a draw that stiffens as it is pulled, like a bowstring
                            the Slingshot: the same, softer
                            the Hookshot or the Longshot: a light wall past the middle of the pull
                            the Boomerang: a click, resistance that gives way past the middle (the throw)
                            the Megaton Hammer: a heavy wall from early in the pull
                            Bombs or Bombchus: a light click
                            Deku Sticks: a short light band of resistance in the middle of the pull
                            Deku Nuts: a lighter click, early
                            any other item: free
     the trigger ZL is on   a light wall past the first fifth of the pull: shield and lock-on
   ZR and ZL go by the controls (a trigger bound to neither is left free; one bound to both plays ZR's). The item is the
   one on ZR, PouchMgr's AssignableItem (host/oot_wheel.c's item numbers: 30 the bow, 46 to 48 its Fire, Ice and Light
   Arrows, 4 the Slingshot, 5 and 6 the Hookshot and the Longshot, 3 the Boomerang, 7 the Hammer, 2 Bombs, 9 Bombchus, 0
   Deku Sticks; 1 is taken to be Deku Nuts, the one number between Deku Sticks and Bombs, which the log's item number
   checks in play).

   The effect bytes are the controller's "zone" effects: ten zones over the trigger's travel, a strength of 1 to 8 each
   (3 bits a zone), as Nielk1's trigger effect notes and RenHDrum (third_party/renhdrum/src/dualsense/trigger_effect.rs)
   have them; the 47 bytes are SDL's DS5EffectsState_t with only the triggers' enable bits set, so SDL_SendGamepadEffect
   leaves the rumble, the lights and the audio alone. */
#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { TRIG_LEVEL_OFF = 0, TRIG_LEVEL_LIGHT, TRIG_LEVEL_NORMAL, TRIG_LEVEL_STRONG };   /* the row (HOS_OPT_ADAPTIVE_TRIGGERS) */
enum { TRIG_ROLE_NONE = 0, TRIG_ROLE_ZL, TRIG_ROLE_ZR };                              /* what a trigger is bound to */
enum {   /* the item on ZR, as the triggers care */
    TRIG_ITEM_NONE = 0, TRIG_ITEM_BOW, TRIG_ITEM_SLINGSHOT, TRIG_ITEM_HOOKSHOT, TRIG_ITEM_BOOMERANG, TRIG_ITEM_HAMMER,
    TRIG_ITEM_BOMB, TRIG_ITEM_STICK, TRIG_ITEM_NUT, TRIG_ITEM_KINDS
};

#define TRIG_EFFECT_SIZE 11   /* one trigger's effect */
#define TRIG_REPORT_SIZE 47   /* SDL's DS5EffectsState_t */
#define TRIG_ZONES 10
#define TRIG_MODE_OFF 0x05
#define TRIG_MODE_FEEDBACK 0x21
#define TRIG_MODE_WEAPON 0x25

/* The level: HOS_ADAPTIVE_TRIGGERS when set (0 to 3, or off/on; anything else: the row), else the row's value */
static inline int trig_level(const char *env, int option) {
    if (env && *env) {
        if (!strcmp(env, "off")) return TRIG_LEVEL_OFF;
        if (!strcmp(env, "on")) return TRIG_LEVEL_NORMAL;
        if (env[0] >= '0' && env[0] <= '3' && !env[1]) return env[0] - '0';
    }
    return option < TRIG_LEVEL_OFF || option > TRIG_LEVEL_STRONG ? TRIG_LEVEL_NORMAL : option;
}

/* The item on ZR (PouchMgr's AssignableItem, -1 unknown) as the triggers care */
static inline int trig_item_kind(int item) {
    if (item == 30 || (item >= 46 && item <= 48)) return TRIG_ITEM_BOW;
    if (item == 4) return TRIG_ITEM_SLINGSHOT;
    if (item == 5 || item == 6) return TRIG_ITEM_HOOKSHOT;
    if (item == 3) return TRIG_ITEM_BOOMERANG;
    if (item == 7) return TRIG_ITEM_HAMMER;
    if (item == 2 || item == 9) return TRIG_ITEM_BOMB;
    if (item == 0) return TRIG_ITEM_STICK;
    if (item == 1) return TRIG_ITEM_NUT;
    return TRIG_ITEM_NONE;
}

/* What the trigger ZR is on plays for an item kind, in words (the log's) */
static inline const char *trig_item_name(int kind) {
    static const char *const names[TRIG_ITEM_KINDS] = {
        "free", "the bow's draw", "the Slingshot's draw", "the Hookshot's wall", "the Boomerang's click",
        "the Hammer's wall", "the bombs' click", "the Deku Stick's band", "the Deku Nut's click",
    };
    return kind >= 0 && kind < TRIG_ITEM_KINDS ? names[kind] : "free";
}

/* What a physical trigger plays for: the controls' two pad inputs of ZL and of ZR (HOS_PAD_*, -1 none), and the
   trigger's own HOS_PAD_* */
static inline int trig_role(int pad, const int zl[2], const int zr[2]) {
    if (pad < 0) return TRIG_ROLE_NONE;
    if (zr[0] == pad || zr[1] == pad) return TRIG_ROLE_ZR;
    if (zl[0] == pad || zl[1] == pad) return TRIG_ROLE_ZL;
    return TRIG_ROLE_NONE;
}

/* A zone effect from a strength per zone (0 free, 1 to 8) */
static inline void trig_zones(const int strengths[TRIG_ZONES], uint8_t out[TRIG_EFFECT_SIZE]) {
    uint32_t active = 0, force = 0;
    for (int z = 0; z < TRIG_ZONES; z++) {
        int s = strengths[z];
        if (s <= 0) continue;
        if (s > 8) s = 8;
        active |= 1u << z;
        force |= (uint32_t)((s - 1) & 7) << (3 * z);
    }
    memset(out, 0, TRIG_EFFECT_SIZE);
    if (!active) {
        out[0] = TRIG_MODE_OFF;
        return;
    }
    out[0] = TRIG_MODE_FEEDBACK;
    out[1] = (uint8_t)active, out[2] = (uint8_t)(active >> 8);
    out[3] = (uint8_t)force, out[4] = (uint8_t)(force >> 8), out[5] = (uint8_t)(force >> 16), out[6] = (uint8_t)(force >> 24);
}

/* A draw: from a quarter of top at the first zone up to top (1 to 8) at the last two, as RenHDrum's bow */
static inline void trig_draw(int top, uint8_t out[TRIG_EFFECT_SIZE]) {
    int s[TRIG_ZONES];
    const int start = (top + 2) / 4 > 1 ? (top + 2) / 4 : 1;
    for (int z = 0; z < TRIG_ZONES; z++) s[z] = start + ((top - start) * (z < 8 ? z : 8) + 4) / 8;
    trig_zones(s, out);
}

/* A wall: strength (1 to 8) from zone `from` (0 to 9) to the end of the pull */
static inline void trig_wall(int from, int strength, uint8_t out[TRIG_EFFECT_SIZE]) {
    int s[TRIG_ZONES];
    for (int z = 0; z < TRIG_ZONES; z++) s[z] = z >= from ? strength : 0;
    trig_zones(s, out);
}

/* A band: strength (1 to 8) from zone `from` to zone `to` (0 to 9), free before and after */
static inline void trig_band(int from, int to, int strength, uint8_t out[TRIG_EFFECT_SIZE]) {
    int s[TRIG_ZONES];
    for (int z = 0; z < TRIG_ZONES; z++) s[z] = z >= from && z <= to ? strength : 0;
    trig_zones(s, out);
}

/* A click ("weapon"): resistance (1 to 8) from zone `start` (2 to 7) that gives way at zone `end` (start+1 to 8), as
   RenHDrum's weapon effect */
static inline void trig_weapon(int start, int end, int strength, uint8_t out[TRIG_EFFECT_SIZE]) {
    if (start < 2) start = 2;
    if (start > 7) start = 7;
    if (end < start + 1) end = start + 1;
    if (end > 8) end = 8;
    if (strength < 1) strength = 1;
    if (strength > 8) strength = 8;
    const unsigned zones = 1u << start | 1u << end;
    memset(out, 0, TRIG_EFFECT_SIZE);
    out[0] = TRIG_MODE_WEAPON;
    out[1] = (uint8_t)zones, out[2] = (uint8_t)(zones >> 8);
    out[3] = (uint8_t)(strength - 1);
}

/* One trigger's effect: its role, the level, whether the game is in play, the item on ZR (trig_item_kind) */
static inline void trig_effect(int role, int level, int in_play, int item, uint8_t out[TRIG_EFFECT_SIZE]) {
    if (level < TRIG_LEVEL_LIGHT || level > TRIG_LEVEL_STRONG || !in_play) role = TRIG_ROLE_NONE;
    const int k = level - 1;   /* (Light, Normal, Strong) */
    static const int bow[3] = {4, 6, 8}, sling[3] = {2, 4, 6}, hook[3] = {1, 2, 3}, shield[3] = {1, 2, 3};
    static const int boomerang[3] = {3, 5, 7}, hammer[3] = {4, 6, 8}, bomb[3] = {2, 3, 4}, stick[3] = {1, 2, 3},
                     nut[3] = {1, 2, 3};
    if (role == TRIG_ROLE_ZR && item == TRIG_ITEM_BOW) trig_draw(bow[k], out);
    else if (role == TRIG_ROLE_ZR && item == TRIG_ITEM_SLINGSHOT) trig_draw(sling[k], out);
    else if (role == TRIG_ROLE_ZR && item == TRIG_ITEM_HOOKSHOT) trig_wall(5, hook[k], out);
    else if (role == TRIG_ROLE_ZR && item == TRIG_ITEM_BOOMERANG) trig_weapon(3, 6, boomerang[k], out);
    else if (role == TRIG_ROLE_ZR && item == TRIG_ITEM_HAMMER) trig_wall(1, hammer[k], out);
    else if (role == TRIG_ROLE_ZR && item == TRIG_ITEM_BOMB) trig_weapon(2, 4, bomb[k], out);
    else if (role == TRIG_ROLE_ZR && item == TRIG_ITEM_STICK) trig_band(2, 5, stick[k], out);
    else if (role == TRIG_ROLE_ZR && item == TRIG_ITEM_NUT) trig_weapon(2, 3, nut[k], out);
    else if (role == TRIG_ROLE_ZL) trig_wall(2, shield[k], out);
    else trig_wall(TRIG_ZONES, 0, out);   /* (free) */
}

/* The report SDL_SendGamepadEffect takes for a DualSense: both triggers' effects, nothing else touched */
static inline void trig_report(const uint8_t left[TRIG_EFFECT_SIZE], const uint8_t right[TRIG_EFFECT_SIZE],
                               uint8_t out[TRIG_REPORT_SIZE]) {
    memset(out, 0, TRIG_REPORT_SIZE);
    out[0] = 0x04 | 0x08;   /* ucEnableBits1: the right trigger's effect, the left's */
    memcpy(out + 10, right, TRIG_EFFECT_SIZE);
    memcpy(out + 21, left, TRIG_EFFECT_SIZE);
}

/* Whether a report is both triggers free */
static inline int trig_report_free(const uint8_t r[TRIG_REPORT_SIZE]) {
    return r[10] == TRIG_MODE_OFF && r[21] == TRIG_MODE_OFF;
}
