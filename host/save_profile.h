/* Longshot save profiles. Profile 1 is the existing user folder; 2..9 are separate playthroughs. */
#pragma once
#include <stddef.h>

/* Returns 1 after selecting/creating the folder, 0 on error. Never falls back after a requested profile fails. */
int hos_save_profile_select(const char *base, char *out, size_t capacity);
